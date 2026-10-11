from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.generation import runpod
from apps.generation.capabilities import get_capability
from apps.generation.models import GenerationJob
from apps.studio.models import Asset, Project
from apps.studio.services import AssetService

logger = logging.getLogger(__name__)

UPLOAD_SALT = "generation-result-upload"
READ_CHUNK = 1024 * 1024
MAX_RESULT_JSON_CHARS = 4000


class JobRejected(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def upload_token(job_id: int) -> str:
    return signing.dumps({"j": job_id}, salt=UPLOAD_SALT)


def upload_token_valid(token: str, job_id: int) -> bool:
    max_age = int(settings.GENERATION_JOB_TTL_SECONDS) + 600
    try:
        data = signing.loads(token, salt=UPLOAD_SALT, max_age=max_age)
    except signing.BadSignature:
        return False
    return isinstance(data, dict) and data.get("j") == job_id


def upload_url(job_id: int) -> str:
    return f"{settings.GENERATION_PUBLIC_URL}/api/generation/jobs/{job_id}/result/"


def clean_result(value) -> dict:
    """Keeps a small JSON object of worker-reported details; anything else is dropped."""
    if not isinstance(value, dict):
        return {}
    if len(repr(value)) > MAX_RESULT_JSON_CHARS:
        return {}
    return value


class JobService:
    @staticmethod
    def visible_to(user):
        return GenerationJob.objects.filter(workspace__memberships__user=user)

    @staticmethod
    def create(*, user, workspace_id: int, capability_name: str, params: dict, project_id=None, scene_id=None) -> GenerationJob:
        capability = get_capability(capability_name)
        if capability is None:
            raise JobRejected("unknown_capability", "This kind of generation is not available.")
        if not runpod.is_configured():
            raise JobRejected(
                "generation_not_configured",
                "The GPU worker is not connected yet. An administrator must set " + ", ".join(runpod.missing_settings()) + ".",
                409,
            )
        clean_params = capability.validate(params)
        if project_id is not None and not Project.objects.filter(pk=project_id, workspace_id=workspace_id).exists():
            raise JobRejected("project_not_found", "Project not found in this workspace.")
        with transaction.atomic():
            # Serialise the cap check per workspace so two requests cannot both slip under it.
            from apps.accounts.models import Workspace

            Workspace.objects.select_for_update().get(pk=workspace_id)
            active = GenerationJob.objects.filter(
                workspace_id=workspace_id, status__in=GenerationJob.ACTIVE_STATUSES,
            ).count()
            if active >= settings.GENERATION_MAX_ACTIVE_JOBS:
                raise JobRejected(
                    "too_many_active_jobs",
                    f"At most {settings.GENERATION_MAX_ACTIVE_JOBS} generation jobs can run at once. Wait for one to finish.",
                    429,
                )
            job = GenerationJob.objects.create(
                workspace_id=workspace_id, requested_by=user, capability=capability.name, params=clean_params,
                project_id=project_id, scene_id=scene_id,
            )
        return job

    @staticmethod
    @transaction.atomic
    def cancel(job: GenerationJob) -> GenerationJob:
        current = GenerationJob.objects.select_for_update().get(pk=job.pk)
        if current.status in GenerationJob.ACTIVE_STATUSES:
            current.status = GenerationJob.Status.CANCELED
            current.finished_at = timezone.now()
            current.next_check_at = None
            current.save()
        return current


def finish_job(job_id: int, status: str, *, code: str = "", message: str = "", only_from=GenerationJob.ACTIVE_STATUSES, **fields) -> bool:
    """Moves an active job to a final state exactly once; never overwrites a finished job."""
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status not in only_from:
            return False
        job.status = status
        job.error_code = code
        job.error_message = message[:500]
        job.finished_at = timezone.now()
        job.next_check_at = None
        for key, value in fields.items():
            setattr(job, key, value)
        job.save()
    return True


def _accepts_results(job: GenerationJob) -> bool:
    """A warm GPU worker can finish before we record its job id, so an in-flight submit also accepts a result."""
    if job.result_asset_id:
        return False
    if job.status in (GenerationJob.Status.SUBMITTED, GenerationJob.Status.RUNNING):
        return True
    return job.status == GenerationJob.Status.QUEUED and job.submit_attempts > 0


def ingest_result(job_id: int, stream, content_length: int) -> GenerationJob:
    """Stores a worker upload as a private asset and completes the job. Raises JobRejected."""
    limit = int(settings.GENERATION_MAX_RESULT_BYTES)
    if content_length <= 0:
        raise JobRejected("empty_upload", "The upload was empty.")
    if content_length > limit:
        raise JobRejected("upload_too_large", "The result is larger than the allowed size.", 413)
    job = GenerationJob.objects.select_related("workspace").filter(pk=job_id).first()
    if job is None:
        raise JobRejected("not_found", "Job not found.", 404)
    capability = get_capability(job.capability)
    if capability is None:
        raise JobRejected("unknown_capability", "This kind of generation is not available.")
    if not _accepts_results(job):
        raise JobRejected("job_not_accepting_results", "This job is not waiting for a result.", 409)

    scratch = tempfile.NamedTemporaryFile(prefix="chameleon-result-", delete=False)
    try:
        received = 0
        with scratch:
            while received < content_length:
                chunk = stream.read(min(READ_CHUNK, content_length - received))
                if not chunk:
                    break
                received += len(chunk)
                scratch.write(chunk)
        if received != content_length:
            raise JobRejected("incomplete_upload", "The upload ended early.")
        with open(scratch.name, "rb") as handle:
            sniffed = AssetService.sniff(handle.read(16))
        if sniffed is None:
            raise JobRejected("unsupported_result", "The result is not a supported image, video or audio file.", 415)
        content_type, extension, asset_type = sniffed
        if asset_type not in capability.output_types:
            raise JobRejected("unexpected_result_type", "The result is not the kind of file this job produces.", 415)
        key = f"workspaces/{job.workspace_id}/assets/{uuid.uuid4().hex}.{extension}"
        with open(scratch.name, "rb") as handle:
            saved_key = default_storage.save(key, File(handle))
        try:
            with transaction.atomic():
                current = GenerationJob.objects.select_for_update().get(pk=job.pk)
                if not _accepts_results(current):
                    raise JobRejected("job_not_accepting_results", "This job is not waiting for a result.", 409)
                asset = Asset.objects.create(
                    workspace_id=job.workspace_id, created_by=current.requested_by, asset_type=asset_type,
                    name=f"{capability.label} {current.id}.{extension}", storage_key=saved_key,
                    content_type=content_type, size_bytes=received,
                    provenance={"source": "generation", "job_id": current.id, "capability": current.capability},
                )
                current.result_asset = asset
                current.status = GenerationJob.Status.COMPLETED
                current.finished_at = timezone.now()
                current.error_code = ""
                current.error_message = ""
                current.save()
        except Exception:
            default_storage.delete(saved_key)
            raise
        return current
    finally:
        try:
            os.unlink(scratch.name)
        except OSError:
            logger.warning("Could not remove temporary result file %s.", scratch.name)


def deadline_passed(job: GenerationJob) -> bool:
    return timezone.now() - job.created_at > timedelta(seconds=int(settings.GENERATION_JOB_TTL_SECONDS))
