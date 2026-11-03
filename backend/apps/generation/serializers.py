from rest_framework import serializers

from apps.generation.capabilities import CAPABILITIES
from apps.generation.models import GenerationJob


class JobSerializer(serializers.ModelSerializer):
    workspace_id = serializers.IntegerField(read_only=True)
    project_id = serializers.IntegerField(read_only=True)
    scene_id = serializers.IntegerField(read_only=True)
    result_asset_id = serializers.IntegerField(read_only=True)
    label = serializers.SerializerMethodField()

    def get_label(self, obj):
        capability = CAPABILITIES.get(obj.capability)
        return capability.label if capability else obj.capability

    class Meta:
        model = GenerationJob
        fields = [
            "id", "workspace_id", "project_id", "scene_id", "capability", "label", "status", "params",
            "result_asset_id", "result", "delay_ms", "execution_ms", "error_code", "error_message",
            "created_at", "finished_at",
        ]
        read_only_fields = fields


class JobCreateSerializer(serializers.Serializer):
    workspace_id = serializers.IntegerField(min_value=1)
    capability = serializers.CharField(max_length=64)
    params = serializers.JSONField(required=False, default=dict)
    project_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    scene_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate_params(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("params must be an object.")
        if len(str(value)) > 10_000:
            raise serializers.ValidationError("params is too large.")
        return value
