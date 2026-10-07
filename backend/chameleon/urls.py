from django.urls import path, include

urlpatterns = [
    path('api/', include('apps.accounts.urls')),
    path('api/', include('api.urls')),
]
