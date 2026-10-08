from rest_framework import serializers

from apps.studio.models import Export, Project


class ExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=Project.Format.choices, required=False)
    burn_captions = serializers.BooleanField(default=True)
    caption_track_id = serializers.IntegerField(min_value=1, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Request must be an object.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        if "burn_captions" in data and not isinstance(data["burn_captions"], bool):
            raise serializers.ValidationError({"burn_captions": ["Must be a boolean."]})
        if "caption_track_id" in data and (
            isinstance(data["caption_track_id"], bool) or not isinstance(data["caption_track_id"], int)
        ):
            raise serializers.ValidationError({"caption_track_id": ["Must be an integer."]})
        return super().to_internal_value(data)


class ExportSerializer(serializers.ModelSerializer):
    video_available = serializers.SerializerMethodField()
    subtitles_available = serializers.SerializerMethodField()

    def get_video_available(self, obj):
        return obj.status == Export.Status.COMPLETED and bool(obj.output_path)

    def get_subtitles_available(self, obj):
        return obj.status == Export.Status.COMPLETED and bool(obj.subtitle_path)

    class Meta:
        model = Export
        fields = [
            "id", "project_id", "status", "format", "settings", "error_code", "error_message",
            "video_available", "subtitles_available", "created_at", "updated_at",
        ]
        read_only_fields = fields
