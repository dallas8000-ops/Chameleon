from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.test import Client, SimpleTestCase, TestCase
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Workspace, WorkspaceMembership
from apps.accounts.serializers import RegisterSerializer
from apps.accounts.views import is_duplicate_email_conflict


class RegistrationConflictTests(SimpleTestCase):
    class DatabaseConflict(Exception):
        def __init__(self, code: str, constraint: str, *, field: str = "pgcode") -> None:
            super().__init__("database constraint violation")
            setattr(self, field, code)
            self.diag = SimpleNamespace(constraint_name=constraint)

    def test_postgres_only_maps_email_unique_constraint(self) -> None:
        for field in ("pgcode", "sqlstate"):
            for constraint, expected in [
            ("accounts_user_email_key", True),
            ("accounts_workspace_slug_key", False),
            ]:
                with self.subTest(field=field, constraint=constraint):
                    cause = self.DatabaseConflict("23505", constraint, field=field)
                    error = IntegrityError("database constraint violation")
                    error.__cause__ = cause
                    self.assertEqual(is_duplicate_email_conflict(error), expected)

    def test_postgres_non_unique_error_is_not_mapped(self) -> None:
        cause = self.DatabaseConflict("23502", "accounts_user_email_key")
        error = IntegrityError("database constraint violation")
        error.__cause__ = cause
        self.assertFalse(is_duplicate_email_conflict(error))


class AuthApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.csrf_client = Client(enforce_csrf_checks=True)

    def test_raced_email_insert_returns_duplicate_validation_after_rollback(self) -> None:
        validate_email = RegisterSerializer.validate_email

        def insert_competing_user(serializer, value):
            email = validate_email(serializer, value)
            get_user_model().objects.create_user(email=email)
            return email

        with patch.object(RegisterSerializer, "validate_email", insert_competing_user):
            response = self._register()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(
            response.json()["errors"],
            {"email": ["A user with this email already exists."]},
        )
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Workspace.objects.count(), 0)
        self.assertEqual(WorkspaceMembership.objects.count(), 0)
        self.assertFalse(self.csrf_client.get("/api/auth/session/").json()["authenticated"])

    def test_unrelated_registration_integrity_error_is_not_hidden(self) -> None:
        with patch.object(
            Workspace.objects,
            "create",
            side_effect=IntegrityError("unrelated workspace constraint"),
        ):
            with self.assertRaisesMessage(IntegrityError, "unrelated workspace constraint"):
                self._register()

        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Workspace.objects.count(), 0)
        self.assertEqual(WorkspaceMembership.objects.count(), 0)

    def test_auth_rate_exceeded_returns_429(self) -> None:
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth": "2/minute"}):
            first = self._register(email="invalid")
            second = self._register(email="invalid")
            third = self._register(email="invalid")

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(third.status_code, 429)
        self.assertIn("Retry-After", third.headers)
        self.assertIn("throttled", third.json()["detail"].lower())
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_logout_missing_csrf_is_rejected_and_preserves_session(self) -> None:
        self.assertEqual(self._register().status_code, 201)

        response = self.csrf_client.post(
            "/api/auth/logout/",
            data={},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.csrf_client.get("/api/auth/session/").json()["authenticated"])

    def _get_csrf_token(self) -> str:
        response = self.csrf_client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.json()["csrfToken"]

    def _register(
        self,
        *,
        email: str = "owner@example.com",
        password: str = "ChangeMe123!",
        workspace_name: str = "Owner Studio",
    ):
        csrf_token = self._get_csrf_token()
        return self.csrf_client.post(
            "/api/auth/register/",
            data={
                "email": email,
                "password": password,
                "workspace_name": workspace_name,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

    def test_register_creates_workspace_membership_and_session_bootstrap(self) -> None:
        response = self._register()

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["user"]["email"], "owner@example.com")
        self.assertEqual(payload["workspace"]["name"], "Owner Studio")
        self.assertEqual(payload["workspace"]["slug"], "owner-studio")

        membership = WorkspaceMembership.objects.select_related("workspace", "user").get()
        self.assertEqual(membership.role, WorkspaceMembership.Role.OWNER)
        self.assertEqual(membership.user.email, "owner@example.com")
        self.assertEqual(membership.workspace.name, "Owner Studio")

        session_response = self.csrf_client.get("/api/auth/session/")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(
            session_response.json(),
            {
                "authenticated": True,
                "user": {"id": membership.user_id, "email": "owner@example.com"},
                "workspaces": [
                    {
                        "id": membership.workspace_id,
                        "name": "Owner Studio",
                        "slug": "owner-studio",
                        "role": WorkspaceMembership.Role.OWNER,
                    }
                ],
            },
        )

    def test_register_rejects_invalid_input_without_partial_records(self) -> None:
        response = self._register(password="password")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Workspace.objects.count(), 0)
        self.assertEqual(WorkspaceMembership.objects.count(), 0)

    def test_register_rejects_duplicate_email_case_insensitively(self) -> None:
        first_response = self._register(email="Owner@Example.com", workspace_name="First Studio")
        second_response = self._register(email="owner@example.com", workspace_name="Second Studio")

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json()["code"], "validation_error")
        self.assertIn("email", second_response.json()["errors"])
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Workspace.objects.count(), 1)

    def test_register_allows_same_workspace_name_with_unique_slug(self) -> None:
        first_response = self._register(email="owner1@example.com")
        self.csrf_client = Client(enforce_csrf_checks=True)
        second_response = self._register(email="owner2@example.com")

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)

        slugs = list(Workspace.objects.order_by("id").values_list("slug", flat=True))
        self.assertEqual(slugs, ["owner-studio", "owner-studio-2"])

    def test_register_requires_csrf_for_anonymous_request(self) -> None:
        response = self.csrf_client.post(
            "/api/auth/register/",
            data={
                "email": "owner@example.com",
                "password": "ChangeMe123!",
                "workspace_name": "Owner Studio",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_login_rejects_invalid_credentials(self) -> None:
        get_user_model().objects.create_user(
            email="owner@example.com",
            password="ChangeMe123!",
        )
        csrf_token = self._get_csrf_token()

        response = self.csrf_client.post(
            "/api/auth/login/",
            data={"email": "owner@example.com", "password": "WrongPassword123!"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "code": "invalid_credentials",
                "message": "Email or password is incorrect.",
                "errors": {"non_field_errors": ["Email or password is incorrect."]},
            },
        )

    def test_login_requires_csrf_for_anonymous_request(self) -> None:
        get_user_model().objects.create_user(
            email="owner@example.com",
            password="ChangeMe123!",
        )

        response = self.csrf_client.post(
            "/api/auth/login/",
            data={"email": "owner@example.com", "password": "ChangeMe123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_login_logout_and_session_bootstrap(self) -> None:
        user = get_user_model().objects.create_user(
            email="owner@example.com",
            password="ChangeMe123!",
        )
        workspace = Workspace.objects.create(name="Owner Studio")
        WorkspaceMembership.objects.create(
            user=user,
            workspace=workspace,
            role=WorkspaceMembership.Role.OWNER,
        )
        csrf_token = self._get_csrf_token()

        login_response = self.csrf_client.post(
            "/api/auth/login/",
            data={"email": "owner@example.com", "password": "ChangeMe123!"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["authenticated"], True)

        session_response = self.csrf_client.get("/api/auth/session/")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.json()["user"]["email"], "owner@example.com")
        self.assertEqual(session_response.json()["workspaces"][0]["name"], "Owner Studio")

        logout_token = self._get_csrf_token()
        logout_response = self.csrf_client.post(
            "/api/auth/logout/",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=logout_token,
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json(), {"authenticated": False, "user": None, "workspaces": []})

        post_logout_response = self.csrf_client.get("/api/auth/session/")
        self.assertEqual(
            post_logout_response.json(),
            {"authenticated": False, "user": None, "workspaces": []},
        )
