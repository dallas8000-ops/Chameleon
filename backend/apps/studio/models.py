from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import Workspace


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        EXPORTING = "exporting", "Exporting"
        FAILED = "failed", "Failed"

    class Format(models.TextChoices):
        VERTICAL = "9:16", "9:16"
        LANDSCAPE = "16:9", "16:9"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=180)
    format = models.CharField(max_length=16, choices=Format.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Scene(models.Model):
    class Kind(models.TextChoices):
        SCRIPT = "script", "Script"
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        PRESENTER = "presenter", "Presenter"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scenes")
    order_index = models.PositiveIntegerField()
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=120)
    script_text = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order_index", "id"]


class Asset(models.Model):
    class AssetType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="assets")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    asset_type = models.CharField(max_length=32, choices=AssetType.choices)
    name = models.CharField(max_length=180)
    # Server-generated key inside Django storage; never a client-supplied path or URL.
    storage_key = models.CharField(max_length=255, unique=True)
    content_type = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    provenance = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class CaptionTrack(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="captions")
    language = models.CharField(max_length=16)
    segments = models.JSONField(default=list)
    style = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "language"], name="unique_caption_language_per_project"),
        ]


class Export(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="exports")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED)
    format = models.CharField(max_length=16, choices=Project.Format.choices)
    # Private controlled-storage keys, never serialized to clients.
    output_path = models.CharField(max_length=255, blank=True)
    subtitle_path = models.CharField(max_length=255, blank=True)
    settings = models.JSONField(default=dict)
    manifest = models.JSONField(default=dict)
    attempts = models.PositiveSmallIntegerField(default=0)
    attempt_token = models.CharField(max_length=32, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    cleanup_keys = models.JSONField(default=list, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
