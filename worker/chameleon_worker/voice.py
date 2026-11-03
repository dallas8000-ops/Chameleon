"""Reads a line in a cloned voice with Chatterbox (MIT).

Chatterbox pins old library versions, so it lives in its own environment (.venv-voice) and runs as a short
child process: this module writes the sample to a temporary file, runs voice_cli.py with VOICE_PYTHON, and
reads back the WAV. Every output carries Resemble AI's imperceptible Perth watermark.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

VOICE_CLI = Path(__file__).resolve().parent.parent / "voice_cli.py"
TIMEOUT_SECONDS = 540


class ParamError(ValueError):
    pass


def check_params(params: object) -> str:
    if not isinstance(params, dict):
        raise ParamError("The voice settings were missing.")
    text = params.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ParamError("The line to speak must be 1 to 1000 characters.")
    return " ".join(text.split())


def run(params: object, sample: bytes) -> tuple[dict, bytes]:
    text = check_params(params)
    python = os.environ.get("VOICE_PYTHON", "")
    if not python or not Path(python).is_file():
        raise RuntimeError("The voice model is not installed on this worker (VOICE_PYTHON is not set).")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="chameleon-voice-") as scratch:
        reference = Path(scratch) / "sample.wav"
        output = Path(scratch) / "line.wav"
        reference.write_bytes(sample)
        completed = subprocess.run(
            [python, str(VOICE_CLI), str(reference), str(output), text],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
        if completed.returncode != 0 or not output.is_file():
            last = (completed.stderr or completed.stdout).strip().splitlines()[-1:] or ["no output"]
            raise RuntimeError(f"The voice model failed: {last[0][:200]}")
        audio = output.read_bytes()
    return {"model": "ResembleAI/chatterbox", "seconds": round(time.monotonic() - started, 2), "characters": len(text)}, audio
