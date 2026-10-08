from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import Workspace, WorkspaceMembership
from apps.accounts.permissions import WorkspaceScopedPermission


class WorkspaceAccessTests(TestCase):
    def setUp(self) -> None:
        self.owner = get_user_model().objects.create_user(
            email="owner@example.com",
            password="ChangeMe123!",
        )
        self.other = get_user_model().objects.create_user(
            email="other@example.com",
            password="ChangeMe123!",
        )
        self.owner_workspace = Workspace.objects.create(name="Owner Studio")
        self.hidden_workspace = Workspace.objects.create(name="Hidden Studio")
        WorkspaceMembership.objects.create(
            user=self.owner,
            workspace=self.owner_workspace,
            role=WorkspaceMembership.Role.OWNER,
        )
        WorkspaceMembership.objects.create(
            user=self.other,
            workspace=self.hidden_workspace,
            role=WorkspaceMembership.Role.OWNER,
        )

        self.client.force_login(self.owner)

    def test_user_only_sees_visible_workspaces(self) -> None:
        response = self.client.get("/api/workspaces/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "id": self.owner_workspace.id,
                    "name": "Owner Studio",
                    "slug": "owner-studio",
                    "role": WorkspaceMembership.Role.OWNER,
                }
            ],
        )

    def test_foreign_workspace_is_not_visible(self) -> None:
        response = self.client.get("/api/workspaces/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.hidden_workspace.id, [item["id"] for item in response.json()])
        self.assertFalse(
            WorkspaceScopedPermission.has_workspace_access(self.owner, self.hidden_workspace.id)
        )

    def test_owner_can_mutate_workspace(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        csrf_token = csrf_client.get("/api/auth/csrf/").json()["csrfToken"]

        response = csrf_client.patch(
            f"/api/workspaces/{self.owner_workspace.id}/",
            data={"name": "Renamed Studio"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.owner_workspace.refresh_from_db()
        self.assertEqual(self.owner_workspace.name, "Renamed Studio")
        self.assertEqual(self.owner_workspace.slug, "renamed-studio")

    def test_reviewer_cannot_mutate_workspace(self) -> None:
        reviewer = get_user_model().objects.create_user(
            email="reviewer@example.com",
            password="ChangeMe123!",
        )
        WorkspaceMembership.objects.create(
            user=reviewer,
            workspace=self.owner_workspace,
            role=WorkspaceMembership.Role.REVIEWER,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(reviewer)
        csrf_token = csrf_client.get("/api/auth/csrf/").json()["csrfToken"]

        response = csrf_client.patch(
            f"/api/workspaces/{self.owner_workspace.id}/",
            data={"name": "Nope"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "code": "forbidden",
                "message": "You do not have permission to modify this workspace.",
                "errors": {"workspace": ["You do not have permission to modify this workspace."]},
            },
        )
        self.owner_workspace.refresh_from_db()
        self.assertEqual(self.owner_workspace.name, "Owner Studio")

    def test_foreign_workspace_mutation_returns_not_found(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        csrf_token = csrf_client.get("/api/auth/csrf/").json()["csrfToken"]

        response = csrf_client.patch(
            f"/api/workspaces/{self.hidden_workspace.id}/",
            data={"name": "Nope"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "code": "not_found",
                "message": "Workspace not found.",
                "errors": {"workspace": ["Workspace not found."]},
            },
        )
