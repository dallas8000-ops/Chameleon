from rest_framework import serializers


class JobBaseSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)
    project_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    scene_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class ImageGenerationSerializer(JobBaseSerializer):
    prompt = serializers.CharField(max_length=4000, allow_blank=False)
    aspect_ratio = serializers.ChoiceField(choices=("1:1", "16:9", "9:16"), default="1:1")
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)


class PresenterGenerationSerializer(JobBaseSerializer):
    script_text = serializers.CharField(max_length=20000, required=False, allow_blank=True)
    image_asset_id = serializers.IntegerField(min_value=1)
    audio_asset_id = serializers.IntegerField(min_value=1)
    start_seconds = serializers.FloatField(min_value=0)
    end_seconds = serializers.FloatField(min_value=0.1)
    generation_mode = serializers.ChoiceField(
        choices=("realistic", "prompted"),
        default="realistic",
    )
    prompt = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {field: ["Unsupported field. Use workspace-owned asset identifiers."] for field in unknown}
                )
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["end_seconds"] <= attrs["start_seconds"]:
            raise serializers.ValidationError({"end_seconds": "Must be greater than start_seconds."})
        max_duration = 45 if attrs["generation_mode"] == "prompted" else 300
        if attrs["end_seconds"] - attrs["start_seconds"] > max_duration:
            raise serializers.ValidationError(
                {"end_seconds": f"Clip duration cannot exceed {max_duration} seconds for this mode."}
            )
        if attrs.get("generation_mode") == "prompted" and not attrs.get("prompt"):
            raise serializers.ValidationError({"prompt": "A prompt is required for prompted generation."})
        return attrs


class GenerationJobSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    workspace_id = serializers.IntegerField()
    project_id = serializers.IntegerField(allow_null=True)
    scene_id = serializers.IntegerField(allow_null=True)
    capability = serializers.CharField()
    status = serializers.CharField()
    payload = serializers.JSONField()
    result = serializers.JSONField()
    provider_name = serializers.CharField()
    provider_job_id = serializers.CharField()
    quoted_credits = serializers.IntegerField()
    error_code = serializers.CharField()
    error_message = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.capability == "presenter.generate":
            data["payload"] = {
                key: value for key, value in data["payload"].items()
                if key in PresenterGenerationSerializer().fields
            }
        return data
