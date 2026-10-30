from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.generation.models import GenerationJob
from apps.generation.services import upload_token
from apps.generation.tasks import submit_job
from apps.generation.tests.test_generation import Base
from apps.studio.models import Asset, Character

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32
Status = GenerationJob.Status


class VoiceTests(Base):
    def audio(self, workspace=None, kind="audio"):
        workspace = workspace or self.workspace
        key = default_storage.save(f"workspaces/{workspace.id}/assets/sample.wav", ContentFile(WAV))
        return Asset.objects.create(
            workspace=workspace, asset_type=kind, name="sample.wav", storage_key=key,
            content_type="audio/wav", size_bytes=len(WAV),
        )

    def voice_job(self, sample, **extra):
        return GenerationJob.objects.create(
            workspace=self.workspace, requested_by=self.editor, capability="voice",
            params={"text": "hi", "voice_sample_asset_id": sample.id}, **extra,
        )

    def create(self, params):
        with patch("apps.generation.views.dispatch"):
            return self.post("/api/generation/jobs/", {"workspace_id": self.workspace.id, "capability": "voice", "params": params})

    def test_voice_job_needs_a_line_and_a_sample_from_this_workspace(self):
        sample = self.audio()
        response = self.create({"text": "  Hello   Kampala ", "voice_sample_asset_id": sample.id})
        self.assertEqual(response.status_code, 202, response.content)
        job = GenerationJob.objects.get(pk=response.json()["id"])
        self.assertEqual(job.params, {"text": "Hello Kampala", "voice_sample_asset_id": sample.id})
        foreign = self.audio(workspace=self.other_workspace)
        picture = self.audio(kind="image")
        for params in ({}, {"text": "hi"}, {"text": "", "voice_sample_asset_id": sample.id}, {"text": "x" * 1001, "voice_sample_asset_id": sample.id},
                       {"text": "hi", "voice_sample_asset_id": foreign.id}, {"text": "hi", "voice_sample_asset_id": picture.id}):
            with self.subTest(params=params):
                self.assertIn(self.create(params).status_code, (400,))

    def test_submit_sends_an_input_url_with_the_job_token(self):
        sample = self.audio()
        job = self.voice_job(sample)
        with patch("apps.generation.tasks.runpod.submit", return_value="rp-5") as submit, patch("apps.generation.tasks.schedule_poll"):
            submit_job(job.id)
        payload = submit.call_args.args[0]
        self.assertEqual(payload["input"]["url"], f"https://chameleon.test/api/generation/jobs/{job.id}/input/")
        self.assertEqual(payload["input"]["token"], payload["upload"]["token"])

    def test_worker_downloads_the_sample_only_with_the_token_while_the_job_runs(self):
        sample = self.audio()
        job = self.voice_job(sample, status=Status.SUBMITTED, provider_job_id="rp-1")
        url = f"/api/generation/jobs/{job.id}/input/"
        self.client.logout()
        ok = self.client.get(url, HTTP_X_UPLOAD_TOKEN=upload_token(job.id))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(b"".join(ok.streaming_content), WAV)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(url, HTTP_X_UPLOAD_TOKEN=upload_token(job.id + 1)).status_code, 403)
        job.status = Status.COMPLETED
        job.save()
        self.assertEqual(self.client.get(url, HTTP_X_UPLOAD_TOKEN=upload_token(job.id)).status_code, 409)

    def test_jobs_without_an_input_have_no_download(self):
        job = self.submitted_job()
        response = self.client.get(f"/api/generation/jobs/{job.id}/input/", HTTP_X_UPLOAD_TOKEN=upload_token(job.id))
        self.assertEqual(response.status_code, 404)

    def test_voice_results_are_stored_as_audio(self):
        sample = self.audio()
        job = self.voice_job(sample, status=Status.SUBMITTED, provider_job_id="rp-1")
        response = self.put_result(job, body=WAV)
        self.assertEqual(response.status_code, 201, response.content)
        job.refresh_from_db()
        self.assertEqual(job.result_asset.asset_type, "audio")


class PictureReferenceTests(Base):
    audio = VoiceTests.audio

    def picture(self, params):
        with patch("apps.generation.views.dispatch"):
            return self.post("/api/generation/jobs/", {"workspace_id": self.workspace.id, "capability": "text_to_image", "params": params})

    def test_reference_picture_is_optional_but_must_be_an_image_here(self):
        image = self.audio(kind="image")
        response = self.picture({"prompt": "Marcus in Kampala", "reference_asset_id": image.id})
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(GenerationJob.objects.get(pk=response.json()["id"]).params["reference_asset_id"], image.id)
        self.assertEqual(self.picture({"prompt": "a street"}).status_code, 202)
        for bad in (self.audio().id, self.audio(workspace=self.other_workspace, kind="image").id, 0, True):
            with self.subTest(bad=bad):
                self.assertEqual(self.picture({"prompt": "x", "reference_asset_id": bad}).status_code, 400)

    def test_only_pictures_with_a_reference_send_an_input(self):
        image = self.audio(kind="image")
        jobs = [GenerationJob.objects.create(workspace=self.workspace, requested_by=self.editor, capability="text_to_image",
                                             params=params)
                for params in ({"prompt": "x", "reference_asset_id": image.id}, {"prompt": "x"})]
        payloads = []
        for job in jobs:
            with patch("apps.generation.tasks.runpod.submit", return_value="rp-6") as submit, patch("apps.generation.tasks.schedule_poll"):
                submit_job(job.id)
            payloads.append(submit.call_args.args[0])
        self.assertIn("input", payloads[0])
        self.assertNotIn("input", payloads[1])


class CharacterVoiceSampleTests(Base):
    def test_a_character_keeps_an_audio_voice_sample_from_its_workspace(self):
        key = default_storage.save(f"workspaces/{self.workspace.id}/assets/v.wav", ContentFile(WAV))
        sample = Asset.objects.create(workspace=self.workspace, asset_type="audio", name="v.wav", storage_key=key,
                                      content_type="audio/wav", size_bytes=len(WAV))
        image = Asset.objects.create(workspace=self.workspace, asset_type="image", name="i.png", storage_key="k/i.png",
                                     content_type="image/png", size_bytes=1)
        character = Character.objects.create(workspace=self.workspace, name="Ada")
        url = f"/api/characters/{character.id}/"
        response = self.patch(url, {"voice_sample_asset_id": sample.id})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["voice_sample_asset_id"], sample.id)
        self.assertEqual(self.patch(url, {"voice_sample_asset_id": image.id}).status_code, 400)
        self.assertIsNone(self.patch(url, {"voice_sample_asset_id": None}).json()["voice_sample_asset_id"])
