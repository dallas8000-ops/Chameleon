from __future__ import annotations

from django.db import IntegrityError, transaction
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import WorkspaceMembership
from apps.accounts.views import error_response
from apps.studio.models import Asset, CaptionTrack, Project
from apps.studio.serializers import (
    AssetSerializer,
    AssetUploadSerializer,
    CaptionCreateSerializer,
    CaptionSerializer,
    CaptionUpdateSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    ProjectSerializer,
    SceneSerializer,
    SceneWriteSerializer,
)
from apps.studio.services import AssetRejected, AssetService, ProjectService, SceneService


def not_found() -> Response:
    return error_response(code="not_found", message="Not found.", errors=None, status_code=404)


def read_only() -> Response:
    return error_response(
        code="workspace_read_only",
        message="Your role cannot modify this workspace.",
        errors=None,
        status_code=403,
    )


def invalid(serializer) -> Response:
    return error_response(
        code="validation_error",
        message="Invalid request.",
        errors=serializer.errors,
        status_code=400,
    )


class StudioView(APIView):
    permission_classes = [permissions.IsAuthenticated]


class ProjectListCreateView(StudioView):
    def get(self, request):
        projects = ProjectService.visible_to(request.user)
        workspace_id = request.query_params.get("workspace_id")
        if workspace_id is not None:
            if not workspace_id.isdigit():
                return error_response(
                    code="validation_error",
                    message="Invalid request.",
                    errors={"workspace_id": ["A valid integer is required."]},
                    status_code=400,
                )
            projects = projects.filter(workspace_id=int(workspace_id))
        return Response(ProjectSerializer(projects, many=True).data)

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        data = serializer.validated_data
        role = ProjectService.role_in_workspace(request.user, data["workspace_id"])
        if role is None:
            return not_found()
        if role not in (WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.EDITOR):
            return read_only()
        project = Project.objects.create(
            workspace_id=data["workspace_id"], title=data["title"].strip(), format=data["format"]
        )
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ProjectDetailView(StudioView):
    def get(self, request, project_id):
        project = ProjectService.detail_queryset(request.user).filter(id=project_id).first()
        if project is None:
            return not_found()
        return Response(ProjectDetailSerializer(project).data)


class SceneCreateView(StudioView):
    def post(self, request, project_id):
        project = ProjectService.visible_to(request.user).filter(id=project_id).first()
        if project is None:
            return not_found()
        if not ProjectService.can_write(request.user, project.workspace_id):
            return read_only()
        serializer = SceneWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        scene = SceneService.create(project, serializer.validated_data)
        return Response(SceneSerializer(scene).data, status=status.HTTP_201_CREATED)


class SceneDetailView(StudioView):
    def patch(self, request, scene_id):
        scene = ProjectService.get_scene(request.user, scene_id)
        if scene is None:
            return not_found()
        if not ProjectService.can_write(request.user, scene.project.workspace_id):
            return read_only()
        serializer = SceneWriteSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return invalid(serializer)
        scene = SceneService.update(scene, serializer.validated_data)
        return Response(SceneSerializer(scene).data)

    def get(self, request, scene_id):
        scene = ProjectService.get_scene(request.user, scene_id)
        if scene is None:
            return not_found()
        return Response(SceneSerializer(scene).data)


class CaptionCreateView(StudioView):
    def post(self, request, project_id):
        project = ProjectService.visible_to(request.user).filter(id=project_id).first()
        if project is None:
            return not_found()
        if not ProjectService.can_write(request.user, project.workspace_id):
            return read_only()
        serializer = CaptionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                caption = CaptionTrack.objects.create(project=project, **data)
        except IntegrityError:
            return error_response(
                code="validation_error",
                message="Invalid request.",
                errors={"language": ["A caption track for this language already exists."]},
                status_code=400,
            )
        return Response(CaptionSerializer(caption).data, status=status.HTTP_201_CREATED)


class CaptionDetailView(StudioView):
    def get(self, request, caption_id):
        caption = ProjectService.get_caption(request.user, caption_id)
        if caption is None:
            return not_found()
        return Response(CaptionSerializer(caption).data)

    def patch(self, request, caption_id):
        caption = ProjectService.get_caption(request.user, caption_id)
        if caption is None:
            return not_found()
        if not ProjectService.can_write(request.user, caption.project.workspace_id):
            return read_only()
        serializer = CaptionUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        for field, value in serializer.validated_data.items():
            setattr(caption, field, value)
        caption.save(update_fields=[*serializer.validated_data, "updated_at"])
        return Response(CaptionSerializer(caption).data)


class AssetListCreateView(StudioView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        assets = AssetService.visible_to(request.user)
        workspace_id = request.query_params.get("workspace_id")
        if workspace_id is not None:
            if not workspace_id.isdigit():
                return error_response(
                    code="validation_error",
                    message="Invalid request.",
                    errors={"workspace_id": ["A valid integer is required."]},
                    status_code=400,
                )
            assets = assets.filter(workspace_id=int(workspace_id))
        return Response(AssetSerializer(assets, many=True).data)

    def post(self, request):
        serializer = AssetUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        data = serializer.validated_data
        role = ProjectService.role_in_workspace(request.user, data["workspace_id"])
        if role is None:
            return not_found()
        if not ProjectService.can_write(request.user, data["workspace_id"]):
            return read_only()
        try:
            asset = AssetService.create_from_upload(
                user=request.user,
                workspace_id=data["workspace_id"],
                uploaded=data["file"],
                name=data.get("name"),
            )
        except AssetRejected as exc:
            return error_response(
                code="validation_error",
                message="Invalid request.",
                errors={"file": [str(exc)]},
                status_code=400,
            )
        return Response(AssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class AssetDetailView(StudioView):
    def get(self, request, asset_id):
        asset = AssetService.visible_to(request.user).filter(id=asset_id).first()
        if asset is None:
            return not_found()
        return Response(AssetSerializer(asset).data)
