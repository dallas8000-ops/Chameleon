from django.urls import path

from apps.studio.views import (
    AssetDetailView,
    AssetListCreateView,
    CaptionCreateView,
    CaptionDetailView,
    ExportCreateView,
    ExportDetailView,
    ExportDownloadView,
    ProjectDetailView,
    ProjectListCreateView,
    SceneCreateView,
    SceneDetailView,
)

urlpatterns = [
    path("projects/", ProjectListCreateView.as_view(), name="project-list"),
    path("projects/<int:project_id>/", ProjectDetailView.as_view(), name="project-detail"),
    path("projects/<int:project_id>/exports/", ExportCreateView.as_view(), name="export-create"),
    path("exports/<int:export_id>/", ExportDetailView.as_view(), name="export-detail"),
    path(
        "exports/<int:export_id>/video/", ExportDownloadView.as_view(),
        {"artifact": "video"}, name="export-video",
    ),
    path(
        "exports/<int:export_id>/subtitles/", ExportDownloadView.as_view(),
        {"artifact": "subtitles"}, name="export-subtitles",
    ),
    path("projects/<int:project_id>/scenes/", SceneCreateView.as_view(), name="scene-create"),
    path("scenes/<int:scene_id>/", SceneDetailView.as_view(), name="scene-detail"),
    path("projects/<int:project_id>/captions/", CaptionCreateView.as_view(), name="caption-create"),
    path("captions/<int:caption_id>/", CaptionDetailView.as_view(), name="caption-detail"),
    path("assets/", AssetListCreateView.as_view(), name="asset-list"),
    path("assets/<int:asset_id>/", AssetDetailView.as_view(), name="asset-detail"),
]
