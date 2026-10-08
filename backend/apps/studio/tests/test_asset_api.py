import shutil
import tempfile

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.studio.models import Asset
from apps.studio.tests.fixtures import StudioFixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class AssetApiTests(StudioFixture):
    def setUp(self) -> None:
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

    def upload(self, content=PNG, name="../../evil.png", content_type="image/png", **extra):
        f = SimpleUploadedFile(name, content, content_type=content_type)
        return self.client.post("/api/assets/", {"workspace_id": self.workspace.id, "file": f, **extra})

    def test_upload_stores_safely_and_hides_storage_details(self) -> None:
        self.client.force_login(self.editor)
        r = self.upload()
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body.get("source"), "upload")
        self.assertNotIn("storage_key", body)
        self.assertNotIn("url", body)
        asset = Asset.objects.get(pk=body["id"])
        self.assertEqual(asset.workspace_id, self.workspace.id)
        self.assertEqual(asset.provenance["source"], "upload")
        self.assertEqual(asset.provenance["uploaded_by"], self.editor.id)
        self.assertEqual(asset.name, "evil.png")
        self.assertNotIn("evil", asset.storage_key)
        self.assertTrue(asset.storage_key.startswith(f"workspaces/{self.workspace.id}/assets/"))
        self.assertTrue(default_storage.exists(asset.storage_key))
        self.assertEqual(self.client.get(f"/api/assets/{asset.id}/").json(), body)
        self.assertEqual([a["id"] for a in self.client.get("/api/assets/").json()], [asset.id])

    def test_invalid_uploads_rejected(self) -> None:
        self.client.force_login(self.owner)
        cases = [
            self.upload(content=b"<script>alert(1)</script>", name="x.png"),
            self.upload(content=PNG, content_type="video/mp4"),
            self.upload(content=b"", name="e.png"),
            self.client.post("/api/assets/", {"workspace_id": self.workspace.id}),
            self.client.post("/api/assets/", {"workspace_id": "abc"}),
        ]
        for r in cases:
            self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(Asset.objects.count(), 0)

    def test_source_label_is_safe_server_provenance_only(self):
        self.client.force_login(self.owner)
        asset = Asset.objects.get(pk=self.upload().json()["id"])
        for provenance, expected in (
            ({"source": "generation", "url": "https://private/token", "requested_by": self.owner.id}, "generation"),
            ({"source": "https://private/token"}, "unknown"),
            ({}, "unknown"),
        ):
            asset.provenance = provenance
            asset.save(update_fields=["provenance"])
            response = self.client.get(f"/api/assets/{asset.id}/")
            self.assertEqual(response.json().get("source"), expected)
            self.assertNotIn("private/token", response.content.decode())
            self.assertNotIn("provenance", response.json())

    def test_oversized_upload_rejected_during_parsing(self) -> None:
        self.client.force_login(self.owner)
        with override_settings(STUDIO_MAX_UPLOAD_BYTES=10):
            response = self.upload()
        self.assertEqual(response.status_code, 413, response.content)
        self.assertEqual(response.json()["code"], "upload_too_large")
        self.assertEqual(Asset.objects.count(), 0)

    def test_provenance_is_server_generated_and_not_serialized(self) -> None:
        self.client.force_login(self.owner)
        r = self.upload(provenance='{"source":"forged"}', source="generation")
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertNotIn("provenance", body)
        self.assertEqual(body["source"], "upload")
        asset = Asset.objects.get(pk=body["id"])
        self.assertEqual(asset.provenance["source"], "upload")
        self.assertEqual(asset.provenance["uploaded_by"], self.owner.id)
        self.assertEqual(asset.provenance["original_filename"], "evil.png")
        self.client.force_login(self.reviewer)
        for response in (self.client.get(f"/api/assets/{asset.id}/"), self.client.get("/api/assets/")):
            text = response.content.decode()
            self.assertNotIn("provenance", text)
            self.assertNotIn("original_filename", text)
            self.assertNotIn("uploaded_by", text)
    def test_foreign_and_reviewer_upload_denied(self) -> None:
        self.client.force_login(self.outsider)
        self.assertEqual(self.upload().status_code, 404)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(Asset.objects.count(), 0)
