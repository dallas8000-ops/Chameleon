from rest_framework import serializers


class JobBaseSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)
    project_id = serializers.IntegerField(min_value=1, required=False, allow_null=True, default=None)
    scene_id = serializers.IntegerField(min_value=1, required=False, allow_null=True, default=None)


class ImageGenerationSerializer(JobBaseSerializer):
    prompt = serializers.CharField(max_length=4000, allow_blank=False)
    aspect_ratio = serializers.ChoiceField(choices=("1:1", "16:9", "9:16"), default="1:1")
    name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields) if isinstance(data, dict) else set()
        if unknown:
            raise serializers.ValidationError({field: ["Unsupported field."] for field in unknown})
        return super().to_internal_value(data)


class ImageSubmissionSerializer(ImageGenerationSerializer):
    quote_id = serializers.UUIDField()


class IngestionRetrySerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if data:
            raise serializers.ValidationError({"non_field_errors": ["No input fields are accepted."]})
        return {}


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
    provider_reported_credits = serializers.IntegerField(allow_null=True)
    asset_status = serializers.CharField()
    asset_error_code = serializers.CharField()
    asset_retryable = serializers.SerializerMethodField()
    accepted_quote = serializers.SerializerMethodField()
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
        data["result"] = (
            {"asset_id": instance.generated_asset_id}
            if instance.asset_status == "ready" and instance.generated_asset_id
            and instance.generated_asset.workspace_id == instance.workspace_id else {}
        )
        if not instance.accepted_quote:
            data["quoted_credits"] = None
        # Provider strings may contain URLs or signed tokens. Expose only curated local diagnostics.
        from apps.jobs.public import safe_job_error
        data["error_code"], data["error_message"] = safe_job_error(instance)
        # Do not serialize even legacy arbitrary URLs hidden inside JSON payloads.
        data.pop("payload", None)
        return data

    def get_asset_retryable(self, instance):
        return instance.asset_status == "failed" and instance.asset_error_code in {
            "result_download_failed", "result_storage_failed", "result_unavailable",
        }

    def get_accepted_quote(self, instance):
        return {key: value for key, value in instance.accepted_quote.items() if key in {
            "quote_id", "estimated_credits", "pricing_version", "parameters", "basis",
            "expires_at", "price_guaranteed",
        }}
