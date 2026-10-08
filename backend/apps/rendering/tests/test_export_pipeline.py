import json
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.jobs.models import GenerationJob
from apps.studio.models import Asset, CaptionTrack, Scene
from apps.studio.tests.fixtures import StudioFixture


class ExportPipelineTests(StudioFixture):
    def setUp(self):
        super().setUp()
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.owner)
        self.url = f"/api/projects/{self.project.id}/exports/"

    def asset(self, *, video=False, foreign=False):
        workspace = self.other_workspace if foreign else self.workspace
        key = default_storage.save(
            f"workspaces/{workspace.id}/assets/fixture.{ 'mp4' if video else 'png'}",
            ContentFile(b"fixture media"),
        )
        return Asset.objects.create(
            workspace=workspace, asset_type="video" if video else "image", name="fixture",
            storage_key=key, content_type="video/mp4" if video else "image/png", size_bytes=13,
        )

    def scene(self, asset=None, **config):
        return Scene.objects.create(
            project=self.project, order_index=self.project.scenes.count(),
            kind="video" if asset and asset.asset_type == "video" else "image",
            title="Scene", config={**({"asset_id": asset.id} if asset else {}), **config},
        )

    def create_export(self, data=None):
        with self.captureOnCommitCallbacks(execute=False):
            response = self.post(self.url, data or {})
        self.assertEqual(response.status_code, 201, response.content)
        from apps.studio.models import Export
        return Export.objects.get(pk=response.json()["id"])

    def fake_process(self, command, **kwargs):
        self.assertIsInstance(command, list)
        self.assertIs(kwargs["shell"], False)
        self.assertGreater(kwargs["timeout"], 0)
        self.assertLessEqual(kwargs["timeout"], 600)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
                "format": {"duration": "2.5"},
                "streams": [
                    {"codec_type": "video", "width": 640, "height": 360},
                    {"codec_type": "audio"},
                ],
            }).encode())
        self.assertIn("-protocol_whitelist", command)
        self.assertIn("file", command)
        self.assertIn("-threads", command)
        self.assertIn("-fs", command)
        Path(command[-1]).write_bytes(b"assembled mp4")
        return subprocess.CompletedProcess(command, 0)

    def render(self, export, process=None):
        from apps.rendering.tasks import render_export
        with patch("apps.rendering.services.subprocess.run", side_effect=process or self.fake_process):
            render_export(export.id)
        export.refresh_from_db()

    def test_create_persists_safe_defaults_and_private_snapshot(self):
        scene = self.scene(self.asset())
        export = self.create_export()
        self.assertEqual(export.status, "queued")
        self.assertEqual(export.format, "9:16")
        self.assertEqual(export.settings, {
            "width": 1080, "height": 1920, "fps": 30, "video_codec": "libx264",
            "audio_codec": "aac", "burn_captions": True, "caption_track_id": None,
        })
        self.assertEqual(export.manifest["scenes"][0]["duration_seconds"], 5)
        scene.config["duration_seconds"] = 80
        scene.save()
        self.assertEqual(export.manifest["scenes"][0]["duration_seconds"], 5)
        detail = self.client.get(f"/api/exports/{export.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("storage_key", detail.content.decode())
        self.assertNotIn("manifest", detail.json())
        self.assertNotIn("output_path", detail.json())

    def test_no_source_is_explicit_failed_export(self):
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.status, "failed")
        self.assertEqual(export.error_code, "export_no_source")
        self.assertTrue(export.error_message)
        self.assertFalse(export.output_path)

    def test_foreign_and_reviewer_access(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.post(self.url, {}).status_code, 404)
        self.client.force_login(self.owner)
        export = self.create_export()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/api/exports/{export.id}/").status_code, 404)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.post(self.url, {}).status_code, 403)
        self.assertEqual(self.client.get(f"/api/exports/{export.id}/").status_code, 200)
        self.client.force_login(self.editor)
        self.assertEqual(self.post(self.url, {}).status_code, 201)

    def test_invalid_settings_rejected_without_record(self):
        from apps.studio.models import Export
        for data in [
            {"format": "1:1"}, {"format": "../../out"}, {"output_path": "C:\\secret.mp4"},
            {"codec": "-evil"}, {"settings": {"filter": "movie=http://internal"}},
            {"burn_captions": "yes"}, {"caption_track_id": True},
        ]:
            with self.subTest(data=data):
                self.assertEqual(self.post(self.url, data).status_code, 400)
        self.assertEqual(Export.objects.count(), 0)

    def test_caption_selection_and_scope(self):
        first = CaptionTrack.objects.create(project=self.project, language="en", segments=[])
        CaptionTrack.objects.create(project=self.project, language="fr", segments=[])
        self.assertEqual(self.post(self.url, {}).status_code, 400)
        export = self.create_export({"caption_track_id": first.id, "format": "16:9"})
        self.assertEqual((export.settings["width"], export.settings["height"]), (1920, 1080))
        from apps.studio.models import Project
        other = Project.objects.create(workspace=self.other_workspace, title="Other", format="9:16")
        foreign = CaptionTrack.objects.create(project=other, language="en")
        self.assertEqual(self.post(self.url, {"caption_track_id": foreign.id}).status_code, 404)

    def test_foreign_asset_and_generation_job_return_404(self):
        scene = self.scene(self.asset(foreign=True))
        self.assertEqual(self.post(self.url, {}).status_code, 404)
        foreign = GenerationJob.objects.create(
            workspace=self.other_workspace, capability="image.generate", status="completed",
        )
        scene.config = {"generation_job_id": foreign.id}
        scene.save()
        self.assertEqual(self.post(self.url, {}).status_code, 404)

    def test_temporary_provider_url_and_client_path_never_render(self):
        job = GenerationJob.objects.create(
            workspace=self.workspace, project=self.project, capability="image.generate",
            status="completed", result={"url": "http://127.0.0.1/private"},
        )
        scene = self.scene(generation_job_id=job.id)
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.error_code, "export_source_unavailable")
        scene.config = {"rendered_path": "C:\\secret.mp4"}
        scene.save()
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.error_code, "export_unsafe_source")

    def test_durable_job_asset_can_render(self):
        asset = self.asset()
        job = GenerationJob.objects.create(
            workspace=self.workspace, project=self.project, capability="image.generate",
            status="completed", result={"asset_id": asset.id}, asset_status="ready", generated_asset=asset,
        )
        self.scene(generation_job_id=job.id)
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.status, "completed")

    def test_image_duration_bounds_and_video_duration_override_rejected(self):
        image = self.asset()
        scene = self.scene(image)
        for value in [0, 121, True, "5", 10**400]:
            scene.config = {"asset_id": image.id, "duration_seconds": value}
            scene.save()
            self.assertEqual(self.post(self.url, {}).status_code, 400)
        scene.config = {"asset_id": self.asset(video=True).id, "duration_seconds": 5}
        scene.save()
        self.assertEqual(self.post(self.url, {}).status_code, 400)
        for value in [1, 120]:
            scene.config = {"asset_id": image.id, "duration_seconds": value}
            scene.save()
            self.assertEqual(self.post(self.url, {}).status_code, 201)

    def test_ordered_render_burns_captions_and_publishes_both_files_once(self):
        image = self.asset()
        video = self.asset(video=True)
        self.scene(video)
        image_scene = self.scene(image, duration_seconds=3)
        image_scene.order_index = 0
        image_scene.save()
        self.project.scenes.filter(config__asset_id=video.id).update(order_index=1)
        CaptionTrack.objects.create(
            project=self.project, language="en",
            segments=[{"start": 0, "end": 1.25, "text": "<b>Hello</b>\nworld"}],
        )
        export = self.create_export()
        calls = []
        def process(command, **kwargs):
            export.refresh_from_db()
            self.assertEqual(export.status, "processing")
            calls.append(command)
            return self.fake_process(command, **kwargs)
        self.render(export, process)
        self.assertEqual(export.status, "completed")
        self.assertEqual(export.attempts, 1)
        with default_storage.open(export.subtitle_path) as subtitle:
            self.assertEqual(subtitle.read().decode(), "1\n00:00:00,000 --> 00:00:01,250\nHello\nworld\n")
        with default_storage.open(export.output_path) as output:
            self.assertEqual(output.read(), b"assembled mp4")
        render_commands = [c for c in calls if c[0] == "ffmpeg"]
        self.assertEqual(len(render_commands), 3)
        self.assertIn("-loop", render_commands[0])
        self.assertNotIn("-loop", render_commands[1])
        self.assertIn("concat=n=2:v=1:a=1", " ".join(render_commands[-1]))
        self.assertIn("subtitles=captions.srt", " ".join(render_commands[-1]))
        self.assertIn("scale=1080:1920", " ".join(render_commands[0]))
        self.assertIn("libx264", render_commands[-1])
        self.assertIn("aac", render_commands[-1])
        paths = (export.output_path, export.subtitle_path)
        def forbidden(*args, **kwargs):
            self.fail("A completed delivery must not run FFmpeg again")
        self.render(export, forbidden)
        self.assertEqual((export.output_path, export.subtitle_path), paths)
        self.assertEqual(export.attempts, 1)

    def test_disabled_burn_in_still_publishes_subtitles(self):
        self.scene(self.asset())
        CaptionTrack.objects.create(
            project=self.project, language="en", segments=[{"start": 0, "end": 1, "text": "Hello"}],
        )
        export = self.create_export({"burn_captions": False})
        calls = []
        def process(command, **kwargs):
            calls.append(command)
            return self.fake_process(command, **kwargs)
        self.render(export, process)
        self.assertEqual(export.status, "completed")
        self.assertTrue(export.subtitle_path)
        self.assertNotIn("subtitles=", " ".join(calls[-1]))

    def test_subprocess_failures_are_structured_without_paths_or_stderr(self):
        self.scene(self.asset())
        for error, code in [
            (FileNotFoundError("C:\\private\\ffmpeg"), "export_binary_missing"),
            (subprocess.CalledProcessError(1, ["ffmpeg"], stderr=b"private path"), "export_process_failed"),
            (subprocess.TimeoutExpired(["ffmpeg"], 600), "export_timeout"),
        ]:
            export = self.create_export()
            def process(*args, **kwargs):
                raise error
            self.render(export, process)
            self.assertEqual(export.status, "failed")
            self.assertEqual(export.error_code, code)
            self.assertFalse(export.output_path)
            self.assertFalse(export.subtitle_path)
            self.assertNotIn("private", export.error_message)

    def test_missing_media_and_unsafe_storage_key_fail(self):
        asset = self.asset()
        self.scene(asset)
        default_storage.delete(asset.storage_key)
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.error_code, "export_source_missing")
        asset.storage_key = "../../secret.mp4"
        asset.save()
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.error_code, "export_unsafe_source")

    def test_bad_probe_and_no_output_fail_instead_of_success(self):
        self.scene(self.asset(video=True))
        export = self.create_export()
        self.render(export, lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout=b'{"format":{"duration":"nan"},"streams":[]}'))
        self.assertEqual(export.error_code, "export_invalid_media")
        export = self.create_export()
        def no_output(command, **kwargs):
            if command[0] == "ffprobe":
                return self.fake_process(command, **kwargs)
            return subprocess.CompletedProcess(command, 0)
        self.render(export, no_output)
        self.assertEqual(export.error_code, "export_output_missing")

    def test_broker_failure_retains_recoverable_schedule(self):
        from apps.rendering.tasks import recover_exports
        with patch("apps.rendering.tasks.render_export.delay", side_effect=OperationalError("offline")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post(self.url, {})
            self.assertEqual(response.status_code, 201)
            from apps.studio.models import Export
            export = Export.objects.get(pk=response.json()["id"])
            self.assertEqual(export.status, "queued")
            self.assertEqual(export.error_code, "export_dispatch_unavailable")
        export.next_attempt_at = timezone.now() - timedelta(seconds=1)
        export.save()
        with patch("apps.rendering.tasks.render_export.delay", side_effect=lambda pk: None):
            recover_exports()
        export.refresh_from_db()
        self.assertGreater(export.next_attempt_at, timezone.now())

    def test_stale_attempt_is_fenced_and_retry_budget_bounded(self):
        from apps.rendering.tasks import recover_exports
        export = self.create_export()
        export.status = "processing"
        export.attempts = 3
        export.attempt_token = "a" * 32
        export.lease_expires_at = timezone.now() - timedelta(seconds=1)
        export.save()
        recover_exports()
        export.refresh_from_db()
        self.assertEqual(export.status, "failed")
        self.assertEqual(export.error_code, "export_retry_exhausted")
        self.assertFalse(export.attempt_token)

    def test_failed_sidecar_publication_cleans_video_and_remains_failed(self):
        self.scene(self.asset())
        CaptionTrack.objects.create(
            project=self.project, language="en", segments=[{"start": 0, "end": 1, "text": "Hi"}],
        )
        export = self.create_export()
        save = default_storage.save
        def fail_sidecar(key, content, **kwargs):
            if key.endswith(".srt"):
                raise OSError("storage unavailable")
            return save(key, content, **kwargs)
        with patch("apps.rendering.tasks.default_storage.save", side_effect=fail_sidecar):
            self.render(export)
        self.assertEqual(export.error_code, "export_storage_failed")
        self.assertFalse(export.output_path)
        self.assertFalse(export.subtitle_path)
        self.assertEqual(list(Path(self.media.name).rglob("*.mp4")), [])

    def test_recovery_dispatch_can_start_before_next_sweep_and_old_attempt_cannot_publish(self):
        from apps.rendering.tasks import claim_export, publish_export, recover_exports, render_export
        self.scene(self.asset())
        export = self.create_export()
        old = claim_export(export.id)
        export.refresh_from_db()
        old_key = export.cleanup_keys[0]
        default_storage.save(old_key, ContentFile(b"interrupted output"))
        export.lease_expires_at = timezone.now() - timedelta(seconds=1)
        export.save()
        with patch(
            "apps.rendering.tasks.render_export.apply_async",
            side_effect=lambda args, *pos, **kw: render_export(args[0]),
        ):
            with patch("apps.rendering.services.subprocess.run", side_effect=self.fake_process):
                with self.captureOnCommitCallbacks(execute=True):
                    recover_exports()
        export.refresh_from_db()
        self.assertEqual(export.status, "completed")
        self.assertEqual(export.attempts, 2)
        self.assertFalse(default_storage.exists(old_key))
        published = export.output_path
        with tempfile.TemporaryDirectory() as scratch:
            old_output = Path(scratch) / "old.mp4"
            old_output.write_bytes(b"obsolete")
            publish_export(old, old_output, None)
        export.refresh_from_db()
        self.assertEqual(export.output_path, published)
        with default_storage.open(published) as content:
            self.assertEqual(content.read(), b"assembled mp4")

    def test_completed_artifacts_can_be_downloaded_privately_by_reviewer_only(self):
        self.scene(self.asset())
        CaptionTrack.objects.create(
            project=self.project, language="en", segments=[{"start": 0, "end": 1, "text": "Hi"}],
        )
        export = self.create_export()
        self.render(export)
        self.client.force_login(self.reviewer)
        for kind, expected in [("video", b"assembled mp4"), ("subtitles", b"1\n")]:
            response = self.client.get(f"/api/exports/{export.id}/{kind}/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(b"".join(response.streaming_content).startswith(expected))
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertNotIn("workspaces", response["Content-Disposition"])
            response.close()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/api/exports/{export.id}/video/").status_code, 404)

    def test_terminal_exports_do_not_starve_queued_recovery(self):
        from apps.rendering.tasks import recover_exports
        from apps.studio.models import Export
        Export.objects.bulk_create([
            Export(project=self.project, format="9:16", status="failed") for _ in range(101)
        ])
        queued = self.create_export()
        recover_exports()
        queued.refresh_from_db()
        self.assertGreater(queued.next_attempt_at, timezone.now())

    def test_resource_duration_limits_and_image_probe_without_duration(self):
        self.scene(self.asset(), duration_seconds=120)
        for _ in range(5):
            self.scene(self.asset(), duration_seconds=120)
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.error_code, "export_resource_limit")
        self.project.scenes.all().delete()
        self.scene(self.asset())
        export = self.create_export({"format": "16:9"})
        commands = []
        def image_process(command, **kwargs):
            commands.append(command)
            if command[0] == "ffprobe":
                return subprocess.CompletedProcess(command, 0, stdout=b'{"streams":[{"codec_type":"video","width":64,"height":64}]}')
            return self.fake_process(command, **kwargs)
        self.render(export, image_process)
        self.assertEqual(export.status, "completed")
        self.assertIn("scale=1920:1080", " ".join(commands[1]))

    def test_active_delivery_does_not_claim_twice_or_publish_after_lease_expiry(self):
        from apps.rendering.tasks import claim_export, publish_export
        self.scene(self.asset())
        export = self.create_export()
        attempt = claim_export(export.id)
        self.assertIsNone(claim_export(export.id))
        export.refresh_from_db()
        self.assertEqual(export.attempts, 1)
        export.lease_expires_at = timezone.now() - timedelta(seconds=1)
        export.save()
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "out.mp4"
            output.write_bytes(b"late output")
            publish_export(attempt, output, None)
        export.refresh_from_db()
        self.assertEqual(export.status, "processing")
        self.assertFalse(export.output_path)
        self.assertFalse(default_storage.exists(export.cleanup_keys[0]))

    def test_caption_snapshot_does_not_change_with_later_edits(self):
        self.scene(self.asset())
        caption = CaptionTrack.objects.create(
            project=self.project, language="en", segments=[{"start": 0, "end": 1, "text": "Original"}],
        )
        export = self.create_export()
        caption.segments = [{"start": 0, "end": 1, "text": "Changed"}]
        caption.save()
        self.render(export)
        with default_storage.open(export.subtitle_path) as content:
            self.assertIn(b"Original", content.read())

    def test_captions_past_video_end_and_oversized_source_fail_explicitly(self):
        from apps.rendering import services
        asset = self.asset()
        self.scene(asset)
        caption = CaptionTrack.objects.create(
            project=self.project, language="en", segments=[{"start": 0, "end": 6, "text": "Too late"}],
        )
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.error_code, "export_invalid_captions")
        caption.delete()
        export = self.create_export()
        with patch.object(services, "MAX_BYTES", 5):
            self.render(export)
        self.assertEqual(export.error_code, "export_resource_limit")

    def test_scene_count_is_bounded_and_partial_scene_exports_are_not_silent(self):
        from apps.studio.models import Export
        self.scene(self.asset())
        self.scene()
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.error_code, "export_no_source")
        for _ in range(19):
            self.scene()
        count = Export.objects.count()
        self.assertEqual(self.post(self.url, {}).status_code, 400)
        self.assertEqual(Export.objects.count(), count)

    def test_video_without_audio_gets_silence_and_timestamps_are_reset(self):
        self.scene(self.asset(video=True))
        export = self.create_export()
        commands = []
        def process(command, **kwargs):
            commands.append(command)
            if command[0] == "ffprobe":
                return subprocess.CompletedProcess(command, 0, stdout=b'{"format":{"duration":"2"},"streams":[{"codec_type":"video","width":64,"height":64}]}')
            return self.fake_process(command, **kwargs)
        self.render(export, process)
        self.assertEqual(export.status, "completed")
        self.assertIn("anullsrc=r=48000:cl=stereo", commands[1])
        self.assertIn("setpts=PTS-STARTPTS", " ".join(commands[1]))
        self.assertIn("asetpts=PTS-STARTPTS", " ".join(commands[1]))

    def test_invalid_probe_dimensions_are_rejected_before_ffmpeg(self):
        self.scene(self.asset(video=True))
        for width in [0, 5000, "invalid"]:
            export = self.create_export()
            def process(command, **kwargs):
                self.assertEqual(command[0], "ffprobe")
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
                    "format": {"duration": "2"},
                    "streams": [{"codec_type": "video", "width": width, "height": 64}],
                }).encode())
            self.render(export, process)
            self.assertEqual(export.error_code, "export_invalid_media")


class ExportCommandTests(SimpleTestCase):
    def test_commands_reject_urls_relative_paths_and_invalid_dimensions(self):
        from apps.rendering.services import ExportFailure, build_ffmpeg_command
        with tempfile.TemporaryDirectory() as scratch:
            output = str(Path(scratch) / "out.mp4")
            for value in ["https://internal/clip.mp4", "..\\clip.mp4", "relative.mp4"]:
                with self.subTest(value=value), self.assertRaises(ExportFailure):
                    build_ffmpeg_command(scene_paths=[value], output_path=output, burn_captions=False)
            with self.assertRaises(ExportFailure):
                build_ffmpeg_command(
                    scene_paths=[str(Path(scratch) / "scene.mp4")], output_path=output,
                    burn_captions=False, width=1, height=2,
                )
