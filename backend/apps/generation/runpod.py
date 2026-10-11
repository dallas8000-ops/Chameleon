"""Minimal RunPod Serverless client. Only the backend ever holds the API key."""
from __future__ import annotations

import requests
from django.conf import settings

TIMEOUT_SECONDS = 20


class RunPodError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def is_configured() -> bool:
    return bool(
        getattr(settings, "RUNPOD_API_KEY", "")
        and getattr(settings, "RUNPOD_ENDPOINT_ID", "")
        and getattr(settings, "GENERATION_PUBLIC_URL", "")
    )


def missing_settings() -> list[str]:
    names = ("RUNPOD_API_KEY", "RUNPOD_ENDPOINT_ID", "GENERATION_PUBLIC_URL")
    return [name for name in names if not getattr(settings, name, "")]


def _url(path: str) -> str:
    base = getattr(settings, "RUNPOD_API_BASE", "https://api.runpod.ai/v2").rstrip("/")
    return f"{base}/{settings.RUNPOD_ENDPOINT_ID}/{path}"


def _request(method: str, path: str, **kwargs) -> dict:
    if not is_configured():
        raise RunPodError("generation_not_configured", "The GPU worker is not configured on the server.")
    headers = {"Authorization": f"Bearer {settings.RUNPOD_API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.request(method, _url(path), headers=headers, timeout=TIMEOUT_SECONDS, **kwargs)
    except (requests.ConnectionError, requests.Timeout):
        raise RunPodError("provider_unreachable", "The GPU service could not be reached.", retryable=True) from None
    except requests.RequestException:
        raise RunPodError("provider_error", "The GPU service request failed.", retryable=True) from None
    if response.status_code in (401, 403):
        raise RunPodError("provider_auth_failed", "The GPU service rejected the API key.")
    if response.status_code == 404:
        raise RunPodError("provider_endpoint_missing", "The GPU endpoint was not found; check RUNPOD_ENDPOINT_ID.")
    if response.status_code == 429 or response.status_code >= 500:
        raise RunPodError("provider_busy", "The GPU service is busy or unavailable.", retryable=True)
    if response.status_code >= 400:
        raise RunPodError("provider_rejected", "The GPU service rejected the request.")
    try:
        data = response.json()
    except ValueError:
        raise RunPodError("provider_response_invalid", "The GPU service returned an unreadable response.", retryable=True) from None
    if not isinstance(data, dict):
        raise RunPodError("provider_response_invalid", "The GPU service returned an unexpected response.", retryable=True)
    return data


def submit(payload: dict, *, execution_timeout_seconds: int, ttl_seconds: int) -> str:
    data = _request(
        "POST", "run",
        json={
            "input": payload,
            "policy": {"executionTimeout": execution_timeout_seconds * 1000, "ttl": ttl_seconds * 1000},
        },
    )
    job_id = data.get("id")
    if not isinstance(job_id, str) or not job_id or len(job_id) > 120:
        raise RunPodError("provider_response_invalid", "The GPU service did not return a job id.", retryable=True)
    return job_id


def status(provider_job_id: str) -> dict:
    return _request("GET", f"status/{provider_job_id}")


def cancel(provider_job_id: str) -> None:
    _request("POST", f"cancel/{provider_job_id}")
