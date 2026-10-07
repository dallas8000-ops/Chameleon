from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.accounts.models import Workspace, WorkspaceMembership
from apps.jobs.models import GenerationJob, UsageLedgerEntry
from apps.jobs.services import apply_provider_update
from apps.jobs.tasks import poll_provider_job, recover_provider_polls, submit_provider_job
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

    def stale_claim(self):
        self.job.provider_submission_started_at = timezone.now() - timedelta(minutes=6)
        self.job.save()

    def test_crash_after_acceptance_becomes_unknown_without_repeated_paid_post(self):
        original_save = GenerationJob.save

        def crash_before_id_save(job, *args, **kwargs):
            if job.provider_job_id:
                raise SystemExit("worker interrupted after acceptance")
            return original_save(job, *args, **kwargs)

        with (
            patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider),
            patch.object(GenerationJob, "save", new=crash_before_id_save),
        ):
            with self.assertRaises(SystemExit):
                submit_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "pending_provider")
        self.assertEqual(self.job.provider_job_id, "")
        self.assertIsNotNone(self.job.provider_submission_started_at)
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            submit_provider_job.run(self.job.id)
            self.stale_claim()
            call_command("poll_generation_jobs", stdout=StringIO())
            submit_provider_job.run(self.job.id)
            call_command("poll_generation_jobs", stdout=StringIO())
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.error_code, "provider_submission_outcome_unknown")
        self.assertEqual(self.job.provider_job_id, "")
        self.assertEqual(self.job.result, {})
        self.provider.submit_image_generation.assert_called_once()
        self.provider.get_generation_update.assert_not_called()

    def test_repeated_stale_delivery_marks_unknown_and_never_posts(self):
        self.stale_claim()
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            submit_provider_job.run(self.job.id)
            submit_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.error_code, "provider_submission_outcome_unknown")
        self.provider.submit_image_generation.assert_not_called()

    def test_recovery_preserves_fresh_claim_and_unclaimed_pending_job(self):
        self.job.provider_submission_started_at = timezone.now()
        self.job.save()
        unclaimed = GenerationJob.objects.create(
            workspace=self.job.workspace, capability="image.generate",
            provider_name="magic_hour", payload={},
        )
        call_command("poll_generation_jobs", stdout=StringIO())
        self.job.refresh_from_db()
        unclaimed.refresh_from_db()
        self.assertEqual(self.job.status, "pending_provider")
        self.assertEqual(unclaimed.status, "pending_provider")

    def test_periodic_sweep_marks_stale_claim_without_guessing_id_or_posting(self):
        self.stale_claim()
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            recover_provider_polls.run()
            recover_provider_polls.run()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.error_code, "provider_submission_outcome_unknown")
        self.assertEqual(self.job.provider_job_id, "")
        self.provider.submit_image_generation.assert_not_called()
        self.provider.get_generation_update.assert_not_called()

    def test_late_original_response_restores_tracking_after_stale_sweep(self):
        def delayed_acceptance(**kwargs):
            self.stale_claim()
            recover_provider_polls.run()
            return ProviderSubmission("remote-1", 5, {})

        self.provider.submit_image_generation.side_effect = delayed_acceptance
        with (
            patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider),
            patch("apps.jobs.tasks.poll_provider_job.delay"),
        ):
            submit_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "queued")
        self.assertEqual(self.job.provider_job_id, "remote-1")
        self.assertEqual(self.job.error_code, "")
        self.assertIsNotNone(self.job.next_poll_at)
        self.provider.submit_image_generation.assert_called_once()

    def test_late_response_cannot_overwrite_operator_closed_tracking(self):
        def delayed_acceptance(**kwargs):
            self.stale_claim()
            recover_provider_polls.run()
            call_command(
                "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                close=True, note="Explicit local tracking closure.", stdout=StringIO(),
            )
            return ProviderSubmission("remote-1", 5, {})

        self.provider.submit_image_generation.side_effect = delayed_acceptance
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            submit_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.error_code, "provider_submission_tracking_closed")
        self.assertEqual(self.job.provider_job_id, "")
        self.assertEqual(UsageLedgerEntry.objects.count(), 0)
        self.provider.submit_image_generation.assert_called_once()

    def test_stale_cutoff_is_exactly_five_minutes(self):
        now = timezone.now()
        self.job.provider_submission_started_at = now - timedelta(seconds=299)
        self.job.save()
        with patch("apps.jobs.tasks.timezone.now", return_value=now):
            recover_provider_polls.run()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "pending_provider")
        self.job.provider_submission_started_at = now - timedelta(seconds=300)
        self.job.save()
        with patch("apps.jobs.tasks.timezone.now", return_value=now):
            recover_provider_polls.run()
        self.job.refresh_from_db()
        self.assertEqual(self.job.error_code, "provider_submission_outcome_unknown")

    def test_unknown_submission_error_is_visible_only_to_workspace_members(self):
        self.stale_claim()
        call_command("poll_generation_jobs", stdout=StringIO())
        user = get_user_model().objects.create_user(email="reconcile@example.com", password="password")
        WorkspaceMembership.objects.create(user=user, workspace=self.job.workspace, role="reviewer")
        self.client.force_login(user)
        response = self.client.get(f"/api/jobs/{self.job.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(response.json()["error_code"], "provider_submission_outcome_unknown")
        WorkspaceMembership.objects.filter(user=user).delete()
        self.assertEqual(self.client.get(f"/api/jobs/{self.job.id}/").status_code, 404)

    def test_operator_attaches_real_id_then_polls_without_paid_resubmission(self):
        self.stale_claim()
        call_command("poll_generation_jobs", stdout=StringIO())
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            call_command(
                "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                provider_job_id="remote-1", note="Matched provider project history by time and prompt.",
                stdout=StringIO(),
            )
            call_command("poll_generation_jobs", stdout=StringIO())
        self.job.refresh_from_db()
        self.assertEqual(self.job.provider_job_id, "remote-1")
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.submission_resolution["action"], "attached")
        self.assertEqual(UsageLedgerEntry.objects.filter(job=self.job).count(), 1)
        self.provider.submit_image_generation.assert_not_called()

    def test_operator_can_close_unknown_tracking_without_faking_cancellation_or_usage(self):
        self.stale_claim()
        call_command("poll_generation_jobs", stdout=StringIO())
        call_command(
            "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
            close=True, note="Provider support confirmed no accepted project.", stdout=StringIO(),
        )
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.error_code, "provider_submission_tracking_closed")
        self.assertEqual(self.job.provider_job_id, "")
        self.assertEqual(self.job.submission_resolution["action"], "closed")
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            submit_provider_job.run(self.job.id)
        self.provider.submit_image_generation.assert_not_called()
        self.assertEqual(UsageLedgerEntry.objects.count(), 0)
        with self.assertRaises(CommandError):
            call_command(
                "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                close=True, note="Repeated closure.", stdout=StringIO(),
            )

    def test_attached_active_project_is_swept_without_resubmission(self):
        self.stale_claim()
        recover_provider_polls.run()
        self.provider.get_generation_update.return_value = ProviderJobUpdate(
            status="processing", result={}, external_event_id="poll:remote-1:rendering",
        )
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            call_command(
                "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                provider_job_id="remote-1", note="Confirmed matching project.", stdout=StringIO(),
            )
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")
        self.assertIsNotNone(self.job.next_poll_at)
        self.provider.get_generation_update.return_value = ProviderJobUpdate(
            status="completed", result={}, external_event_id="poll:remote-1:complete", amount_credits=5,
        )
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            recover_provider_polls.run()
            submit_provider_job.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.provider.submit_image_generation.assert_not_called()

    def test_reconciliation_rejects_arbitrary_paths_and_keeps_note_private(self):
        self.stale_claim()
        recover_provider_polls.run()
        for provider_id in ("https://provider.example/project", "../remote-1"):
            with self.assertRaises(CommandError):
                call_command(
                    "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                    provider_job_id=provider_id, note="Investigated.", stdout=StringIO(),
                )
        call_command(
            "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
            close=True, note="Private operator case reference.", stdout=StringIO(),
        )
        user = get_user_model().objects.create_user(email="note@example.com", password="password")
        WorkspaceMembership.objects.create(user=user, workspace=self.job.workspace, role="owner")
        self.client.force_login(user)
        response = self.client.get(f"/api/jobs/{self.job.id}/")
        self.assertNotIn("submission_resolution", response.json())
        self.assertNotIn("Private operator case reference", response.content.decode())

    def test_reconciliation_rejects_wrong_workspace_fresh_claim_and_missing_note(self):
        with self.assertRaises(CommandError):
            call_command(
                "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                close=True, note="Fresh job.", stdout=StringIO(),
            )
        self.stale_claim()
        call_command("poll_generation_jobs", stdout=StringIO())
        for workspace_id, note in ((999999, "Wrong workspace"), (self.job.workspace_id, "")):
            with self.assertRaises(CommandError):
                call_command(
                    "reconcile_generation_job", self.job.id, workspace_id=workspace_id,
                    close=True, note=note, stdout=StringIO(),
                )
        self.job.refresh_from_db()
        self.assertEqual(self.job.error_code, "provider_submission_outcome_unknown")

    def test_operator_attachment_rechecks_job_after_status_get(self):
        self.stale_claim()
        recover_provider_polls.run()
        update = self.provider.get_generation_update.return_value

        def close_during_get(**kwargs):
            call_command(
                "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                close=True, note="Concurrent operator closed tracking.", stdout=StringIO(),
            )
            return update

        self.provider.get_generation_update.side_effect = close_during_get
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            with self.assertRaises(CommandError):
                call_command(
                    "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                    provider_job_id="remote-1", note="Confirmed history match.", stdout=StringIO(),
                )
        self.job.refresh_from_db()
        self.assertEqual(self.job.error_code, "provider_submission_tracking_closed")
        self.assertEqual(self.job.provider_job_id, "")
        self.assertEqual(UsageLedgerEntry.objects.count(), 0)
        self.provider.submit_image_generation.assert_not_called()

    def test_reconciliation_get_failure_or_duplicate_id_cannot_attach(self):
        self.stale_claim()
        call_command("poll_generation_jobs", stdout=StringIO())
        self.provider.get_generation_update.side_effect = ProviderError("provider_http_404", "Not found.")
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            with self.assertRaises(CommandError):
                call_command(
                    "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                    provider_job_id="remote-missing", note="Checked history.", stdout=StringIO(),
                )
        GenerationJob.objects.create(
            workspace=Workspace.objects.create(name="Other"), capability="image.generate",
            provider_name="magic_hour", provider_job_id="remote-1", status="queued", payload={},
        )
        self.provider.get_generation_update.side_effect = None
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=self.provider):
            with self.assertRaises(CommandError):
                call_command(
                    "reconcile_generation_job", self.job.id, workspace_id=self.job.workspace_id,
                    provider_job_id="remote-1", note="Checked history.", stdout=StringIO(),
                )
        self.job.refresh_from_db()
        self.assertEqual(self.job.provider_job_id, "")
        self.provider.submit_image_generation.assert_not_called()
