"""Runs the real worker code against a real running Django server; only RunPod's own API is faked."""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.test import LiveServerTestCase, override_settings

from apps.accounts.models import Workspace, WorkspaceMembership
from apps.generation.models import GenerationJob
from apps.generation.tasks import poll_job, submit_job

WORKER_DIR = Path(__file__).resolve().parents[4] / "worker"


class RoundTripTests(LiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(WORKER_DIR))
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        sys.path.remove(str(WORKER_DIR))

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(
            MEDIA_ROOT=self.media, RUNPOD_API_KEY="rp-test-key", RUNPOD_ENDPOINT_ID="ep123",
            GENERATION_PUBLIC_URL=self.live_server_url,
        )
        override.enable()
        self.addCleanup(override.disable)
        env = patch.dict(os.environ, {"WORKER_ALLOW_INSECURE_UPLOAD": "1"})
        env.start()
        self.addCleanup(env.stop)
        User = get_user_model()
        self.user = User.objects.create_user(email="editor@example.com", password="Zq7!pleasant-Harbor-42")
        self.workspace = Workspace.objects.create(name="Studio")
        WorkspaceMembership.objects.create(user=self.user, workspace=self.workspace, role=WorkspaceMembership.Role.EDITOR)
        self.client.force_login(self.user)

    def test_diagnostic_job_goes_from_the_api_through_the_worker_and_back(self):
        from chameleon_worker.router import handle

        with patch("apps.generation.views.dispatch"):
            response = self.client.post(
                "/api/generation/jobs/", data={"workspace_id": self.workspace.id, "capability": "diagnostic"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 202, response.content)
        job = GenerationJob.objects.get(pk=response.json()["id"])

        outputs = {}

        def fake_runpod_run(payload, **kwargs):
            with patch("chameleon_worker.diagnostic.gpu_info", return_value=[{"name": "RTX 4090", "memory_mb": 24564, "memory_used_mb": 0, "driver": "550"}]):
                outputs["output"] = handle({"input": payload})
            return "rp-int-1"

        with patch("apps.generation.tasks.runpod.submit", side_effect=fake_runpod_run), patch("apps.generation.tasks.schedule_poll"):
            submit_job(job.id)
        self.assertNotIn("error", outputs["output"], outputs["output"])

        job.refresh_from_db()
        self.assertEqual(job.status, GenerationJob.Status.COMPLETED)
        self.assertIsNotNone(job.result_asset_id)

        reply = {"status": "COMPLETED", "output": outputs["output"], "executionTime": 1800, "delayTime": 4200}
        with patch("apps.generation.tasks.runpod.status", return_value=reply):
            poll_job(job.id)
        job.refresh_from_db()
        self.assertEqual((job.execution_ms, job.delay_ms), (1800, 4200))
        self.assertEqual(job.result["gpus"][0]["name"], "RTX 4090")

        asset = job.result_asset
        with default_storage.open(asset.storage_key, "rb") as stored:
            self.assertTrue(stored.read().startswith(b"\x89PNG"))
        content = self.client.get(f"/api/assets/{asset.id}/content/")
        self.addCleanup(content.close)
        self.assertEqual((content.status_code, content["Content-Type"]), (200, "image/png"))
        self.assertEqual(self.client.get(f"/api/assets/{asset.id}/").json()["source"], "generation")
        detail = self.client.get(f"/api/generation/jobs/{job.id}/").json()
        self.assertEqual((detail["status"], detail["result_asset_id"]), ("completed", asset.id))
