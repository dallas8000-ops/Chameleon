from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSubmission:
    provider_job_id: str
    quoted_credits: int
    raw_response: dict


@dataclass(frozen=True)
class ProviderJobUpdate:
    status: str
    result: dict
    error_code: str = ""
    error_message: str = ""
    amount_credits: int | None = None
    external_event_id: str = ""


class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BaseMediaProvider:
    provider_name = "base"
    capabilities: frozenset[str] = frozenset()

    def is_configured(self) -> bool:
        raise NotImplementedError

    def supports_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def submit_image_generation(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        name: str = "",
    ) -> ProviderSubmission:
        raise NotImplementedError

    def submit_presenter_generation(self, *, script_text: str, scene_payload: dict) -> ProviderSubmission:
        raise NotImplementedError

    def get_generation_update(self, *, job) -> ProviderJobUpdate:
        raise NotImplementedError
