import hashlib
import json
import os
import shutil
import subprocess
import uuid
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.jobs.downloads import DownloadRejected, authorized_origins, download_image
from apps.jobs.models import GeneratedFileCandidate, GenerationJob
from apps.providers.base import ProviderError
from apps.providers.registry import ProviderRegistry
from apps.studio.models import Asset
from apps.studio.services import AssetService

RETRYABLE = {"result_download_failed", "result_storage_failed", "result_unavailable"}


def staging_root():
    return Path(settings.BASE_DIR) / "private_generation_staging"


def acquire_source(job, path):
    from apps.rendering.services import safe_storage_key
    limit = min(25 * 1024 * 1024, getattr(settings, "STUDIO_MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
    for candidate in job.asset_cleanup_keys:
        if (candidate.get("token") != job.asset_attempt_token or not candidate.get("sha256")
                or not safe_storage_key(candidate.get("key", ""), job.workspace_id)):
            continue
        key = candidate["key"]
        if not default_storage.exists(key):
            continue
        if not 0 < candidate.get("size", 0) <= limit:
            continue
        with default_storage.open(key, "rb") as stored, path.open("wb") as target:
            size = 0
            while chunk := stored.read(64 * 1024):
                size += len(chunk)
                if size > limit:
                    raise DownloadRejected("result_storage_failed")
                target.write(chunk)
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if size == candidate["size"] and digest == candidate["sha256"]:
            return candidate["content_type"], key
        path.unlink(missing_ok=True)

    update = ProviderRegistry.get(job.provider_name).get_generation_update(job=job)
    downloads = update.result.get("downloads") if isinstance(update.result, dict) else None
    if update.status != "completed" or not isinstance(downloads, list) or len(downloads) != 1:
        raise DownloadRejected("result_unavailable")
    item = downloads[0]
    if not isinstance(item, dict) or not isinstance(item.get("url"), str):
        raise DownloadRejected("result_download_policy")
    try:
        expires = parse_datetime(item["expires_at"])
        if not expires or timezone.is_naive(expires) or expires <= timezone.now():
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise DownloadRejected("result_unavailable") from None
    with path.open("wb") as target:
        declared = download_image(item["url"], target)
    return declared, None


def validate_image(path):
    """File-only probe plus decode; signatures alone cannot validate a complete image."""
    output = path.with_suffix(".probe")
    try:
        with output.open("wb") as stream:
            subprocess.run([
                getattr(settings, "FFPROBE_BINARY", "ffprobe"), "-v", "error", "-max_alloc", "67108864",
                "-threads", "1",
                "-protocol_whitelist", "file", "-format_whitelist", "png_pipe,jpeg_pipe,webp_pipe",
                "-count_frames", "-show_entries", "stream=codec_type,width,height,nb_read_frames",
                "-of", "json", str(path),
            ], stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.DEVNULL,
                shell=False, check=True, timeout=10)
        if output.stat().st_size > 65536:
            raise ValueError
        streams = json.loads(output.read_bytes())["streams"]
        if len(streams) != 1:
            raise ValueError
        image = streams[0]
        width, height = int(image["width"]), int(image["height"])
        if (image["codec_type"] != "video" or int(image["nb_read_frames"]) != 1
                or not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 16_777_216):
            raise ValueError
        subprocess.run([
            getattr(settings, "FFMPEG_BINARY", "ffmpeg"), "-v", "error", "-xerror",
            "-max_alloc", "67108864", "-threads", "1", "-filter_threads", "1",
            "-protocol_whitelist", "file", "-format_whitelist", "png_pipe,jpeg_pipe,webp_pipe",
            "-err_detect", "explode", "-i", str(path), "-f", "null", os.devnull,
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            shell=False, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise DownloadRejected("result_invalid_media") from None
    finally:
        output.unlink(missing_ok=True)


def cleanup_candidates(job_id):
    # Holding the job lock makes cleanup and publication mutually exclusive.
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None:
            return
        retained = []
        for item in job.asset_cleanup_keys:
            if item["token"] == job.asset_attempt_token and job.asset_status == "ingesting":
                retained.append(item)
                continue
            if Asset.objects.filter(storage_key=item["key"]).exists():
                continue
            try:
                default_storage.delete(item["key"])
                GeneratedFileCandidate.objects.filter(storage_key=item["key"]).delete()
            except OSError:
                retained.append(item)
        job.asset_cleanup_keys = retained
        job.save(update_fields=["asset_cleanup_keys"])


@shared_task
def ingest_result(job_id):
    token = uuid.uuid4().hex
    now = timezone.now()
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().filter(
            pk=job_id, capability="image.generate", status="completed",
        ).first()
        if job is None or job.asset_status == "ready":
            return
        if job.asset_status == "failed":
            return
        if job.asset_status == "ingesting" and job.asset_lease_until and job.asset_lease_until > now:
            return
        if job.asset_next_attempt_at and job.asset_next_attempt_at > now:
            return
        if job.asset_attempts >= 5:
            job.asset_status = "failed"
            job.asset_error_code = job.asset_error_code or "result_download_failed"
            job.asset_next_attempt_at = None
            job.save(update_fields=["asset_status", "asset_error_code", "asset_next_attempt_at"])
            return
        job.asset_status = "ingesting"
        job.asset_attempt_token = token
        job.asset_attempts += 1
        job.asset_lease_until = now + timedelta(seconds=180)
        job.asset_next_attempt_at = job.asset_lease_until
        # Fence cleanup while a new lease verifies candidate bytes from a crashed writer.
        for item in job.asset_cleanup_keys:
            item["token"] = token
        job.save(update_fields=["asset_status", "asset_attempt_token", "asset_attempts",
                                "asset_lease_until", "asset_next_attempt_at", "asset_cleanup_keys"])

    directory = staging_root() / str(job_id) / token
    try:
        if not authorized_origins():
            raise DownloadRejected("result_download_policy")
        if getattr(settings, "GENERATION_STORAGE_CONFIRMED", False) is not True:
            raise DownloadRejected("result_storage_unconfirmed")
        if not job.provider_job_id:
            raise DownloadRejected("result_unavailable")
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "source"
        declared, reusable_key = acquire_source(job, path)
        with path.open("rb") as source:
            sniffed = AssetService.sniff(source.read(16))
            if not sniffed or sniffed[0] not in {"image/png", "image/jpeg", "image/webp"} or declared != sniffed[0]:
                raise DownloadRejected("result_invalid_media")
            source.seek(0)
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        content_type, extension, asset_type = sniffed
        validate_image(path)
        size = path.stat().st_size
        key = reusable_key or f"workspaces/{job.workspace_id}/assets/{token}.{extension}"
        with transaction.atomic():
            current = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
            if current is None or current.asset_attempt_token != token or current.asset_status != "ingesting":
                return
            if not reusable_key:
                current.asset_cleanup_keys.append({
                    "key": key, "token": token, "sha256": checksum,
                    "size": size, "content_type": content_type,
                })
            current.save(update_fields=["asset_cleanup_keys"])
            GeneratedFileCandidate.objects.get_or_create(
                storage_key=key, defaults={"job": current, "attempt_token": token,
                                          "cleanup_after": current.asset_lease_until},
            )
        if reusable_key:
            saved = reusable_key
        else:
            with path.open("rb") as source:
                saved = default_storage.save(key, File(source))
        if saved != key:
            # A backend rename must not create an untracked orphan.
            with transaction.atomic():
                current = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
                if current:
                    current.asset_cleanup_keys.append({"key": saved, "token": token})
                    current.save(update_fields=["asset_cleanup_keys"])
                GeneratedFileCandidate.objects.get_or_create(
                    storage_key=saved, defaults={"job": current, "attempt_token": token,
                                                "cleanup_after": timezone.now() + timedelta(seconds=180)},
                )
            default_storage.delete(saved)
            raise DownloadRejected("result_storage_failed")
        with default_storage.open(key, "rb") as stored:
            if hashlib.file_digest(stored, "sha256").hexdigest() != checksum:
                raise DownloadRejected("result_storage_failed")
        with transaction.atomic():
            current = GenerationJob.objects.select_for_update().filter(pk=job_id).first()
            if current is None or current.asset_attempt_token != token or current.asset_status != "ingesting":
                adopted = current and any(
                    item["key"] == key and item["token"] == current.asset_attempt_token
                    for item in current.asset_cleanup_keys
                )
                if not adopted and not Asset.objects.filter(storage_key=key).exists():
                    default_storage.delete(key)
                return
            asset = Asset.objects.create(
                workspace_id=current.workspace_id, created_by_id=current.requested_by_id,
                name=AssetService.safe_name(current.payload.get("name") or f"Generated image {job_id}"),
                storage_key=key, content_type=content_type, size_bytes=size, asset_type=asset_type,
                provenance={
                    "source": "generation", "job_id": job_id, "provider": current.provider_name,
                    "provider_job_id": current.provider_job_id, "workspace_id": current.workspace_id,
                    "requested_by": current.accepted_quote.get("requester_id", current.requested_by_id),
                    "output_index": 0, "sha256": checksum, "captured_at": timezone.now().isoformat(),
                    "quote_id": current.accepted_quote.get("quote_id"),
                    "pricing_version": current.accepted_quote.get("pricing_version"),
                    "parameters": current.accepted_quote.get("parameters", {}),
                },
            )
            current.generated_asset = asset
            current.asset_status = "ready"
            current.asset_error_code = ""
            current.asset_next_attempt_at = None
            current.asset_lease_until = None
            current.result = {"asset_id": asset.id}
            current.save(update_fields=["generated_asset", "asset_status", "asset_error_code", "result",
                                        "asset_next_attempt_at", "asset_lease_until", "updated_at"])
    except (DownloadRejected, ProviderError, OSError) as error:
        code = error.code if isinstance(error, DownloadRejected) else (
            "result_download_failed" if isinstance(error, ProviderError) else "result_storage_failed"
        )
        GenerationJob.objects.filter(pk=job_id, asset_attempt_token=token, asset_status="ingesting").update(
            asset_status="pending" if code in RETRYABLE and job.asset_attempts < 5 else "failed",
            asset_error_code=code, asset_lease_until=None,
            asset_next_attempt_at=(timezone.now() + timedelta(seconds=min(30 * 2 ** job.asset_attempts, 600))
                                   if code in RETRYABLE and job.asset_attempts < 5 else None),
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)
        cleanup_candidates(job_id)


@shared_task
def recover_ingestions():
    now = timezone.now()
    ids = list(GenerationJob.objects.filter(
        capability="image.generate", status="completed", asset_status__in=["pending", "ingesting"],
    ).filter(Q(asset_next_attempt_at__lte=now) | Q(asset_next_attempt_at__isnull=True))
        .values_list("id", flat=True)[:100])
    for job_id in ids:
        ingest_result.run(job_id)
    for job_id in GenerationJob.objects.exclude(asset_cleanup_keys=[]).values_list("id", flat=True)[:100]:
        cleanup_candidates(job_id)
    for candidate_id in GeneratedFileCandidate.objects.exclude(
        storage_key__in=Asset.objects.values("storage_key"),
    ).filter(Q(cleanup_after__lte=now) | Q(cleanup_after__isnull=True)).values_list("id", flat=True)[:100]:
        with transaction.atomic():
            candidate = GeneratedFileCandidate.objects.filter(pk=candidate_id).first()
            if candidate is None:
                continue
            job = GenerationJob.objects.select_for_update().filter(pk=candidate.job_id).first()
            if Asset.objects.filter(storage_key=candidate.storage_key).exists():
                continue
            if job and job.asset_status == "ingesting" and job.asset_lease_until and job.asset_lease_until > now:
                continue
            try:
                default_storage.delete(candidate.storage_key)
            except OSError:
                continue
            candidate.delete()
    if staging_root().exists():
        for directory in staging_root().glob("*/*"):
            if not directory.is_dir() or not directory.parent.name.isdigit():
                continue
            active = GenerationJob.objects.filter(
                pk=int(directory.parent.name), asset_attempt_token=directory.name,
                asset_status="ingesting", asset_lease_until__gt=now,
            ).exists()
            if not active:
                shutil.rmtree(directory, ignore_errors=True)
    return len(ids)
