"""Sends a finished file back to the Chameleon backend using the one-time URL and token it supplied."""
from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

UPLOAD_PATH = re.compile(r"^/api/generation/jobs/(\d+)/result/$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}
TIMEOUT_SECONDS = 120
ATTEMPTS = 3


class UploadError(Exception):
    pass


def check_target(upload: object, job_id: object) -> tuple[str, str]:
    if not isinstance(upload, dict) or not isinstance(upload.get("url"), str) or not isinstance(upload.get("token"), str):
        raise UploadError("The job did not include an upload target.")
    url, token = upload["url"], upload["token"]
    parsed = urlparse(url)
    local = parsed.hostname in LOCAL_HOSTS
    if parsed.scheme != "https" and not (local and os.environ.get("WORKER_ALLOW_INSECURE_UPLOAD") == "1"):
        raise UploadError("Results can only be uploaded over https.")
    match = UPLOAD_PATH.match(parsed.path)
    if not match or parsed.query or parsed.fragment or (isinstance(job_id, int) and int(match.group(1)) != job_id):
        raise UploadError("The upload target does not match this job.")
    if not token or len(token) > 512:
        raise UploadError("The upload token is invalid.")
    return url, token


def upload_result(upload: object, job_id: object, body: bytes, content_type: str) -> None:
    url, token = check_target(upload, job_id)
    last_error = "unknown error"
    for attempt in range(1, ATTEMPTS + 1):
        request = urllib.request.Request(
            url, data=body, method="PUT",
            headers={"Content-Type": content_type, "Content-Length": str(len(body)), "X-Upload-Token": token},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except urllib.error.HTTPError as error:
            last_error = f"HTTP {error.code}"
            if error.code < 500 and error.code != 429:
                raise UploadError(f"The server refused the result ({last_error}).") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = type(error).__name__
        if attempt < ATTEMPTS:
            time.sleep(min(2 ** attempt, 8))
    raise UploadError(f"The result could not be delivered after {ATTEMPTS} tries ({last_error}).")
