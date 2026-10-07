from django.db import transaction

from apps.jobs.models import GenerationJob, ProviderEvent, UsageLedgerEntry
from apps.providers.registry import ProviderRegistry


class UnsupportedCapability(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


def submit_generation_job(
    *,
    workspace_id: int,
    project_id: int | None,
    scene_id: int | None,
    capability: str,
    payload: dict,
) -> GenerationJob:
    provider_name = "magic_hour"
    provider = ProviderRegistry.get(provider_name)
    if not provider.supports_capability(capability):
        raise UnsupportedCapability(capability)

    job = GenerationJob.objects.create(
        workspace_id=workspace_id,
        project_id=project_id,
        scene_id=scene_id,
        capability=capability,
        status=GenerationJob.Status.PENDING_PROVIDER,
        payload=payload,
        provider_name=provider_name,
    )
    if not provider.is_configured():
        GenerationJob.objects.filter(pk=job.pk).update(
            status=GenerationJob.Status.BLOCKED_PROVIDER_NOT_CONFIGURED,
            error_code="provider_not_configured",
            error_message="Configure MAGIC_HOUR_API_KEY before submitting generation requests.",
        )
        job.refresh_from_db()
        return job

    from apps.jobs.tasks import submit_provider_job

    try:
        submit_provider_job.delay(job.id)
    except Exception:
        GenerationJob.objects.filter(pk=job.pk, status=GenerationJob.Status.PENDING_PROVIDER).update(
            status=GenerationJob.Status.FAILED,
            error_code="job_queue_unavailable",
            error_message="The generation worker could not be reached. Retry this request.",
        )
        job.refresh_from_db()
    return job


@transaction.atomic
def record_usage_once(*, job_id: int, external_event_id: str, amount_credits: int) -> UsageLedgerEntry:
    if not external_event_id or len(external_event_id) > 160:
        raise ValueError("external_event_id must contain 1 to 160 characters.")
    if isinstance(amount_credits, bool) or not isinstance(amount_credits, int) or amount_credits < 0:
        raise ValueError("amount_credits must be a non-negative integer.")
    entry, created = UsageLedgerEntry.objects.get_or_create(
        external_event_id=external_event_id,
        defaults={"job_id": job_id, "amount_credits": amount_credits},
    )
    if not created and (entry.job_id != job_id or entry.amount_credits != amount_credits):
        raise IdempotencyConflict("The usage event identifier was already used for a different ledger entry.")
    return entry


@transaction.atomic
def apply_provider_update(
    *,
    job_id: int,
    external_event_id: str,
    status: str,
    result: dict | None = None,
    error_code: str = "",
    error_message: str = "",
    amount_credits: int | None = None,
) -> GenerationJob:
    valid_statuses = set(GenerationJob.Status.values)
    if status not in valid_statuses:
        raise ValueError("Provider updates must use a known generation job state.")
    if not external_event_id or len(external_event_id) > 160:
        raise ValueError("external_event_id must contain 1 to 160 characters.")
    if result is not None and not isinstance(result, dict):
        raise ValueError("result must be an object.")

    job = GenerationJob.objects.select_for_update().get(pk=job_id)
    _, created = ProviderEvent.objects.get_or_create(job=job, external_event_id=external_event_id)
    if not created:
        return job

    allowed_transitions = {
        GenerationJob.Status.PENDING_PROVIDER: {
            GenerationJob.Status.QUEUED,
            GenerationJob.Status.PROCESSING,
            GenerationJob.Status.COMPLETED,
            GenerationJob.Status.FAILED,
            GenerationJob.Status.CANCELED,
            GenerationJob.Status.BLOCKED_PROVIDER_NOT_CONFIGURED,
        },
        GenerationJob.Status.QUEUED: {
            GenerationJob.Status.QUEUED,
            GenerationJob.Status.PROCESSING,
            GenerationJob.Status.COMPLETED,
            GenerationJob.Status.FAILED,
            GenerationJob.Status.CANCELED,
        },
        GenerationJob.Status.PROCESSING: {
            GenerationJob.Status.PROCESSING,
            GenerationJob.Status.COMPLETED,
            GenerationJob.Status.FAILED,
            GenerationJob.Status.CANCELED,
        },
    }
    if status in allowed_transitions.get(job.status, set()):
        job.status = status
        job.error_code = error_code
        job.error_message = error_message
        if status == GenerationJob.Status.COMPLETED and result is not None:
            job.result = result
        job.save(update_fields=["status", "error_code", "error_message", "result", "updated_at"])

    if amount_credits is not None:
        if isinstance(amount_credits, bool) or not isinstance(amount_credits, int) or amount_credits < 0:
            raise ValueError("amount_credits must be a non-negative integer.")
        record_usage_once(
            job_id=job.id,
            external_event_id=f"usage:{job.id}",
            amount_credits=amount_credits,
        )
    return job
