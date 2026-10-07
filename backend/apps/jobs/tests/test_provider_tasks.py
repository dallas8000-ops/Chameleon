from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.accounts.models import Workspace
from apps.jobs.models import GenerationJob, UsageLedgerEntry
from apps.jobs.services import apply_provider_update
from apps.jobs.tasks import poll_provider_job, submit_provider_job
from apps.providers.base import ProviderError, ProviderJobUpdate, ProviderSubmission


@override_settings(MAGIC_HOUR_API_KEY="test-key")
class ProviderTaskTests(TestCase):
    def setUp(self):
        self.job = GenerationJob.objects.create(
            workspace=Workspace.objects.create(name="Studio"),
            capability="image.generate", payload={"prompt": "Studio"},
            provider_name="magic_hour",
        )
        self.provider = Mock()
        self.provider.is_configured.return_value = True
        self.provider.submit_image_generation.return_value = ProviderSubmission("remote-1", 5, {})
        self.provider.get_generation_update.return_value = ProviderJobUpdate(
            status="completed", result={"downloads": [{"url": "https://provider.example/output.png"}]},
            amount_credits=5, external_event_id="poll:remote-1:complete",
        )

    def test_poll_queue_failure_keeps_durable_schedule_and_recovers_without_resubmission(self):
        with (
            patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider),
            patch("apps.jobs.tasks.poll_provider_job.delay", side_effect=OperationalError("offline")),
            self.assertLogs("apps.jobs.tasks", level="ERROR") as logs,
        ):
            submit_provider_job.run(self.job.id)
        self.assertIn("durable schedule retained", logs.output[0])
        self.job.refresh_from_db()
        self.assertEqual(self.job.provider_job_id, "remote-1")
        self.assertIsNotNone(self.job.next_poll_at)
        self.assertEqual(self.job.error_code, "provider_poll_unavailable")
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            call_command("poll_generation_jobs", stdout=StringIO())
            call_command("poll_generation_jobs", stdout=StringIO())
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.assertIsNone(self.job.next_poll_at)
        self.provider.submit_image_generation.assert_called_once()
        self.assertEqual(UsageLedgerEntry.objects.filter(job=self.job).count(), 1)

    def test_followup_queue_failure_remains_due_for_recovery(self):
        self.job.status = "queued"
        self.job.provider_job_id = "remote-1"
        self.job.save()
        self.provider.get_generation_update.return_value = ProviderJobUpdate(
            status="processing", result={}, external_event_id="poll:remote-1:rendering",
        )
        with (
            patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider),
            patch("apps.jobs.tasks.poll_provider_job.apply_async", side_effect=OperationalError("offline")),
            self.assertLogs("apps.jobs.tasks", level="ERROR"),
        ):
            poll_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")
        self.assertIsNotNone(self.job.next_poll_at)
        self.assertEqual(self.job.error_code, "provider_poll_unavailable")

    def test_future_poll_lease_prevents_duplicate_status_requests(self):
        self.job.status = "queued"
        self.job.provider_job_id = "remote-1"
        self.job.next_poll_at = timezone.now() + timedelta(seconds=60)
        self.job.save()
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            poll_provider_job.run(self.job.id)
            call_command("poll_generation_jobs", stdout=StringIO())
        self.provider.get_generation_update.assert_not_called()

    def test_status_fetch_failure_is_retained_and_rescheduled_with_bounded_backoff(self):
        self.job.status = "queued"
        self.job.provider_job_id = "remote-1"
        self.job.poll_attempts = 20
        self.job.save()
        self.provider.get_generation_update.side_effect = ProviderError(
            "provider_unavailable", "Status server unavailable.",
        )
        with (
            patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider),
            patch("apps.jobs.tasks.poll_provider_job.apply_async") as schedule,
        ):
            poll_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "queued")
        self.assertEqual(self.job.error_code, "provider_unavailable")
        self.assertEqual(self.job.poll_attempts, 21)
        self.assertIsNotNone(self.job.next_poll_at)
        schedule.assert_called_once_with(args=[self.job.id], countdown=240)

    def test_removed_provider_key_does_not_discard_tracking(self):
        self.job.status = "queued"
        self.job.provider_job_id = "remote-1"
        self.job.save()
        self.provider.is_configured.return_value = False
        with (
            patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider),
            patch("apps.jobs.tasks.poll_provider_job.apply_async") as schedule,
        ):
            poll_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "queued")
        self.assertEqual(self.job.provider_job_id, "remote-1")
        self.assertEqual(self.job.error_code, "provider_not_configured")
        self.assertIsNotNone(self.job.next_poll_at)
        self.provider.get_generation_update.assert_not_called()
        schedule.assert_called_once_with(args=[self.job.id], countdown=15)

    def test_completed_provider_failures_cannot_be_manually_resumed(self):
        self.job.status = "failed"
        self.job.error_code = "render_failed"
        self.job.provider_job_id = "remote-1"
        self.job.save()
        with self.assertRaises(CommandError):
            call_command("poll_generation_jobs", resume_job=self.job.id, stdout=StringIO())

    def test_provider_callback_can_complete_exhausted_tracking(self):
        self.job.status = "failed"
        self.job.error_code = "provider_poll_exhausted"
        self.job.provider_job_id = "remote-1"
        self.job.save()
        updated = apply_provider_update(
            job_id=self.job.id, external_event_id="webhook:remote-1:complete",
            status="completed", amount_credits=5,
            result={"downloads": [{"url": "https://provider.example/output.png"}]},
        )
        self.assertEqual(updated.status, "completed")
        self.assertEqual(updated.error_code, "")
        self.assertEqual(UsageLedgerEntry.objects.filter(job=self.job).count(), 1)

    def test_poll_exhaustion_can_resume_tracking_without_paid_resubmission(self):
        self.job.status = "queued"
        self.job.provider_job_id = "remote-1"
        self.job.poll_attempts = 80
        self.job.next_poll_at = timezone.now()
        self.job.save()
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            poll_provider_job.run(self.job.id)
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, "failed")
            self.assertEqual(self.job.error_code, "provider_poll_exhausted")
            call_command("poll_generation_jobs", resume_job=self.job.id, stdout=StringIO())
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.provider.submit_image_generation.assert_not_called()

    def test_legacy_presenter_paths_are_not_submitted_by_worker(self):
        self.job.capability = "presenter.generate"
        self.job.payload = {
            "image_file_path": "https://foreign.example/person.png",
            "audio_file_path": "api-assets/foreign.mp3",
            "start_seconds": 0, "end_seconds": 5,
        }
        self.job.save()
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            submit_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.error_code, "capability_unavailable")
        self.provider.submit_presenter_generation.assert_not_called()
