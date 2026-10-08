from __future__ import annotations

from django.contrib.auth import get_user_model, password_validation
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Workspace, WorkspaceMembership


User = get_user_model()


class WorkspaceMembershipSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="workspace_id", read_only=True)
    name = serializers.CharField(source="workspace.name", read_only=True)
    slug = serializers.CharField(source="workspace.slug", read_only=True)

    class Meta:
        model = WorkspaceMembership
        fields = ["id", "name", "slug", "role"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    workspace_name = serializers.CharField(max_length=120)

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate_password(self, value: str) -> str:
        candidate = User(email=self.initial_data.get("email", ""))
        password_validation.validate_password(value, user=candidate)
        return value

    def validate_workspace_name(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Workspace name is required.")
        return cleaned

    @transaction.atomic
    def create(self, validated_data: dict[str, str]) -> WorkspaceMembership:
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
        )
        workspace = Workspace.objects.create(
            name=validated_data["workspace_name"],
            slug=Workspace.build_unique_slug(validated_data["workspace_name"]),
        )
        return WorkspaceMembership.objects.create(
            user=user,
            workspace=workspace,
            role=WorkspaceMembership.Role.OWNER,
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class WorkspaceUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=120)

    class Meta:
        model = Workspace
        fields = ["name"]

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Workspace name is required.")
        return cleaned

    def update(self, instance: Workspace, validated_data: dict[str, str]) -> Workspace:
        instance.name = validated_data["name"]
        instance.slug = Workspace.build_unique_slug(instance.name, exclude_pk=instance.pk)
        instance.save(update_fields=["name", "slug", "updated_at"])
        return instance
