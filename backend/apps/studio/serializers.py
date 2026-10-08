from __future__ import annotations

import math
import re
from numbers import Real

from rest_framework import serializers

from apps.studio.models import Asset, CaptionTrack, Project, Scene

MAX_JSON_BYTES = 10_000
MAX_SEGMENTS = 2000
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def validate_json_object(value, *, field: str):
    if not isinstance(value, dict):
        raise serializers.ValidationError(f"{field} must be an object.")
    if len(str(value)) > MAX_JSON_BYTES:
        raise serializers.ValidationError(f"{field} is too large.")
    return value


class ProjectCreateSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=180)
    format = serializers.ChoiceField(choices=Project.Format.choices)


class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = ["id", "project_id", "order_index", "kind", "title", "script_text", "config"]
        read_only_fields = fields


class SceneWriteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Scene.Kind.choices)
    title = serializers.CharField(max_length=120)
    script_text = serializers.CharField(allow_blank=True, max_length=20000, required=False)
    config = serializers.JSONField(required=False)
    order_index = serializers.IntegerField(min_value=0, required=False)

    def validate_config(self, value):
        return validate_json_object(value, field="config")


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
        fields = ["id", "workspace_id", "title", "format", "status", "created_at", "updated_at"]
        read_only_fields = fields


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
