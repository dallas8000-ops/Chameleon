from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from apps.accounts.models import Workspace, WorkspaceMembership
from apps.jobs.models import GenerationJob
from apps.jobs.quoting import accept_quote, create_quote
from apps.jobs.tasks import submit_provider_job
from apps.jobs.tests.test_generation_contract import tariff
from apps.providers.base import ProviderSubmission


class GenerationRaceTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock races require PostgreSQL; use CHAMELEON_TEST_DATABASE_URL.")
        self.config = override_settings(
            MAGIC_HOUR_API_KEY="test-only", GENERATION_IMAGE_TARIFF=tariff(),
            GENERATION_DOWNLOAD_ORIGINS=["https://media.example"], GENERATION_STORAGE_CONFIRMED=True,
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.user = get_user_model().objects.create(email="race@example.com")
        self.workspace = Workspace.objects.create(name="Race")
        WorkspaceMembership.objects.create(user=self.user, workspace=self.workspace, role="owner")
        self.payload = {"workspace_id": self.workspace.id, "prompt": "Daylight", "aspect_ratio": "1:1"}
        self.quote = create_quote(self.user, self.payload)

    def threaded(self, operation):
        def run():
            close_old_connections()
            try:
                return operation()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(run), pool.submit(run)
            return first.result(timeout=20), second.result(timeout=20)

    def test_concurrent_acceptance_creates_one_job_and_one_paid_submission(self):
        with patch("apps.jobs.tasks.dispatch_submission"):
            ids = self.threaded(lambda: accept_quote(self.user, self.payload, self.quote.id, "same-key").id)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(GenerationJob.objects.count(), 1)
        provider = Mock()
        provider.is_configured.return_value = True
        provider.submit_image_generation.return_value = ProviderSubmission("remote-race", 5, {})
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=provider), \
             patch("apps.jobs.tasks.poll_provider_job.delay"):
            self.threaded(lambda: submit_provider_job.run(ids[0]))
        self.assertEqual(provider.submit_image_generation.call_count, 1)
        self.assertEqual(GenerationJob.objects.get().provider_job_id, "remote-race")

    def test_two_quotes_with_same_key_cannot_create_two_jobs(self):
        from apps.jobs.quoting import ContractError
        other = create_quote(self.user, self.payload)
        def accept(quote_id):
            close_old_connections()
            try:
                return accept_quote(self.user, self.payload, quote_id, "same-key").id
            except ContractError as error:
                return error.code
            finally:
                close_old_connections()
        with patch("apps.jobs.tasks.dispatch_submission"), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(accept, item.id) for item in (self.quote, other)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results.count("idempotency_conflict"), 1)
        self.assertEqual(GenerationJob.objects.count(), 1)

    def test_parallel_ingestion_uses_one_lease_and_creates_one_owned_asset(self):
        from datetime import timedelta
        from pathlib import Path
        import shutil
        import threading
        from django.conf import settings
        from django.utils import timezone
        from apps.jobs.ingestion import ingest_result
        from apps.jobs.services import apply_provider_update
        from apps.providers.base import ProviderJobUpdate
        from apps.studio.models import Asset
        media = Path(settings.BASE_DIR) / ".test-ingestion-race"
        media.mkdir(exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with patch("apps.jobs.tasks.dispatch_submission"):
            job = accept_quote(self.user, self.payload, self.quote.id, "race-ingestion")
        job.provider_job_id = "remote-1"
        job.save()
        apply_provider_update(job_id=job.id, external_event_id="done", status="completed")
        entered, release = threading.Event(), threading.Event()
        provider = Mock()
        provider.get_generation_update.return_value = ProviderJobUpdate(
            status="completed", result={"downloads": [{"url": "https://media.example/output",
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()}]},
        )
        def download(url, target):
            entered.set()
            if not release.wait(timeout=10):
                raise AssertionError("Lease test stalled")
            target.write(b"\x89PNG\r\n\x1a\n" + b"fixture")
            return "image/png"
        def ingest():
            close_old_connections()
            try:
                ingest_result.run(job.id)
            finally:
                close_old_connections()
        with override_settings(MEDIA_ROOT=str(media)), \
             patch("apps.jobs.ingestion.ProviderRegistry.get", return_value=provider), \
             patch("apps.jobs.ingestion.download_image", side_effect=download), \
             patch("apps.jobs.ingestion.validate_image"), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(ingest)
            self.assertTrue(entered.wait(timeout=5))
            second = pool.submit(ingest)
            second.result(timeout=5)
            release.set()
            first.result(timeout=10)
        self.assertEqual(Asset.objects.count(), 1)
        job.refresh_from_db()
        self.assertEqual(job.asset_status, "ready")
        self.assertEqual(job.generated_asset.workspace_id, self.workspace.id)
        self.assertEqual(provider.get_generation_update.call_count, 1)
