import hashlib
import hmac
import json
import time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Workspace
from apps.jobs.models import GenerationJob, UsageLedgerEntry


@override_settings(MAGIC_HOUR_WEBHOOK_SECRET="webhook-test-secret")
class MagicHourWebhookTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user(email="webhook@example.com", password="password")
        workspace = Workspace.objects.create(name="Webhook")
        self.job = GenerationJob.objects.create(
            workspace=workspace,
            capability="image.generate",
            status=GenerationJob.Status.QUEUED,
            payload={"prompt": "studio"},
            provider_name="magic_hour",
            provider_job_id="provider-image-1",
        )

    def post_event(self, event, *, timestamp=None, signature_override=None):
        raw_body = json.dumps(event, separators=(",", ":")).encode()
        timestamp = str(timestamp if timestamp is not None else int(time.time()))
        signature = hmac.new(
            b"webhook-test-secret",
            timestamp.encode() + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()
        return self.client.generic(
            "POST",
            "/api/jobs/webhooks/magic-hour/",
            data=raw_body,
            content_type="application/json",
            HTTP_MAGIC_HOUR_EVENT_TIMESTAMP=timestamp,
            HTTP_MAGIC_HOUR_EVENT_SIGNATURE=signature_override or signature,
        )

    def test_duplicate_completion_webhooks_update_job_and_ledger_once(self):
        event = {
            "type": "image.completed",
            "payload": {
                "id": "provider-image-1",
                "status": "complete",
                "credits_charged": 5,
                "downloads": [{"url": "https://videos.magichour.ai/image.png", "expires_at": "later"}],
            },
        }
        first = self.post_event(event)
        second = self.post_event(event)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(self.job.result["downloads"][0]["url"], event["payload"]["downloads"][0]["url"])
        self.assertEqual(UsageLedgerEntry.objects.count(), 1)
        self.assertEqual(UsageLedgerEntry.objects.get().amount_credits, 5)

    def test_invalid_signature_does_not_update_job(self):
        response = self.post_event(
            {"type": "image.started", "payload": {"id": "provider-image-1"}},
            signature_override="0" * 64,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "invalid_webhook_signature")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, GenerationJob.Status.QUEUED)

    def test_expired_signed_webhook_is_rejected(self):
        response = self.post_event(
            {"type": "image.started", "payload": {"id": "provider-image-1"}},
            timestamp=int(time.time()) - 301,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "invalid_webhook_signature")
