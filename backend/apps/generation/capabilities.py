"""The capabilities a job can request. Phase 3 adds real models here; each entry validates its own params."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rest_framework import serializers


@dataclass(frozen=True)
class Capability:
    name: str
    label: str
    description: str
    validate: Callable[[dict], dict]
    # Seconds the GPU may spend on one job before RunPod stops it (credit protection).
    max_execution_seconds: int = 300
    # Kinds of file the worker may upload as this capability's result.
    output_types: tuple[str, ...] = ("image",)
    # Param naming a workspace asset the worker downloads as input, and the asset type it must be.
    input_asset_param: str | None = None
    input_asset_type: str | None = None


def _no_params(params: dict) -> dict:
    if params:
        raise serializers.ValidationError({"params": ["This capability takes no parameters."]})
    return {}


PICTURE_SIZES = {"portrait": (768, 1344), "landscape": (1344, 768), "square": (1024, 1024)}


def _text_to_image_params(params: dict) -> dict:
    unknown = set(params) - {"prompt", "negative_prompt", "size", "seed", "steps", "reference_asset_id"}
    if unknown:
        raise serializers.ValidationError({"params": [f"Unknown settings: {sorted(unknown)}."]})
    prompt = params.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
        raise serializers.ValidationError({"prompt": ["Describe the picture in 1 to 2000 characters."]})
    negative = params.get("negative_prompt", "")
    if not isinstance(negative, str) or len(negative) > 2000:
        raise serializers.ValidationError({"negative_prompt": ["Must be text of at most 2000 characters."]})
    size = params.get("size", "portrait")
    if size not in PICTURE_SIZES:
        raise serializers.ValidationError({"size": [f"Choose one of {sorted(PICTURE_SIZES)}."]})
    steps = params.get("steps", 30)
    if isinstance(steps, bool) or not isinstance(steps, int) or not 10 <= steps <= 50:
        raise serializers.ValidationError({"steps": ["Must be a whole number from 10 to 50."]})
    cleaned = {"prompt": prompt.strip(), "negative_prompt": negative.strip(), "steps": steps}
    cleaned["width"], cleaned["height"] = PICTURE_SIZES[size]
    seed = params.get("seed")
    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**31:
            raise serializers.ValidationError({"seed": ["Must be a whole number from 0 to 2147483647."]})
        cleaned["seed"] = seed
    reference = params.get("reference_asset_id")
    if reference is not None:
        if isinstance(reference, bool) or not isinstance(reference, int) or reference < 1:
            raise serializers.ValidationError({"reference_asset_id": ["Choose a reference picture."]})
        cleaned["reference_asset_id"] = reference
    return cleaned


def _voice_params(params: dict) -> dict:
    unknown = set(params) - {"text", "voice_sample_asset_id"}
    if unknown:
        raise serializers.ValidationError({"params": [f"Unknown settings: {sorted(unknown)}."]})
    text = params.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise serializers.ValidationError({"text": ["The line to speak must be 1 to 1000 characters."]})
    sample = params.get("voice_sample_asset_id")
    if isinstance(sample, bool) or not isinstance(sample, int) or sample < 1:
        raise serializers.ValidationError({"voice_sample_asset_id": ["Choose a voice sample."]})
    return {"text": " ".join(text.split()), "voice_sample_asset_id": sample}


CAPABILITIES: dict[str, Capability] = {
    "diagnostic": Capability(
        name="diagnostic",
        label="GPU check",
        description="Starts the GPU worker, reports its graphics card and memory, and returns a test image.",
        validate=_no_params,
        max_execution_seconds=120,
    ),
    "text_to_image": Capability(
        name="text_to_image",
        label="Picture",
        description="Makes a still picture from a written description (Stable Diffusion XL), optionally keeping a character's face from a reference picture (IP-Adapter).",
        validate=_text_to_image_params,
        # The first job also loads the model into GPU memory.
        max_execution_seconds=600,
        input_asset_param="reference_asset_id",
        input_asset_type="image",
    ),
    "voice": Capability(
        name="voice",
        label="Voice",
        description="Reads a line aloud in the voice of a short sample (Chatterbox). Only clone voices you own or may use.",
        validate=_voice_params,
        max_execution_seconds=600,
        output_types=("audio",),
        input_asset_param="voice_sample_asset_id",
        input_asset_type="audio",
    ),
}


def get_capability(name: str) -> Capability | None:
    return CAPABILITIES.get(name)
