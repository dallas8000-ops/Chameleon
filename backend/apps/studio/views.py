from __future__ import annotations

import logging
import re

from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.http import FileResponse
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import WorkspaceMembership
from apps.accounts.views import error_response
from apps.studio.models import Asset, CaptionTrack, Export, Project
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
from apps.studio.upload_handlers import StudioUploadSizeLimitHandler

logger = logging.getLogger(__name__)

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


class ExportCreateView(StudioView):
    def post(self, request, project_id):
        from apps.rendering.serializers import ExportRequestSerializer, ExportSerializer
        from apps.rendering.services import ExportNotFound, snapshot_export
        from apps.rendering.tasks import queue_export_job
        from rest_framework.exceptions import ValidationError

        project = ProjectService.visible_to(request.user).filter(pk=project_id).first()
        if project is None:
            return not_found()
        if not ProjectService.can_write(request.user, project.workspace_id):
            return read_only()
        serializer = ExportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        try:
            with transaction.atomic():
                project = Project.objects.select_for_update().get(pk=project.pk)
                output_format, export_settings, manifest = snapshot_export(project, serializer.validated_data)
                export = Export.objects.create(
                    project=project, format=output_format, settings=export_settings, manifest=manifest,
                )
                transaction.on_commit(lambda: queue_export_job(project.id, export.id))
        except ExportNotFound:
            return not_found()
        except ValidationError as error:
            return error_response(
                code="validation_error", message="Invalid request.", errors=error.detail, status_code=400,
            )
        return Response(ExportSerializer(export).data, status=status.HTTP_201_CREATED)


class ExportDetailView(StudioView):
    def get(self, request, export_id):
        from apps.rendering.serializers import ExportSerializer

        export = Export.objects.filter(
            pk=export_id, project__workspace__memberships__user=request.user,
        ).first()
        if export is None:
            return not_found()
        return Response(ExportSerializer(export).data)


class ExportDownloadView(StudioView):
    def get(self, request, export_id, artifact):
        export = Export.objects.select_related("project").filter(
            pk=export_id, project__workspace__memberships__user=request.user,
            status=Export.Status.COMPLETED,
        ).first()
        if export is None:
            return not_found()
        key = export.output_path if artifact == "video" else export.subtitle_path
        extension = "mp4" if artifact == "video" else "srt"
        if not key:
            return not_found()
        if not re.fullmatch(
            rf"workspaces/{export.project.workspace_id}/exports/{export.id}/[a-f0-9]{{32}}\.{extension}", key,
        ):
            logger.error("Invalid private artifact key for export %s.", export.id)
            return error_response(
                code="export_storage_failed", message="The export artifact is unavailable.",
                errors=None, status_code=503,
            )
        try:
            stored = default_storage.open(key, "rb")
        except OSError:
            logger.exception("Private artifact read failed for export %s.", export.id)
            return error_response(
                code="export_storage_failed", message="The export artifact is unavailable.",
                errors=None, status_code=503,
            )
        response = FileResponse(
            stored, as_attachment=True, filename=f"export-{export.id}.{extension}",
            content_type="video/mp4" if artifact == "video" else "application/x-subrip",
        )
        response["Cache-Control"] = "private, no-store"
        return response


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

    def initialize_request(self, request, *args, **kwargs):
        request.upload_handlers.insert(0, StudioUploadSizeLimitHandler(request))
        return super().initialize_request(request, *args, **kwargs)

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
