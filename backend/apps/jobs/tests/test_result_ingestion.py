import io
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.jobs.models import GenerationJob
from apps.jobs.services import apply_provider_update
from apps.providers.base import ProviderJobUpdate
from apps.studio.models import Asset
from apps.studio.tests.fixtures import StudioFixture


class DownloadBoundaryTests(SimpleTestCase):
    @override_settings(GENERATION_DOWNLOAD_ORIGINS=["https://media.example"])
    def test_signed_output_path_and_query_are_preserved_on_authorized_origin(self):
        from apps.jobs.downloads import authorized_origins, download_image
        payload = b"\x89PNG\r\n\x1a\nfixture"
        headers = {"Content-Type": "image/png", "Content-Length": str(len(payload))}
        response = Mock(status=200)
        response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
        response.read.side_effect = [payload, b""]
        connection = Mock()
        connection.getresponse.return_value = response
        path = "/outputs/project-1/image%20one.png?Expires=1999999999&Signature=abc%2Fdef%3D&Key-Pair-Id=fixture"
        target = io.BytesIO()
        with patch("apps.jobs.downloads.resolve", return_value=["8.8.8.8"]), \
             patch("apps.jobs.downloads.PinnedHTTPSConnection", return_value=connection):
            self.assertEqual(download_image("https://media.example" + path, target), "image/png")
        self.assertEqual(target.getvalue(), payload)
        self.assertEqual(connection.request.call_args.args, ("GET", path))
        self.assertEqual(authorized_origins(), {"media.example"})
        with override_settings(GENERATION_DOWNLOAD_ORIGINS=["https://media.example" + path]):
            self.assertEqual(authorized_origins(), set())

    @override_settings(GENERATION_DOWNLOAD_ORIGINS=["https://media.example"])
    def test_origin_private_dns_and_redirects_are_rejected(self):
        from apps.jobs.downloads import DownloadRejected, download_image

        for url in ("http://media.example/a", "https://media.example.evil/a",
                    "https://user@media.example/a", "https://127.0.0.1/a", "https://media.example:444/a"):
            with self.subTest(url=url), self.assertRaises(DownloadRejected):
                download_image(url, io.BytesIO())
        with patch("apps.jobs.downloads.resolve", return_value=["127.0.0.1"]):
            with self.assertRaises(DownloadRejected):
                download_image("https://media.example/a", io.BytesIO())

    def test_public_address_filter_rejects_transition_metadata_and_mixed_dns(self):
        from apps.jobs.downloads import public_ip
        for address in ("127.0.0.1", "169.254.169.254", "10.0.0.1", "192.168.1.2",
                        "::1", "fe80::1", "fc00::1", "::ffff:8.8.8.8", "2002:0808:0808::1",
                        "0.0.0.0", "224.0.0.1"):
            with self.subTest(address=address):
                self.assertFalse(public_ip(address))
        self.assertTrue(public_ip("8.8.8.8"))

    @override_settings(GENERATION_DOWNLOAD_ORIGINS=["https://media.example"])
    def test_mixed_dns_never_opens_a_connection(self):
        from apps.jobs.downloads import DownloadRejected, download_image
        with patch("apps.jobs.downloads.resolve", return_value=["8.8.8.8", "::1"]), \
             patch("apps.jobs.downloads.PinnedHTTPSConnection") as connect:
            with self.assertRaises(DownloadRejected):
                download_image("https://media.example/a", io.BytesIO())
            connect.assert_not_called()

    def test_pinned_connection_checks_peer_and_preserves_tls_hostname(self):
        import time
        from apps.jobs.downloads import DownloadRejected, PinnedHTTPSConnection
        raw = Mock()
        raw.getpeername.return_value = ("8.8.8.8", 443)
        connection = PinnedHTTPSConnection("media.example", "8.8.8.8", time.monotonic() + 60)
        context = Mock()
        connection._context = context
        with patch("apps.jobs.downloads.socket.socket", return_value=raw):
            connection.connect()
        raw.connect.assert_called_once_with(("8.8.8.8", 443))
        context.wrap_socket.assert_called_once_with(raw, server_hostname="media.example")
        raw.getpeername.return_value = ("127.0.0.1", 443)
        with patch("apps.jobs.downloads.socket.socket", return_value=raw), self.assertRaises(DownloadRejected):
            connection.connect()

    @override_settings(GENERATION_DOWNLOAD_ORIGINS=["https://media.example"])
    def test_empty_truncated_mime_encoding_and_deadline_boundaries(self):
        from apps.jobs.downloads import DownloadRejected, download_image
        for headers, chunks, code in (
            ({}, [b""], "result_invalid_media"),
            ({"Content-Length": "5"}, [b"abc", b""], "result_invalid_media"),
            ({"Content-Length": "-2"}, [], "result_invalid_media"),
            ({"Content-Encoding": "gzip"}, [], "result_download_policy"),
        ):
            response = Mock(status=200)
            response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
            response.read.side_effect = chunks
            connection = Mock()
            connection.getresponse.return_value = response
            with self.subTest(headers=headers), \
                 patch("apps.jobs.downloads.resolve", return_value=["8.8.8.8"]), \
                 patch("apps.jobs.downloads.PinnedHTTPSConnection", return_value=connection):
                with self.assertRaises(DownloadRejected) as caught:
                    download_image("https://media.example/a", io.BytesIO())
                self.assertEqual(caught.exception.code, code)

    @override_settings(GENERATION_DOWNLOAD_ORIGINS=["https://media.example"], STUDIO_MAX_UPLOAD_BYTES=8)
    def test_stream_size_and_redirect_boundaries(self):
        from apps.jobs.downloads import DownloadRejected, download_image

        response = Mock(status=200)
        response.getheader.side_effect = lambda key, default=None: {"Content-Type": "image/png"}.get(key, default)
        response.read.side_effect = [b"012345678", b""]
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("apps.jobs.downloads.resolve", return_value=["8.8.8.8"]), \
             patch("apps.jobs.downloads.PinnedHTTPSConnection", return_value=connection):
            with self.assertRaises(DownloadRejected):
                download_image("https://media.example/a", io.BytesIO())
            response.status = 302
            with self.assertRaises(DownloadRejected):
                download_image("https://media.example/a", io.BytesIO())


class ResultIngestionTests(StudioFixture):
    def setUp(self):
        super().setUp()
        self.directory = Path(settings.BASE_DIR) / ".test-ingestion"
        self.directory.mkdir(exist_ok=True)
        self.override = override_settings(
            MEDIA_ROOT=str(self.directory), GENERATION_STORAGE_CONFIRMED=True,
            GENERATION_DOWNLOAD_ORIGINS=["https://media.example"],
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.directory, ignore_errors=True))
        self.job = GenerationJob.objects.create(
            workspace=self.workspace, requested_by=self.owner, project=self.project,
            provider_name="magic_hour", provider_job_id="remote-1", capability="image.generate",
            status="queued", payload={"prompt": "Daylight"},
        )

    def complete(self):
        apply_provider_update(job_id=self.job.id, external_event_id="completion", status="completed", amount_credits=5)

    def test_completion_without_outputs_schedules_ingestion_and_hides_details(self):
        self.complete()
        self.job.refresh_from_db()
        self.assertEqual(self.job.asset_status, "pending")
        self.assertIsNotNone(self.job.asset_next_attempt_at)

    def test_expired_output_is_refreshed_and_duplicate_tasks_create_one_asset(self):
        from apps.jobs.ingestion import ingest_result

        self.complete()
        provider = Mock()
        provider.get_generation_update.return_value = ProviderJobUpdate(
            status="completed", result={"downloads": [{"url": "https://media.example/fresh.png",
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()}]},
        )
        def download(url, target):
            target.write(b"\x89PNG\r\n\x1a\n" + b"valid-fixture")
            return "image/png"
        with patch("apps.jobs.ingestion.ProviderRegistry.get", return_value=provider), \
             patch("apps.jobs.ingestion.download_image", side_effect=download), \
             patch("apps.jobs.ingestion.validate_image"):
            ingest_result.run(self.job.id)
            ingest_result.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.asset_status, "ready")
        self.assertEqual(Asset.objects.count(), 1)
        self.assertEqual(self.job.generated_asset.workspace_id, self.workspace.id)
        self.assertEqual(self.job.generated_asset.created_by_id, self.owner.id)
        self.assertEqual(provider.get_generation_update.call_count, 1)
        provider.submit_image_generation.assert_not_called()

    def test_storage_failure_retains_completed_job_and_recoverable_schedule(self):
        from apps.jobs.ingestion import ingest_result
        self.complete()
        provider = Mock()
        provider.get_generation_update.side_effect = OSError("private token")
        with patch("apps.jobs.ingestion.ProviderRegistry.get", return_value=provider):
            ingest_result.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.asset_status, "pending")
        self.assertIsNotNone(self.job.asset_next_attempt_at)
        self.assertFalse(Asset.objects.exists())

    def test_renamed_storage_orphan_is_registered_even_after_workspace_deletion(self):
        from django.core.files.storage import default_storage
        from apps.jobs.ingestion import ingest_result, recover_ingestions
        from apps.jobs.models import GeneratedFileCandidate
        self.complete()
        provider = Mock()
        provider.get_generation_update.return_value = ProviderJobUpdate(
            status="completed", result={"downloads": [{"url": "https://media.example/fresh.png",
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()}]},
        )
        renamed = f"workspaces/{self.workspace.id}/assets/backend-renamed.png"
        original_save = default_storage.save
        def rename_and_delete(key, content):
            original_save(renamed, content)
            self.workspace.delete()
            return renamed
        def download(url, target):
            target.write(b"\x89PNG\r\n\x1a\n" + b"fixture")
            return "image/png"
        with patch("apps.jobs.ingestion.ProviderRegistry.get", return_value=provider), \
             patch("apps.jobs.ingestion.download_image", side_effect=download), \
             patch("apps.jobs.ingestion.validate_image"), \
             patch("apps.jobs.ingestion.default_storage.save", side_effect=rename_and_delete), \
             patch("apps.jobs.ingestion.default_storage.delete", side_effect=OSError("offline")):
            ingest_result.run(self.job.id)
        self.assertTrue(GeneratedFileCandidate.objects.filter(storage_key=renamed).exists())
        GeneratedFileCandidate.objects.update(cleanup_after=timezone.now() - timedelta(seconds=1))
        recover_ingestions.run()
        self.assertFalse(default_storage.exists(renamed))
        provider.submit_image_generation.assert_not_called()

    def test_active_lease_and_exhausted_budget_prevent_downloads_and_manual_retry_is_scoped(self):
        from apps.jobs.ingestion import ingest_result
        self.complete()
        GenerationJob.objects.filter(pk=self.job.id).update(
            asset_status="ingesting", asset_lease_until=timezone.now() + timedelta(minutes=2),
        )
        with patch("apps.jobs.ingestion.ProviderRegistry.get") as provider:
            ingest_result.run(self.job.id)
            provider.assert_not_called()
        GenerationJob.objects.filter(pk=self.job.id).update(
            asset_status="pending", asset_attempts=5, asset_next_attempt_at=timezone.now(),
        )
        ingest_result.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.asset_status, "failed")
        self.client.force_login(self.outsider)
        url = f"/api/jobs/{self.job.id}/asset-ingestion/retry/"
        self.assertEqual(self.post(url, {}).status_code, 404)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.post(url, {}).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.post(url, {"url": "https://evil"}).status_code, 400)
        self.assertEqual(self.post(url, {}).status_code, 202)
        self.job.refresh_from_db()
        self.assertEqual(self.job.asset_attempts, 0)
        self.assertEqual(self.job.provider_job_id, "remote-1")
        self.assertIsNone(self.job.provider_submission_started_at)

    def test_invalid_media_fails_asset_only_and_policy_failure_cannot_be_retried(self):
        from apps.jobs.ingestion import ingest_result
        self.complete()
        provider = Mock()
        provider.get_generation_update.return_value = ProviderJobUpdate(
            status="completed", result={"downloads": [{"url": "https://media.example/a",
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()}]},
        )
        def invalid(url, target):
            target.write(b"<html>not media")
            return "image/png"
        with patch("apps.jobs.ingestion.ProviderRegistry.get", return_value=provider), \
             patch("apps.jobs.ingestion.download_image", side_effect=invalid):
            ingest_result.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.asset_error_code, "result_invalid_media")
        self.client.force_login(self.owner)
        self.assertEqual(self.post(f"/api/jobs/{self.job.id}/asset-ingestion/retry/", {}).status_code, 409)
        self.assertFalse(Asset.objects.exists())

    def test_stale_lease_and_expired_provider_url_recover_without_generation(self):
        from apps.jobs.ingestion import recover_ingestions
        self.complete()
        GenerationJob.objects.filter(pk=self.job.id).update(
            asset_status="ingesting", asset_attempt_token="old",
            asset_lease_until=timezone.now() - timedelta(seconds=1),
            asset_next_attempt_at=timezone.now() - timedelta(seconds=1),
            result={"downloads": [{"url": "https://media.example/expired"}]},
        )
        provider = Mock()
        provider.get_generation_update.return_value = ProviderJobUpdate(
            status="completed", result={"downloads": [{"url": "https://media.example/fresh",
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat()}]},
        )
        def download(url, target):
            self.assertEqual(url, "https://media.example/fresh")
            target.write(b"\x89PNG\r\n\x1a\n" + b"fixture")
            return "image/png"
        with patch("apps.jobs.ingestion.ProviderRegistry.get", return_value=provider), \
             patch("apps.jobs.ingestion.download_image", side_effect=download), \
             patch("apps.jobs.ingestion.validate_image"):
            recover_ingestions.run()
        self.job.refresh_from_db()
        self.assertEqual(self.job.asset_status, "ready")
        provider.submit_image_generation.assert_not_called()

    def test_verified_candidate_survives_crash_and_is_reused_without_network(self):
        from apps.jobs.ingestion import ingest_result
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        import hashlib
        self.complete()
        content = b"\x89PNG\r\n\x1a\n" + b"verified-fixture"
        key = f"workspaces/{self.workspace.id}/assets/crashed.png"
        default_storage.save(key, ContentFile(content))
        GenerationJob.objects.filter(pk=self.job.id).update(
            asset_status="ingesting", asset_attempt_token="old",
            asset_lease_until=timezone.now() - timedelta(seconds=1),
            asset_next_attempt_at=timezone.now() - timedelta(seconds=1),
            asset_cleanup_keys=[{"key": key, "token": "old", "sha256": hashlib.sha256(content).hexdigest(),
                                 "size": len(content), "content_type": "image/png"}],
        )
        with patch("apps.jobs.ingestion.ProviderRegistry.get") as provider, \
             patch("apps.jobs.ingestion.validate_image"):
            ingest_result.run(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.asset_status, "ready")
        self.assertEqual(self.job.generated_asset.storage_key, key)
        provider.assert_not_called()

    def test_workspace_deleted_after_storage_write_has_durable_orphan_cleanup(self):
        from apps.jobs.models import GeneratedFileCandidate
        from apps.jobs.ingestion import recover_ingestions
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        key = f"workspaces/{self.workspace.id}/assets/orphan.png"
        default_storage.save(key, ContentFile(b"partial"))
        GeneratedFileCandidate.objects.create(job=self.job, storage_key=key, attempt_token="dead")
        self.workspace.delete()
        recover_ingestions.run()
        self.assertFalse(default_storage.exists(key))
        self.assertFalse(GeneratedFileCandidate.objects.exists())

    def test_decoder_processes_have_allocation_timeout_and_file_only_bounds(self):
        import json
        from apps.jobs.ingestion import validate_image
        path = self.directory / "image"
        path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        def process(command, **options):
            self.assertIn("-max_alloc", command)
            self.assertIn("-protocol_whitelist", command)
            self.assertIn("file", command)
            self.assertLessEqual(options["timeout"], 10)
            self.assertIs(options["shell"], False)
            if "-show_entries" in command:
                options["stdout"].write(json.dumps({"streams": [{
                    "codec_type": "video", "width": 640, "height": 640, "nb_read_frames": "1",
                }]}).encode())
        with patch("apps.jobs.ingestion.subprocess.run", side_effect=process):
            validate_image(path)

    def test_decoder_rejects_animation_and_excessive_dimensions(self):
        import json
        from apps.jobs.downloads import DownloadRejected
        from apps.jobs.ingestion import validate_image
        path = self.directory / "image"
        path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        for width, frames in ((100000, "1"), (640, "2")):
            def process(command, **options):
                if "-show_entries" in command:
                    options["stdout"].write(json.dumps({"streams": [{
                        "codec_type": "video", "width": width, "height": 640, "nb_read_frames": frames,
                    }]}).encode())
            with self.subTest(width=width, frames=frames), \
                 patch("apps.jobs.ingestion.subprocess.run", side_effect=process), self.assertRaises(DownloadRejected):
                validate_image(path)

    def test_operator_recovery_requires_evidence_scope_and_config_and_never_regenerates(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        self.complete()
        GenerationJob.objects.filter(pk=self.job.id).update(asset_status="failed", asset_error_code="result_download_policy")
        for workspace_id, note in ((self.other_workspace.id, "Corrected origin policy"), (self.workspace.id, "")):
            with self.assertRaises(CommandError):
                call_command("recover_generated_asset", self.job.id, workspace_id=workspace_id, note=note)
        with override_settings(GENERATION_DOWNLOAD_ORIGINS=[]), self.assertRaises(CommandError):
            call_command("recover_generated_asset", self.job.id, workspace_id=self.workspace.id, note="Corrected origins")
        with patch("apps.jobs.tasks.submit_provider_job.delay") as paid:
            call_command("recover_generated_asset", self.job.id, workspace_id=self.workspace.id,
                         note="Origin approved after operator verification", stdout=io.StringIO())
            paid.assert_not_called()
        self.job.refresh_from_db()
        self.assertEqual(self.job.asset_status, "pending")
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.provider_job_id, "remote-1")
        self.assertTrue(self.job.submission_resolution["asset_recoveries"])
