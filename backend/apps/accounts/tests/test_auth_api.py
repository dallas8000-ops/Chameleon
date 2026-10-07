from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import Workspace, WorkspaceMembership


class AuthApiTests(TestCase):
    def setUp(self) -> None:
        self.csrf_client = Client(enforce_csrf_checks=True)

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
