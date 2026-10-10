from __future__ import annotations

import math
import re
from numbers import Real

from rest_framework import serializers

from apps.studio.models import Asset, CaptionTrack, Character, Project, Scene

MAX_JSON_BYTES = 10_000
MAX_SEGMENTS = 2000
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def validate_json_object(value, *, field: str):
    if not isinstance(value, dict):
        raise serializers.ValidationError(f"{field} must be an object.")
    if len(str(value)) > MAX_JSON_BYTES:
        raise serializers.ValidationError(f"{field} is too large.")
    return value


MAX_OVERLAYS = 5
MAX_SCENE_SECONDS = 600
OVERLAY_POSITIONS = ("top", "center", "bottom")
OVERLAY_SIZES = ("small", "medium", "large")


def _number(value, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise serializers.ValidationError({field: ["Must be a number."]})
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise serializers.ValidationError({field: [f"Must be between {minimum:g} and {maximum:g}."]})
    return number


def validate_overlays(value) -> list[dict]:
    if not isinstance(value, list):
        raise serializers.ValidationError({"overlays": ["Must be a list."]})
    if len(value) > MAX_OVERLAYS:
        raise serializers.ValidationError({"overlays": [f"At most {MAX_OVERLAYS} text overlays per scene."]})
    cleaned = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise serializers.ValidationError({"overlays": [f"Overlay {index + 1} must be an object."]})
        unknown = set(raw) - {"text", "start", "end", "position", "size"}
        if unknown:
            raise serializers.ValidationError({"overlays": [f"Overlay {index + 1} has unknown fields: {sorted(unknown)}."]})
        text = raw.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 140:
            raise serializers.ValidationError({"overlays": [f"Overlay {index + 1} text must be 1 to 140 characters."]})
        start = _number(raw.get("start", 0), "overlays", minimum=0, maximum=MAX_SCENE_SECONDS)
        end = _number(raw.get("end"), "overlays", minimum=0.1, maximum=MAX_SCENE_SECONDS)
        if end <= start:
            raise serializers.ValidationError({"overlays": [f"Overlay {index + 1} must end after it starts."]})
        position = raw.get("position", "center")
        size = raw.get("size", "medium")
        if position not in OVERLAY_POSITIONS or size not in OVERLAY_SIZES:
            raise serializers.ValidationError({"overlays": [f"Overlay {index + 1} has an unsupported position or size."]})
        cleaned.append({"text": text.strip(), "start": start, "end": end, "position": position, "size": size})
    return cleaned


def validate_scene_config(value) -> dict:
    """Validates the render-related keys of a scene config; other keys are kept untouched."""
    config = dict(validate_json_object(value, field="config"))
    for key in ("trim_start", "trim_end", "audio_asset_id", "fit_to_audio"):
        if key in config and config[key] is None:
            del config[key]
    if "trim_start" in config:
        config["trim_start"] = _number(config["trim_start"], "trim_start", minimum=0, maximum=MAX_SCENE_SECONDS)
    if "trim_end" in config:
        config["trim_end"] = _number(config["trim_end"], "trim_end", minimum=0.1, maximum=MAX_SCENE_SECONDS)
        if config["trim_end"] <= config.get("trim_start", 0):
            raise serializers.ValidationError({"trim_end": ["Must be after the trim start."]})
    if "audio_asset_id" in config and (
        isinstance(config["audio_asset_id"], bool) or not isinstance(config["audio_asset_id"], int) or config["audio_asset_id"] < 1
    ):
        raise serializers.ValidationError({"audio_asset_id": ["Must be a positive integer."]})
    for key in ("audio_volume", "clip_volume"):
        if key in config:
            config[key] = _number(config[key], key, minimum=0, maximum=2)
    if "audio_start" in config:
        config["audio_start"] = _number(config["audio_start"], "audio_start", minimum=0, maximum=MAX_SCENE_SECONDS)
    if "fit_to_audio" in config and not isinstance(config["fit_to_audio"], bool):
        raise serializers.ValidationError({"fit_to_audio": ["Must be true or false."]})
    if "overlays" in config:
        config["overlays"] = validate_overlays(config["overlays"])
    return config


class ProjectCreateSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=180)
    format = serializers.ChoiceField(choices=Project.Format.choices)


class SceneSerializer(serializers.ModelSerializer):
    character_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Scene
        fields = ["id", "project_id", "order_index", "kind", "title", "script_text", "config", "character_id"]
        read_only_fields = fields


class SceneWriteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Scene.Kind.choices)
    title = serializers.CharField(max_length=120)
    script_text = serializers.CharField(allow_blank=True, max_length=20000, required=False)
    config = serializers.JSONField(required=False)
    order_index = serializers.IntegerField(min_value=0, required=False)
    character_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)

    def validate_config(self, value):
        return validate_scene_config(value)


class CharacterSerializer(serializers.ModelSerializer):
    workspace_id = serializers.IntegerField(read_only=True)
    reference_asset_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Character
        fields = [
            "id", "workspace_id", "name", "role", "description", "face_prompt", "negative_prompt",
            "voice_notes", "reference_asset_id", "created_at", "updated_at",
        ]
        read_only_fields = fields


class CharacterWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    role = serializers.CharField(max_length=120, allow_blank=True, required=False)
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    face_prompt = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    negative_prompt = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    voice_notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    reference_asset_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value


class CharacterCreateSerializer(CharacterWriteSerializer):
    workspace_id = serializers.IntegerField(min_value=1)


class ScriptImportSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)
    script = serializers.CharField(max_length=200_000, trim_whitespace=False)
    format = serializers.ChoiceField(choices=Project.Format.choices, default=Project.Format.VERTICAL)
    dry_run = serializers.BooleanField(default=True)
    create_characters = serializers.BooleanField(default=True)
    episodes = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_null=True, max_length=30,
    )


class CaptionSegmentSerializer(serializers.Serializer):
    start = serializers.FloatField(min_value=0)
    end = serializers.FloatField(min_value=0)
    text = serializers.CharField(max_length=500)

    def validate(self, attrs):
        for key in ("start", "end"):
            if not math.isfinite(attrs[key]):
                raise serializers.ValidationError({key: "Must be a finite number."})
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "Must be greater than start."})
        return attrs


def validate_segments(value):
    if not isinstance(value, list):
        raise serializers.ValidationError("segments must be a list.")
    if len(value) > MAX_SEGMENTS:
        raise serializers.ValidationError(f"At most {MAX_SEGMENTS} segments are allowed.")
    cleaned = []
    previous_end = 0.0
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise serializers.ValidationError({index: "Segment must be an object."})
        for key in ("start", "end"):
            if isinstance(raw.get(key), bool) or not isinstance(raw.get(key), Real):
                raise serializers.ValidationError({index: {key: "Must be a number."}})
            try:
                if not math.isfinite(float(raw[key])):
                    raise serializers.ValidationError({index: {key: "Must be a finite number."}})
            except OverflowError:
                raise serializers.ValidationError({index: {key: "Must be a finite number."}}) from None
        unknown = set(raw) - {"start", "end", "text"}
        if unknown:
            raise serializers.ValidationError({index: f"Unknown fields: {sorted(unknown)}."})
        serializer = CaptionSegmentSerializer(data=raw)
        if not serializer.is_valid():
            raise serializers.ValidationError({index: serializer.errors})
        segment = {key: serializer.validated_data[key] for key in ("start", "end", "text")}
        if segment["start"] < previous_end:
            raise serializers.ValidationError({index: {"start": "Segments must be ordered and must not overlap."}})
        previous_end = segment["end"]
        cleaned.append(segment)
    return cleaned


class CaptionCreateSerializer(serializers.Serializer):
    language = serializers.CharField(max_length=16)
    segments = serializers.JSONField(required=False, default=list)
    style = serializers.JSONField(required=False, default=dict)

    def validate_language(self, value):
        value = value.strip()
        if not LANGUAGE_RE.match(value):
            raise serializers.ValidationError("Must be a language tag such as 'en' or 'pt-BR'.")
        return value

    def validate_segments(self, value):
        return validate_segments(value)

    def validate_style(self, value):
        return validate_json_object(value, field="style")


class CaptionUpdateSerializer(serializers.Serializer):
    segments = serializers.JSONField(required=False)
    style = serializers.JSONField(required=False)

    def validate_segments(self, value):
        return validate_segments(value)

    def validate_style(self, value):
        return validate_json_object(value, field="style")

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide segments or style.")
        return attrs


class CaptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaptionTrack
        fields = ["id", "project_id", "language", "segments", "style", "updated_at"]
        read_only_fields = fields


class ProjectSerializer(serializers.ModelSerializer):
    workspace_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = ["id", "workspace_id", "title", "format", "status", "ai_disclosure", "created_at", "updated_at"]
        read_only_fields = fields


class ProjectUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=180, required=False)
    ai_disclosure = serializers.BooleanField(required=False)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide title or ai_disclosure.")
        return attrs


class ProjectDetailSerializer(ProjectSerializer):
    scenes = SceneSerializer(many=True, read_only=True)
    captions = CaptionSerializer(many=True, read_only=True)

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ["scenes", "captions"]
        read_only_fields = fields


class AssetSerializer(serializers.ModelSerializer):
    workspace_id = serializers.IntegerField(read_only=True)
    source = serializers.SerializerMethodField()

    def get_source(self, obj):
        source = obj.provenance.get("source") if isinstance(obj.provenance, dict) else None
        return source if source in ("upload", "generation") else "unknown"

    class Meta:
        model = Asset
        fields = ["id", "workspace_id", "asset_type", "source", "name", "content_type", "size_bytes", "created_at"]
        read_only_fields = fields


class AssetUploadSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=180, required=False, allow_blank=False)
    file = serializers.FileField(allow_empty_file=False)
