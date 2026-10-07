from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import GenerationJob
from apps.jobs.tasks import poll_provider_job, recover_provider_polls


class Command(BaseCommand):
    help = "Poll due provider jobs directly, without requiring a working Celery broker."

    def add_arguments(self, parser):
        parser.add_argument("--resume-job", type=int, help="Resume a job whose local polling budget was exhausted.")

    def handle(self, *args, **options):
        job_id = options["resume_job"]
        if job_id is not None:
            with transaction.atomic():
                job = GenerationJob.objects.select_for_update().filter(
                    pk=job_id, status=GenerationJob.Status.FAILED, error_code="provider_poll_exhausted",
                ).exclude(provider_job_id="").first()
                if job is None:
                    raise CommandError("Only jobs with exhausted local polling and a provider ID can be resumed.")
                job.status = GenerationJob.Status.QUEUED
                job.error_code = ""
                job.error_message = ""
                job.next_poll_at = timezone.now()
                job.poll_attempts = 0
                job.save(update_fields=[
                    "status", "error_code", "error_message", "next_poll_at", "poll_attempts", "updated_at",
                ])
            poll_provider_job.run(job_id)
            self.stdout.write(f"Resumed provider tracking for job {job_id}; no generation was resubmitted.")
        else:
            count = recover_provider_polls.run()
            self.stdout.write(f"Checked {count} due provider jobs.")
