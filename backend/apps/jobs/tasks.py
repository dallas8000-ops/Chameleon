import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.jobs.models import GenerationJob
from apps.jobs.services import apply_provider_update
from apps.providers.base import ProviderError
from apps.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)
POLL_LIMIT = 80
ACTIVE_STATES = (GenerationJob.Status.QUEUED, GenerationJob.Status.PROCESSING)
SUBMISSION_STALE_SECONDS = 300
SUBMISSION_UNKNOWN_CODE = "provider_submission_outcome_unknown"


def mark_stale_submission(job: GenerationJob) -> bool:
    if (
        job.status != GenerationJob.Status.PENDING_PROVIDER
        or job.provider_job_id
        or job.provider_submission_started_at is None
        or job.provider_submission_started_at > timezone.now() - timedelta(seconds=SUBMISSION_STALE_SECONDS)
    ):
        return False
    job.status = GenerationJob.Status.FAILED
    job.error_code = SUBMISSION_UNKNOWN_CODE
    job.error_message = (
        "Submission was interrupted; Magic Hour may have accepted and charged this request. "
        "Do not resubmit. An operator must check provider history and use reconcile_generation_job "
        "to attach the actual provider ID or close local tracking."
    )
    job.save(update_fields=["status", "error_code", "error_message", "updated_at"])
    logger.warning("Provider submission outcome unknown for job %s; operator reconciliation required.", job.id)
    return True


def recover_stale_submissions() -> int:
    with transaction.atomic():
        stale = list(
            GenerationJob.objects.select_for_update().filter(
                status=GenerationJob.Status.PENDING_PROVIDER,
                provider_job_id="",
                provider_submission_started_at__lte=timezone.now() - timedelta(seconds=SUBMISSION_STALE_SECONDS),
            ).order_by("provider_submission_started_at", "id")[:100]
        )
        return sum(mark_stale_submission(job) for job in stale)


@shared_task
def submit_provider_job(job_id: int) -> None:
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status != GenerationJob.Status.PENDING_PROVIDER:
            return
        if job.provider_submission_started_at is not None:
            mark_stale_submission(job)
            return
        provider = ProviderRegistry.get(job.provider_name)
        if not provider.is_configured():
            job.status = GenerationJob.Status.BLOCKED_PROVIDER_NOT_CONFIGURED
            job.error_code = "provider_not_configured"
            job.error_message = "Configure MAGIC_HOUR_API_KEY before submitting generation requests."
            job.save(update_fields=["status", "error_code", "error_message", "updated_at"])
            return
        job.provider_submission_started_at = timezone.now()
        job.save(update_fields=["provider_submission_started_at", "updated_at"])

    try:
        if job.capability == "image.generate":
            submission = provider.submit_image_generation(
                prompt=job.payload["prompt"],
                aspect_ratio=job.payload.get("aspect_ratio", "1:1"),
                name=job.payload.get("name", ""),
            )
        elif job.capability == "presenter.generate":
            raise ProviderError(
                "capability_unavailable",
                "Presenter generation requires a secure workspace asset bridge, which is not configured.",
            )
        else:
            raise ProviderError("capability_unavailable", "This provider does not support the requested capability.")
    except ProviderError as error:
        GenerationJob.objects.filter(pk=job.id, status=GenerationJob.Status.PENDING_PROVIDER).update(
            status=GenerationJob.Status.FAILED,
            error_code=error.code,
            error_message=error.message,
        )
        return

    with transaction.atomic():
        current = GenerationJob.objects.select_for_update().get(pk=job.id)
        recoverable_unknown = (
            current.status == GenerationJob.Status.FAILED and current.error_code == SUBMISSION_UNKNOWN_CODE
            and not current.provider_job_id
        )
        if current.status != GenerationJob.Status.PENDING_PROVIDER and not recoverable_unknown:
            return
        current.status = GenerationJob.Status.QUEUED
        current.error_code = ""
        current.error_message = ""
        current.provider_job_id = submission.provider_job_id
        current.quoted_credits = submission.quoted_credits
        current.next_poll_at = timezone.now()
        current.save(update_fields=[
            "status", "error_code", "error_message", "provider_job_id", "quoted_credits", "next_poll_at", "updated_at",
        ])
    try:
        poll_provider_job.delay(job.id)
    except (OperationalError, OSError):
        polling_queue_failed(job.id)


def polling_queue_failed(job_id: int) -> None:
    logger.exception("Provider polling dispatch failed for job %s; durable schedule retained.", job_id)
    GenerationJob.objects.filter(pk=job_id, status__in=ACTIVE_STATES).update(
        error_code="provider_poll_unavailable",
        error_message="Polling dispatch failed; the durable schedule will be recovered by the polling sweeper.",
        updated_at=timezone.now(),
    )


@shared_task
def poll_provider_job(job_id: int) -> None:
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status not in ACTIVE_STATES or not job.provider_job_id:
            return
        now = timezone.now()
        if job.next_poll_at is not None and job.next_poll_at > now:
            return
        if job.poll_attempts >= POLL_LIMIT:
            job.status = GenerationJob.Status.FAILED
            job.error_code = "provider_poll_exhausted"
            job.error_message = (
                "Local tracking exhausted its polling budget; the provider outcome is unknown. "
                "Resume tracking with poll_generation_jobs --resume-job before creating another paid request."
            )
            job.next_poll_at = None
            job.save(update_fields=["status", "error_code", "error_message", "next_poll_at", "updated_at"])
            return
        job.poll_attempts += 1
        # A committed lease also schedules recovery if this worker dies during the HTTP request.
        job.next_poll_at = now + timedelta(seconds=60)
        job.save(update_fields=["poll_attempts", "next_poll_at", "updated_at"])

    provider = ProviderRegistry.get(job.provider_name)
    delay = 15
    try:
        if not provider.is_configured():
            raise ProviderError("provider_not_configured", "Configure MAGIC_HOUR_API_KEY to resume status polling.")
        update = provider.get_generation_update(job=job)
    except ProviderError as error:
        # A status-fetch failure is not evidence that the paid generation itself failed.
        GenerationJob.objects.filter(pk=job.id, status__in=ACTIVE_STATES).update(
            error_code=error.code,
            error_message=error.message,
            updated_at=timezone.now(),
        )
        delay = min(15 * 2 ** min(job.poll_attempts - 1, 4), 240)
    else:
        apply_provider_update(
            job_id=job.id,
            external_event_id=update.external_event_id,
            status=update.status,
            result=update.result,
            error_code=update.error_code,
            error_message=update.error_message,
            amount_credits=update.amount_credits,
        )
        GenerationJob.objects.filter(pk=job.id, status__in=ACTIVE_STATES).update(
            error_code="", error_message="",
        )

    scheduled = GenerationJob.objects.filter(pk=job.id, status__in=ACTIVE_STATES).update(
        next_poll_at=timezone.now() + timedelta(seconds=delay),
    )
    if scheduled:
        try:
            poll_provider_job.apply_async(args=[job.id], countdown=delay)
        except (OperationalError, OSError):
            polling_queue_failed(job.id)


@shared_task
def recover_provider_polls() -> int:
    recover_stale_submissions()
    due_ids = list(
        GenerationJob.objects.filter(status__in=ACTIVE_STATES)
        .exclude(provider_job_id="")
        .filter(Q(next_poll_at__lte=timezone.now()) | Q(next_poll_at__isnull=True))
        .order_by("next_poll_at", "id")
        .values_list("id", flat=True)[:100]
    )
    for job_id in due_ids:
        poll_provider_job.run(job_id)
    return len(due_ids)
