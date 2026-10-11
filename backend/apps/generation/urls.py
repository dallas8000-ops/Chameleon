from django.urls import path

from apps.generation.views import CapabilitiesView, JobCancelView, JobDetailView, JobListCreateView, result_upload

urlpatterns = [
    path("generation/capabilities/", CapabilitiesView.as_view(), name="generation-capabilities"),
    path("generation/jobs/", JobListCreateView.as_view(), name="generation-job-list"),
    path("generation/jobs/<int:job_id>/", JobDetailView.as_view(), name="generation-job-detail"),
    path("generation/jobs/<int:job_id>/cancel/", JobCancelView.as_view(), name="generation-job-cancel"),
    path("generation/jobs/<int:job_id>/result/", result_upload, name="generation-result-upload"),
]
