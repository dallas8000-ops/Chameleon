import hashlib
import hmac
import json
import time

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import WorkspaceMembership
from apps.accounts.views import error_response
from apps.jobs.models import GenerationJob
from apps.jobs.serializers import (
    GenerationJobSerializer,
    ImageGenerationSerializer,
    ImageSubmissionSerializer,
    IngestionRetrySerializer,
    PresenterGenerationSerializer,
)
from apps.jobs.services import (
    PresenterAssetInvalid,
    PresenterAssetNotFound,
    UnsupportedCapability,
    apply_provider_update,
    submit_generation_job,
)
from apps.studio.services import ProjectService
from apps.jobs.quoting import ContractError


def not_found() -> Response:
    return error_response(code="not_found", message="Not found.", errors=None, status_code=404)


def invalid(serializer) -> Response:
    return error_response(
        code="validation_error",
        message="Invalid request.",
        errors=serializer.errors,
        status_code=400,
    )


class GenerationJobView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, job_id):
        job = GenerationJob.objects.filter(
            id=job_id,
            workspace__memberships__user=request.user,
        ).first()
        if job is None:
            return not_found()
        response = Response(GenerationJobSerializer(job).data)
        response["Cache-Control"] = "private, no-store"
        return response


class MagicHourWebhookView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    max_body_bytes = 64 * 1024
    timestamp_tolerance_seconds = 300

    def post(self, request):
        secret = getattr(settings, "MAGIC_HOUR_WEBHOOK_SECRET", "")
        if not secret:
            return error_response(
                code="webhook_not_configured",
                message="Magic Hour webhook verification is not configured.",
                errors=None,
                status_code=503,
            )

        content_length = request.META.get("CONTENT_LENGTH")
        if content_length and content_length.isdigit() and int(content_length) > self.max_body_bytes:
            return error_response(
                code="invalid_webhook",
                message="Webhook payload is too large.",
                errors=None,
                status_code=413,
            )
        raw_body = request.body
        if len(raw_body) > self.max_body_bytes:
            return error_response(
                code="invalid_webhook",
                message="Webhook payload is too large.",
                errors=None,
                status_code=413,
            )

        timestamp = request.headers.get("magic-hour-event-timestamp", "")
        signature = request.headers.get("magic-hour-event-signature", "")
        try:
            timestamp_value = int(timestamp)
        except (TypeError, ValueError):
            timestamp_value = 0
        if (
            not signature
            or not timestamp_value
            or abs(time.time() - timestamp_value) > self.timestamp_tolerance_seconds
        ):
            return self._invalid_signature()
        signed_payload = timestamp.encode("ascii") + b"." + raw_body
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, signature):
            return self._invalid_signature()

        try:
            event = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response(
                code="invalid_webhook",
                message="Webhook payload must be valid JSON.",
                errors=None,
                status_code=400,
            )
        if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
            return error_response(
                code="invalid_webhook",
                message="Webhook event payload is invalid.",
                errors=None,
                status_code=400,
            )
        event_type = event.get("type")
        type_parts = event_type.split(".") if isinstance(event_type, str) else []
        if len(type_parts) != 2 or type_parts[0] not in {"image", "video"}:
            return error_response(
                code="invalid_webhook",
                message="Webhook event type is not supported.",
                errors=None,
                status_code=400,
            )
        state_by_event = {
            "started": GenerationJob.Status.PROCESSING,
            "completed": GenerationJob.Status.COMPLETED,
            "errored": GenerationJob.Status.FAILED,
        }
        mapped_status = state_by_event.get(type_parts[1])
        provider_job_id = event["payload"].get("id")
        if mapped_status is None or not isinstance(provider_job_id, str) or not provider_job_id:
            return error_response(
                code="invalid_webhook",
                message="Webhook event does not contain a supported job update.",
                errors=None,
                status_code=400,
            )
        job = GenerationJob.objects.filter(
            provider_name="magic_hour",
            provider_job_id=provider_job_id,
            capability="image.generate" if type_parts[0] == "image" else "presenter.generate",
        ).first()
        if job is None:
            return not_found()

        provider_error = event["payload"].get("error")
        if not isinstance(provider_error, dict):
            provider_error = {}
        credits = event["payload"].get("credits_charged")
        if isinstance(credits, bool) or not isinstance(credits, int) or credits < 0:
            credits = None
        result = {}
        downloads = event["payload"].get("downloads")
        if mapped_status == GenerationJob.Status.COMPLETED and isinstance(downloads, list) and downloads:
            result = {"downloads": downloads}
        updated_job = apply_provider_update(
            job_id=job.id,
            external_event_id=f"webhook:{event_type}:{provider_job_id}",
            status=mapped_status,
            result=result,
            error_code=(
                provider_error.get("code", "")
                if mapped_status == GenerationJob.Status.FAILED
                and isinstance(provider_error.get("code", ""), str)
                else ""
            ),
            error_message=(
                provider_error.get("message", "")
                if mapped_status == GenerationJob.Status.FAILED
                and isinstance(provider_error.get("message", ""), str)
                else ""
            ),
            amount_credits=credits if mapped_status == GenerationJob.Status.COMPLETED else None,
        )
        response = Response({"success": True, "id": updated_job.id, "status": updated_job.status})
        response["Cache-Control"] = "private, no-store"
        return response

    @staticmethod
    def _invalid_signature() -> Response:
        return error_response(
            code="invalid_webhook_signature",
            message="Webhook signature is invalid or expired.",
            errors=None,
            status_code=401,
        )


class GenerationSubmissionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = None
    capability = ""

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        data = serializer.validated_data
        role = ProjectService.role_in_workspace(request.user, data["workspace_id"])
        if role is None:
            return not_found()
        if role not in (WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.EDITOR):
            return error_response(
                code="workspace_read_only",
                message="Your role cannot modify this workspace.",
                errors=None,
                status_code=403,
            )

        project_id = data.get("project_id")
        if project_id is not None:
            project = ProjectService.for_workspace(request.user, data["workspace_id"]).filter(id=project_id).first()
            if project is None:
                return not_found()
        scene_id = data.get("scene_id")
        if scene_id is not None:
            scene = ProjectService.get_scene(request.user, scene_id)
            if scene is None or scene.project.workspace_id != data["workspace_id"]:
                return not_found()
            if project_id is None or scene.project_id != project_id:
                return not_found()

        try:
            job = submit_generation_job(
                workspace_id=data["workspace_id"],
                project_id=project_id,
                scene_id=scene_id,
                capability=self.capability,
                payload=data,
            )
        except PresenterAssetNotFound:
            return not_found()
        except PresenterAssetInvalid as error:
            return error_response(
                code="validation_error",
                message="Invalid presenter assets.",
                errors=error.errors,
                status_code=400,
            )
        except UnsupportedCapability as error:
            return error_response(
                code="capability_unavailable",
                message=str(error),
                errors=None,
                status_code=409,
            )

        serialized = GenerationJobSerializer(job).data
        if job.status == GenerationJob.Status.BLOCKED_PROVIDER_NOT_CONFIGURED:
            return Response(
                {
                    **serialized,
                    "code": "provider_not_configured",
                    "message": job.error_message,
                    "errors": {},
                },
                status=status.HTTP_409_CONFLICT,
            )
        if job.error_code == "job_queue_unavailable":
            return Response(
                {
                    **serialized,
                    "code": job.error_code,
                    "message": job.error_message,
                    "errors": {},
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(serialized, status=status.HTTP_202_ACCEPTED)


class ImageGenerationView(GenerationSubmissionView):
    serializer_class = ImageGenerationSerializer
    capability = "image.generate"

    def post(self, request):
        import re
        from apps.jobs.quoting import accept_quote
        serializer = ImageSubmissionSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
            return contract_response("validation_error", "A bounded Idempotency-Key is required.", 400)
        payload = dict(serializer.validated_data)
        quote_id = payload.pop("quote_id")
        try:
            job = accept_quote(request.user, payload, quote_id, key)
        except ContractError as error:
            response = contract_response(error.code, error.message, error.status)
            if error.submission_not_accepted:
                response.data["submission_not_accepted"] = True
            return response
        response = Response(GenerationJobSerializer(job).data, status=202)
        response["Cache-Control"] = "private, no-store"
        return response


def contract_response(code, message, status_code=409):
    response = error_response(code=code, message=message, errors={}, status_code=status_code)
    if code in {"quote_changed", "quote_expired"}:
        response.data["requires_requote"] = True
    response["Cache-Control"] = "private, no-store"
    return response


class ImageQuoteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "generation_quote"

    def post(self, request):
        from apps.jobs.quoting import create_quote, quote_projection
        if len(request.body) > 16 * 1024:
            return contract_response("validation_error", "Quote request is too large.", 413)
        serializer = ImageGenerationSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        try:
            quote = create_quote(request.user, dict(serializer.validated_data))
        except ContractError as error:
            response = contract_response(error.code, error.message, error.status)
            response.data.update({"available": False, "quote": None})
            return response
        response = Response(quote_projection(quote))
        response["Cache-Control"] = "private, no-store"
        return response


class GenerationCapabilitiesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.jobs.quoting import PARAMETERS, active_tariff, validate_scope
        workspace_id = request.query_params.get("workspace_id", "")
        if not workspace_id.isdigit() or int(workspace_id) < 1:
            return contract_response("validation_error", "A workspace ID is required.", 400)
        workspace_id = int(workspace_id)
        try:
            validate_scope(request.user, {"workspace_id": workspace_id}, write=False)
        except ContractError as error:
            return contract_response(error.code, error.message, error.status)
        try:
            version, reason = active_tariff()["pricing_version"], None
        except ContractError as error:
            version, reason = None, error.code
        response = Response({
            "workspace_id": workspace_id, "capabilities": [
                {"capability": "image.generate", "available": reason is None,
                 "can_submit": reason is None and ProjectService.can_write(request.user, workspace_id),
                 "reason_code": reason, "provider": "magic_hour", "pricing_version": version,
                 "supported_parameters": {**PARAMETERS, "aspect_ratios": ["1:1", "16:9", "9:16"]}},
                {"capability": "presenter.generate", "available": False, "can_submit": False,
                 "reason_code": "capability_unavailable"},
            ],
        })
        response["Cache-Control"] = "private, no-store"
        return response


class AssetIngestionRetryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, job_id):
        from django.db import transaction
        from django.utils import timezone
        serializer = IngestionRetrySerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        with transaction.atomic():
            job = GenerationJob.objects.select_for_update().filter(
                pk=job_id, workspace__memberships__user=request.user,
            ).first()
            if job is None:
                return not_found()
            if not ProjectService.can_write(request.user, job.workspace_id):
                return contract_response("workspace_read_only", "Your role cannot modify this workspace.", 403)
            if job.status != "completed" or not job.provider_job_id:
                return contract_response("result_unavailable", "Only confirmed completed jobs can retry saving.")
            if job.asset_status == "ready":
                return Response(GenerationJobSerializer(job).data)
            if job.asset_status == "failed" and not GenerationJobSerializer().get_asset_retryable(job):
                return contract_response("result_download_policy", "Operator correction is required before saving.")
            if job.asset_status not in {"pending", "ingesting"}:
                job.asset_status = "pending"
                job.asset_attempts = 0
                job.asset_next_attempt_at = timezone.now()
                job.save(update_fields=["asset_status", "asset_attempts", "asset_next_attempt_at"])
        return Response(GenerationJobSerializer(job).data, status=202)


class PresenterGenerationView(GenerationSubmissionView):
    serializer_class = PresenterGenerationSerializer
    capability = "presenter.generate"
