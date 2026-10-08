import logging
import re
from copy import copy

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.jobs.models import GenerationJob
from apps.jobs.services import apply_provider_update
from apps.jobs.tasks import SUBMISSION_UNKNOWN_CODE
from apps.providers.base import ProviderError
from apps.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Resolve an unknown submission outcome; never submits or retries generation."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("--workspace-id", type=int, required=True)
        parser.add_argument("--note", required=True, help="Operator evidence from provider history/support.")
        actions = parser.add_mutually_exclusive_group(required=True)
        actions.add_argument("--provider-job-id", help="Actual ID confirmed by the operator in provider history.")
        actions.add_argument("--close", action="store_true", help="Close local tracking, not the provider project.")

    def handle(self, *args, **options):
        note = options["note"].strip()
        if not note or len(note) > 2000:
            raise CommandError("An evidence note of 1 to 2000 characters is required.")
        provider_job_id = options["provider_job_id"]
        if bool(provider_job_id) == bool(options["close"]):
            raise CommandError("Choose exactly one action: attach a provider ID or close local tracking.")
        if provider_job_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", provider_job_id):
            raise CommandError("Provider ID must be a project identifier, not a URL or path.")
        job = self.unknown_job(options).first()
        if job is None:
            raise CommandError("No unknown submission in the specified workspace is eligible for reconciliation.")

        update = None
        if provider_job_id:
            if GenerationJob.objects.filter(
                provider_name=job.provider_name, provider_job_id=provider_job_id,
            ).exists():
                raise CommandError("That provider project is already attached to a local job.")
            probe = copy(job)
            probe.provider_job_id = provider_job_id
            try:
                update = ProviderRegistry.get(job.provider_name).get_generation_update(job=probe)
            except ProviderError as error:
                raise CommandError(f"Cannot verify provider project: {error.code}: {error.message}") from error

        try:
            with transaction.atomic():
                current = self.unknown_job(options).select_for_update().first()
                if current is None:
                    raise CommandError("Job changed during verification; inspect its current state before reconciling.")
                if provider_job_id:
                    current.provider_job_id = provider_job_id
                    current.status = GenerationJob.Status.QUEUED
                    current.error_code = ""
                    current.error_message = ""
                    current.next_poll_at = timezone.now()
                    current.poll_attempts = 0
                else:
                    current.error_code = "provider_submission_tracking_closed"
                    current.error_message = (
                        "Operator closed local tracking after reconciliation. "
                        "This does not cancel a provider project, confirm a refund, or authorize an automatic retry."
                    )
                current.submission_resolution = {
                    "action": "attached" if provider_job_id else "closed",
                    "note": note,
                    "resolved_at": timezone.now().isoformat(),
                    "provider_job_id": provider_job_id or "",
                }
                current.save(update_fields=[
                    "provider_job_id", "status", "error_code", "error_message", "next_poll_at",
                    "poll_attempts", "submission_resolution", "updated_at",
                ])
                if update is not None:
                    apply_provider_update(
                        job_id=current.id, external_event_id=update.external_event_id,
                        status=update.status, result=update.result, error_code=update.error_code,
                        error_message=update.error_message, amount_credits=update.amount_credits,
                    )
        except IntegrityError as error:
            # Another operator may attach the same project while the status GET is in flight.
            if provider_job_id and GenerationJob.objects.filter(
                provider_name=job.provider_name, provider_job_id=provider_job_id,
            ).exists():
                raise CommandError("That provider project was attached concurrently; no changes were made.") from error
            raise
        logger.info("Operator reconciled submission for workspace %s job %s.", job.workspace_id, job.id)
        self.stdout.write(f"Reconciled job {job.id}; no generation request was submitted.")

    @staticmethod
    def unknown_job(options):
        return GenerationJob.objects.filter(
            pk=options["job_id"], workspace_id=options["workspace_id"],
            status=GenerationJob.Status.FAILED, error_code=SUBMISSION_UNKNOWN_CODE,
            provider_job_id="", provider_submission_started_at__isnull=False,
        )
