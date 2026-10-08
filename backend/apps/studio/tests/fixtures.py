from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Workspace, WorkspaceMembership
from apps.studio.models import Project

Role = WorkspaceMembership.Role


class StudioFixture(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.owner = User.objects.create_user(email="owner@example.com", password="pw-Strong-123")
        self.editor = User.objects.create_user(email="editor@example.com", password="pw-Strong-123")
        self.reviewer = User.objects.create_user(email="reviewer@example.com", password="pw-Strong-123")
        self.outsider = User.objects.create_user(email="outsider@example.com", password="pw-Strong-123")
        self.workspace = Workspace.objects.create(name="Studio")
        self.other_workspace = Workspace.objects.create(name="Other")
        for user, role in ((self.owner, Role.OWNER), (self.editor, Role.EDITOR), (self.reviewer, Role.REVIEWER)):
            WorkspaceMembership.objects.create(user=user, workspace=self.workspace, role=role)
        WorkspaceMembership.objects.create(user=self.outsider, workspace=self.other_workspace, role=Role.OWNER)
        self.project = Project.objects.create(workspace=self.workspace, title="Reel", format="9:16")

    def post(self, url, data, **kw):
        return self.client.post(url, data=data, content_type="application/json", **kw)

    def patch(self, url, data):
        return self.client.patch(url, data=data, content_type="application/json")
