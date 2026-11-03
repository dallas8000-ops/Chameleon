"""Runs jobs on this computer's graphics card behind the same API the backend uses for RunPod Serverless.

The backend needs no special code path: point RUNPOD_API_BASE at http://127.0.0.1:<port>/v2 and set
RUNPOD_API_KEY to LOCAL_GPU_TOKEN (run-gpu.ps1 does both). Jobs run one at a time, because one card
holds one model. The server listens on 127.0.0.1 only and every request needs the token.
"""
from __future__ import annotations

import hmac
import json
import os
import queue
import re
import threading
import time
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from chameleon_worker.router import handle

ROUTE = re.compile(r"^/v2/[A-Za-z0-9_-]{1,64}/(run|status/([0-9a-f-]{36})|cancel/([0-9a-f-]{36}))$")
MAX_BODY = 1024 * 1024
KEEP_FINISHED = 500


class JobQueue:
    def __init__(self, runner=handle):
        self.runner = runner
        self.jobs: OrderedDict[str, dict] = OrderedDict()
        self.lock = threading.Lock()
        self.pending: queue.Queue[str] = queue.Queue()
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def submit(self, job_input: dict) -> str:
        job_id = str(uuid.uuid4())
        with self.lock:
            self.jobs[job_id] = {"status": "IN_QUEUE", "input": job_input, "queued": time.monotonic(), "cancel": False}
            while len(self.jobs) > KEEP_FINISHED:
                oldest = next(iter(self.jobs))
                if self.jobs[oldest]["status"] in ("IN_QUEUE", "IN_PROGRESS"):
                    break
                self.jobs.popitem(last=False)
        self.pending.put(job_id)
        return job_id

    def status(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            body = {"id": job_id, "status": job["status"]}
            for key in ("output", "delayTime", "executionTime"):
                if key in job:
                    body[key] = job[key]
            return body

    def cancel(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            job["cancel"] = True
            if job["status"] == "IN_QUEUE":
                job["status"] = "CANCELLED"
        return self.status(job_id)

    def _work(self) -> None:
        while True:
            job_id = self.pending.get()
            with self.lock:
                job = self.jobs.get(job_id)
                if job is None or job["status"] != "IN_QUEUE":
                    continue
                job["status"] = "IN_PROGRESS"
                started = time.monotonic()
                job["delayTime"] = int((started - job["queued"]) * 1000)
                job_input = job["input"]
            output = self.runner({"input": job_input})
            with self.lock:
                job["executionTime"] = int((time.monotonic() - started) * 1000)
                # A job canceled while running cannot be interrupted, but its result is not reported as wanted.
                job["status"] = "CANCELLED" if job["cancel"] else "COMPLETED"
                job["output"] = output


def make_server(token: str, port: int, jobs: JobQueue) -> ThreadingHTTPServer:
    if len(token) < 32:
        raise ValueError("LOCAL_GPU_TOKEN must be at least 32 characters.")
    expected = f"Bearer {token}".encode()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _route(self, method: str):
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected):
                self._reply(401, {"error": "Unauthorized."})
                return None
            match = ROUTE.match(self.path)
            if match is None:
                self._reply(404, {"error": "Not found."})
                return None
            action = match.group(1).split("/")[0]
            if (action == "status") != (method == "GET"):
                self._reply(405, {"error": "Method not allowed."})
                return None
            return action, match.group(2) or match.group(3)

        def do_GET(self):
            routed = self._route("GET")
            if routed:
                found = jobs.status(routed[1])
                self._reply(200, found) if found else self._reply(404, {"error": "Unknown job."})

        def do_POST(self):
            routed = self._route("POST")
            if not routed:
                return
            action, job_id = routed
            if action == "cancel":
                found = jobs.cancel(job_id)
                self._reply(200, found) if found else self._reply(404, {"error": "Unknown job."})
                return
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or int(length) > MAX_BODY:
                self._reply(413, {"error": "The request body is missing or too large."})
                return
            try:
                body = json.loads(self.rfile.read(int(length)))
            except ValueError:
                self._reply(400, {"error": "The request body is not JSON."})
                return
            if not isinstance(body, dict) or not isinstance(body.get("input"), dict):
                self._reply(400, {"error": "The request needs an input object."})
                return
            self._reply(200, {"id": jobs.submit(body["input"]), "status": "IN_QUEUE"})

        def log_message(self, format, *args):  # noqa: A002 - signature set by BaseHTTPRequestHandler
            print(f"[gpu] {self.command} {self.path.split('/')[-1] if 'status' in self.path else self.path}", flush=True)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    token = os.environ.get("LOCAL_GPU_TOKEN", "")
    port = int(os.environ.get("LOCAL_GPU_PORT", "8189"))
    server = make_server(token, port, JobQueue())
    print(f"Local GPU worker listening on http://127.0.0.1:{port} (jobs run one at a time).", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
