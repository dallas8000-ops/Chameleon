from __future__ import annotations

import json
import math
import re
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import serializers

from apps.jobs.models import GenerationJob
from apps.studio.models import Asset, CaptionTrack, Export, Project
from apps.studio.serializers import validate_segments

MAX_SCENES = 20
MAX_DURATION = 600
MAX_BYTES = 250 * 1024 * 1024
RENDER_SECONDS = 600
MEDIA_FORMATS = "mov,matroska,webm,image2,png_pipe,jpeg_pipe,gif,webp_pipe"


class ExportFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ExportNotFound(Exception):
    pass


def valid_id(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def image_duration(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise serializers.ValidationError({"duration_seconds": ["Must be a number from 1 to 120."]})
    try:
        duration = float(value)
    except OverflowError:
        duration = math.inf
    if not math.isfinite(duration) or not 1 <= duration <= 120:
        raise serializers.ValidationError({"duration_seconds": ["Must be a number from 1 to 120."]})
    return duration


def safe_storage_key(key: str, workspace_id: int) -> bool:
    return bool(re.fullmatch(
        rf"workspaces/{workspace_id}/assets/[A-Za-z0-9_-]+\.(png|jpg|jpeg|gif|webp|mp4|webm)", key,
    ))


def snapshot_export(project: Project, data: dict) -> tuple[str, dict, dict]:
    caption_id = data.get("caption_track_id")
    if caption_id is not None:
        caption = CaptionTrack.objects.filter(project=project, pk=caption_id).first()
        if caption is None:
            raise ExportNotFound
    else:
        captions = list(project.captions.order_by("id")[:2])
        if len(captions) > 1:
            raise serializers.ValidationError({"caption_track_id": ["Select a caption track."]})
        caption = captions[0] if captions else None
    output_format = data.get("format", project.format)
    width, height = (1080, 1920) if output_format == "9:16" else (1920, 1080)
    export_settings = {
        "width": width, "height": height, "fps": 30, "video_codec": "libx264",
        "audio_codec": "aac", "burn_captions": data["burn_captions"],
        "caption_track_id": caption.id if caption else None,
    }
    scenes = list(project.scenes.order_by("order_index", "id")[:MAX_SCENES + 1])
    if len(scenes) > MAX_SCENES:
        raise serializers.ValidationError({"scenes": [f"At most {MAX_SCENES} scenes are supported."]})
    manifest = {"scenes": [], "captions": validate_segments(caption.segments) if caption else []}
    for scene in scenes:
        config = scene.config
        if not isinstance(config, dict):
            raise serializers.ValidationError({"scenes": ["Scene config must be an object."]})
        if set(config) & {"rendered_path", "path", "url", "storage_key", "overlay_asset_id"}:
            manifest["source_error"] = {
                "code": "export_unsafe_source",
                "message": "Use a workspace Asset as the full-frame source; paths, URLs and overlays are unsupported.",
            }
        asset_id = config.get("asset_id")
        if "generation_job_id" in config:
            job_id = config["generation_job_id"]
            if not valid_id(job_id):
                raise serializers.ValidationError({"generation_job_id": ["Must be a positive integer."]})
            job = GenerationJob.objects.filter(
                pk=job_id, workspace_id=project.workspace_id, project=project,
            ).first()
            if job is None:
                raise ExportNotFound
            if asset_id is not None:
                raise serializers.ValidationError({"scenes": ["Use asset_id or generation_job_id, not both."]})
            asset_id = job.result.get("asset_id") if isinstance(job.result, dict) else None
            if job.status != GenerationJob.Status.COMPLETED or not valid_id(asset_id):
                manifest["source_error"] = {
                    "code": "export_source_unavailable",
                    "message": "Generation must be completed and copied into a durable workspace Asset before export.",
                }
                continue
        if asset_id is None:
            continue
        if not valid_id(asset_id):
            raise serializers.ValidationError({"asset_id": ["Must be a positive integer."]})
        asset = Asset.objects.filter(pk=asset_id, workspace_id=project.workspace_id).first()
        if asset is None:
            raise ExportNotFound
        if asset.asset_type not in (Asset.AssetType.IMAGE, Asset.AssetType.VIDEO):
            raise serializers.ValidationError({"asset_id": ["A supported image or video is required."]})
        if asset.asset_type == Asset.AssetType.VIDEO and "duration_seconds" in config:
            raise serializers.ValidationError({"duration_seconds": ["Video duration is probed, not configurable."]})
        manifest["scenes"].append({
            "scene_id": scene.id, "asset_id": asset.id, "storage_key": asset.storage_key,
            "asset_type": asset.asset_type,
            "duration_seconds": image_duration(config.get("duration_seconds", 5))
            if asset.asset_type == Asset.AssetType.IMAGE else None,
        })
    # Do not silently omit an unrenderable scene from an otherwise successful video.
    if scenes and len(manifest["scenes"]) != len(scenes) and "source_error" not in manifest:
        manifest["source_error"] = {
            "code": "export_no_source", "message": "Every scene needs a supported workspace Asset before export.",
        }
    return output_format, export_settings, manifest


def local_path(value: str) -> str:
    path = Path(value)
    if not path.is_absolute() or "\x00" in value or "://" in value or ".." in path.parts:
        raise ExportFailure("export_unsafe_source", "Only staged local files may be rendered.")
    return str(path)


def build_ffmpeg_command(
    *, scene_paths: list[str], output_path: str, burn_captions: bool,
    width: int = 1080, height: int = 1920,
) -> list[str]:
    if (width, height) not in ((1080, 1920), (1920, 1080)) or not isinstance(burn_captions, bool):
        raise ExportFailure("export_invalid_settings", "Unsupported render settings.")
    if not 1 <= len(scene_paths) <= MAX_SCENES:
        raise ExportFailure("export_no_source", "At least one supported scene is required.")
    command = ffmpeg_base()
    for path in scene_paths:
        command.extend(["-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS, "-i", local_path(path)])
    inputs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(scene_paths)))
    graph = f"{inputs}concat=n={len(scene_paths)}:v=1:a=1[v][a]"
    if burn_captions:
        graph += ";[v]subtitles=captions.srt[vout]"
    command.extend([
        "-filter_complex", graph, "-map", "[vout]" if burn_captions else "[v]", "-map", "[a]",
        *encoding_args(), "-fs", str(MAX_BYTES), local_path(output_path),
    ])
    return command


def ffmpeg_base() -> list[str]:
    return [
        getattr(settings, "FFMPEG_BINARY", "ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error",
        "-y", "-threads", "2", "-filter_threads", "2", "-filter_complex_threads", "2",
    ]


def encoding_args() -> list[str]:
    return [
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-threads", "2",
        "-movflags", "+faststart",
    ]


def run_process(command: list[str], directory: Path, deadline: float, *, capture=False):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ExportFailure("export_timeout", "The export exceeded its render time budget.")
    try:
        return subprocess.run(
            command, cwd=str(directory), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False, check=True, timeout=min(remaining, 60 if capture else remaining),
        )
    except FileNotFoundError:
        raise ExportFailure("export_binary_missing", "FFmpeg and FFprobe must be installed on the export worker.") from None
    except subprocess.TimeoutExpired:
        raise ExportFailure("export_timeout", "The export exceeded its render time budget.") from None
    except subprocess.CalledProcessError:
        raise ExportFailure("export_process_failed", "FFmpeg could not process the source media.") from None


def probe(path: Path, directory: Path, deadline: float, *, image: bool = False) -> tuple[float, bool]:
    result = run_process([
        getattr(settings, "FFPROBE_BINARY", "ffprobe"), "-v", "error",
        "-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS,
        "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json", str(path),
    ], directory, deadline, capture=True)
    try:
        data = json.loads(result.stdout)
        duration = 5.0 if image else float(data["format"]["duration"])
        streams = data["streams"]
        videos = [s for s in streams if s.get("codec_type") == "video"]
        if not videos or not math.isfinite(duration) or not 0 < duration <= MAX_DURATION:
            raise ValueError
        width, height = int(videos[0]["width"]), int(videos[0]["height"])
        if not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 16_777_216:
            raise ValueError
        return duration, any(s.get("codec_type") == "audio" for s in streams)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError):
        raise ExportFailure("export_invalid_media", "Source video has invalid or unsupported media metadata.") from None


def subtitle_text(segments: list[dict]) -> str:
    def timestamp(seconds):
        milliseconds = round(seconds * 1000)
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, milliseconds = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"
    blocks = []
    for index, segment in enumerate(segments, 1):
        text = re.sub(r"<[^>]*>", "", segment["text"])
        text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text).replace("\r", "")
        text = "\n".join(line for line in text.splitlines() if line.strip())
        blocks.append(f"{index}\n{timestamp(segment['start'])} --> {timestamp(segment['end'])}\n{text}\n")
    return "\n".join(blocks)


def verify_output(path: Path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ExportFailure("export_output_missing", "FFmpeg produced no usable output.")
    if path.stat().st_size >= MAX_BYTES:
        raise ExportFailure("export_resource_limit", "The export exceeded its output size limit.")


def assemble_export(export: Export, directory: Path) -> tuple[Path, Path | None]:
    deadline = time.monotonic() + RENDER_SECONDS
    manifest = export.manifest
    if manifest.get("source_error"):
        error = manifest["source_error"]
        raise ExportFailure(error["code"], error["message"])
    scenes = manifest.get("scenes", [])
    if not scenes:
        raise ExportFailure("export_no_source", "Add a supported workspace Asset to every scene before export.")
    if len(scenes) > MAX_SCENES:
        raise ExportFailure("export_resource_limit", "Too many scenes for one export.")
    width, height = export.settings["width"], export.settings["height"]
    if (width, height) not in ((1080, 1920), (1920, 1080)):
        raise ExportFailure("export_invalid_settings", "Unsupported render dimensions.")
    total_bytes = 0
    total_duration = 0.0
    normalized_bytes = 0
    staged = []
    for index, scene in enumerate(scenes):
        asset = Asset.objects.filter(
            pk=scene["asset_id"], workspace_id=export.project.workspace_id,
            storage_key=scene["storage_key"], asset_type=scene["asset_type"],
        ).first()
        if asset is None:
            raise ExportFailure("export_source_missing", "A snapshotted source Asset is no longer available.")
        key = asset.storage_key
        if not safe_storage_key(key, export.project.workspace_id):
            raise ExportFailure("export_unsafe_source", "Source media must use controlled workspace storage.")
        source = directory / f"source-{index}{Path(key).suffix}"
        try:
            with default_storage.open(key, "rb") as stored, source.open("wb") as target:
                while chunk := stored.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_BYTES:
                        raise ExportFailure("export_resource_limit", "Source media exceeds the export size limit.")
                    if time.monotonic() > deadline:
                        raise ExportFailure("export_timeout", "The export exceeded its render time budget.")
                    target.write(chunk)
        except FileNotFoundError:
            raise ExportFailure("export_source_missing", "Source media is missing from private storage.") from None
        duration, audio = probe(source, directory, deadline, image=scene["asset_type"] == Asset.AssetType.IMAGE)
        if scene["asset_type"] == Asset.AssetType.IMAGE:
            duration = image_duration(scene["duration_seconds"])
            audio = False
        total_duration += duration
        if total_duration > MAX_DURATION:
            raise ExportFailure("export_resource_limit", "An export may contain at most 600 seconds of media.")
        output = directory / f"scene-{index}.mp4"
        command = ffmpeg_base()
        if scene["asset_type"] == Asset.AssetType.IMAGE:
            command.extend(["-loop", "1"])
        command.extend([
            "-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS, "-i", str(source),
        ])
        if not audio:
            command.extend(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
        command.extend([
            "-map", "0:v:0", "-map", "0:a:0" if audio else "1:a:0",
            "-vf", f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
            "-af", "asetpts=PTS-STARTPTS,aresample=48000,apad", "-t", str(duration), *encoding_args(),
            "-fs", str(MAX_BYTES), str(output),
        ])
        run_process(command, directory, deadline)
        verify_output(output)
        normalized_bytes += output.stat().st_size
        if normalized_bytes > MAX_BYTES:
            raise ExportFailure("export_resource_limit", "Intermediate media exceeds the export size limit.")
        staged.append(str(output))
        source.unlink()
    segments = manifest.get("captions", [])
    if segments and segments[-1]["end"] > total_duration:
        raise ExportFailure("export_invalid_captions", "Captions extend beyond the assembled video duration.")
    subtitles = directory / "captions.srt" if segments else None
    if subtitles:
        subtitles.write_bytes(subtitle_text(segments).encode("utf-8"))
    output = directory / "export.mp4"
    command = build_ffmpeg_command(
        scene_paths=staged, output_path=str(output),
        burn_captions=bool(subtitles and export.settings["burn_captions"]), width=width, height=height,
    )
    run_process(command, directory, deadline)
    verify_output(output)
    return output, subtitles
