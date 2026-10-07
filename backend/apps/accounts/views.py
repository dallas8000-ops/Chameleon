from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import WorkspaceMembership
from apps.accounts.permissions import WorkspaceScopedPermission
from apps.accounts.serializers import (
    LoginSerializer,
    RegisterSerializer,
    WorkspaceMembershipSerializer,
    WorkspaceUpdateSerializer,
)


def error_response(
    *,
    code: str,
    message: str,
    errors: dict[str, list[str] | dict] | None,
    status_code: int,
) -> Response:
    return Response(
        {
            "code": code,
            "message": message,
            "errors": errors or {},
        },
        status=status_code,
    )


def build_session_payload(user) -> dict:
    if not getattr(user, "is_authenticated", False):
        return {
            "authenticated": False,
            "user": None,
            "workspaces": [],
        }

    memberships = WorkspaceMembership.for_user(user)
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
        },
        "workspaces": WorkspaceMembershipSerializer(memberships, many=True).data,
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="validation_error",
                message="Registration data is invalid.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        membership = serializer.save()
        login(request, membership.user)
        payload = build_session_payload(membership.user)
        payload["workspace"] = WorkspaceMembershipSerializer(membership).data
        return Response(payload, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="validation_error",
                message="Login data is invalid.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            message = "Email or password is incorrect."
            return error_response(
                code="invalid_credentials",
                message=message,
                errors={"non_field_errors": [message]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        login(request, user)
        return Response(build_session_payload(user))


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(build_session_payload(request.user))


class SessionView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(build_session_payload(request.user))


class WorkspaceListView(APIView):
    def get(self, request):
        memberships = WorkspaceMembership.for_user(request.user)
        return Response(WorkspaceMembershipSerializer(memberships, many=True).data)


class WorkspaceDetailView(APIView):
    def patch(self, request, workspace_id: int):
        membership = WorkspaceMembership.for_user(request.user).filter(workspace_id=workspace_id).first()
        if membership is None:
            return error_response(
                code="not_found",
                message="Workspace not found.",
                errors={"workspace": ["Workspace not found."]},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if not WorkspaceScopedPermission.has_owner_access(request.user, workspace_id):
            message = "You do not have permission to modify this workspace."
            return error_response(
                code="forbidden",
                message=message,
                errors={"workspace": [message]},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = WorkspaceUpdateSerializer(membership.workspace, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                code="validation_error",
                message="Workspace data is invalid.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        workspace = serializer.save()
        workspace_payload = WorkspaceMembershipSerializer(membership).data
        workspace_payload["name"] = workspace.name
        workspace_payload["slug"] = workspace.slug
        return Response(workspace_payload)
