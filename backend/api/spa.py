"""Same-origin delivery of the built single-page app.

Static assets are served by WhiteNoise from ``FRONTEND_DIST_DIR``; this view only
answers client-side routes (deep links such as ``/studio/3``) with ``index.html``.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_safe

INDEX_MISSING_MESSAGE = (
    "Frontend bundle is not available. Build it with "
    "`npm --prefix frontend ci && npm --prefix frontend run build` "
    "or point FRONTEND_DIST_DIR at the built assets."
)


def index_path() -> Path:
    return Path(settings.FRONTEND_DIST_DIR) / "index.html"


@require_safe
def spa_index(request, *args, **kwargs) -> HttpResponse:
    path = index_path()
    try:
        markup = path.read_bytes()
    except OSError:
        return HttpResponse(INDEX_MISSING_MESSAGE, status=503, content_type="text/plain")
    response = HttpResponse(markup, content_type="text/html")
    # The entry document names hashed asset bundles, so it must never be cached.
    response["Cache-Control"] = "no-store, must-revalidate"
    return response
