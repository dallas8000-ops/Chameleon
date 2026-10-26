"""Routes a RunPod job to the capability it asks for. Phase 3 registers the real models here."""
from __future__ import annotations

from chameleon_worker import diagnostic, text_to_image
from chameleon_worker.upload import UploadError, check_target, upload_result


def _run_diagnostic(job: dict) -> dict:
    summary, image = diagnostic.run()
    upload_result(job.get("upload"), job.get("job_id"), image, "image/png")
    return {"result": summary}


def _run_text_to_image(job: dict) -> dict:
    # Check the target before spending GPU time on a picture that could not be delivered.
    upload = job.get("upload")
    check_target(upload, job.get("job_id"))
    summary, image = text_to_image.run(job.get("params"))
    upload_result(upload, job.get("job_id"), image, "image/png")
    return {"result": summary}


CAPABILITIES = {"diagnostic": _run_diagnostic, "text_to_image": _run_text_to_image}


def handle(event: dict) -> dict:
    """RunPod handler. Returns {"error": ...} for failures so the backend can show a clear message."""
    job = event.get("input") if isinstance(event, dict) else None
    if not isinstance(job, dict):
        return {"error": "The job input was missing or malformed."}
    runner = CAPABILITIES.get(job.get("capability"))
    if runner is None:
        return {"error": f"This worker does not support the capability {str(job.get('capability'))[:60]!r}."}
    try:
        return runner(job)
    except (UploadError, text_to_image.ParamError) as error:
        return {"error": str(error)}
    except Exception as error:  # noqa: BLE001 - the GPU service must always get a readable failure
        return {"error": f"{type(error).__name__}: {str(error)[:200]}"}
