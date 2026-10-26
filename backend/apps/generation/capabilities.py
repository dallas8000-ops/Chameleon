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


def _no_params(params: dict) -> dict:
    if params:
        raise serializers.ValidationError({"params": ["This capability takes no parameters."]})
    return {}


PICTURE_SIZES = {"portrait": (768, 1344), "landscape": (1344, 768), "square": (1024, 1024)}


def _text_to_image_params(params: dict) -> dict:
    unknown = set(params) - {"prompt", "negative_prompt", "size", "seed", "steps"}
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
    return cleaned


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
        description="Makes a still picture from a written description (Stable Diffusion XL).",
        validate=_text_to_image_params,
        # The first job also loads the model into GPU memory.
        max_execution_seconds=600,
    ),
}


def get_capability(name: str) -> Capability | None:
    return CAPABILITIES.get(name)
