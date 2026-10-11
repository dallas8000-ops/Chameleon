from __future__ import annotations

import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import error_response
from apps.generation import runpod
from apps.generation.capabilities import CAPABILITIES
from apps.generation.models import GenerationJob
from apps.generation.serializers import JobCreateSerializer, JobSerializer
from apps.generation.services import JobRejected, JobService, ingest_result, upload_token_valid
from apps.generation.tasks import cancel_provider_job, dispatch, submit_job
from apps.studio.services import ProjectService
from apps.studio.views import StudioView, invalid, not_found, read_only

logger = logging.getLogger(__name__)
RECENT_JOBS = 50


class CapabilitiesView(StudioView):
    def get(self, request):
        workspace_id = request.query_params.get("workspace_id", "")
        if not workspace_id.isdigit() or ProjectService.role_in_workspace(request.user, int(workspace_id)) is None:
            return not_found()
        configured = runpod.is_configured()
        return Response({
            "configured": configured,
            "missing": runpod.missing_settings(),
            "capabilities": [
                {"capability": c.name, "label": c.label, "description": c.description, "available": configured}
                for c in CAPABILITIES.values()
            ],
        })


class JobListCreateView(StudioView):
    def get(self, request):
        jobs = JobService.visible_to(request.user)
        workspace_id = request.query_params.get("workspace_id")
        if workspace_id is not None:
            if not workspace_id.isdigit():
                return error_response(
                    code="validation_error", message="Invalid request.",
                    errors={"workspace_id": ["A valid integer is required."]}, status_code=400,
                )
            jobs = jobs.filter(workspace_id=int(workspace_id))
        return Response(JobSerializer(jobs[:RECENT_JOBS], many=True).data)

    def post(self, request):
        serializer = JobCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer)
        data = serializer.validated_data
        if ProjectService.role_in_workspace(request.user, data["workspace_id"]) is None:
            return not_found()
        if not ProjectService.can_write(request.user, data["workspace_id"]):
            return read_only()
        try:
            job = JobService.create(
                user=request.user, workspace_id=data["workspace_id"], capability_name=data["capability"],
                params=data["params"], project_id=data.get("project_id"), scene_id=data.get("scene_id"),
            )
        except JobRejected as rejected:
            return error_response(
                code=rejected.code, message=rejected.message, errors=None, status_code=rejected.status_code,
            )
        transaction.on_commit(lambda: dispatch(submit_job, job.id))
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class JobDetailView(StudioView):
    def get(self, request, job_id):
        job = JobService.visible_to(request.user).filter(pk=job_id).first()
        if job is None:
            return not_found()
        return Response(JobSerializer(job).data)


class JobCancelView(StudioView):
    def post(self, request, job_id):
        job = JobService.visible_to(request.user).filter(pk=job_id).first()
        if job is None:
            return not_found()
        if not ProjectService.can_write(request.user, job.workspace_id):
            return read_only()
        was_active = job.status in GenerationJob.ACTIVE_STATUSES
        job = JobService.cancel(job)
        if was_active and job.provider_job_id:
            transaction.on_commit(lambda: cancel_provider_job.delay(job.provider_job_id))
        return Response(JobSerializer(job).data)


def _upload_error(code: str, message: str, status_code: int) -> JsonResponse:
    return JsonResponse({"code": code, "message": message}, status=status_code)


@csrf_exempt
def result_upload(request, job_id):
    """Called by the GPU worker with a one-time signed token; it has no user session."""
    if request.method != "PUT":
        response = _upload_error("method_not_allowed", "Use PUT.", 405)
        response["Allow"] = "PUT"
        return response
    if not upload_token_valid(request.headers.get("X-Upload-Token", ""), job_id):
        return _upload_error("invalid_token", "The upload token is missing, invalid or expired.", 403)
    length = request.headers.get("Content-Length", "")
    if not length.isdigit():
        return _upload_error("length_required", "A Content-Length header is required.", 411)
    try:
        job = ingest_result(job_id, request, int(length))
    except JobRejected as rejected:
        return _upload_error(rejected.code, rejected.message, rejected.status_code)
    except OSError:
        logger.exception("Private storage failed while saving the result of generation job %s.", job_id)
        return _upload_error("storage_failed", "The result could not be stored.", 503)
    return JsonResponse({"id": job.id, "asset_id": job.result_asset_id}, status=201)
