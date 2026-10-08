from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from apps.jobs.models import GenerationJob
from apps.studio.tests.fixtures import StudioFixture


def tariff():
    return {
        "version": "test-v1", "enabled": True, "verified_by": "test-operator",
        "verified_at": timezone.now().isoformat(),
        "valid_until": (timezone.now() + timedelta(days=1)).isoformat(),
        "credits": 5,
    }


class GenerationContractTests(StudioFixture):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_login(self.owner)
        self.input = {"workspace_id": self.workspace.id, "project_id": self.project.id, "prompt": "Daylight"}

    def quote(self):
        return self.post("/api/jobs/image-generation/quote/", self.input)

    def submit(self, quote, key="attempt-1", **changes):
        return self.post("/api/jobs/image-generation/", {**self.input, "quote_id": quote, **changes},
                         HTTP_IDEMPOTENCY_KEY=key)

    def configured(self):
        return override_settings(
            MAGIC_HOUR_API_KEY="test-only", GENERATION_IMAGE_TARIFF=tariff(),
            GENERATION_DOWNLOAD_ORIGINS=["https://media.example"], GENERATION_STORAGE_CONFIRMED=True,
        )

    def test_defaults_are_unavailable_and_direct_submit_cannot_bypass_quote(self):
        response = self.quote()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "pricing_unavailable")
        self.assertEqual(self.post("/api/jobs/image-generation/", self.input).status_code, 400)
        self.assertEqual(GenerationJob.objects.count(), 0)

    def test_quote_then_idempotent_submit_retains_estimate_and_requester(self):
        with self.configured():
            quote = self.quote()
            self.assertEqual(quote.status_code, 200)
            body = quote.json()
            self.assertEqual(body["estimated_credits"], 5)
            self.assertFalse(body["price_guaranteed"])
            self.assertEqual(body["parameters"]["resolution"], "640px")
            with self.captureOnCommitCallbacks(execute=False):
                first = self.submit(body["quote_id"])
                again = self.submit(body["quote_id"])
                changed = self.submit(body["quote_id"], prompt="Night")
            self.assertEqual(first.status_code, 202)
            self.assertEqual(first.json()["id"], again.json()["id"])
            self.assertEqual(changed.status_code, 409)
            job = GenerationJob.objects.get()
            self.assertEqual(job.requested_by_id, self.owner.id)
            self.assertEqual(job.quoted_credits, 5)
            self.assertIsNone(job.provider_reported_credits)

    def test_stale_changed_and_foreign_quotes_never_create_jobs(self):
        from apps.jobs.models import GenerationQuote

        with self.configured():
            quote = self.quote().json()["quote_id"]
            self.assertEqual(self.submit(quote, prompt="Different").json()["code"], "quote_changed")
            GenerationQuote.objects.filter(pk=quote).update(expires_at=timezone.now() - timedelta(seconds=1))
            self.assertEqual(self.submit(quote).json()["code"], "quote_expired")
            self.client.force_login(self.editor)
            self.assertEqual(self.submit(quote).status_code, 404)
        self.assertFalse(GenerationJob.objects.exists())

    def test_roles_and_strict_inputs(self):
        with self.configured():
            self.assertEqual(self.post("/api/jobs/image-generation/quote/", {**self.input, "url": "https://x"}).status_code, 400)
            self.client.force_login(self.reviewer)
            self.assertEqual(self.quote().status_code, 403)
            capabilities = self.client.get(f"/api/jobs/capabilities/?workspace_id={self.workspace.id}")
            self.assertFalse(capabilities.json()["capabilities"][0]["can_submit"])
            self.client.force_login(self.outsider)
            self.assertEqual(self.quote().status_code, 404)

    def test_version_revocation_blocks_unstarted_worker_and_retry_returns_accepted_job(self):
        from apps.jobs.tasks import submit_provider_job

        with self.configured():
            quote = self.quote().json()["quote_id"]
            with self.captureOnCommitCallbacks(execute=False):
                accepted = self.submit(quote).json()
            with override_settings(GENERATION_IMAGE_TARIFF={}):
                self.assertEqual(self.submit(quote).json()["id"], accepted["id"])
                with patch("apps.providers.magic_hour.MagicHourProvider.submit_image_generation") as paid:
                    submit_provider_job.run(accepted["id"])
                paid.assert_not_called()
            job = GenerationJob.objects.get()
            self.assertEqual(job.error_code, "pricing_unavailable")
            self.assertIsNone(job.provider_submission_started_at)

    def test_revoked_membership_blocks_queued_paid_submission(self):
        from apps.accounts.models import WorkspaceMembership
        from apps.jobs.tasks import submit_provider_job
        from apps.providers.base import ProviderSubmission
        with self.configured():
            quote = self.quote().json()["quote_id"]
            with self.captureOnCommitCallbacks(execute=False):
                accepted = self.submit(quote).json()
            WorkspaceMembership.objects.filter(user=self.owner, workspace=self.workspace).update(role="reviewer")
            with patch("apps.jobs.tasks.ProviderRegistry.get") as provider:
                provider.return_value.submit_image_generation.return_value = ProviderSubmission("remote-red", 5, {})
                provider.return_value.is_configured.return_value = True
                submit_provider_job.run(accepted["id"])
            provider.assert_not_called()
        job = GenerationJob.objects.get()
        self.assertIsNone(job.provider_submission_started_at)
        self.assertEqual(job.error_code, "workspace_read_only")

    def test_public_job_projection_hides_provider_urls_and_raw_errors(self):
        job = GenerationJob.objects.create(
            workspace=self.workspace, capability="image.generate", status="completed",
            result={"downloads": [{"url": "https://private/token"}], "asset_id": 999},
            error_message="https://private/token", error_code="raw-provider-error",
        )
        response = self.client.get(f"/api/jobs/{job.id}/")
        self.assertNotIn("https://", response.content.decode())
        self.assertNotIn("downloads", response.content.decode())
        self.assertNotIn("asset_id", response.json()["result"])

    def test_each_operator_gate_and_expired_tariff_fail_closed(self):
        with self.configured():
            for config, code in (
                ({"GENERATION_DOWNLOAD_ORIGINS": []}, "download_origins_unavailable"),
                ({"GENERATION_STORAGE_CONFIRMED": False}, "storage_unavailable"),
                ({"MAGIC_HOUR_API_KEY": ""}, "provider_not_configured"),
                ({"GENERATION_IMAGE_TARIFF": {**tariff(), "verified_by": ""}}, "pricing_unavailable"),
                ({"GENERATION_IMAGE_TARIFF": {**tariff(), "verified_by": True}}, "pricing_unavailable"),
                ({"GENERATION_IMAGE_TARIFF": {**tariff(), "version": {"invalid": True}}}, "pricing_unavailable"),
                ({"GENERATION_IMAGE_TARIFF": {**tariff(), "version": "v" * 81}}, "pricing_unavailable"),
                ({"GENERATION_IMAGE_TARIFF": {**tariff(), "credits": True}}, "pricing_unavailable"),
                ({"GENERATION_IMAGE_TARIFF": {**tariff(), "valid_until": timezone.now().isoformat()}}, "pricing_unavailable"),
            ):
                with self.subTest(code=code), override_settings(**config):
                    response = self.quote()
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()["code"], code)
                    self.assertIsNone(response.json()["quote"])

    def test_revoked_role_blocks_exact_retry_and_quote_foreign_project_is_hidden(self):
        from apps.accounts.models import WorkspaceMembership
        from apps.studio.models import Project
        with self.configured():
            foreign = Project.objects.create(workspace=self.other_workspace, title="Private", format="9:16")
            self.assertEqual(self.post("/api/jobs/image-generation/quote/",
                                      {**self.input, "project_id": foreign.id}).status_code, 404)
            quote = self.quote().json()["quote_id"]
            with self.captureOnCommitCallbacks(execute=False):
                self.assertEqual(self.submit(quote).status_code, 202)
            WorkspaceMembership.objects.filter(user=self.owner, workspace=self.workspace).update(role="reviewer")
            self.assertEqual(self.submit(quote).status_code, 403)

    def test_expired_consumed_quote_returns_same_job_with_new_key_without_generation(self):
        from apps.jobs.models import GenerationQuote
        with self.configured():
            quote = self.quote().json()["quote_id"]
            with self.captureOnCommitCallbacks(execute=False):
                first = self.submit(quote)
                GenerationQuote.objects.filter(pk=quote).update(expires_at=timezone.now() - timedelta(hours=1))
                again = self.submit(quote, key="another-key")
            self.assertEqual(first.json()["id"], again.json()["id"])
            self.assertEqual(GenerationJob.objects.count(), 1)

    def test_reported_discrepancy_disables_future_quotes_but_keeps_existing_job(self):
        with self.configured():
            quote = self.quote().json()["quote_id"]
            with self.captureOnCommitCallbacks(execute=False):
                self.submit(quote)
            GenerationJob.objects.update(provider_reported_credits=7)
            self.assertEqual(self.quote().json()["code"], "pricing_unavailable")
            self.assertEqual(self.submit(quote).status_code, 202)
