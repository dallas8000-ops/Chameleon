from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.generation import runpod
from apps.generation.capabilities import get_capability
from apps.generation.models import GenerationJob
from apps.generation.services import clean_result, deadline_passed, finish_job, upload_token, upload_url

logger = logging.getLogger(__name__)

Status = GenerationJob.Status
MAX_SUBMIT_ATTEMPTS = 3
MAX_POLL_FAILURES = 8
POLL_SECONDS = 5
# Reserves a dispatch window so the sweeper never double-dispatches a job that is already in flight.
RESERVE_SECONDS = 90


def _provider_message(output) -> str:
    if isinstance(output, dict) and isinstance(output.get("error"), str):
        return output["error"][:300]
    return "The GPU worker reported an error."


@shared_task(time_limit=60, acks_late=True)
def submit_job(job_id: int) -> None:
    capability = None
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status != Status.QUEUED or job.provider_job_id:
            return
        if job.next_check_at and job.next_check_at > timezone.now() and job.submit_attempts:
            return
        capability = get_capability(job.capability)
        if capability is None:
            finish_job(job.id, Status.FAILED, code="unknown_capability", message="This kind of generation is not available.")
            return
        if job.submit_attempts >= MAX_SUBMIT_ATTEMPTS:
            finish_job(job.id, Status.FAILED, code="submit_failed", message="The GPU service could not be reached after several tries.")
            return
        job.submit_attempts += 1
        job.next_check_at = timezone.now() + timedelta(seconds=RESERVE_SECONDS)
        job.save(update_fields=["submit_attempts", "next_check_at", "updated_at"])
        payload = {
            "capability": job.capability, "job_id": job.id, "params": job.params,
            "upload": {"url": upload_url(job.id), "token": upload_token(job.id)},
        }
    try:
        provider_job_id = runpod.submit(
            payload, execution_timeout_seconds=capability.max_execution_seconds,
            ttl_seconds=int(settings.GENERATION_JOB_TTL_SECONDS),
        )
    except runpod.RunPodError as error:
        if error.retryable:
            logger.warning("GPU submit for job %s failed (%s); the sweeper will retry.", job_id, error.code)
            return
        finish_job(job_id, Status.FAILED, code=error.code, message=error.message)
        return
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().get(pk=job_id)
        stop_provider_job = False
        if job.status == Status.QUEUED:
            job.provider_job_id = provider_job_id
            job.status = Status.SUBMITTED
        elif job.status == Status.COMPLETED:
            # The worker already delivered its result; keep the id so the poll can fetch timings.
            job.provider_job_id = provider_job_id
        else:
            stop_provider_job = True
        if not stop_provider_job:
            job.next_check_at = timezone.now() + timedelta(seconds=RESERVE_SECONDS)
            job.save()
    if stop_provider_job:
        cancel_provider_job.delay(provider_job_id)
        return
    schedule_poll(job_id, POLL_SECONDS)


def schedule_poll(job_id: int, countdown: int) -> None:
    if settings.GENERATION_POLL_ON_READ:
        # Inline (eager) Celery has no timer, so the next read of the job runs the poll instead.
        GenerationJob.objects.filter(pk=job_id).update(next_check_at=timezone.now() + timedelta(seconds=countdown))
        return
    try:
        poll_job.apply_async(args=[job_id], countdown=countdown)
    except (OperationalError, OSError):
        logger.exception("Could not schedule a poll for generation job %s; the sweeper will retry.", job_id)


@shared_task(time_limit=60, acks_late=True)
def poll_job(job_id: int) -> None:
    job = GenerationJob.objects.filter(pk=job_id).first()
    if job is None or not job.provider_job_id:
        return
    awaiting_timings = job.status == Status.COMPLETED and job.execution_ms is None
    if job.status not in GenerationJob.ACTIVE_STATUSES and not awaiting_timings:
        return
    if deadline_passed(job):
        if job.status in GenerationJob.ACTIVE_STATUSES:
            cancel_provider_job.delay(job.provider_job_id)
            finish_job(job.id, Status.FAILED, code="job_timeout", message="The job took too long and was stopped.")
        return
    try:
        data = runpod.status(job.provider_job_id)
    except runpod.RunPodError as error:
        if not error.retryable:
            if job.status in GenerationJob.ACTIVE_STATUSES:
                finish_job(job.id, Status.FAILED, code=error.code, message=error.message)
            return
        with transaction.atomic():
            current = GenerationJob.objects.select_for_update().get(pk=job_id)
            current.poll_failures += 1
            exhausted = current.poll_failures >= MAX_POLL_FAILURES
            current.next_check_at = timezone.now() + timedelta(seconds=RESERVE_SECONDS)
            current.save(update_fields=["poll_failures", "next_check_at", "updated_at"])
        if exhausted and current.status in GenerationJob.ACTIVE_STATUSES:
            finish_job(job_id, Status.FAILED, code="provider_unreachable", message="The GPU service could not be reached.")
        elif not exhausted:
            schedule_poll(job_id, min(60, POLL_SECONDS * 2 * current.poll_failures))
        return

    state = data.get("status")
    output = data.get("output")
    delay = data.get("delayTime")
    execution = data.get("executionTime")

    def timings() -> dict:
        found = {}
        if isinstance(delay, int) and delay >= 0:
            found["delay_ms"] = delay
        if isinstance(execution, int) and execution >= 0:
            found["execution_ms"] = execution
        return found

    if state in ("IN_QUEUE", "IN_PROGRESS"):
        with transaction.atomic():
            current = GenerationJob.objects.select_for_update().get(pk=job_id)
            if current.status in GenerationJob.ACTIVE_STATUSES:
                current.status = Status.RUNNING if state == "IN_PROGRESS" else Status.SUBMITTED
            current.poll_failures = 0
            current.next_check_at = timezone.now() + timedelta(seconds=RESERVE_SECONDS)
            current.save()
        schedule_poll(job_id, POLL_SECONDS)
        return

    if state == "COMPLETED":
        if isinstance(output, dict) and output.get("error"):
            finish_job(job_id, Status.FAILED, code="worker_error", message=_provider_message(output), **timings())
            return
        summary = clean_result(output.get("result")) if isinstance(output, dict) else {}
        with transaction.atomic():
            current = GenerationJob.objects.select_for_update().get(pk=job_id)
            if current.status == Status.COMPLETED:
                current.result = summary
                for key, value in timings().items():
                    setattr(current, key, value)
                if current.execution_ms is None:
                    current.execution_ms = 0
                current.save()
                return
        # The provider finished but the result file never arrived.
        finish_job(
            job_id, Status.FAILED, code="result_missing",
            message="The GPU finished but no result was received. Check that the worker can reach the server.",
            result=summary, **timings(),
        )
        return

    if state == "FAILED":
        finish_job(job_id, Status.FAILED, code="worker_error", message=_provider_message(output), **timings())
        return
    if state == "CANCELLED":
        finish_job(job_id, Status.CANCELED, code="provider_canceled", message="The job was canceled on the GPU service.", **timings())
        return
    if state == "TIMED_OUT":
        finish_job(job_id, Status.FAILED, code="provider_timeout", message="The GPU stopped the job because it ran too long.", **timings())
        return
    logger.warning("Unrecognised GPU job state %r for generation job %s.", state, job_id)
    with transaction.atomic():
        current = GenerationJob.objects.select_for_update().get(pk=job_id)
        current.poll_failures += 1
        current.next_check_at = timezone.now() + timedelta(seconds=RESERVE_SECONDS)
        current.save(update_fields=["poll_failures", "next_check_at", "updated_at"])
    if current.poll_failures >= MAX_POLL_FAILURES:
        finish_job(job_id, Status.FAILED, code="provider_response_invalid", message="The GPU service reported an unknown state.")
    else:
        schedule_poll(job_id, POLL_SECONDS * 2)


@shared_task
def cancel_provider_job(provider_job_id: str) -> None:
    try:
        runpod.cancel(provider_job_id)
    except runpod.RunPodError:
        logger.warning("Could not cancel GPU job %s; it will stop at its execution limit.", provider_job_id)


def advance_on_read(job: GenerationJob) -> GenerationJob:
    """Local single-process mode: a status read drives the next submit retry or poll that a timer would run."""
    if not settings.GENERATION_POLL_ON_READ:
        return job
    due = job.next_check_at is None or job.next_check_at <= timezone.now()
    if not due:
        return job
    if job.status == Status.QUEUED and not job.provider_job_id:
        submit_job(job.id)
    elif job.provider_job_id and (job.status in GenerationJob.ACTIVE_STATUSES or (job.status == Status.COMPLETED and job.execution_ms is None)):
        poll_job(job.id)
    else:
        return job
    job.refresh_from_db()
    return job


def dispatch(task, job_id: int) -> None:
    try:
        task.delay(job_id)
    except (OperationalError, OSError):
        logger.exception("Dispatch of %s failed for generation job %s; the sweeper will retry.", task.name, job_id)


@shared_task
def recover_generation_jobs() -> int:
    """Re-dispatches work whose Celery message was lost. Reservations prevent double dispatch."""
    now = timezone.now()
    dispatched = 0
    queued = list(GenerationJob.objects.filter(status=Status.QUEUED).order_by("id").values_list("id", flat=True)[:100])
    for job_id in queued:
        with transaction.atomic():
            job = GenerationJob.objects.select_for_update().get(pk=job_id)
            if job.status != Status.QUEUED or job.provider_job_id:
                continue
            if job.next_check_at and job.next_check_at > now:
                continue
            transaction.on_commit(lambda pk=job.id: dispatch(submit_job, pk))
            dispatched += 1
    waiting = list(
        GenerationJob.objects.filter(status__in=(Status.SUBMITTED, Status.RUNNING), next_check_at__lte=now)
        .order_by("id").values_list("id", flat=True)[:100],
    )
    for job_id in waiting:
        with transaction.atomic():
            job = GenerationJob.objects.select_for_update().get(pk=job_id)
            if job.status not in (Status.SUBMITTED, Status.RUNNING) or (job.next_check_at and job.next_check_at > now):
                continue
            job.next_check_at = now + timedelta(seconds=RESERVE_SECONDS)
            job.save(update_fields=["next_check_at", "updated_at"])
            transaction.on_commit(lambda pk=job.id: dispatch(poll_job, pk))
            dispatched += 1
    return dispatched
