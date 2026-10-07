from django.urls import path, include

urlpatterns = [
    path('api/', include('apps.accounts.urls')),
    path('api/', include('apps.studio.urls')),
    path('api/', include('apps.jobs.urls')),
    path('api/', include('api.urls')),
]
