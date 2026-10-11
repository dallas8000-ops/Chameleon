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


CAPABILITIES: dict[str, Capability] = {
    "diagnostic": Capability(
        name="diagnostic",
        label="GPU check",
        description="Starts the GPU worker, reports its graphics card and memory, and returns a test image.",
        validate=_no_params,
        max_execution_seconds=120,
    ),
}


def get_capability(name: str) -> Capability | None:
    return CAPABILITIES.get(name)
