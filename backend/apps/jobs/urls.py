from django.urls import path

from apps.jobs.views import (
    GenerationJobView,
    ImageGenerationView,
    MagicHourWebhookView,
    PresenterGenerationView,
)

urlpatterns = [
    path("jobs/image-generation/", ImageGenerationView.as_view(), name="image-generation"),
    path("jobs/presenter-generation/", PresenterGenerationView.as_view(), name="presenter-generation"),
    path("jobs/webhooks/magic-hour/", MagicHourWebhookView.as_view(), name="magic-hour-webhook"),
    path("jobs/<int:job_id>/", GenerationJobView.as_view(), name="generation-job-detail"),
]
