from django.urls import path

from apps.accounts.views import (
    CsrfTokenView,
    LoginView,
    LogoutView,
    RegisterView,
    SessionView,
    WorkspaceDetailView,
    WorkspaceListView,
)


urlpatterns = [
    path("auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/session/", SessionView.as_view(), name="auth-session"),
    path("workspaces/", WorkspaceListView.as_view(), name="workspace-list"),
    path("workspaces/<int:workspace_id>/", WorkspaceDetailView.as_view(), name="workspace-detail"),
]
