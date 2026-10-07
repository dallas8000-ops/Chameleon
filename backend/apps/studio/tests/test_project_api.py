from apps.studio.models import Scene
from apps.studio.tests.fixtures import StudioFixture


class ProjectApiTests(StudioFixture):
    def test_requires_authentication(self) -> None:
        for method, url in (
            ("get", "/api/projects/"),
            ("post", "/api/projects/"),
            ("get", f"/api/projects/{self.project.id}/"),
            ("post", f"/api/projects/{self.project.id}/scenes/"),
            ("get", "/api/assets/"),
        ):
            self.assertIn(getattr(self.client, method)(url).status_code, (401, 403), url)

    def test_create_project_and_scene_persist_in_order(self) -> None:
        self.client.force_login(self.owner)
        response = self.post(
            "/api/projects/",
            {"workspace_id": self.workspace.id, "title": "Launch Reel", "format": "16:9"},
        )
        self.assertEqual(response.status_code, 201)
        project_id = response.json()["id"]
        for title in ("Hook", "Body", "CTA"):
            r = self.post(f"/api/projects/{project_id}/scenes/", {"kind": "script", "title": title, "script_text": title})
            self.assertEqual(r.status_code, 201)
        detail = self.client.get(f"/api/projects/{project_id}/").json()
        self.assertEqual([s["title"] for s in detail["scenes"]], ["Hook", "Body", "CTA"])
        self.assertEqual([s["order_index"] for s in detail["scenes"]], [0, 1, 2])
        self.assertEqual(detail["captions"], [])
        self.assertEqual(
            sorted(detail),
            ["captions", "created_at", "format", "id", "scenes", "status", "title", "updated_at", "workspace_id"],
        )

    def test_scene_update_and_reorder(self) -> None:
        self.client.force_login(self.editor)
        ids = [
            self.post(f"/api/projects/{self.project.id}/scenes/", {"kind": "image", "title": t}).json()["id"]
            for t in "ABC"
        ]
        r = self.patch(f"/api/scenes/{ids[2]}/", {"order_index": 0, "title": "C2", "config": {"zoom": 1.2}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["title"], "C2")
        titles = list(Scene.objects.filter(project=self.project).values_list("title", "order_index"))
        self.assertEqual(titles, [("C2", 0), ("A", 1), ("B", 2)])
        self.assertEqual(Scene.objects.get(pk=ids[2]).config, {"zoom": 1.2})

    def test_list_only_returns_member_workspaces_and_filters(self) -> None:
        from apps.studio.models import Project

        Project.objects.create(workspace=self.other_workspace, title="Secret", format="9:16")
        self.client.force_login(self.owner)
        self.assertEqual([p["title"] for p in self.client.get("/api/projects/").json()], ["Reel"])
        self.assertEqual(len(self.client.get(f"/api/projects/?workspace_id={self.workspace.id}").json()), 1)
        self.assertEqual(self.client.get(f"/api/projects/?workspace_id={self.other_workspace.id}").json(), [])
        self.assertEqual(self.client.get("/api/projects/?workspace_id=abc").status_code, 400)

    def test_malformed_input_is_rejected_with_structured_errors(self) -> None:
        self.client.force_login(self.owner)
        base = {"workspace_id": self.workspace.id, "title": "T", "format": "9:16"}
        for bad in (
            {"format": "4:3"},
            {"format": "9x16"},
            {"format": ""},
            {"title": ""},
            {"workspace_id": "abc"},
            {"workspace_id": -1},
            {"workspace_id": None},
        ):
            r = self.post("/api/projects/", {**base, **bad})
            self.assertEqual(r.status_code, 400, bad)
            body = r.json()
            self.assertEqual(body["code"], "validation_error")
            self.assertTrue(body["errors"])
        self.assertEqual(self.post("/api/projects/", {}).status_code, 400)
        url = f"/api/projects/{self.project.id}/scenes/"
        for bad in ({"kind": "bogus", "title": "x"}, {"kind": "script"}, {"kind": "script", "title": "x", "config": []}):
            self.assertEqual(self.post(url, bad).status_code, 400, bad)
        self.assertEqual(Scene.objects.count(), 0)

    def test_foreign_workspace_denied_everywhere(self) -> None:
        from apps.studio.models import Asset, CaptionTrack

        scene = Scene.objects.create(project=self.project, order_index=0, kind="script", title="s")
        caption = CaptionTrack.objects.create(project=self.project, language="en", segments=[])
        asset = Asset.objects.create(
            workspace=self.workspace, asset_type="image", name="a", storage_key="k/1.png",
            content_type="image/png", size_bytes=1,
        )
        self.client.force_login(self.outsider)
        checks = [
            self.client.get(f"/api/projects/{self.project.id}/"),
            self.post(f"/api/projects/{self.project.id}/scenes/", {"kind": "script", "title": "x"}),
            self.client.get(f"/api/scenes/{scene.id}/"),
            self.patch(f"/api/scenes/{scene.id}/", {"title": "hacked"}),
            self.post(f"/api/projects/{self.project.id}/captions/", {"language": "fr"}),
            self.client.get(f"/api/captions/{caption.id}/"),
            self.patch(f"/api/captions/{caption.id}/", {"segments": []}),
            self.client.get(f"/api/assets/{asset.id}/"),
            self.post("/api/projects/", {"workspace_id": self.workspace.id, "title": "x", "format": "9:16"}),
        ]
        for response in checks:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], "not_found")
        self.assertEqual(self.client.get(f"/api/assets/?workspace_id={self.workspace.id}").json(), [])
        missing = self.client.get("/api/projects/99999/")
        self.assertEqual(missing.json(), checks[0].json())
        scene.refresh_from_db()
        self.assertEqual(scene.title, "s")
        self.assertEqual(Scene.objects.count(), 1)

    def test_reviewer_is_read_only_but_can_read(self) -> None:
        scene = Scene.objects.create(project=self.project, order_index=0, kind="script", title="s")
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(f"/api/projects/{self.project.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/scenes/{scene.id}/").status_code, 200)
        writes = [
            self.post("/api/projects/", {"workspace_id": self.workspace.id, "title": "x", "format": "9:16"}),
            self.post(f"/api/projects/{self.project.id}/scenes/", {"kind": "script", "title": "x"}),
            self.patch(f"/api/scenes/{scene.id}/", {"title": "x"}),
            self.post(f"/api/projects/{self.project.id}/captions/", {"language": "en"}),
        ]
        for response in writes:
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "workspace_read_only")
        self.assertEqual(Scene.objects.get().title, "s")
