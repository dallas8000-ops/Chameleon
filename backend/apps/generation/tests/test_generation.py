import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.test import override_settings
from django.utils import timezone

from apps.generation import runpod
from apps.generation.models import GenerationJob
from apps.generation.services import upload_token
from apps.generation.tasks import cancel_provider_job, poll_job, recover_generation_jobs, submit_job
from apps.studio.models import Asset
from apps.studio.tests.fixtures import StudioFixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
CONFIGURED = dict(
    RUNPOD_API_KEY="rp-test-key", RUNPOD_ENDPOINT_ID="ep123", GENERATION_PUBLIC_URL="https://chameleon.test",
    RUNPOD_API_BASE="https://api.runpod.test/v2",
)

Status = GenerationJob.Status


class Base(StudioFixture):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        for override in (override_settings(MEDIA_ROOT=self.media, **CONFIGURED),):
            override.enable()
            self.addCleanup(override.disable)
        self.client.force_login(self.editor)

    def create_job(self, **extra):
        return GenerationJob.objects.create(
            workspace=self.workspace, requested_by=self.editor, capability="diagnostic", **extra,
        )

    def submitted_job(self, **extra):
        return self.create_job(status=Status.SUBMITTED, provider_job_id="rp-1", **extra)

    def put_result(self, job, body=PNG, token=None, **headers):
        return self.client.put(
            f"/api/generation/jobs/{job.id}/result/", data=body, content_type="application/octet-stream",
            HTTP_X_UPLOAD_TOKEN=token if token is not None else upload_token(job.id), **headers,
        )


class CapabilitiesAndCreateTests(Base):
    def test_capabilities_report_configuration_honestly(self):
        data = self.client.get(f"/api/generation/capabilities/?workspace_id={self.workspace.id}").json()
        self.assertTrue(data["configured"])
        self.assertEqual(data["capabilities"][0]["capability"], "diagnostic")
        with override_settings(RUNPOD_API_KEY=""):
            data = self.client.get(f"/api/generation/capabilities/?workspace_id={self.workspace.id}").json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["missing"], ["RUNPOD_API_KEY"])
        self.assertFalse(data["capabilities"][0]["available"])

    def test_capabilities_are_hidden_from_non_members(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/api/generation/capabilities/?workspace_id={self.workspace.id}").status_code, 404)
        self.assertEqual(self.client.get("/api/generation/capabilities/").status_code, 404)

    def test_create_queues_a_job_and_dispatches_after_commit(self):
        with patch("apps.generation.views.dispatch") as dispatch, self.captureOnCommitCallbacks(execute=True):
            response = self.post("/api/generation/jobs/", {"workspace_id": self.workspace.id, "capability": "diagnostic"})
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertEqual((body["status"], body["capability"], body["label"]), ("queued", "diagnostic", "GPU check"))
        dispatch.assert_called_once()
        job = GenerationJob.objects.get(pk=body["id"])
        self.assertEqual((job.workspace_id, job.requested_by_id), (self.workspace.id, self.editor.id))

    def test_create_is_refused_when_not_configured(self):
        with override_settings(RUNPOD_ENDPOINT_ID=""):
            response = self.post("/api/generation/jobs/", {"workspace_id": self.workspace.id, "capability": "diagnostic"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "generation_not_configured")
        self.assertIn("RUNPOD_ENDPOINT_ID", response.json()["message"])
        self.assertFalse(GenerationJob.objects.exists())

    def test_validation_and_roles(self):
        url = "/api/generation/jobs/"
        ws = self.workspace.id
        self.assertEqual(self.post(url, {"workspace_id": ws, "capability": "nope"}).status_code, 400)
        self.assertEqual(self.post(url, {"workspace_id": ws, "capability": "diagnostic", "params": {"x": 1}}).status_code, 400)
        self.assertEqual(self.post(url, {"workspace_id": ws, "capability": "diagnostic", "params": []}).status_code, 400)
        self.assertEqual(self.post(url, {"workspace_id": ws}).status_code, 400)
        self.assertEqual(self.post(url, {"workspace_id": ws, "capability": "diagnostic", "project_id": 9999}).status_code, 400)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.post(url, {"workspace_id": ws, "capability": "diagnostic"}).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.post(url, {"workspace_id": ws, "capability": "diagnostic"}).status_code, 404)
        self.client.logout()
        self.assertIn(self.post(url, {"workspace_id": ws, "capability": "diagnostic"}).status_code, (401, 403))
        self.assertFalse(GenerationJob.objects.exists())

    def test_active_job_cap_protects_credits(self):
        with override_settings(GENERATION_MAX_ACTIVE_JOBS=2), patch("apps.generation.views.dispatch"):
            statuses = [
                self.post("/api/generation/jobs/", {"workspace_id": self.workspace.id, "capability": "diagnostic"}).status_code
                for _ in range(3)
            ]
        self.assertEqual(statuses, [202, 202, 429])
        GenerationJob.objects.update(status=Status.COMPLETED)
        with override_settings(GENERATION_MAX_ACTIVE_JOBS=2), patch("apps.generation.views.dispatch"):
            self.assertEqual(self.post("/api/generation/jobs/", {"workspace_id": self.workspace.id, "capability": "diagnostic"}).status_code, 202)

    def test_list_detail_and_isolation(self):
        job = self.create_job()
        other = GenerationJob.objects.create(workspace=self.other_workspace, capability="diagnostic")
        listed = self.client.get(f"/api/generation/jobs/?workspace_id={self.workspace.id}").json()
        self.assertEqual([item["id"] for item in listed], [job.id])
        self.assertEqual(self.client.get(f"/api/generation/jobs/{job.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/generation/jobs/{other.id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/generation/jobs/?workspace_id=abc").status_code, 400)
        self.assertNotIn("rp-test-key", self.client.get(f"/api/generation/jobs/{job.id}/").content.decode())

    def test_cancel_stops_an_active_job_and_asks_the_provider(self):
        job = self.submitted_job()
        with patch("apps.generation.views.cancel_provider_job") as cancel, self.captureOnCommitCallbacks(execute=True):
            response = self.post(f"/api/generation/jobs/{job.id}/cancel/", {})
        self.assertEqual((response.status_code, response.json()["status"]), (200, "canceled"))
        cancel.delay.assert_called_once_with("rp-1")
        self.client.force_login(self.reviewer)
        self.assertEqual(self.post(f"/api/generation/jobs/{job.id}/cancel/", {}).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.post(f"/api/generation/jobs/{job.id}/cancel/", {}).status_code, 404)

    def test_cancel_does_not_touch_a_finished_job(self):
        job = self.create_job(status=Status.COMPLETED)
        with patch("apps.generation.views.cancel_provider_job") as cancel:
            response = self.post(f"/api/generation/jobs/{job.id}/cancel/", {})
        self.assertEqual(response.json()["status"], "completed")
        cancel.delay.assert_not_called()


class SubmitTaskTests(Base):
    def test_a_result_that_arrives_before_the_job_id_is_recorded_is_kept(self):
        job = self.create_job()

        def worker_finishes_first(payload, **kwargs):
            from django.test import Client

            response = Client().put(
                f"/api/generation/jobs/{job.id}/result/", data=PNG, content_type="application/octet-stream",
                HTTP_X_UPLOAD_TOKEN=payload["upload"]["token"],
            )
            assert response.status_code == 201, response.content
            return "rp-fast"

        with patch("apps.generation.tasks.runpod.submit", side_effect=worker_finishes_first), patch("apps.generation.tasks.cancel_provider_job") as cancel, patch("apps.generation.tasks.schedule_poll") as poll:
            submit_job(job.id)
        cancel.delay.assert_not_called()
        poll.assert_called_once()
        job.refresh_from_db()
        self.assertEqual((job.status, job.provider_job_id), (Status.COMPLETED, "rp-fast"))
        self.assertIsNotNone(job.result_asset_id)

    def test_a_queued_job_with_no_submit_in_flight_refuses_results(self):
        job = self.create_job()
        self.assertEqual(self.put_result(job).status_code, 409)
        GenerationJob.objects.filter(pk=job.pk).update(submit_attempts=1)
        self.assertEqual(self.put_result(job).status_code, 201)

    def test_submit_sends_a_signed_upload_target_and_limits(self):
        job = self.create_job()
        with patch("apps.generation.tasks.runpod.submit", return_value="rp-99") as submit, patch("apps.generation.tasks.schedule_poll") as poll:
            submit_job(job.id)
        job.refresh_from_db()
        self.assertEqual((job.status, job.provider_job_id, job.submit_attempts), (Status.SUBMITTED, "rp-99", 1))
        payload = submit.call_args.args[0]
        self.assertEqual((payload["capability"], payload["job_id"], payload["params"]), ("diagnostic", job.id, {}))
        self.assertEqual(payload["upload"]["url"], f"https://chameleon.test/api/generation/jobs/{job.id}/result/")
        self.assertEqual(payload["upload"]["token"].count(":"), 2)
        self.assertNotIn("rp-test-key", str(payload))
        self.assertEqual(submit.call_args.kwargs["execution_timeout_seconds"], 120)
        poll.assert_called_once()

    def test_submit_is_idempotent_once_a_provider_job_exists(self):
        job = self.submitted_job()
        with patch("apps.generation.tasks.runpod.submit") as submit:
            submit_job(job.id)
        submit.assert_not_called()

    def test_retryable_provider_error_keeps_the_job_queued_for_the_sweeper(self):
        job = self.create_job()
        with patch("apps.generation.tasks.runpod.submit", side_effect=runpod.RunPodError("provider_busy", "busy", retryable=True)):
            submit_job(job.id)
        job.refresh_from_db()
        self.assertEqual((job.status, job.submit_attempts), (Status.QUEUED, 1))
        self.assertGreater(job.next_check_at, timezone.now())

    def test_fatal_provider_error_fails_the_job_with_a_clear_message(self):
        job = self.create_job()
        with patch("apps.generation.tasks.runpod.submit", side_effect=runpod.RunPodError("provider_auth_failed", "The GPU service rejected the API key.")):
            submit_job(job.id)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), (Status.FAILED, "provider_auth_failed"))

    def test_attempts_are_bounded(self):
        job = self.create_job(submit_attempts=3)
        with patch("apps.generation.tasks.runpod.submit") as submit:
            submit_job(job.id)
        submit.assert_not_called()
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), (Status.FAILED, "submit_failed"))

    def test_a_job_canceled_during_submit_is_canceled_at_the_provider(self):
        job = self.create_job()

        def cancel_then_return(*args, **kwargs):
            GenerationJob.objects.filter(pk=job.pk).update(status=Status.CANCELED)
            return "rp-late"

        with patch("apps.generation.tasks.runpod.submit", side_effect=cancel_then_return), patch("apps.generation.tasks.cancel_provider_job") as cancel:
            submit_job(job.id)
        cancel.delay.assert_called_once_with("rp-late")
        job.refresh_from_db()
        self.assertEqual((job.status, job.provider_job_id), (Status.CANCELED, ""))


class PollTaskTests(Base):
    def poll(self, job, data):
        with patch("apps.generation.tasks.runpod.status", return_value=data), patch("apps.generation.tasks.schedule_poll") as again:
            poll_job(job.id)
        job.refresh_from_db()
        return again

    def test_queue_and_progress_states_reschedule(self):
        job = self.submitted_job()
        again = self.poll(job, {"status": "IN_QUEUE"})
        self.assertEqual(job.status, Status.SUBMITTED)
        again.assert_called_once()
        again = self.poll(job, {"status": "IN_PROGRESS"})
        self.assertEqual(job.status, Status.RUNNING)
        again.assert_called_once()

    def test_failed_and_timed_out_report_the_worker_message(self):
        job = self.submitted_job()
        self.poll(job, {"status": "FAILED", "output": {"error": "CUDA out of memory"}, "executionTime": 1500, "delayTime": 900})
        self.assertEqual((job.status, job.error_code, job.error_message), (Status.FAILED, "worker_error", "CUDA out of memory"))
        self.assertEqual((job.execution_ms, job.delay_ms), (1500, 900))
        timed_out = self.submitted_job()
        self.poll(timed_out, {"status": "TIMED_OUT"})
        self.assertEqual(timed_out.error_code, "provider_timeout")

    def test_completed_without_a_received_result_is_an_honest_failure(self):
        job = self.submitted_job()
        self.poll(job, {"status": "COMPLETED", "output": {"result": {"gpu": "x"}}, "executionTime": 800})
        self.assertEqual((job.status, job.error_code), (Status.FAILED, "result_missing"))
        self.assertEqual(job.result, {"gpu": "x"})

    def test_completed_after_upload_records_timings_and_result(self):
        job = self.submitted_job()
        self.assertEqual(self.put_result(job).status_code, 201)
        again = self.poll(job, {"status": "COMPLETED", "output": {"result": {"gpu": "RTX 4090", "vram_mb": 24000}}, "executionTime": 2100, "delayTime": 5000})
        self.assertEqual(job.status, Status.COMPLETED)
        self.assertEqual((job.execution_ms, job.delay_ms), (2100, 5000))
        self.assertEqual(job.result["gpu"], "RTX 4090")
        again.assert_not_called()

    def test_oversized_worker_result_is_dropped(self):
        job = self.submitted_job()
        self.put_result(job)
        self.poll(job, {"status": "COMPLETED", "output": {"result": {"blob": "x" * 5000}}, "executionTime": 10})
        self.assertEqual(job.result, {})

    def test_worker_error_inside_a_completed_response_fails_the_job(self):
        job = self.submitted_job()
        self.poll(job, {"status": "COMPLETED", "output": {"error": "model missing"}})
        self.assertEqual((job.status, job.error_message), (Status.FAILED, "model missing"))

    def test_provider_cancel_and_unknown_state(self):
        job = self.submitted_job()
        self.poll(job, {"status": "CANCELLED"})
        self.assertEqual(job.status, Status.CANCELED)
        unknown = self.submitted_job()
        again = self.poll(unknown, {"status": "WHO_KNOWS"})
        self.assertEqual((unknown.status, unknown.poll_failures), (Status.SUBMITTED, 1))
        again.assert_called_once()

    def test_unreachable_provider_is_retried_then_gives_up(self):
        job = self.submitted_job()
        error = runpod.RunPodError("provider_unreachable", "down", retryable=True)
        for _ in range(7):
            with patch("apps.generation.tasks.runpod.status", side_effect=error), patch("apps.generation.tasks.schedule_poll"):
                poll_job(job.id)
        job.refresh_from_db()
        self.assertEqual((job.status, job.poll_failures), (Status.SUBMITTED, 7))
        with patch("apps.generation.tasks.runpod.status", side_effect=error), patch("apps.generation.tasks.schedule_poll"):
            poll_job(job.id)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), (Status.FAILED, "provider_unreachable"))

    def test_job_past_its_deadline_is_stopped_and_canceled_at_the_provider(self):
        job = self.submitted_job()
        GenerationJob.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(hours=2))
        with patch("apps.generation.tasks.runpod.status") as status, patch("apps.generation.tasks.cancel_provider_job") as cancel:
            poll_job(job.id)
        status.assert_not_called()
        cancel.delay.assert_called_once_with("rp-1")
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), (Status.FAILED, "job_timeout"))

    def test_finished_jobs_are_never_overwritten(self):
        job = self.create_job(status=Status.CANCELED, provider_job_id="rp-1", execution_ms=0)
        with patch("apps.generation.tasks.runpod.status") as status:
            poll_job(job.id)
        status.assert_not_called()


class SweeperTests(Base):
    def test_lost_dispatches_are_recovered_once(self):
        stale_queued = self.create_job()
        waiting = self.submitted_job(next_check_at=timezone.now() - timedelta(seconds=5))
        fresh = self.submitted_job(next_check_at=timezone.now() + timedelta(minutes=5))
        reserved = self.create_job(next_check_at=timezone.now() + timedelta(minutes=1))
        with patch("apps.generation.tasks.dispatch") as dispatch, self.captureOnCommitCallbacks(execute=True):
            count = recover_generation_jobs()
        self.assertEqual(count, 2)
        sent = {call.args[1] for call in dispatch.call_args_list}
        self.assertEqual(sent, {stale_queued.id, waiting.id})
        self.assertNotIn(fresh.id, sent)
        self.assertNotIn(reserved.id, sent)
        with patch("apps.generation.tasks.dispatch") as dispatch, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(recover_generation_jobs(), 1)
        self.assertEqual({call.args[1] for call in dispatch.call_args_list}, {stale_queued.id})


class ResultUploadTests(Base):
    def test_valid_upload_stores_a_private_generated_asset_and_completes_the_job(self):
        self.client.logout()
        job = self.submitted_job()
        response = self.put_result(job)
        self.assertEqual(response.status_code, 201, response.content)
        job.refresh_from_db()
        asset = Asset.objects.get(pk=job.result_asset_id)
        self.assertEqual(job.status, Status.COMPLETED)
        self.assertEqual((asset.workspace_id, asset.asset_type, asset.content_type), (self.workspace.id, "image", "image/png"))
        self.assertEqual(asset.provenance, {"source": "generation", "job_id": job.id, "capability": "diagnostic"})
        self.assertTrue(asset.storage_key.startswith(f"workspaces/{self.workspace.id}/assets/"))
        with default_storage.open(asset.storage_key, "rb") as stored:
            self.assertEqual(stored.read(), PNG)

    def test_generated_asset_is_listed_as_generated_and_served_to_members_only(self):
        job = self.submitted_job()
        self.put_result(job)
        asset_id = GenerationJob.objects.get(pk=job.pk).result_asset_id
        self.assertEqual(self.client.get(f"/api/assets/{asset_id}/").json()["source"], "generation")
        content = self.client.get(f"/api/assets/{asset_id}/content/")
        self.addCleanup(content.close)
        self.assertEqual(content.status_code, 200)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/api/assets/{asset_id}/content/").status_code, 404)

    def test_tokens_are_checked(self):
        job = self.submitted_job()
        other = self.submitted_job()
        self.assertEqual(self.put_result(job, token="").status_code, 403)
        self.assertEqual(self.put_result(job, token="garbage").status_code, 403)
        self.assertEqual(self.put_result(job, token=upload_token(other.id)).status_code, 403)
        with override_settings(GENERATION_JOB_TTL_SECONDS=-700):
            self.assertEqual(self.put_result(job).status_code, 403)
        self.assertFalse(Asset.objects.exists())

    def test_upload_is_single_use_and_only_while_waiting(self):
        job = self.submitted_job()
        self.assertEqual(self.put_result(job).status_code, 201)
        self.assertEqual(self.put_result(job).status_code, 409)
        for status in (Status.QUEUED, Status.CANCELED, Status.FAILED):
            blocked = self.create_job(status=status)
            self.assertEqual(self.put_result(blocked).status_code, 409, status)
        self.assertEqual(Asset.objects.count(), 1)

    def test_bad_files_are_rejected_without_leaving_anything_behind(self):
        job = self.submitted_job()
        self.assertEqual(self.put_result(job, body=b"<script>alert(1)</script>").status_code, 415)
        self.assertEqual(self.put_result(job, body=b"RIFF\x00\x00\x00\x00WAVEfmt ").status_code, 415)
        self.assertIn(self.put_result(job, body=b"").status_code, (400, 411))
        with override_settings(GENERATION_MAX_RESULT_BYTES=10):
            self.assertEqual(self.put_result(job).status_code, 413)
        job.refresh_from_db()
        self.assertEqual((job.status, job.result_asset_id), (Status.SUBMITTED, None))
        self.assertFalse(Asset.objects.exists())

    def test_only_put_is_allowed_and_no_session_or_csrf_is_needed(self):
        job = self.submitted_job()
        self.assertEqual(self.client.get(f"/api/generation/jobs/{job.id}/result/").status_code, 405)
        self.assertEqual(self.client.post(f"/api/generation/jobs/{job.id}/result/", data=PNG, content_type="image/png").status_code, 405)
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        response = strict.put(
            f"/api/generation/jobs/{job.id}/result/", data=PNG, content_type="application/octet-stream",
            HTTP_X_UPLOAD_TOKEN=upload_token(job.id),
        )
        self.assertEqual(response.status_code, 201, response.content)


class RunPodClientTests(Base):
    class Reply:
        def __init__(self, status=200, body=None, bad_json=False):
            self.status_code, self._body, self._bad = status, body if body is not None else {}, bad_json

        def json(self):
            if self._bad:
                raise ValueError("no json")
            return self._body

    def call(self, reply, fn=lambda: runpod.submit({"capability": "diagnostic"}, execution_timeout_seconds=60, ttl_seconds=600)):
        with patch("apps.generation.runpod.requests.request", return_value=reply) as request:
            return fn(), request

    def test_submit_builds_the_documented_request(self):
        job_id, request = self.call(self.Reply(200, {"id": "abc", "status": "IN_QUEUE"}))
        self.assertEqual(job_id, "abc")
        args, kwargs = request.call_args
        self.assertEqual(args, ("POST", "https://api.runpod.test/v2/ep123/run"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer rp-test-key")
        self.assertEqual(kwargs["json"]["policy"], {"executionTimeout": 60000, "ttl": 600000})
        self.assertEqual(kwargs["json"]["input"], {"capability": "diagnostic"})
        self.assertGreater(kwargs["timeout"], 0)

    def test_error_codes_map_to_clear_failures(self):
        cases = {401: ("provider_auth_failed", False), 404: ("provider_endpoint_missing", False), 429: ("provider_busy", True),
                 503: ("provider_busy", True), 400: ("provider_rejected", False)}
        for status, (code, retryable) in cases.items():
            with self.subTest(status=status), self.assertRaises(runpod.RunPodError) as caught:
                self.call(self.Reply(status))
            self.assertEqual((caught.exception.code, caught.exception.retryable), (code, retryable))
        for reply in (self.Reply(200, bad_json=True), self.Reply(200, [1]), self.Reply(200, {"id": ""})):
            with self.subTest(reply=reply._body), self.assertRaises(runpod.RunPodError) as caught:
                self.call(reply)
            self.assertEqual(caught.exception.code, "provider_response_invalid")

    def test_network_errors_are_retryable_and_never_leak_the_key(self):
        import requests

        with patch("apps.generation.runpod.requests.request", side_effect=requests.ConnectionError("boom rp-test-key")), self.assertRaises(runpod.RunPodError) as caught:
            runpod.status("abc")
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn("rp-test-key", caught.exception.message)

    def test_unconfigured_client_refuses_to_call_out(self):
        with override_settings(RUNPOD_API_KEY=""), patch("apps.generation.runpod.requests.request") as request, self.assertRaises(runpod.RunPodError) as caught:
            runpod.status("abc")
        request.assert_not_called()
        self.assertEqual(caught.exception.code, "generation_not_configured")


class CeleryRegistrationTests(Base):
    def test_tasks_are_registered_and_scheduled(self):
        from django.conf import settings

        from chameleon.celery import app

        app.loader.import_default_modules()
        for name in ("apps.generation.tasks.submit_job", "apps.generation.tasks.poll_job", "apps.generation.tasks.recover_generation_jobs"):
            self.assertIn(name, app.tasks)
        self.assertIn("recover-generation-jobs", settings.CELERY_BEAT_SCHEDULE)
