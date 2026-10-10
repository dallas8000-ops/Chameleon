import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.studio.models import Asset, Character, Scene
from apps.studio.tests.fixtures import StudioFixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class CharacterApiTests(StudioFixture):
    def setUp(self) -> None:
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

    def upload(self, workspace=None, name="face.png"):
        workspace = workspace or self.workspace
        response = self.client.post("/api/assets/", {
            "workspace_id": workspace.id,
            "file": SimpleUploadedFile(name, PNG, content_type="image/png"),
        })
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def create(self, **extra):
        return self.post("/api/characters/", {"workspace_id": self.workspace.id, "name": "Kato", **extra})

    def test_editor_creates_lists_updates_and_deletes(self):
        self.client.force_login(self.editor)
        asset_id = self.upload()
        response = self.create(
            role="Boda boda rider", face_prompt="Ugandan man, mid-20s", negative_prompt="cartoon",
            voice_notes="Ugandan English", reference_asset_id=asset_id,
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["reference_asset_id"], asset_id)
        self.assertEqual(body["workspace_id"], self.workspace.id)
        listed = self.client.get(f"/api/characters/?workspace_id={self.workspace.id}").json()
        self.assertEqual([c["id"] for c in listed], [body["id"]])
        patched = self.patch(f"/api/characters/{body['id']}/", {"role": "Guide", "reference_asset_id": None})
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.json()["role"], "Guide")
        self.assertIsNone(patched.json()["reference_asset_id"])
        self.assertEqual(self.client.delete(f"/api/characters/{body['id']}/").status_code, 204)
        self.assertFalse(Character.objects.exists())

    def test_reviewer_is_read_only_and_outsider_sees_nothing(self):
        self.client.force_login(self.owner)
        character_id = self.create().json()["id"]
        self.client.force_login(self.reviewer)
        self.assertEqual(self.create(name="Other").status_code, 403)
        self.assertEqual(self.patch(f"/api/characters/{character_id}/", {"role": "x"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/characters/{character_id}/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/characters/{character_id}/").status_code, 200)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/api/characters/{character_id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/characters/?workspace_id={self.workspace.id}").json(), [])
        self.assertEqual(self.create().status_code, 404)

    def test_duplicate_name_and_bad_reference_rejected(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create().status_code, 400)
        self.assertEqual(self.create(name="Foreign", reference_asset_id=999).status_code, 400)
        foreign = Asset.objects.create(
            workspace=self.other_workspace, asset_type="image", name="x", storage_key="workspaces/2/assets/a.png",
            content_type="image/png", size_bytes=1,
        )
        self.assertEqual(self.create(name="Foreign", reference_asset_id=foreign.id).status_code, 400)
        video = Asset.objects.create(
            workspace=self.workspace, asset_type="video", name="v", storage_key=f"workspaces/{self.workspace.id}/assets/v.mp4",
            content_type="video/mp4", size_bytes=1,
        )
        self.assertEqual(self.create(name="Video", reference_asset_id=video.id).status_code, 400)
        self.assertEqual(self.create(name="  ").status_code, 400)

    def test_scene_character_must_belong_to_the_workspace(self):
        self.client.force_login(self.owner)
        character_id = self.create().json()["id"]
        foreign = Character.objects.create(workspace=self.other_workspace, name="Foreign")
        url = f"/api/projects/{self.project.id}/scenes/"
        ok = self.post(url, {"kind": "script", "title": "Hi", "character_id": character_id})
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(ok.json()["character_id"], character_id)
        self.assertEqual(self.post(url, {"kind": "script", "title": "Bad", "character_id": foreign.id}).status_code, 400)
        scene_id = ok.json()["id"]
        self.assertEqual(self.patch(f"/api/scenes/{scene_id}/", {"character_id": foreign.id}).status_code, 400)
        cleared = self.patch(f"/api/scenes/{scene_id}/", {"character_id": None})
        self.assertIsNone(cleared.json()["character_id"])

    def test_deleting_a_character_keeps_its_scenes(self):
        self.client.force_login(self.owner)
        character_id = self.create().json()["id"]
        scene = self.post(f"/api/projects/{self.project.id}/scenes/", {
            "kind": "script", "title": "Hi", "character_id": character_id,
        }).json()
        self.client.delete(f"/api/characters/{character_id}/")
        self.assertIsNone(Scene.objects.get(pk=scene["id"]).character_id)


class SceneDeleteAndAssetContentTests(StudioFixture):
    def setUp(self) -> None:
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

    def test_delete_scene_renumbers_and_enforces_roles(self):
        self.client.force_login(self.owner)
        ids = [
            self.post(f"/api/projects/{self.project.id}/scenes/", {"kind": "script", "title": t}).json()["id"]
            for t in ("A", "B", "C")
        ]
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.delete(f"/api/scenes/{ids[1]}/").status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.delete(f"/api/scenes/{ids[1]}/").status_code, 404)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.delete(f"/api/scenes/{ids[1]}/").status_code, 204)
        remaining = list(Scene.objects.filter(project=self.project).values_list("title", "order_index"))
        self.assertEqual(remaining, [("A", 0), ("C", 1)])

    def test_asset_content_is_served_to_members_only(self):
        self.client.force_login(self.editor)
        response = self.client.post("/api/assets/", {
            "workspace_id": self.workspace.id,
            "file": SimpleUploadedFile("pic.png", PNG, content_type="image/png"),
        })
        asset_id = response.json()["id"]
        content = self.client.get(f"/api/assets/{asset_id}/content/")
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content["Content-Type"], "image/png")
        self.assertIn("private", content["Cache-Control"])
        self.assertEqual(b"".join(content.streaming_content), PNG)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(f"/api/assets/{asset_id}/content/").status_code, 200)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/api/assets/{asset_id}/content/").status_code, 404)
        self.client.logout()
        self.assertIn(self.client.get(f"/api/assets/{asset_id}/content/").status_code, (401, 403))

    def test_asset_with_unsafe_storage_key_is_not_served(self):
        self.client.force_login(self.owner)
        asset = Asset.objects.create(
            workspace=self.workspace, asset_type="image", name="x", storage_key="../../etc/passwd.png",
            content_type="image/png", size_bytes=1,
        )
        self.assertEqual(self.client.get(f"/api/assets/{asset.id}/content/").status_code, 503)
