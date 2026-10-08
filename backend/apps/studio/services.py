from __future__ import annotations

import os
import re
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max

from apps.accounts.models import WorkspaceMembership
from apps.studio.models import Asset, CaptionTrack, Project, Scene

WRITE_ROLES = {WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.EDITOR}

# Sniffed from file content; the declared Content-Type must agree.
SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", "png", Asset.AssetType.IMAGE),
    (b"\xff\xd8\xff", 0, "image/jpeg", "jpg", Asset.AssetType.IMAGE),
    (b"GIF8", 0, "image/gif", "gif", Asset.AssetType.IMAGE),
    (b"\x1a\x45\xdf\xa3", 0, "video/webm", "webm", Asset.AssetType.VIDEO),
    (b"ftyp", 4, "video/mp4", "mp4", Asset.AssetType.VIDEO),
]


class AssetRejected(Exception):
    pass


def max_upload_bytes() -> int:
    return getattr(settings, "STUDIO_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)


class ProjectService:
    @staticmethod
    def visible_to(user):
        return Project.objects.filter(workspace__memberships__user=user)

    @staticmethod
    def for_workspace(user, workspace_id):
        return ProjectService.visible_to(user).filter(workspace_id=workspace_id)

    @staticmethod
    def role_in_workspace(user, workspace_id) -> str | None:
        return (
            WorkspaceMembership.for_user(user)
            .filter(workspace_id=workspace_id)
            .values_list("role", flat=True)
            .first()
        )

    @classmethod
    def can_write(cls, user, workspace_id) -> bool:
        return cls.role_in_workspace(user, workspace_id) in WRITE_ROLES

    @staticmethod
    def detail_queryset(user):
        return ProjectService.visible_to(user).prefetch_related("scenes", "captions")

    @staticmethod
    def get_scene(user, scene_id) -> Scene | None:
        return Scene.objects.select_related("project").filter(
            id=scene_id, project__workspace__memberships__user=user
        ).first()

    @staticmethod
    def get_caption(user, caption_id) -> CaptionTrack | None:
        return CaptionTrack.objects.select_related("project").filter(
            id=caption_id, project__workspace__memberships__user=user
        ).first()


class SceneService:
    @staticmethod
    @transaction.atomic
    def create(project: Project, data: dict) -> Scene:
        Project.objects.select_for_update().get(pk=project.pk)
        siblings = list(Scene.objects.filter(project=project))
        scene = Scene(
            project=project,
            kind=data["kind"],
            title=data["title"],
            script_text=data.get("script_text", ""),
            config=data.get("config", {}),
            order_index=0,
        )
        scene.save()
        position = min(data.get("order_index", len(siblings)), len(siblings))
        SceneService._renumber(siblings, scene, position)
        scene.refresh_from_db()
        return scene

    @staticmethod
    @transaction.atomic
    def update(scene: Scene, data: dict) -> Scene:
        Project.objects.select_for_update().get(pk=scene.project_id)
        for field in ("kind", "title", "script_text", "config"):
            if field in data:
                setattr(scene, field, data[field])
        scene.save()
        if "order_index" in data:
            siblings = list(Scene.objects.filter(project_id=scene.project_id).exclude(pk=scene.pk))
            SceneService._renumber(siblings, scene, min(data["order_index"], len(siblings)))
        scene.refresh_from_db()
        return scene

    @staticmethod
    def _renumber(siblings: list[Scene], scene: Scene, position: int) -> None:
        ordered = [s for s in siblings if s.pk != scene.pk]
        ordered.insert(position, scene)
        for index, item in enumerate(ordered):
            if item.order_index != index:
                Scene.objects.filter(pk=item.pk).update(order_index=index)


class AssetService:
    @staticmethod
    def visible_to(user):
        return Asset.objects.filter(workspace__memberships__user=user)

    @staticmethod
    def sniff(head: bytes):
        for magic, offset, content_type, ext, asset_type in SIGNATURES:
            if head[offset : offset + len(magic)] == magic:
                return content_type, ext, asset_type
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "image/webp", "webp", Asset.AssetType.IMAGE
        return None

    @staticmethod
    def safe_name(raw: str) -> str:
        base = os.path.basename((raw or "").replace("\\", "/"))
        base = re.sub(r"[^\w .\-]", "_", base).strip(" .")
        return base[:180] or "upload"

    @classmethod
    def create_from_upload(cls, *, user, workspace_id, uploaded, name=None) -> Asset:
        if uploaded.size > max_upload_bytes():
            raise AssetRejected("File exceeds the maximum upload size.")
        head = uploaded.read(16)
        uploaded.seek(0)
        sniffed = cls.sniff(head)
        if sniffed is None:
            raise AssetRejected("Unsupported or unrecognised file type.")
        content_type, ext, asset_type = sniffed
        declared = (getattr(uploaded, "content_type", "") or "").split(";")[0].strip().lower()
        if declared != content_type:
            raise AssetRejected("Declared content type does not match file content.")
        original = cls.safe_name(uploaded.name)
        storage_key = f"workspaces/{workspace_id}/assets/{uuid.uuid4().hex}.{ext}"
        saved_key = default_storage.save(storage_key, ContentFile(uploaded.read()))
        try:
            return Asset.objects.create(
                workspace_id=workspace_id,
                created_by=user,
                asset_type=asset_type,
                name=(name or original)[:180],
                storage_key=saved_key,
                content_type=content_type,
                size_bytes=uploaded.size,
                provenance={"source": "upload", "uploaded_by": user.id, "original_filename": original},
            )
        except Exception:
            default_storage.delete(saved_key)
            raise
