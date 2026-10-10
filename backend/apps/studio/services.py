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
from apps.studio.models import Asset, CaptionTrack, Character, Project, Scene
from apps.studio.script_import import EXPORT_SCENE_LIMIT, ScriptImportError, match_character, parse_script

WRITE_ROLES = {WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.EDITOR}

# Sniffed from file content; the declared Content-Type must agree.
SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", "png", Asset.AssetType.IMAGE),
    (b"\xff\xd8\xff", 0, "image/jpeg", "jpg", Asset.AssetType.IMAGE),
    (b"GIF8", 0, "image/gif", "gif", Asset.AssetType.IMAGE),
    (b"\x1a\x45\xdf\xa3", 0, "video/webm", "webm", Asset.AssetType.VIDEO),
    (b"ftyp", 4, "video/mp4", "mp4", Asset.AssetType.VIDEO),
    (b"ID3", 0, "audio/mpeg", "mp3", Asset.AssetType.AUDIO),
    (b"\xff\xfb", 0, "audio/mpeg", "mp3", Asset.AssetType.AUDIO),
    (b"\xff\xf3", 0, "audio/mpeg", "mp3", Asset.AssetType.AUDIO),
    (b"\xff\xf2", 0, "audio/mpeg", "mp3", Asset.AssetType.AUDIO),
]

# Browsers and tools label the same audio formats differently.
CONTENT_TYPE_ALIASES = {
    "audio/mpeg": {"audio/mp3"},
    "audio/wav": {"audio/x-wav", "audio/wave", "audio/vnd.wave"},
    "audio/mp4": {"audio/x-m4a", "audio/m4a"},
}


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
            character_id=data.get("character_id"),
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
        for field in ("kind", "title", "script_text", "config", "character_id"):
            if field in data:
                setattr(scene, field, data[field])
        scene.save()
        if "order_index" in data:
            siblings = list(Scene.objects.filter(project_id=scene.project_id).exclude(pk=scene.pk))
            SceneService._renumber(siblings, scene, min(data["order_index"], len(siblings)))
        scene.refresh_from_db()
        return scene

    @staticmethod
    @transaction.atomic
    def delete(scene: Scene) -> None:
        Project.objects.select_for_update().get(pk=scene.project_id)
        project_id = scene.project_id
        scene.delete()
        for index, item in enumerate(Scene.objects.filter(project_id=project_id).order_by("order_index", "id")):
            if item.order_index != index:
                Scene.objects.filter(pk=item.pk).update(order_index=index)

    @staticmethod
    def _renumber(siblings: list[Scene], scene: Scene, position: int) -> None:
        ordered = [s for s in siblings if s.pk != scene.pk]
        ordered.insert(position, scene)
        for index, item in enumerate(ordered):
            if item.order_index != index:
                Scene.objects.filter(pk=item.pk).update(order_index=index)


class CharacterService:
    @staticmethod
    def visible_to(user):
        return Character.objects.filter(workspace__memberships__user=user)

    @staticmethod
    def in_workspace(workspace_id: int, character_id: int | None) -> bool:
        return character_id is None or Character.objects.filter(pk=character_id, workspace_id=workspace_id).exists()

    @staticmethod
    def reference_is_valid(workspace_id: int, asset_id: int | None) -> bool:
        return asset_id is None or Asset.objects.filter(
            pk=asset_id, workspace_id=workspace_id, asset_type=Asset.AssetType.IMAGE,
        ).exists()


class AssetService:
    @staticmethod
    def visible_to(user):
        return Asset.objects.filter(workspace__memberships__user=user)

    @staticmethod
    def sniff(head: bytes):
        if head[4:8] == b"ftyp" and head[8:12] in (b"M4A ", b"M4B "):
            return "audio/mp4", "m4a", Asset.AssetType.AUDIO
        for magic, offset, content_type, ext, asset_type in SIGNATURES:
            if head[offset : offset + len(magic)] == magic:
                return content_type, ext, asset_type
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "image/webp", "webp", Asset.AssetType.IMAGE
        if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
            return "audio/wav", "wav", Asset.AssetType.AUDIO
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
        if declared != content_type and declared not in CONTENT_TYPE_ALIASES.get(content_type, set()):
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


class ScriptImportService:
    @staticmethod
    def _plan(workspace_id: int, script: str):
        episodes, characters = parse_script(script)
        existing = {c.name.lower(): c for c in Character.objects.filter(workspace_id=workspace_id)}
        names = list({*(c.name for c in characters), *(c.name for c in existing.values())})
        return episodes, characters, existing, names

    @classmethod
    def preview(cls, workspace_id: int, script: str) -> dict:
        episodes, characters, existing, names = cls._plan(workspace_id, script)
        warnings: list[str] = []
        episode_data = []
        for episode in episodes:
            scenes, unmatched = [], set()
            for scene in episode.scenes:
                matched = match_character(scene.speaker, names) if scene.speaker else None
                if scene.speaker and matched is None:
                    unmatched.add(scene.speaker)
                scenes.append({
                    "title": scene.title, "role": scene.role, "speaker": scene.speaker,
                    "character": matched, "text": scene.text,
                })
            over = len(episode.scenes) > EXPORT_SCENE_LIMIT
            if over:
                warnings.append(
                    f"Episode {episode.number} has {len(episode.scenes)} scenes; export supports at most {EXPORT_SCENE_LIMIT}."
                )
            if unmatched:
                warnings.append(f"Episode {episode.number}: no character for {', '.join(sorted(unmatched))}.")
            episode_data.append({
                "number": episode.number, "title": episode.title, "scene_count": len(episode.scenes),
                "over_export_limit": over, "scenes": scenes,
            })
        return {
            "characters": [
                {
                    "name": c.name, "role": c.role, "description": c.description, "face_prompt": c.face_prompt,
                    "negative_prompt": c.negative_prompt, "exists": c.name.lower() in existing,
                }
                for c in characters
            ],
            "episodes": episode_data,
            "warnings": warnings,
        }

    @classmethod
    @transaction.atomic
    def create(cls, workspace_id: int, script: str, project_format: str, episode_numbers, create_characters: bool) -> dict:
        episodes, characters, existing, names = cls._plan(workspace_id, script)
        if episode_numbers is not None:
            available = {e.number for e in episodes}
            missing = sorted(set(episode_numbers) - available)
            if missing:
                raise ScriptImportError(f"Episode {missing[0]} is not in the script.")
            episodes = [e for e in episodes if e.number in set(episode_numbers)]
        if not episodes:
            raise ScriptImportError("Select at least one episode.")
        ids = {name: character.id for name, character in existing.items()}
        created = []
        if create_characters:
            for parsed in characters:
                if parsed.name.lower() in ids:
                    continue
                character = Character.objects.create(
                    workspace_id=workspace_id, name=parsed.name[:120],
                    role=parsed.role if len(parsed.role) <= 120 else parsed.role[:119].rstrip() + "…",
                    description=parsed.description[:5000], face_prompt=parsed.face_prompt[:5000],
                    negative_prompt=parsed.negative_prompt[:2000],
                )
                ids[character.name.lower()] = character.id
                created.append(character.name)
        projects = []
        for episode in episodes:
            project = Project.objects.create(
                workspace_id=workspace_id, title=f"Ep {episode.number}: {episode.title}"[:180], format=project_format,
            )
            scenes = []
            for index, scene in enumerate(episode.scenes):
                matched = match_character(scene.speaker, list(ids)) if scene.speaker else None
                config = {"source": "script_import", "episode": episode.number, "role": scene.role}
                for key, value in (("speaker", scene.speaker), ("delivery", scene.delivery), ("location", scene.location)):
                    if value:
                        config[key] = value
                if scene.on_screen:
                    config["on_screen_text"] = scene.text
                scenes.append(Scene(
                    project=project, order_index=index, kind=Scene.Kind.SCRIPT, title=scene.title[:120],
                    script_text=scene.text, config=config, character_id=ids.get(matched.lower()) if matched else None,
                ))
            Scene.objects.bulk_create(scenes)
            projects.append({"id": project.id, "title": project.title, "scene_count": len(scenes)})
        return {"projects": projects, "characters_created": created}
