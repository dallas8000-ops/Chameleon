import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from chameleon_worker import diagnostic
from chameleon_worker.png import gradient_png
from chameleon_worker.router import handle
from chameleon_worker.upload import UploadError, check_target, upload_result

TOKEN = "abc:def:ghi"


class FakeBackend:
    """Stands in for the Chameleon upload endpoint."""

    def __init__(self, statuses=(201,)):
        self.statuses = list(statuses)
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_PUT(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                owner.requests.append({"path": self.path, "token": self.headers.get("X-Upload-Token"), "type": self.headers.get("Content-Type"), "body": body})
                status = owner.statuses.pop(0) if len(owner.statuses) > 1 else owner.statuses[0]
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": status < 300}).encode())

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def url(self, job_id=7):
        return f"http://127.0.0.1:{self.server.server_port}/api/generation/jobs/{job_id}/result/"


class PngTests(unittest.TestCase):
    def test_gradient_is_a_valid_png(self):
        png = gradient_png(16, 8)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(png.endswith(b"IEND\xaeB`\x82"))


class UploadTargetTests(unittest.TestCase):
    def test_https_target_matching_the_job_is_accepted(self):
        url, token = check_target({"url": "https://app.example/api/generation/jobs/7/result/", "token": TOKEN}, 7)
        self.assertEqual((url, token), ("https://app.example/api/generation/jobs/7/result/", TOKEN))

    def test_unsafe_targets_are_refused(self):
        good = "https://app.example/api/generation/jobs/7/result/"
        bad = [
            None, {}, {"url": good}, {"token": TOKEN}, {"url": 5, "token": TOKEN},
            {"url": "http://app.example/api/generation/jobs/7/result/", "token": TOKEN},
            {"url": "http://127.0.0.1:9/api/generation/jobs/7/result/", "token": TOKEN},
            {"url": "https://app.example/api/other/", "token": TOKEN},
            {"url": good + "?x=1", "token": TOKEN},
            {"url": "https://app.example/api/generation/jobs/8/result/", "token": TOKEN},
            {"url": good, "token": ""},
            {"url": good, "token": "x" * 600},
        ]
        for upload in bad:
            with self.subTest(upload=upload), self.assertRaises(UploadError):
                check_target(upload, 7)

    def test_plain_http_is_allowed_for_localhost_only_when_explicitly_enabled(self):
        upload = {"url": "http://127.0.0.1:9/api/generation/jobs/7/result/", "token": TOKEN}
        with patch.dict("os.environ", {"WORKER_ALLOW_INSECURE_UPLOAD": "1"}):
            check_target(upload, 7)
            with self.assertRaises(UploadError):
                check_target({"url": "http://evil.example/api/generation/jobs/7/result/", "token": TOKEN}, 7)


@patch.dict("os.environ", {"WORKER_ALLOW_INSECURE_UPLOAD": "1"})
class UploadTests(unittest.TestCase):
    def test_sends_the_file_with_the_token(self):
        with FakeBackend() as backend:
            upload_result({"url": backend.url(), "token": TOKEN}, 7, b"PNGDATA", "image/png")
        (request,) = backend.requests
        self.assertEqual((request["path"], request["token"], request["type"], request["body"]), ("/api/generation/jobs/7/result/", TOKEN, "image/png", b"PNGDATA"))

    def test_client_errors_are_not_retried(self):
        with FakeBackend([409]) as backend, self.assertRaises(UploadError) as caught:
            upload_result({"url": backend.url(), "token": TOKEN}, 7, b"x", "image/png")
        self.assertEqual(len(backend.requests), 1)
        self.assertIn("409", str(caught.exception))

    def test_server_errors_are_retried_then_succeed(self):
        with patch("chameleon_worker.upload.time.sleep"), FakeBackend([503, 503, 201]) as backend:
            upload_result({"url": backend.url(), "token": TOKEN}, 7, b"x", "image/png")
        self.assertEqual(len(backend.requests), 3)

    def test_gives_up_after_three_tries(self):
        with patch("chameleon_worker.upload.time.sleep"), FakeBackend([500]) as backend, self.assertRaises(UploadError):
            upload_result({"url": backend.url(), "token": TOKEN}, 7, b"x", "image/png")
        self.assertEqual(len(backend.requests), 3)

    def test_unreachable_backend_fails_cleanly(self):
        with patch("chameleon_worker.upload.time.sleep"), self.assertRaises(UploadError):
            upload_result({"url": "http://127.0.0.1:1/api/generation/jobs/7/result/", "token": TOKEN}, 7, b"x", "image/png")


class DiagnosticTests(unittest.TestCase):
    def test_parses_nvidia_smi_output(self):
        class Done:
            stdout = "NVIDIA GeForce RTX 4090, 24564, 512, 550.54.14\n"

        with patch("chameleon_worker.diagnostic.subprocess.run", return_value=Done()):
            self.assertEqual(diagnostic.gpu_info(), [{"name": "NVIDIA GeForce RTX 4090", "memory_mb": 24564, "memory_used_mb": 512, "driver": "550.54.14"}])

    def test_missing_or_broken_nvidia_smi_means_no_gpu(self):
        with patch("chameleon_worker.diagnostic.subprocess.run", side_effect=FileNotFoundError):
            summary, image = diagnostic.run()
        self.assertFalse(summary["gpu_detected"])
        self.assertEqual(summary["gpus"], [])
        self.assertTrue(image.startswith(b"\x89PNG"))

        class Garbage:
            stdout = "unexpected\n"

        with patch("chameleon_worker.diagnostic.subprocess.run", return_value=Garbage()):
            self.assertEqual(diagnostic.gpu_info(), [])


@patch.dict("os.environ", {"WORKER_ALLOW_INSECURE_UPLOAD": "1"})
class RouterTests(unittest.TestCase):
    def event(self, backend, **extra):
        return {"input": {"capability": "diagnostic", "job_id": 7, "params": {}, "upload": {"url": backend.url(), "token": TOKEN}, **extra}}

    def test_diagnostic_uploads_a_png_and_reports_hardware(self):
        with FakeBackend() as backend, patch("chameleon_worker.diagnostic.gpu_info", return_value=[{"name": "RTX 4090", "memory_mb": 24564}]):
            output = handle(self.event(backend))
        self.assertNotIn("error", output)
        self.assertEqual(output["result"]["gpus"][0]["name"], "RTX 4090")
        self.assertTrue(output["result"]["gpu_detected"])
        (request,) = backend.requests
        self.assertTrue(request["body"].startswith(b"\x89PNG"))
        self.assertEqual(request["type"], "image/png")

    def test_failures_come_back_as_readable_errors_and_never_raise(self):
        with FakeBackend([409]) as backend:
            self.assertIn("409", handle(self.event(backend))["error"])
        self.assertIn("does not support", handle({"input": {"capability": "dance"}})["error"])
        self.assertIn("malformed", handle({})["error"])
        self.assertIn("malformed", handle({"input": "x"})["error"])
        with patch("chameleon_worker.router.diagnostic.run", side_effect=RuntimeError("boom")):
            self.assertEqual(handle({"input": {"capability": "diagnostic"}})["error"], "RuntimeError: boom")


class TextToImageParamTests(unittest.TestCase):
    def test_defaults_and_limits(self):
        from chameleon_worker.text_to_image import ParamError, check_params

        settings = check_params({"prompt": "  a lighthouse at dusk ", "width": 768, "height": 1344, "seed": 5})
        self.assertEqual(settings, {"prompt": "a lighthouse at dusk", "negative_prompt": "", "width": 768, "height": 1344, "steps": 30, "seed": 5})
        self.assertTrue(0 <= check_params({"prompt": "x"})["seed"] < 2**31)
        for bad in (None, {}, {"prompt": ""}, {"prompt": "x" * 2001}, {"prompt": "x", "width": 500, "height": 500},
                    {"prompt": "x", "steps": 5}, {"prompt": "x", "steps": True}, {"prompt": "x", "seed": -1}, {"prompt": "x", "negative_prompt": 3}):
            with self.subTest(bad=bad), self.assertRaises(ParamError):
                check_params(bad)

    def test_bad_params_come_back_as_a_readable_error_before_any_gpu_work(self):
        with patch.dict("os.environ", {"WORKER_ALLOW_INSECURE_UPLOAD": "1"}):
            output = handle({"input": {"capability": "text_to_image", "job_id": 7, "params": {"prompt": ""},
                                       "upload": {"url": "http://127.0.0.1:9/api/generation/jobs/7/result/", "token": TOKEN}}})
        self.assertIn("description", output["error"])
        with patch("chameleon_worker.router.text_to_image.run") as run:
            output = handle({"input": {"capability": "text_to_image", "job_id": 7, "params": {"prompt": "x"}, "upload": {}}})
        run.assert_not_called()
        self.assertIn("upload target", output["error"])


class LocalServerTests(unittest.TestCase):
    TOKEN = "t" * 40

    def setUp(self):
        from chameleon_worker.local_server import JobQueue, make_server

        self.release = threading.Event()

        def runner(event):
            self.release.wait(5)
            return {"result": {"echo": event["input"]["params"]}}

        self.jobs = JobQueue(runner)
        self.server = make_server(self.TOKEN, 0, self.jobs)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/v2/local"

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None, token=None):
        import urllib.error
        import urllib.request

        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"Authorization": f"Bearer {token or self.TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def wait_for(self, job_id, state):
        for _ in range(100):
            status, body = self.call("GET", f"/status/{job_id}")
            if body.get("status") == state:
                return body
            time.sleep(0.05)
        self.fail(f"job never reached {state}: {body}")

    def test_runs_jobs_in_order_with_runpod_shaped_status(self):
        status, first = self.call("POST", "/run", {"input": {"params": {"n": 1}}, "policy": {}})
        self.assertEqual((status, first["status"]), (200, "IN_QUEUE"))
        _, second = self.call("POST", "/run", {"input": {"params": {"n": 2}}})
        self.wait_for(first["id"], "IN_PROGRESS")
        self.assertEqual(self.call("GET", f"/status/{second['id']}")[1]["status"], "IN_QUEUE")
        self.release.set()
        done = self.wait_for(first["id"], "COMPLETED")
        self.assertEqual(done["output"], {"result": {"echo": {"n": 1}}})
        self.assertIsInstance(done["executionTime"], int)
        self.assertIsInstance(done["delayTime"], int)
        self.assertEqual(self.wait_for(second["id"], "COMPLETED")["output"]["result"]["echo"], {"n": 2})

    def test_queued_jobs_can_be_canceled(self):
        _, running = self.call("POST", "/run", {"input": {"params": {}}})
        _, queued = self.call("POST", "/run", {"input": {"params": {}}})
        self.wait_for(running["id"], "IN_PROGRESS")
        self.assertEqual(self.call("POST", f"/cancel/{queued['id']}")[1]["status"], "CANCELLED")
        self.release.set()
        self.wait_for(running["id"], "COMPLETED")
        self.assertEqual(self.call("GET", f"/status/{queued['id']}")[1]["status"], "CANCELLED")

    def test_rejects_bad_tokens_paths_and_bodies(self):
        self.assertEqual(self.call("POST", "/run", {"input": {}}, token="wrong")[0], 401)
        self.assertEqual(self.call("GET", "/status/not-a-job")[0], 404)
        self.assertEqual(self.call("GET", f"/status/{'0' * 8}-0000-0000-0000-{'0' * 12}")[0], 404)
        self.assertEqual(self.call("GET", "/run")[0], 405)
        self.assertEqual(self.call("POST", "/run", {"nope": 1})[0], 400)
        self.assertEqual(self.call("POST", "/run", [1])[0], 400)

    def test_refuses_to_start_with_a_short_token(self):
        from chameleon_worker.local_server import make_server

        with self.assertRaises(ValueError):
            make_server("short", 0, self.jobs)


if __name__ == "__main__":
    unittest.main()
