from django.urls import path

from apps.jobs.views import (
    GenerationJobView,
    ImageGenerationView,
    MagicHourWebhookView,
    PresenterGenerationView,
    ImageQuoteView,
    GenerationCapabilitiesView,
    AssetIngestionRetryView,
)

urlpatterns = [
    path("jobs/capabilities/", GenerationCapabilitiesView.as_view(), name="generation-capabilities"),
    path("jobs/image-generation/quote/", ImageQuoteView.as_view(), name="image-generation-quote"),
    path("jobs/<int:job_id>/asset-ingestion/retry/", AssetIngestionRetryView.as_view(), name="asset-ingestion-retry"),
    path("jobs/image-generation/", ImageGenerationView.as_view(), name="image-generation"),
    path("jobs/presenter-generation/", PresenterGenerationView.as_view(), name="presenter-generation"),
    path("jobs/webhooks/magic-hour/", MagicHourWebhookView.as_view(), name="magic-hour-webhook"),
    path("jobs/<int:job_id>/", GenerationJobView.as_view(), name="generation-job-detail"),
]
