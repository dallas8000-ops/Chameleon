from django.test import TestCase

from apps.accounts.models import Workspace
from apps.jobs.models import GenerationJob, UsageLedgerEntry
from apps.jobs.services import IdempotencyConflict, apply_provider_update, record_usage_once


class UsageLedgerTests(TestCase):
    def setUp(self):
        workspace = Workspace.objects.create(name="Ledger")
        self.job = GenerationJob.objects.create(
            workspace=workspace,
            capability="image.generate",
            status=GenerationJob.Status.QUEUED,
            payload={},
            provider_name="magic_hour",
            provider_job_id="provider-job-1",
        )

    def test_duplicate_provider_event_does_not_duplicate_usage(self):
        first = record_usage_once(job_id=self.job.id, external_event_id="evt-1", amount_credits=12)
        second = record_usage_once(job_id=self.job.id, external_event_id="evt-1", amount_credits=12)

        self.assertEqual(first.id, second.id)
        self.assertEqual(UsageLedgerEntry.objects.count(), 1)

    def test_duplicate_completion_update_and_usage_are_idempotent(self):
        update = {
            "status": "completed",
            "result": {"downloads": ["https://provider.example/output.png"]},
            "amount_credits": 12,
            "external_event_id": "evt-complete",
        }
        first = apply_provider_update(job_id=self.job.id, **update)
        second = apply_provider_update(job_id=self.job.id, **update)

        self.assertEqual(first.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(second.updated_at, first.updated_at)
        self.assertEqual(UsageLedgerEntry.objects.count(), 1)
        self.assertEqual(UsageLedgerEntry.objects.get().amount_credits, 12)

    def test_provider_error_is_retained_without_fabricating_result(self):
        failed = apply_provider_update(
            job_id=self.job.id,
            external_event_id="evt-failed",
            status="failed",
            error_code="render_failed",
            error_message="Provider could not render this request.",
        )
        self.assertEqual(failed.status, GenerationJob.Status.FAILED)
        self.assertEqual(failed.error_code, "render_failed")
        self.assertEqual(failed.error_message, "Provider could not render this request.")
        self.assertEqual(failed.result, {})

    def test_usage_is_once_per_job_even_when_callbacks_use_different_event_ids(self):
        for event_id in ("webhook-event-1", "poll-event-2"):
            apply_provider_update(
                job_id=self.job.id,
                external_event_id=event_id,
                status="completed",
                amount_credits=12,
            )
        self.assertEqual(UsageLedgerEntry.objects.count(), 1)
        self.assertEqual(UsageLedgerEntry.objects.get().external_event_id, f"usage:{self.job.id}")

    def test_stale_poll_update_cannot_move_completed_job_back_to_queued(self):
        apply_provider_update(
            job_id=self.job.id,
            external_event_id="poll:completed",
            status="completed",
            result={"downloads": ["https://provider.example/output.png"]},
        )
        stale = apply_provider_update(
            job_id=self.job.id,
            external_event_id="poll:queued-late",
            status="queued",
        )
        self.assertEqual(stale.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(stale.result, {"downloads": ["https://provider.example/output.png"]})

    def test_reused_ledger_id_with_different_value_is_rejected(self):
        record_usage_once(job_id=self.job.id, external_event_id="evt-conflict", amount_credits=12)
        with self.assertRaises(IdempotencyConflict):
            record_usage_once(job_id=self.job.id, external_event_id="evt-conflict", amount_credits=13)
        self.assertEqual(UsageLedgerEntry.objects.count(), 1)
