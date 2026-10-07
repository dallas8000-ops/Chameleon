from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import GenerationJob
from apps.jobs.services import apply_provider_update
from apps.providers.base import ProviderError
from apps.providers.registry import ProviderRegistry


@shared_task
def submit_provider_job(job_id: int) -> None:
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
        if (
            job is None
            or job.status != GenerationJob.Status.PENDING_PROVIDER
            or job.provider_submission_started_at is not None
        ):
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
            submission = provider.submit_presenter_generation(
                script_text=job.payload.get("script_text", ""),
                scene_payload=job.payload,
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
        if current.status != GenerationJob.Status.PENDING_PROVIDER:
            return
        current.status = GenerationJob.Status.QUEUED
        current.provider_job_id = submission.provider_job_id
        current.quoted_credits = submission.quoted_credits
        current.save(update_fields=["status", "provider_job_id", "quoted_credits", "updated_at"])
    try:
        poll_provider_job.delay(job.id)
    except Exception:
        GenerationJob.objects.filter(pk=job.id, status=GenerationJob.Status.QUEUED).update(
            error_code="provider_poll_unavailable",
            error_message="Magic Hour accepted the job, but status polling could not be queued.",
            updated_at=timezone.now(),
        )


@shared_task(bind=True, max_retries=80)
def poll_provider_job(self, job_id: int) -> None:
    job = GenerationJob.objects.filter(pk=job_id).first()
    if job is None or job.status not in (
        GenerationJob.Status.QUEUED,
        GenerationJob.Status.PROCESSING,
    ):
        return
    provider = ProviderRegistry.get(job.provider_name)
    if not provider.is_configured():
        GenerationJob.objects.filter(
            pk=job.id,
            status__in=(GenerationJob.Status.QUEUED, GenerationJob.Status.PROCESSING),
        ).update(
            error_code="provider_not_configured",
            error_message="Configure MAGIC_HOUR_API_KEY to resume provider status polling.",
            updated_at=timezone.now(),
        )
        return
    try:
        update = provider.get_generation_update(job=job)
    except ProviderError as error:
        if error.code == "provider_unavailable":
            if self.request.retries >= self.max_retries:
                GenerationJob.objects.filter(
                    pk=job.id,
                    status__in=(GenerationJob.Status.QUEUED, GenerationJob.Status.PROCESSING),
                ).update(
                    error_code="provider_poll_unavailable",
                    error_message="Magic Hour status could not be checked after repeated retries.",
                    updated_at=timezone.now(),
                )
                return
            raise self.retry(countdown=min(15 * (2 ** min(self.request.retries, 4)), 240))
        apply_provider_update(
            job_id=job.id,
            external_event_id=f"poll-error:{job.provider_job_id}:{error.code}",
            status=GenerationJob.Status.FAILED,
            error_code=error.code,
            error_message=error.message,
        )
        return

    apply_provider_update(
        job_id=job.id,
        external_event_id=update.external_event_id,
        status=update.status,
        result=update.result,
        error_code=update.error_code,
        error_message=update.error_message,
        amount_credits=update.amount_credits,
    )
    if update.status in (GenerationJob.Status.QUEUED, GenerationJob.Status.PROCESSING):
        raise self.retry(countdown=15)
