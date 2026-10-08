from django.urls import path, include, re_path

from api.spa import spa_index

urlpatterns = [
    path('api/', include('apps.accounts.urls')),
    path('api/', include('apps.studio.urls')),
    path('api/', include('apps.jobs.urls')),
    path('api/', include('api.urls')),
    # Client-side routes fall back to the SPA entry document. /api, /static and the
    # hashed /assets bundles are excluded so a missing file 404s instead of
    # returning HTML with a 200.
    re_path(r'^(?!api/|static/|assets/).*$', spa_index, name='spa-index'),
]
