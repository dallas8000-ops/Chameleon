"""Reports what hardware this worker really has, then returns a test image through the full upload path."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time

from chameleon_worker.png import gradient_png

NVIDIA_QUERY = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader,nounits"]


def gpu_info() -> list[dict]:
    try:
        completed = subprocess.run(NVIDIA_QUERY, capture_output=True, text=True, timeout=15, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in completed.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        try:
            gpus.append({"name": parts[0], "memory_mb": int(float(parts[1])), "memory_used_mb": int(float(parts[2])), "driver": parts[3]})
        except ValueError:
            continue
    return gpus


def run() -> tuple[dict, bytes]:
    started = time.monotonic()
    gpus = gpu_info()
    free_gb = round(shutil.disk_usage("/").free / 1e9, 1) if os.path.exists("/") else None
    summary = {
        "gpus": gpus,
        "gpu_detected": bool(gpus),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "disk_free_gb": free_gb,
    }
    image = gradient_png()
    summary["check_seconds"] = round(time.monotonic() - started, 2)
    return summary, image
