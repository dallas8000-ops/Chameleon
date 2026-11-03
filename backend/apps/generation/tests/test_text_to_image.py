from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from apps.generation.models import GenerationJob
from apps.generation.tests.test_generation import Base

Status = GenerationJob.Status


class TextToImageCapabilityTests(Base):
    def create(self, params):
        with patch("apps.generation.views.dispatch"):
            return self.post("/api/generation/jobs/", {"workspace_id": self.workspace.id, "capability": "text_to_image", "params": params})

    def test_valid_settings_become_worker_params(self):
        response = self.create({"prompt": "  a lighthouse at dusk ", "negative_prompt": "blurry", "size": "landscape", "seed": 42})
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json()["label"], "Picture")
        job = GenerationJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.params, {"prompt": "a lighthouse at dusk", "negative_prompt": "blurry", "steps": 30, "width": 1344, "height": 768, "seed": 42})
        self.assertEqual(self.create({"prompt": "x"}).status_code, 202)
        self.assertEqual(GenerationJob.objects.order_by("-id").first().params["width"], 768)

    def test_bad_settings_are_refused(self):
        for params in ({}, {"prompt": ""}, {"prompt": "x" * 2001}, {"prompt": "x", "size": "huge"}, {"prompt": "x", "steps": 9},
                       {"prompt": "x", "seed": -1}, {"prompt": "x", "seed": True}, {"prompt": "x", "width": 4000}):
            with self.subTest(params=params):
                self.assertEqual(self.create(params).status_code, 400)
        self.assertFalse(GenerationJob.objects.exists())

    def test_capability_is_listed(self):
        data = self.client.get(f"/api/generation/capabilities/?workspace_id={self.workspace.id}").json()
        self.assertIn("text_to_image", [c["capability"] for c in data["capabilities"]])


@override_settings(GENERATION_POLL_ON_READ=True)
class PollOnReadTests(Base):
    def read(self, job):
        return self.client.get(f"/api/generation/jobs/{job.id}/").json()

    def test_a_due_status_read_polls_the_provider_and_schedules_the_next_check(self):
        job = self.submitted_job()
        with patch("apps.generation.tasks.runpod.status", return_value={"status": "IN_PROGRESS"}) as status:
            self.assertEqual(self.read(job)["status"], "running")
            status.assert_called_once_with("rp-1")
            # The next check is a few seconds away, so an immediate second read does not hit the provider.
            self.read(job)
            status.assert_called_once()
        job.refresh_from_db()
        self.assertLess(job.next_check_at, timezone.now() + timedelta(seconds=10))

    def test_a_queued_job_whose_submit_failed_is_retried_on_read(self):
        job = self.create_job()
        with patch("apps.generation.tasks.runpod.submit", return_value="rp-7") as submit:
            body = self.read(job)
        submit.assert_called_once()
        self.assertEqual(body["status"], "submitted")

    def test_finished_jobs_and_not_yet_due_jobs_are_left_alone(self):
        done = self.create_job(status=Status.COMPLETED, provider_job_id="rp-2", execution_ms=5)
        waiting = self.submitted_job(next_check_at=timezone.now() + timedelta(minutes=1))
        with patch("apps.generation.tasks.runpod.status") as status, patch("apps.generation.tasks.runpod.submit") as submit:
            self.read(done)
            self.read(waiting)
        status.assert_not_called()
        submit.assert_not_called()

    @override_settings(GENERATION_POLL_ON_READ=False)
    def test_off_by_default(self):
        job = self.submitted_job()
        with patch("apps.generation.tasks.runpod.status") as status:
            self.read(job)
        status.assert_not_called()
