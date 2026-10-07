from django.db import models
from django.db.models import Q

from apps.accounts.models import Workspace
from apps.studio.models import Project, Scene


class GenerationJob(models.Model):
    class Status(models.TextChoices):
        PENDING_PROVIDER = "pending_provider", "Pending provider"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"
        BLOCKED_PROVIDER_NOT_CONFIGURED = (
            "blocked_provider_not_configured",
            "Blocked: provider not configured",
        )

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="generation_jobs")
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="generation_jobs",
        null=True,
        blank=True,
    )
    scene = models.ForeignKey(
        Scene,
        on_delete=models.SET_NULL,
        related_name="generation_jobs",
        null=True,
        blank=True,
    )
    capability = models.CharField(max_length=64)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.PENDING_PROVIDER)
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict, blank=True)
    provider_name = models.CharField(max_length=64, blank=True)
    provider_job_id = models.CharField(max_length=120, blank=True)
    provider_submission_started_at = models.DateTimeField(null=True, blank=True)
    next_poll_at = models.DateTimeField(null=True, blank=True, db_index=True)
    poll_attempts = models.PositiveIntegerField(default=0)
    quoted_credits = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["workspace", "created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["provider_name", "provider_job_id"],
                condition=~Q(provider_job_id=""),
                name="unique_provider_job_identifier",
            ),
        ]


class ProviderEvent(models.Model):
    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name="provider_events")
    external_event_id = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "external_event_id"],
                name="unique_provider_event_per_job",
            ),
        ]


class UsageLedgerEntry(models.Model):
    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name="ledger_entries")
    external_event_id = models.CharField(max_length=160, unique=True)
    amount_credits = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
