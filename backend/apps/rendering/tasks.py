import logging
import re
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.rendering.services import ExportFailure, assemble_export
from apps.studio.models import Export

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
LEASE_SECONDS = 660


def queue_export_job(project_id: int, export_id: int) -> None:
    if not Export.objects.filter(pk=export_id, project_id=project_id, status=Export.Status.QUEUED).exists():
        return
    try:
        render_export.delay(export_id)
    except (OperationalError, OSError):
        logger.exception("Export dispatch failed for export %s; durable schedule retained.", export_id)
        Export.objects.filter(pk=export_id, status=Export.Status.QUEUED).update(
            error_code="export_dispatch_unavailable",
            error_message="Export dispatch is unavailable; the background sweeper will retry.",
            next_attempt_at=timezone.now() + timedelta(seconds=30), updated_at=timezone.now(),
        )


def cleanup(export: Export) -> bool:
    remaining = []
    for key in export.cleanup_keys:
        if not re.fullmatch(
            rf"workspaces/{export.project.workspace_id}/exports/{export.id}/[a-f0-9]{{32}}\.(mp4|srt)", key,
        ):
            logger.error("Refusing invalid export cleanup key for export %s.", export.id)
            remaining.append(key)
            continue
        try:
            default_storage.delete(key)
        except OSError:
            logger.exception("Private artifact cleanup failed for export %s.", export.id)
            remaining.append(key)
    export.cleanup_keys = remaining
    return not remaining


def claim_export(export_id: int) -> Export | None:
    with transaction.atomic():
        export = Export.objects.select_for_update().select_related("project").filter(pk=export_id).first()
        if export is None or export.status != Export.Status.QUEUED:
            return None
        if not cleanup(export):
            export.error_code = "export_storage_failed"
            export.error_message = "Private artifact cleanup is unavailable; recovery will retry."
            export.next_attempt_at = timezone.now() + timedelta(seconds=30)
            export.save()
            return None
        if export.attempts >= MAX_ATTEMPTS:
            export.status = Export.Status.FAILED
            export.error_code = "export_retry_exhausted"
            export.error_message = "Export attempts were exhausted. Create a new export after checking the worker."
            export.save()
            return None
        export.status = Export.Status.PROCESSING
        export.attempts += 1
        export.attempt_token = uuid.uuid4().hex
        export.lease_expires_at = timezone.now() + timedelta(seconds=LEASE_SECONDS)
        prefix = f"workspaces/{export.project.workspace_id}/exports/{export.id}/{export.attempt_token}"
        # Persist intended keys before any storage writes so interrupted publication can be recovered.
        export.cleanup_keys = [f"{prefix}.mp4", f"{prefix}.srt"]
        export.error_code = ""
        export.error_message = ""
        export.save()
        return export


def fail_export(export: Export, error: ExportFailure) -> None:
    with transaction.atomic():
        current = Export.objects.select_for_update().select_related("project").filter(
            pk=export.id, status=Export.Status.PROCESSING, attempt_token=export.attempt_token,
        ).first()
        if current is None:
            return
        cleanup(current)
        current.status = Export.Status.FAILED
        current.error_code = error.code
        current.error_message = error.message
        current.output_path = ""
        current.subtitle_path = ""
        current.attempt_token = ""
        current.lease_expires_at = None
        current.save()
    logger.warning("Export %s failed: %s", export.id, error.code)


def publish_export(export: Export, output: Path, subtitles: Path | None) -> None:
    with transaction.atomic():
        current = Export.objects.select_for_update().select_related("project").filter(
            pk=export.id, status=Export.Status.PROCESSING, attempt_token=export.attempt_token,
            lease_expires_at__gt=timezone.now(),
        ).first()
        if current is None:
            logger.warning("Discarding fenced export attempt for export %s.", export.id)
            return
        paths = []
        try:
            for key, path in zip(current.cleanup_keys, (output, subtitles)):
                if path is None:
                    paths.append("")
                    continue
                with path.open("rb") as content:
                    saved = default_storage.save(key, File(content))
                if saved != key:
                    # Never publish an unexpectedly renamed collision as the intended attempt.
                    default_storage.delete(saved)
                    raise ExportFailure("export_storage_failed", "Private storage could not publish the export safely.")
                paths.append(saved)
        except OSError:
            raise ExportFailure("export_storage_failed", "Private storage could not publish all export artifacts.") from None
        current.output_path, current.subtitle_path = paths
        current.status = Export.Status.COMPLETED
        current.cleanup_keys = []
        current.attempt_token = ""
        current.lease_expires_at = None
        current.error_code = ""
        current.error_message = ""
        current.save()


@shared_task(time_limit=650, acks_late=True, reject_on_worker_lost=True)
def render_export(export_id: int) -> None:
    export = claim_export(export_id)
    if export is None:
        return
    try:
        with tempfile.TemporaryDirectory(prefix="chameleon-export-") as scratch:
            output, subtitles = assemble_export(export, Path(scratch))
            publish_export(export, output, subtitles)
    except ExportFailure as error:
        fail_export(export, error)
    except OSError:
        logger.exception("Export storage or process IO failed for export %s.", export.id)
        fail_export(export, ExportFailure("export_storage_failed", "Export storage or worker IO is unavailable."))
    except Exception:
        logger.exception("Unexpected export failure for export %s.", export.id)
        fail_export(export, ExportFailure("export_internal_error", "The export worker encountered an unexpected error."))


@shared_task
def recover_exports() -> int:
    now = timezone.now()
    ids = list(Export.objects.filter(
        Q(status=Export.Status.QUEUED, next_attempt_at__lte=now)
        | Q(status=Export.Status.PROCESSING, lease_expires_at__lte=now)
        | (Q(status=Export.Status.FAILED, next_attempt_at__lte=now) & ~Q(cleanup_keys=[])),
    ).order_by("next_attempt_at", "id").values_list("id", flat=True)[:100])
    dispatched = 0
    for export_id in ids:
        with transaction.atomic():
            export = Export.objects.select_for_update().select_related("project").get(pk=export_id)
            if export.status == Export.Status.COMPLETED or export.next_attempt_at > now:
                continue
            if export.status == Export.Status.PROCESSING:
                if export.lease_expires_at is None or export.lease_expires_at > now:
                    continue
                export.attempt_token = ""
                export.lease_expires_at = None
                export.status = Export.Status.QUEUED if export.attempts < MAX_ATTEMPTS else Export.Status.FAILED
                export.error_code = "export_worker_interrupted" if export.attempts < MAX_ATTEMPTS else "export_retry_exhausted"
                export.error_message = "The export worker was interrupted; recovery is bounded to three attempts."
            cleaned = cleanup(export)
            export.next_attempt_at = now + timedelta(seconds=30)
            export.save()
            if export.status == Export.Status.QUEUED and cleaned:
                # next_attempt_at reserves dispatch, not execution; duplicate deliveries are fenced by status.
                transaction.on_commit(lambda pk=export.id: dispatch_recovered(pk))
                dispatched += 1
    return dispatched


def dispatch_recovered(export_id: int) -> None:
    try:
        render_export.delay(export_id)
    except (OperationalError, OSError):
        logger.exception("Recovered export dispatch failed for export %s; schedule retained.", export_id)
