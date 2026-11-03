from django.conf import settings
from django.db import models

from apps.accounts.models import Workspace
from apps.studio.models import Asset, Project, Scene


class GenerationJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SUBMITTED = "submitted", "Waiting for a GPU"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    ACTIVE_STATUSES = (Status.QUEUED, Status.SUBMITTED, Status.RUNNING)

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="generation_jobs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    scene = models.ForeignKey(Scene, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    capability = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    params = models.JSONField(default=dict)
    provider_job_id = models.CharField(max_length=120, blank=True)
    submit_attempts = models.PositiveSmallIntegerField(default=0)
    poll_failures = models.PositiveSmallIntegerField(default=0)
    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    result_asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Small, whitelisted summary the worker reports (for example GPU details); never raw provider output.
    result = models.JSONField(default=dict, blank=True)
    delay_ms = models.PositiveBigIntegerField(null=True, blank=True)
    execution_ms = models.PositiveBigIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["workspace", "status"])]
