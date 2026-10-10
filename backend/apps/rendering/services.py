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

from apps.studio.models import Asset, CaptionTrack, Export, Project
from apps.studio.serializers import validate_scene_config, validate_segments

MAX_SCENES = 20
MAX_DURATION = 600
MAX_BYTES = 250 * 1024 * 1024
RENDER_SECONDS = 600
MEDIA_FORMATS = "mov,matroska,webm,image2,png_pipe,jpeg_pipe,gif,webp_pipe,mp3,wav"
OVERLAY_FONT = "DejaVu Sans"
OVERLAY_SIZES = {"small": 48, "medium": 72, "large": 104}
OVERLAY_MARGINS = {"top": (8, 140), "center": (5, 0), "bottom": (2, 330)}
AI_LABEL_TEXT = "AI-generated characters"


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
        rf"workspaces/{workspace_id}/assets/[A-Za-z0-9_-]+\.(png|jpg|jpeg|gif|webp|mp4|webm|mp3|wav|m4a)", key,
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
        "burn_ai_label": data.get("burn_ai_label", False),
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
        config = validate_scene_config(config)
        asset_id = config.get("asset_id")
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
        is_image = asset.asset_type == Asset.AssetType.IMAGE
        entry = {
            "scene_id": scene.id, "asset_id": asset.id, "storage_key": asset.storage_key,
            "asset_type": asset.asset_type,
            "duration_seconds": image_duration(config.get("duration_seconds", 5)) if is_image else None,
            "trim_start": 0.0 if is_image else config.get("trim_start", 0.0),
            "trim_end": None if is_image else config.get("trim_end"),
            "fit_to_audio": bool(is_image and config.get("fit_to_audio", False)),
            "clip_volume": config.get("clip_volume", 1.0),
            "overlays": config.get("overlays", []),
            "audio": None,
        }
        audio_id = config.get("audio_asset_id")
        if audio_id is not None:
            audio = Asset.objects.filter(
                pk=audio_id, workspace_id=project.workspace_id, asset_type=Asset.AssetType.AUDIO,
            ).first()
            if audio is None:
                raise ExportNotFound
            entry["audio"] = {
                "asset_id": audio.id, "storage_key": audio.storage_key,
                "volume": config.get("audio_volume", 1.0), "start": config.get("audio_start", 0.0),
            }
        elif entry["fit_to_audio"]:
            raise serializers.ValidationError({"fit_to_audio": ["Choose a voice track to match its length."]})
        manifest["scenes"].append(entry)
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
    width: int = 1080, height: int = 1920, burn_ai_label: bool = False,
) -> list[str]:
    if (
        (width, height) not in ((1080, 1920), (1920, 1080))
        or not isinstance(burn_captions, bool) or not isinstance(burn_ai_label, bool)
    ):
        raise ExportFailure("export_invalid_settings", "Unsupported render settings.")
    if not 1 <= len(scene_paths) <= MAX_SCENES:
        raise ExportFailure("export_no_source", "At least one supported scene is required.")
    command = ffmpeg_base()
    for path in scene_paths:
        command.extend(["-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS, "-i", local_path(path)])
    inputs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(scene_paths)))
    graph = f"{inputs}concat=n={len(scene_paths)}:v=1:a=1[v][a]"
    current = "[v]"
    if burn_captions:
        graph += f";{current}subtitles=captions.srt[vcaptions]"
        current = "[vcaptions]"
    if burn_ai_label:
        graph += f";{current}ass=label.ass[vlabel]"
        current = "[vlabel]"
    command.extend([
        "-filter_complex", graph, "-map", current, "-map", "[a]",
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
    remaining = min(deadline - time.monotonic(), RENDER_SECONDS)
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


def probe_audio(path: Path, directory: Path, deadline: float) -> float:
    result = run_process([
        getattr(settings, "FFPROBE_BINARY", "ffprobe"), "-v", "error",
        "-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS,
        "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path),
    ], directory, deadline, capture=True)
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        if (
            not any(s.get("codec_type") == "audio" for s in data["streams"])
            or not math.isfinite(duration) or not 0 < duration <= MAX_DURATION
        ):
            raise ValueError
        return duration
    except (ValueError, KeyError, TypeError, IndexError, OverflowError):
        raise ExportFailure("export_invalid_media", "Voice track has invalid or unsupported media metadata.") from None


def ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def ass_text(text: str) -> str:
    # Braces and backslashes would be parsed as override codes, so they are dropped.
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f\x7f{}\\]", "", text).replace("\r", "")
    return r"\N".join(line.strip() for line in cleaned.split("\n") if line.strip())


def ass_document(width: int, height: int, events: list[tuple[float, float, int, int, int, str]]) -> str:
    """events: (start, end, alignment, margin_v, font_size, text)."""
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Default,{OVERLAY_FONT},72,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,1,2,"
        "90,90,160,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for start, end, alignment, margin, size, text in events:
        lines.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,{margin},,"
            f"{{\\an{alignment}\\fs{size}}}{ass_text(text)}"
        )
    return "\n".join(lines) + "\n"


def overlay_events(overlays: list[dict], duration: float) -> list[tuple[float, float, int, int, int, str]]:
    events = []
    for overlay in overlays:
        start = min(float(overlay["start"]), duration)
        end = min(float(overlay["end"]), duration)
        if end <= start or not ass_text(overlay["text"]):
            continue
        alignment, margin = OVERLAY_MARGINS[overlay["position"]]
        events.append((start, end, alignment, margin, OVERLAY_SIZES[overlay["size"]], overlay["text"]))
    return events


def copy_private(key: str, target: Path, budget: int, deadline: float) -> int:
    copied = 0
    try:
        with default_storage.open(key, "rb") as stored, target.open("wb") as handle:
            while chunk := stored.read(1024 * 1024):
                copied += len(chunk)
                if copied > budget:
                    raise ExportFailure("export_resource_limit", "Source media exceeds the export size limit.")
                if time.monotonic() > deadline:
                    raise ExportFailure("export_timeout", "The export exceeded its render time budget.")
                handle.write(chunk)
    except FileNotFoundError:
        raise ExportFailure("export_source_missing", "Source media is missing from private storage.") from None
    return copied


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
        total_bytes += copy_private(key, source, MAX_BYTES - total_bytes, deadline)
        is_image = scene["asset_type"] == Asset.AssetType.IMAGE
        duration, audio = probe(source, directory, deadline, image=is_image)

        voice = scene.get("audio")
        voice_path = None
        voice_duration = 0.0
        if voice:
            voice_asset = Asset.objects.filter(
                pk=voice["asset_id"], workspace_id=export.project.workspace_id,
                storage_key=voice["storage_key"], asset_type=Asset.AssetType.AUDIO,
            ).first()
            if voice_asset is None:
                raise ExportFailure("export_source_missing", "A snapshotted voice track is no longer available.")
            if not safe_storage_key(voice_asset.storage_key, export.project.workspace_id):
                raise ExportFailure("export_unsafe_source", "Voice tracks must use controlled workspace storage.")
            voice_path = directory / f"voice-{index}{Path(voice_asset.storage_key).suffix}"
            total_bytes += copy_private(voice_asset.storage_key, voice_path, MAX_BYTES - total_bytes, deadline)
            voice_duration = probe_audio(voice_path, directory, deadline)

        clip_start = 0.0
        if is_image:
            duration = image_duration(scene["duration_seconds"])
            if scene.get("fit_to_audio") and voice:
                duration = min(120.0, max(1.0, voice["start"] + voice_duration))
            audio = False
        else:
            clip_start = float(scene.get("trim_start") or 0.0)
            clip_end = min(float(scene.get("trim_end") or duration), duration)
            if clip_start >= duration or clip_end - clip_start < 0.1:
                raise ExportFailure("export_invalid_trim", "A video trim starts after the clip ends or is too short.")
            duration = clip_end - clip_start
        total_duration += duration
        if total_duration > MAX_DURATION:
            raise ExportFailure("export_resource_limit", "An export may contain at most 600 seconds of media.")

        video_filter = (
            f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
        )
        events = overlay_events(scene.get("overlays", []), duration)
        if events:
            (directory / f"overlays-{index}.ass").write_text(ass_document(width, height, events), encoding="utf-8")
            video_filter += f",ass=overlays-{index}.ass"

        output = directory / f"scene-{index}.mp4"
        command = ffmpeg_base()
        if is_image:
            command.extend(["-loop", "1"])
        elif clip_start:
            command.extend(["-ss", f"{clip_start:.3f}"])
        command.extend(["-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS, "-i", str(source)])
        base_audio = 0
        if not audio:
            command.extend(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
            base_audio = 1
        if voice_path is not None:
            command.extend(["-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS, "-i", str(voice_path)])
            voice_input = base_audio + 1
            delay = int(round(voice["start"] * 1000))
            graph = (
                f"[0:v:0]{video_filter}[v];"
                f"[{base_audio}:a:0]asetpts=PTS-STARTPTS,aresample=48000,volume={scene.get('clip_volume', 1.0)}[base];"
                f"[{voice_input}:a:0]asetpts=PTS-STARTPTS,aresample=48000,adelay={delay}|{delay},"
                f"volume={voice['volume']}[voice];"
                "[base][voice]amix=inputs=2:duration=longest:normalize=0,apad[aout]"
            )
            command.extend(["-filter_complex", graph, "-map", "[v]", "-map", "[aout]"])
        else:
            command.extend([
                "-map", "0:v:0", "-map", "0:a:0" if audio else "1:a:0", "-vf", video_filter,
                "-af", "asetpts=PTS-STARTPTS,aresample=48000,apad",
            ])
        command.extend(["-t", str(duration), *encoding_args(), "-fs", str(MAX_BYTES), str(output)])
        run_process(command, directory, deadline)
        verify_output(output)
        normalized_bytes += output.stat().st_size
        if normalized_bytes > MAX_BYTES:
            raise ExportFailure("export_resource_limit", "Intermediate media exceeds the export size limit.")
        staged.append(str(output))
        source.unlink()
        if voice_path is not None:
            voice_path.unlink()
    segments = manifest.get("captions", [])
    if segments and segments[-1]["end"] > total_duration:
        raise ExportFailure("export_invalid_captions", "Captions extend beyond the assembled video duration.")
    subtitles = directory / "captions.srt" if segments else None
    if subtitles:
        subtitles.write_bytes(subtitle_text(segments).encode("utf-8"))
    burn_label = bool(export.settings.get("burn_ai_label"))
    if burn_label:
        (directory / "label.ass").write_text(
            ass_document(width, height, [(0.0, total_duration + 1, 7, 60, OVERLAY_SIZES["small"] // 2, AI_LABEL_TEXT)]),
            encoding="utf-8",
        )
    output = directory / "export.mp4"
    command = build_ffmpeg_command(
        scene_paths=staged, output_path=str(output),
        burn_captions=bool(subtitles and export.settings["burn_captions"]), width=width, height=height,
        burn_ai_label=burn_label,
    )
    run_process(command, directory, deadline)
    verify_output(output)
    return output, subtitles
