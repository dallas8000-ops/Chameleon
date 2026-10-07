from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Workspace, WorkspaceMembership
from apps.jobs.models import GenerationJob, UsageLedgerEntry
from apps.jobs.services import UnsupportedCapability, submit_generation_job
from apps.jobs.tasks import poll_provider_job, submit_provider_job
from apps.providers.base import ProviderJobUpdate, ProviderSubmission
from apps.studio.models import Asset, Project, Scene


class JobSubmissionTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(email="job@example.com", password="password")
        self.reviewer = get_user_model().objects.create_user(email="reviewer@example.com", password="password")
        self.workspace = Workspace.objects.create(name="Studio")
        WorkspaceMembership.objects.create(user=self.owner, workspace=self.workspace, role="owner")
        WorkspaceMembership.objects.create(user=self.reviewer, workspace=self.workspace, role="reviewer")
        self.project = Project.objects.create(workspace=self.workspace, title="Launch Reel", format="9:16")
        self.scene = Scene.objects.create(
            project=self.project, order_index=0, kind="presenter", title="Intro", script_text="Hello"
        )

    def post(self, url, data):
        return self.client.post(url, data=data, content_type="application/json")

    @override_settings(MAGIC_HOUR_API_KEY="")
    def test_image_generation_without_provider_key_persists_blocked_job(self):
        self.client.force_login(self.owner)
        snapshot = {
            "workspace_id": self.workspace.id,
            "project_id": self.project.id,
            "prompt": "Studio background",
        }
        with patch("apps.jobs.tasks.submit_provider_job.delay") as submit:
            response = self.post("/api/jobs/image-generation/", snapshot)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "provider_not_configured")
        self.assertEqual(response.json()["status"], "blocked_provider_not_configured")
        submit.assert_not_called()
        job = GenerationJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.status, GenerationJob.Status.BLOCKED_PROVIDER_NOT_CONFIGURED)
        self.assertEqual(job.payload, {**snapshot, "aspect_ratio": "1:1"})
        self.assertEqual(job.error_code, "provider_not_configured")

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_configured_provider_job_is_persisted_before_task_dispatch(self):
        self.client.force_login(self.owner)
        payload = {"workspace_id": self.workspace.id, "prompt": "Soft daylight studio"}

        def assert_job_exists(job_id):
            job = GenerationJob.objects.get(pk=job_id)
            self.assertEqual(job.status, GenerationJob.Status.PENDING_PROVIDER)
            self.assertEqual(job.payload, {**payload, "aspect_ratio": "1:1"})

        with patch("apps.jobs.tasks.submit_provider_job.delay", side_effect=assert_job_exists) as submit:
            response = self.post("/api/jobs/image-generation/", payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "pending_provider")
        submit.assert_called_once_with(response.json()["id"])

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_presenter_submission_requires_supported_asset_inputs(self):
        self.client.force_login(self.owner)
        response = self.post(
            "/api/jobs/presenter-generation/",
            {
                "workspace_id": self.workspace.id,
                "project_id": self.project.id,
                "scene_id": self.scene.id,
                "script_text": "Hello",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertTrue(response.json()["errors"])
        self.assertEqual(GenerationJob.objects.count(), 0)

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_worker_queue_failure_is_a_persisted_structured_error(self):
        self.client.force_login(self.owner)
        with patch("apps.jobs.tasks.submit_provider_job.delay", side_effect=RuntimeError("broker offline")):
            response = self.post(
                "/api/jobs/image-generation/",
                {"workspace_id": self.workspace.id, "prompt": "Studio background"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "job_queue_unavailable")
        job = GenerationJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.status, GenerationJob.Status.FAILED)
        self.assertEqual(job.error_code, "job_queue_unavailable")

    def test_unsupported_provider_capability_is_rejected_before_job_creation(self):
        provider = Mock()
        provider.supports_capability.return_value = False
        with patch("apps.jobs.services.ProviderRegistry.get", return_value=provider):
            with self.assertRaises(UnsupportedCapability):
                submit_generation_job(
                    workspace_id=self.workspace.id,
                    project_id=None,
                    scene_id=None,
                    capability="video.export",
                    payload={},
                )
        self.assertEqual(GenerationJob.objects.count(), 0)

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_polling_task_completes_job_and_records_usage_once(self):
        job = GenerationJob.objects.create(
            workspace=self.workspace,
            capability="image.generate",
            status=GenerationJob.Status.QUEUED,
            payload={"prompt": "Studio background"},
            provider_name="magic_hour",
            provider_job_id="remote-image-complete",
        )
        provider = Mock()
        provider.is_configured.return_value = True
        provider.get_generation_update.return_value = ProviderJobUpdate(
            status=GenerationJob.Status.COMPLETED,
            result={"downloads": [{"url": "https://videos.magichour.ai/ready.png"}]},
            amount_credits=5,
            external_event_id="poll:remote-image-complete:complete",
        )
        with patch("apps.jobs.tasks.ProviderRegistry.get", return_value=provider):
            poll_provider_job.run(job.id)
            poll_provider_job.run(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(job.result["downloads"][0]["url"], "https://videos.magichour.ai/ready.png")
        self.assertEqual(UsageLedgerEntry.objects.filter(job=job).count(), 1)

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_presenter_rejects_arbitrary_provider_paths(self):
        self.client.force_login(self.owner)
        payload = {
            "workspace_id": self.workspace.id,
            "project_id": self.project.id,
            "scene_id": self.scene.id,
            "image_file_path": "api-assets/portrait.png",
            "audio_file_path": "api-assets/script.mp3",
            "start_seconds": 0,
            "end_seconds": 8.5,
        }
        with patch("apps.jobs.tasks.submit_provider_job.delay") as submit:
            response = self.post("/api/jobs/presenter-generation/", payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(GenerationJob.objects.count(), 0)
        submit.assert_not_called()

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_presenter_paths_are_rejected_even_with_owned_asset_ids(self):
        self.client.force_login(self.owner)
        image = self.asset()
        audio = self.asset(asset_type="audio", content_type="audio/mpeg")
        with patch("apps.jobs.tasks.submit_provider_job.delay") as submit:
            for path in ("api-assets/other-tenant.png", "https://foreign.example/person.png", "C:\\private\\face.png"):
                response = self.post("/api/jobs/presenter-generation/", {
                    "workspace_id": self.workspace.id, "image_asset_id": image.id, "audio_asset_id": audio.id,
                    "image_file_path": path, "start_seconds": 0, "end_seconds": 5,
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn("image_file_path", response.json()["errors"])
        submit.assert_not_called()
        self.assertEqual(GenerationJob.objects.count(), 0)

    def test_legacy_presenter_input_paths_are_not_exposed_on_job_reads(self):
        job = GenerationJob.objects.create(
            workspace=self.workspace, capability="presenter.generate",
            payload={
                "image_file_path": "api-assets/foreign.png",
                "audio_file_path": "https://foreign.example/voice.mp3",
                "script_text": "Hello",
            },
        )
        self.client.force_login(self.owner)
        response = self.client.get(f"/api/jobs/{job.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payload"], {"script_text": "Hello"})

    def asset(self, workspace=None, asset_type="image", content_type="image/png"):
        return Asset.objects.create(
            workspace=workspace or self.workspace,
            asset_type=asset_type,
            content_type=content_type,
            name="Input",
            storage_key=f"private/{Asset.objects.count() + 1}",
            size_bytes=100,
        )

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_presenter_asset_ids_are_workspace_scoped(self):
        self.client.force_login(self.owner)
        other = Workspace.objects.create(name="Other")
        image = self.asset()
        foreign = self.asset(workspace=other)
        base = {
            "workspace_id": self.workspace.id, "image_asset_id": image.id,
            "audio_asset_id": foreign.id, "start_seconds": 0, "end_seconds": 5,
        }
        with patch("apps.jobs.tasks.submit_provider_job.delay") as submit:
            hidden = self.post("/api/jobs/presenter-generation/", base)
            missing = self.post("/api/jobs/presenter-generation/", {**base, "audio_asset_id": 999999})
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json(), missing.json())
        submit.assert_not_called()

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_presenter_rejects_wrong_media_types(self):
        self.client.force_login(self.owner)
        video = self.asset(asset_type="video", content_type="video/mp4")
        image = self.asset()
        with patch("apps.jobs.tasks.submit_provider_job.delay") as submit:
            for image_id, audio_id in ((video.id, image.id), (image.id, video.id)):
                response = self.post("/api/jobs/presenter-generation/", {
                    "workspace_id": self.workspace.id, "image_asset_id": image_id,
                    "audio_asset_id": audio_id, "start_seconds": 0, "end_seconds": 5,
                })
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "validation_error")
        submit.assert_not_called()

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_presenter_owned_assets_are_blocked_without_secure_provider_bridge(self):
        self.client.force_login(self.owner)
        image = self.asset()
        # A future audio ingestion flow still must not bypass the missing provider bridge.
        audio = self.asset(asset_type="audio", content_type="audio/mpeg")
        with patch("apps.jobs.tasks.submit_provider_job.delay") as submit:
            response = self.post("/api/jobs/presenter-generation/", {
                "workspace_id": self.workspace.id, "image_asset_id": image.id,
                "audio_asset_id": audio.id, "start_seconds": 0, "end_seconds": 5,
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "capability_unavailable")
        self.assertEqual(GenerationJob.objects.count(), 0)
        submit.assert_not_called()

    def test_reviewer_cannot_submit_and_foreign_job_is_not_found(self):
        self.client.force_login(self.reviewer)
        response = self.post(
            "/api/jobs/image-generation/",
            {"workspace_id": self.workspace.id, "prompt": "Background"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "workspace_read_only")

        outsider = get_user_model().objects.create_user(email="outsider@example.com", password="password")
        foreign_workspace = Workspace.objects.create(name="Private")
        WorkspaceMembership.objects.create(user=outsider, workspace=foreign_workspace, role="owner")
        foreign_job = GenerationJob.objects.create(
            workspace=foreign_workspace,
            capability="image.generate",
            status=GenerationJob.Status.QUEUED,
            payload={},
        )
        self.client.force_login(self.owner)
        hidden = self.client.get(f"/api/jobs/{foreign_job.id}/")
        missing = self.client.get("/api/jobs/999999/")
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json(), missing.json())

    @override_settings(MAGIC_HOUR_API_KEY="configured-test-key")
    def test_submission_task_stores_provider_job_id_without_marking_generation_complete(self):
        payload = {
            "workspace_id": self.workspace.id,
            "prompt": "Studio background",
            "aspect_ratio": "16:9",
        }
        job = GenerationJob.objects.create(
            workspace=self.workspace,
            project=self.project,
            capability="image.generate",
            status=GenerationJob.Status.PENDING_PROVIDER,
            payload=payload,
            provider_name="magic_hour",
        )
        provider = Mock()
        provider.is_configured.return_value = True
        provider.submit_image_generation.return_value = ProviderSubmission(
            "remote-image-1", 5, {"id": "remote-image-1"}
        )
        with (
            patch("apps.jobs.tasks.ProviderRegistry.get", return_value=provider),
            patch("apps.jobs.tasks.poll_provider_job.delay") as poll,
        ):
            submit_provider_job.run(job.id)
            submit_provider_job.run(job.id)

        provider.submit_image_generation.assert_called_once_with(
            prompt="Studio background",
            aspect_ratio="16:9",
            name="",
        )
        job.refresh_from_db()
        self.assertEqual(job.status, GenerationJob.Status.QUEUED)
        self.assertEqual(job.provider_job_id, "remote-image-1")
        self.assertEqual(job.quoted_credits, 5)
        self.assertEqual(job.result, {})
        self.assertIsNotNone(job.provider_submission_started_at)
        poll.assert_called_once_with(job.id)
