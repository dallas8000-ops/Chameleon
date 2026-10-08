from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.jobs.downloads import authorized_origins
from apps.jobs.models import GenerationJob


class Command(BaseCommand):
    help = "Schedule a same-project Asset save after operator correction; never generates media."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("--workspace-id", type=int, required=True)
        parser.add_argument("--note", required=True)

    def handle(self, *args, **options):
        note = options["note"].strip()
        if not note or len(note) > 2000:
            raise CommandError("An operator evidence note of 1 to 2000 characters is required.")
        if not authorized_origins() or getattr(settings, "GENERATION_STORAGE_CONFIRMED", False) is not True:
            raise CommandError("Correct and verify private download/storage configuration before recovery.")
        with transaction.atomic():
            job = GenerationJob.objects.select_for_update().filter(
                pk=options["job_id"], workspace_id=options["workspace_id"],
                status="completed", capability="image.generate",
            ).exclude(provider_job_id="").first()
            if job is None or job.asset_status != "failed":
                raise CommandError("Only a failed Asset save for a confirmed completed job is eligible.")
            audit = dict(job.submission_resolution)
            audit.setdefault("asset_recoveries", []).append({"note": note, "at": timezone.now().isoformat()})
            job.submission_resolution = audit
            job.asset_status = "pending"
            job.asset_attempts = 0
            job.asset_next_attempt_at = timezone.now()
            job.save(update_fields=["submission_resolution", "asset_status", "asset_attempts", "asset_next_attempt_at"])
        self.stdout.write(f"Scheduled private Asset recovery for job {job.id}; no generation request was made.")
