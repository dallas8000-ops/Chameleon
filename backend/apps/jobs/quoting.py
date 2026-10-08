from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.jobs.models import GenerationJob, GenerationQuote
from apps.studio.models import Project
from apps.studio.services import ProjectService

SOURCE = "https://docs.magichour.ai/api-reference/models.md"
PARAMETERS = {"model": "z-image-turbo", "resolution": "640px", "image_count": 1, "tool": "general"}


class ContractError(Exception):
    def __init__(self, code, message, status=409, *, submission_not_accepted=False):
        self.code, self.message, self.status = code, message, status
        self.submission_not_accepted = submission_not_accepted


def validate_scope(user, payload, *, write=True):
    role = ProjectService.role_in_workspace(user, payload["workspace_id"])
    if role is None:
        raise ContractError("not_found", "Not found.", 404)
    if write and not ProjectService.can_write(user, payload["workspace_id"]):
        raise ContractError("workspace_read_only", "Your role cannot modify this workspace.", 403)
    project_id, scene_id = payload.get("project_id"), payload.get("scene_id")
    if project_id and not Project.objects.filter(pk=project_id, workspace_id=payload["workspace_id"]).exists():
        raise ContractError("not_found", "Not found.", 404)
    if scene_id:
        scene = ProjectService.get_scene(user, scene_id)
        if scene is None or scene.project_id != project_id or scene.project.workspace_id != payload["workspace_id"]:
            raise ContractError("not_found", "Not found.", 404)
    return role


def active_tariff():
    config = getattr(settings, "GENERATION_IMAGE_TARIFF", {})
    try:
        verified = parse_datetime(config["verified_at"])
        until = parse_datetime(config["valid_until"])
        if (
            config.get("enabled") is not True
            or not isinstance(config.get("version"), str) or not 0 < len(config["version"]) <= 80
            or not config["version"].strip()
            or not isinstance(config.get("verified_by"), str) or not 0 < len(config["verified_by"]) <= 200
            or not config["verified_by"].strip()
            or isinstance(config["credits"], bool) or not isinstance(config["credits"], int)
            or config["credits"] != 5 or not verified or not until
            or timezone.is_naive(verified) or timezone.is_naive(until)
            or not verified <= timezone.now() < until
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ContractError("pricing_unavailable", "Verified image pricing is unavailable.") from None
    if not getattr(settings, "MAGIC_HOUR_API_KEY", ""):
        raise ContractError("provider_not_configured", "Configure Magic Hour on the server before generation.")
    from apps.jobs.downloads import authorized_origins
    if not authorized_origins():
        raise ContractError("download_origins_unavailable", "Private result download origins are not configured.")
    if getattr(settings, "GENERATION_STORAGE_CONFIRMED", False) is not True:
        raise ContractError("storage_unavailable", "Durable private result storage is not confirmed.")
    if GenerationJob.objects.filter(
        accepted_quote__pricing_version=config["version"], provider_reported_credits__isnull=False,
    ).exclude(provider_reported_credits=F("quoted_credits")).exists():
        raise ContractError("pricing_unavailable", "Observed charges differ from the tariff; operator review is required.")
    return {
        **PARAMETERS, "pricing_version": config["version"], "estimated_credits": config["credits"],
        "basis": {"kind": "operator_verified_documented_tariff", "description":
                  "One z-image-turbo image at 640px; operator-verified documented tariff. Estimate, not a guaranteed maximum.",
                  "source_urls": [SOURCE], "verified_at": verified.isoformat()},
        "valid_until": until.isoformat(),
    }


def create_quote(user, payload):
    validate_scope(user, payload)
    snapshot = active_tariff()
    expires = min(timezone.now() + timedelta(minutes=5), parse_datetime(snapshot["valid_until"]))
    return GenerationQuote.objects.create(
        requested_by=user, workspace_id=payload["workspace_id"], payload=payload,
        snapshot=snapshot, expires_at=expires,
    )


def quote_projection(quote):
    return {
        "available": True, "quote_id": str(quote.id), "workspace_id": quote.workspace_id,
        "project_id": quote.payload.get("project_id"), "scene_id": quote.payload.get("scene_id"),
        "provider": "magic_hour", "capability": "image.generate",
        "parameters": {**PARAMETERS, "aspect_ratio": quote.payload["aspect_ratio"]},
        "estimated_credits": quote.snapshot["estimated_credits"], "unit": "provider_credits",
        "pricing_version": quote.snapshot["pricing_version"], "basis": quote.snapshot["basis"],
        "issued_at": quote.issued_at.isoformat(), "expires_at": quote.expires_at.isoformat(),
        "price_guaranteed": False,
    }


@transaction.atomic
def accept_quote(user, payload, quote_id, key):
    # Serializing on the membership also makes concurrent different quotes with the same key
    # resolve to one attempt. Every submit path takes this lock before creating jobs.
    from apps.accounts.models import WorkspaceMembership
    WorkspaceMembership.objects.select_for_update().filter(
        user=user, workspace_id=payload["workspace_id"],
    ).first()
    validate_scope(user, payload)
    existing = GenerationJob.objects.filter(
        workspace_id=payload["workspace_id"], requested_by=user, idempotency_key=key,
    ).first()
    if existing:
        if existing.payload != payload or existing.accepted_quote.get("quote_id") != str(quote_id):
            raise ContractError("idempotency_conflict", "This attempt already belongs to a different request.")
        return existing
    quote = GenerationQuote.objects.select_for_update().filter(
        pk=quote_id, requested_by=user, workspace_id=payload["workspace_id"],
    ).first()
    if quote is None:
        raise ContractError("not_found", "Not found.", 404)
    if quote.payload != payload:
        raise ContractError("quote_changed", "Inputs changed. Request and review a new quote.")
    if quote.job_id:
        return quote.job
    if quote.consumed_at:
        raise ContractError("tracking_unavailable", "This quote was already consumed; operator review is required.")
    if quote.expires_at <= timezone.now():
        raise ContractError("quote_expired", "Quote expired. Request and review a new quote.",
                            submission_not_accepted=True)
    current = active_tariff()
    if quote.snapshot != current:
        raise ContractError("quote_changed", "Pricing changed. Request and review a new quote.",
                            submission_not_accepted=True)
    job = GenerationJob.objects.create(
        workspace_id=payload["workspace_id"], project_id=payload.get("project_id"),
        scene_id=payload.get("scene_id"), requested_by=user, idempotency_key=key, payload=payload,
        capability="image.generate", provider_name="magic_hour", quoted_credits=current["estimated_credits"],
        accepted_quote={**quote_projection(quote), "requester_id": user.id}, dispatch_at=timezone.now(),
    )
    quote.job = job
    quote.consumed_at = timezone.now()
    quote.save(update_fields=["job", "consumed_at"])
    from apps.jobs.tasks import dispatch_submission
    transaction.on_commit(lambda: dispatch_submission(job.id))
    return job
