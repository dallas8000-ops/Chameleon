from apps.studio.models import CaptionTrack
from apps.studio.tests.fixtures import StudioFixture


class CaptionApiTests(StudioFixture):
    def make_caption(self) -> CaptionTrack:
        return CaptionTrack.objects.create(
            project=self.project, language="en", segments=[{"start": 0.0, "end": 1.0, "text": "Hello"}]
        )

    def test_caption_create_and_update_persist(self) -> None:
        self.client.force_login(self.editor)
        r = self.post(
            f"/api/projects/{self.project.id}/captions/",
            {"language": "pt-BR", "segments": [{"start": 0, "end": 1.5, "text": "Oi"}], "style": {"size": 32}},
        )
        self.assertEqual(r.status_code, 201)
        caption_id = r.json()["id"]
        r = self.patch(
            f"/api/captions/{caption_id}/",
            {"segments": [{"start": 0.0, "end": 1.0, "text": "A"}, {"start": 1.0, "end": 2.0, "text": "B"}]},
        )
        self.assertEqual(r.status_code, 200)
        caption = CaptionTrack.objects.get(pk=caption_id)
        self.assertEqual([s["text"] for s in caption.segments], ["A", "B"])
        self.assertEqual(caption.style, {"size": 32})
        detail = self.client.get(f"/api/projects/{self.project.id}/").json()
        self.assertEqual(detail["captions"][0]["id"], caption_id)

    def test_duplicate_language_rejected(self) -> None:
        self.make_caption()
        self.client.force_login(self.owner)
        r = self.post(f"/api/projects/{self.project.id}/captions/", {"language": "en"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("language", r.json()["errors"])

    def test_malformed_segments_rejected_without_mutation(self) -> None:
        caption = self.make_caption()
        self.client.force_login(self.owner)
        bad_payloads = [
            [{"start": 2, "end": 1, "text": "x"}],
            [{"start": 1, "end": 1, "text": "x"}],
            [{"start": -1, "end": 1, "text": "x"}],
            [{"start": "a", "end": 1, "text": "x"}],
            [{"start": True, "end": 2, "text": "x"}],
            [{"start": 0, "end": 1}],
            [{"start": 0, "end": 1, "text": ""}],
            [{"start": 0, "end": 1, "text": "x", "extra": 1}],
            [{"start": 0, "end": 2, "text": "x"}, {"start": 1, "end": 3, "text": "y"}],
            ["nope"],
            "nope",
            {"start": 0},
        ]
        for segments in bad_payloads:
            r = self.patch(f"/api/captions/{caption.id}/", {"segments": segments})
            self.assertEqual(r.status_code, 400, segments)
            self.assertEqual(r.json()["code"], "validation_error")
        self.assertEqual(self.patch(f"/api/captions/{caption.id}/", {}).status_code, 400)
        self.assertEqual(
            self.post(f"/api/projects/{self.project.id}/captions/", {"language": "!!"}).status_code, 400
        )
        caption.refresh_from_db()
        self.assertEqual(caption.segments[0]["text"], "Hello")

    def test_reviewer_cannot_edit_caption(self) -> None:
        caption = self.make_caption()
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(f"/api/captions/{caption.id}/").status_code, 200)
        r = self.patch(f"/api/captions/{caption.id}/", {"segments": []})
        self.assertEqual(r.status_code, 403)
        caption.refresh_from_db()
        self.assertEqual(caption.segments[0]["text"], "Hello")
