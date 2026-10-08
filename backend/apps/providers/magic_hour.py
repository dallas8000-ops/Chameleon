import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

from apps.providers.base import (
    BaseMediaProvider,
    ProviderError,
    ProviderJobUpdate,
    ProviderSubmission,
)


class MagicHourProvider(BaseMediaProvider):
    provider_name = "magic_hour"
    capabilities = frozenset({"image.generate", "presenter.generate"})
    api_base_url = "https://api.magichour.ai"
    timeout_seconds = 20

    def is_configured(self) -> bool:
        return bool(getattr(settings, "MAGIC_HOUR_API_KEY", ""))

    def submit_image_generation(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        name: str = "",
    ) -> ProviderSubmission:
        body = {
            "image_count": 1,
            "model": "z-image-turbo",
            "aspect_ratio": aspect_ratio,
            "resolution": "640px",
            "style": {"prompt": prompt, "tool": "general"},
        }
        if name:
            body["name"] = name
        response = self._request("POST", "/v1/ai-image-generator", body)
        return self._submission(response)

    def submit_presenter_generation(self, *, script_text: str, scene_payload: dict) -> ProviderSubmission:
        # Talking Photo animates supplied audio; it does not synthesize speech from script text.
        body = {
            "start_seconds": scene_payload["start_seconds"],
            "end_seconds": scene_payload["end_seconds"],
            "assets": {
                "image_file_path": scene_payload["image_file_path"],
                "audio_file_path": scene_payload["audio_file_path"],
            },
            "style": {"generation_mode": scene_payload.get("generation_mode", "realistic")},
        }
        if scene_payload.get("generation_mode") == "prompted" and scene_payload.get("prompt"):
            body["style"]["prompt"] = scene_payload["prompt"]
        if scene_payload.get("name"):
            body["name"] = scene_payload["name"]
        response = self._request("POST", "/v1/ai-talking-photo", body)
        return self._submission(response)

    def get_generation_update(self, *, job) -> ProviderJobUpdate:
        kind = "image-projects" if job.capability == "image.generate" else "video-projects"
        response = self._request("GET", f"/v1/{kind}/{quote(job.provider_job_id, safe='')}")
        if response.get("id") != job.provider_job_id:
            raise ProviderError(
                "provider_response_invalid",
                "Magic Hour returned details for an unexpected project identifier.",
            )
        provider_status = response.get("status")
        status_map = {
            "queued": "queued",
            "rendering": "processing",
            "complete": "completed",
            "error": "failed",
            "canceled": "canceled",
        }
        mapped_status = status_map.get(provider_status)
        if mapped_status is None:
            raise ProviderError(
                "provider_status_unknown",
                "Magic Hour returned an unrecognized generation status.",
            )
        amount = response.get("credits_charged")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            amount = None
        result = {"downloads": response["downloads"]} if (
            mapped_status == "completed" and response.get("downloads")
        ) else {}
        provider_error = response.get("error") if isinstance(response.get("error"), dict) else {}
        return ProviderJobUpdate(
            status=mapped_status,
            result=result,
            error_code=provider_error.get("code", "") if mapped_status == "failed" else "",
            error_message=provider_error.get("message", "") if mapped_status == "failed" else "",
            amount_credits=amount if mapped_status == "completed" else None,
            external_event_id=f"poll:{job.provider_job_id}:{provider_status}",
        )

    def _submission(self, response: dict) -> ProviderSubmission:
        provider_job_id = response.get("id")
        quoted_credits = response.get("credits_charged")
        if not isinstance(provider_job_id, str) or not provider_job_id:
            raise ProviderError(
                "provider_response_invalid",
                "Magic Hour accepted no usable job identifier; check provider job status before retrying.",
            )
        if isinstance(quoted_credits, bool) or not isinstance(quoted_credits, int) or quoted_credits < 0:
            quoted_credits = None
        return ProviderSubmission(
            provider_job_id=provider_job_id,
            quoted_credits=quoted_credits,
            raw_response=response,
        )

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        api_key = getattr(settings, "MAGIC_HOUR_API_KEY", "")
        if not api_key:
            raise ProviderError("provider_not_configured", "Configure MAGIC_HOUR_API_KEY before generation.")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.api_base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read())
        except HTTPError as error:
            payload = self._read_error(error)
            raise ProviderError(
                payload.get("code") or f"provider_http_{error.code}",
                payload.get("message") or "Magic Hour could not accept or process this request.",
            ) from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError(
                "provider_unavailable",
                "Magic Hour could not be reached; the request may have been accepted. "
                "Check job status before retrying.",
            ) from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ProviderError(
                "provider_response_invalid",
                "Magic Hour returned an invalid response.",
            ) from None
        if not isinstance(parsed, dict):
            raise ProviderError("provider_response_invalid", "Magic Hour returned an invalid response.")
        return parsed

    @staticmethod
    def _read_error(error: HTTPError) -> dict:
        try:
            parsed = json.loads(error.read())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
