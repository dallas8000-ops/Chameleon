import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.rendering.services import ExportFailure, ass_document, ass_text, overlay_events
from apps.studio.models import Asset, Export, Scene
from apps.studio.tests.fixtures import StudioFixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FeatureBase(StudioFixture):
    def setUp(self):
        super().setUp()
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.owner)
        self.url = f"/api/projects/{self.project.id}/exports/"

    def asset(self, kind="image", workspace=None):
        workspace = workspace or self.workspace
        ext = {"image": "png", "video": "mp4", "audio": "wav"}[kind]
        key = default_storage.save(f"workspaces/{workspace.id}/assets/fixture.{ext}", ContentFile(b"fixture media"))
        return Asset.objects.create(
            workspace=workspace, asset_type=kind, name="fixture", storage_key=key,
            content_type={"image": "image/png", "video": "video/mp4", "audio": "audio/wav"}[kind], size_bytes=13,
        )

    def scene(self, asset, **config):
        return Scene.objects.create(
            project=self.project, order_index=self.project.scenes.count(), kind=asset.asset_type, title="Scene",
            config={"asset_id": asset.id, **config},
        )

    def create_export(self, data=None):
        with self.captureOnCommitCallbacks(execute=False):
            response = self.post(self.url, data or {})
        self.assertEqual(response.status_code, 201, response.content)
        return Export.objects.get(pk=response.json()["id"])


class SceneConfigValidationTests(FeatureBase):
    def patch_config(self, scene, **config):
        return self.patch(f"/api/scenes/{scene.id}/", {"config": config})

    def test_valid_render_settings_are_accepted_and_normalized(self):
        scene = self.scene(self.asset("video"))
        response = self.patch_config(
            scene, asset_id=scene.config["asset_id"], trim_start=1, trim_end=4.5, audio_volume=1.5, audio_start=0.5,
            clip_volume=0.3, source="keep-me",
            overlays=[{"text": "  Hook  ", "start": 0, "end": 2}],
        )
        self.assertEqual(response.status_code, 200, response.content)
        config = response.json()["config"]
        self.assertEqual(config["trim_end"], 4.5)
        self.assertEqual(config["source"], "keep-me")
        self.assertEqual(config["overlays"], [{"text": "Hook", "start": 0.0, "end": 2.0, "position": "center", "size": "medium"}])

    def test_invalid_render_settings_are_rejected(self):
        scene = self.scene(self.asset("video"))
        bad = [
            {"trim_start": -1}, {"trim_start": True}, {"trim_start": "1"}, {"trim_start": 601},
            {"trim_start": 3, "trim_end": 2}, {"trim_end": 0},
            {"audio_volume": 3}, {"clip_volume": -0.1}, {"audio_start": 1e400}, {"audio_asset_id": 0},
            {"audio_asset_id": "7"}, {"fit_to_audio": "yes"},
            {"overlays": "x"}, {"overlays": [{"text": "x"}]}, {"overlays": [{"text": "", "end": 2}]},
            {"overlays": [{"text": "x", "start": 2, "end": 1}]},
            {"overlays": [{"text": "x", "end": 2, "position": "left"}]},
            {"overlays": [{"text": "x", "end": 2, "size": "huge"}]},
            {"overlays": [{"text": "x", "end": 2, "color": "red"}]},
            {"overlays": [{"text": "x" * 141, "end": 2}]},
            {"overlays": [{"text": "x", "end": 2}] * 6},
        ]
        for config in bad:
            with self.subTest(config=config):
                self.assertEqual(self.patch_config(scene, **config).status_code, 400)

    def test_null_clears_optional_settings(self):
        scene = self.scene(self.asset("video"), trim_start=1, trim_end=3)
        config = self.patch_config(scene, trim_start=None, trim_end=None).json()["config"]
        self.assertNotIn("trim_start", config)
        self.assertNotIn("trim_end", config)


class AudioAssetTests(FeatureBase):
    def upload(self, content, name, content_type):
        return self.client.post("/api/assets/", {
            "workspace_id": self.workspace.id, "file": SimpleUploadedFile(name, content, content_type=content_type),
        })

    def test_wav_mp3_and_m4a_are_accepted_as_audio(self):
        samples = [
            (b"RIFF\x00\x00\x00\x00WAVEfmt ", "voice.wav", "audio/wav", "wav"),
            (b"RIFF\x00\x00\x00\x00WAVEfmt ", "voice.wav", "audio/x-wav", "wav"),
            (b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 8, "voice.mp3", "audio/mpeg", "mp3"),
            (b"\xff\xfb\x90\x00" + b"\x00" * 12, "voice.mp3", "audio/mpeg", "mp3"),
            (b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00", "voice.m4a", "audio/mp4", "m4a"),
            (b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00", "voice.m4a", "audio/x-m4a", "m4a"),
        ]
        for content, name, declared, extension in samples:
            with self.subTest(name=name, declared=declared):
                response = self.upload(content, name, declared)
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()["asset_type"], "audio")
                asset = Asset.objects.get(pk=response.json()["id"])
                self.assertTrue(asset.storage_key.endswith("." + extension))
        served = self.client.get(f"/api/assets/{asset.id}/content/")
        self.addCleanup(served.close)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served["Content-Type"], "audio/mp4")

    def test_mismatched_or_unknown_audio_is_rejected(self):
        self.assertEqual(self.upload(b"RIFF\x00\x00\x00\x00WAVEfmt ", "x.wav", "image/png").status_code, 400)
        self.assertEqual(self.upload(b"not audio at all....", "x.wav", "audio/wav").status_code, 400)

    def test_mp4_video_is_still_video(self):
        response = self.upload(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00", "clip.mp4", "video/mp4")
        self.assertEqual(response.json()["asset_type"], "video")

    def test_audio_cannot_be_a_scene_source_or_character_reference(self):
        audio = self.asset("audio")
        Scene.objects.create(project=self.project, order_index=0, kind="video", title="S", config={"asset_id": audio.id})
        self.assertEqual(self.post(self.url, {}).status_code, 400)
        response = self.post("/api/characters/", {"workspace_id": self.workspace.id, "name": "X", "reference_asset_id": audio.id})
        self.assertEqual(response.status_code, 400)


class ProjectUpdateTests(FeatureBase):
    def test_ai_disclosure_and_title_can_be_updated_by_editors_only(self):
        url = f"/api/projects/{self.project.id}/"
        response = self.patch(url, {"ai_disclosure": True, "title": "  New title "})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["ai_disclosure"], response.json()["title"]), (True, "New title"))
        self.assertTrue(self.client.get(url).json()["ai_disclosure"])
        self.assertEqual(self.patch(url, {}).status_code, 400)
        self.assertEqual(self.patch(url, {"title": " "}).status_code, 400)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.patch(url, {"ai_disclosure": False}).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.patch(url, {"ai_disclosure": False}).status_code, 404)


class SnapshotTests(FeatureBase):
    def test_manifest_carries_trim_overlays_and_voice_track(self):
        video, voice = self.asset("video"), self.asset("audio")
        overlays = [{"text": "Hook", "start": 0, "end": 2, "position": "top", "size": "large"}]
        self.scene(video, trim_start=1, trim_end=3, overlays=overlays, audio_asset_id=voice.id, audio_volume=0.8, clip_volume=0.2)
        export = self.create_export({"burn_ai_label": True})
        scene = export.manifest["scenes"][0]
        self.assertEqual((scene["trim_start"], scene["trim_end"], scene["clip_volume"]), (1, 3, 0.2))
        self.assertEqual(scene["overlays"][0]["position"], "top")
        self.assertEqual(scene["audio"], {"asset_id": voice.id, "storage_key": voice.storage_key, "volume": 0.8, "start": 0.0})
        self.assertTrue(export.settings["burn_ai_label"])

    def test_foreign_or_non_audio_voice_track_is_not_found(self):
        image = self.asset("image")
        self.scene(image, audio_asset_id=self.asset("audio", workspace=self.other_workspace).id)
        self.assertEqual(self.post(self.url, {}).status_code, 404)
        Scene.objects.all().delete()
        self.scene(image, audio_asset_id=self.asset("image").id)
        self.assertEqual(self.post(self.url, {}).status_code, 404)

    def test_fit_to_audio_needs_a_voice_track(self):
        self.scene(self.asset("image"), fit_to_audio=True)
        self.assertEqual(self.post(self.url, {}).status_code, 400)

    def test_burn_ai_label_must_be_boolean(self):
        self.scene(self.asset("image"))
        self.assertEqual(self.post(self.url, {"burn_ai_label": "yes"}).status_code, 400)


class FakeFfmpegBase(FeatureBase):
    def setUp(self):
        super().setUp()
        self.commands = []

    def fake_process(self, command, **kwargs):
        self.commands.append(command)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
                "format": {"duration": "8.0"},
                "streams": [{"codec_type": "video", "width": 640, "height": 360}, {"codec_type": "audio"}],
            }).encode())
        Path(command[-1]).write_bytes(b"assembled mp4")
        return subprocess.CompletedProcess(command, 0)

    def render(self, export):
        from apps.rendering.tasks import render_export
        with patch("apps.rendering.services.subprocess.run", side_effect=self.fake_process):
            render_export(export.id)
        export.refresh_from_db()


class RenderCommandTests(FakeFfmpegBase):
    def scene_command(self):
        return next(c for c in self.commands if c[0] != "ffprobe" and c[-1].endswith("scene-0.mp4"))

    def test_video_trim_uses_seek_and_trimmed_length(self):
        self.scene(self.asset("video"), trim_start=2, trim_end=5)
        export = self.create_export()
        self.render(export)
        self.assertEqual(export.status, "completed", export.error_message)
        command = self.scene_command()
        self.assertEqual(command[command.index("-ss") + 1], "2.000")
        self.assertEqual(command[command.index("-t") + 1], "3.0")

    def test_trim_past_the_end_of_the_clip_fails_clearly(self):
        self.scene(self.asset("video"), trim_start=9)
        export = self.create_export()
        self.render(export)
        self.assertEqual((export.status, export.error_code), ("failed", "export_invalid_trim"))

    def test_trim_end_beyond_the_clip_is_clamped(self):
        self.scene(self.asset("video"), trim_start=6, trim_end=50)
        export = self.create_export()
        self.render(export)
        self.assertEqual(self.scene_command()[self.scene_command().index("-t") + 1], "2.0")

    def test_overlays_add_an_ass_filter_and_never_use_raw_text_in_the_command(self):
        self.scene(self.asset("image"), duration_seconds=4, overlays=[{"text": "Hello: {\\an1}'world'", "start": 0, "end": 2}])
        export = self.create_export()
        self.render(export)
        command = self.scene_command()
        self.assertIn("ass=overlays-0.ass", command[command.index("-vf") + 1])
        self.assertFalse(any("world" in part for part in command))

    def test_voice_track_is_mixed_and_delayed(self):
        voice = self.asset("audio")
        self.scene(self.asset("image"), duration_seconds=4, audio_asset_id=voice.id, audio_start=0.5, audio_volume=0.7)
        export = self.create_export()
        self.render(export)
        command = self.scene_command()
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("adelay=500|500", graph)
        self.assertIn("volume=0.7", graph)
        self.assertIn("amix=inputs=2", graph)
        self.assertEqual(command.count("-i"), 3)

    def test_fit_to_audio_uses_the_voice_track_length(self):
        voice = self.asset("audio")
        self.scene(self.asset("image"), fit_to_audio=True, audio_asset_id=voice.id)
        export = self.create_export()
        self.render(export)
        self.assertEqual(self.scene_command()[self.scene_command().index("-t") + 1], "8.0")

    def test_ai_label_is_burned_only_when_requested(self):
        self.scene(self.asset("image"))
        plain = self.create_export()
        self.render(plain)
        final = [c for c in self.commands if c[0] != "ffprobe" and c[-1].endswith("export.mp4")][-1]
        self.assertNotIn("label.ass", final[final.index("-filter_complex") + 1])
        self.commands.clear()
        labelled = self.create_export({"burn_ai_label": True})
        self.render(labelled)
        final = [c for c in self.commands if c[0] != "ffprobe" and c[-1].endswith("export.mp4")][-1]
        self.assertIn("ass=label.ass", final[final.index("-filter_complex") + 1])


class AssHelperTests(StudioFixture):
    def test_text_is_stripped_of_override_codes_and_joined_with_ass_newlines(self):
        self.assertEqual(ass_text("Hi {\\b1}there\\N\nsecond"), "Hi b1thereN" + r"\N" + "second")
        self.assertNotIn("{", ass_text("{x}{\\an9}"))

    def test_events_are_clamped_to_the_scene_and_skip_empty_text(self):
        overlays = [
            {"text": "A", "start": 1, "end": 99, "position": "top", "size": "small"},
            {"text": "B", "start": 5, "end": 6, "position": "center", "size": "medium"},
            {"text": "{}", "start": 0, "end": 1, "position": "bottom", "size": "large"},
        ]
        events = overlay_events(overlays, 4.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][:2], (1.0, 4.0))
        document = ass_document(1080, 1920, events)
        self.assertIn("PlayResX: 1080", document)
        self.assertIn("Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,140,,{\\an8\\fs48}A", document)


FFMPEG = os.environ.get("FFMPEG_BINARY", "")
FFPROBE = os.environ.get("FFPROBE_BINARY", "")


@skipUnless(FFMPEG and FFPROBE and Path(FFMPEG).exists() and Path(FFPROBE).exists(), "Set FFMPEG_BINARY and FFPROBE_BINARY to run.")
class RealFfmpegTests(FeatureBase):
    """Renders real media. Run with FFMPEG_BINARY and FFPROBE_BINARY pointing at working binaries."""

    def setUp(self):
        super().setUp()
        override = override_settings(FFMPEG_BINARY=FFMPEG, FFPROBE_BINARY=FFPROBE)
        override.enable()
        self.addCleanup(override.disable)
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, True)

    def make(self, name, *args):
        target = self.work / name
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args, str(target)], check=True)
        return target

    def store(self, path, kind):
        key = default_storage.save(f"workspaces/{self.workspace.id}/assets/{path.name}", ContentFile(path.read_bytes()))
        return Asset.objects.create(
            workspace=self.workspace, asset_type=kind, name=path.name, storage_key=key,
            content_type={"image": "image/png", "video": "video/mp4", "audio": "audio/wav"}[kind], size_bytes=path.stat().st_size,
        )

    def render(self, export):
        from apps.rendering.tasks import render_export
        render_export(export.id)
        export.refresh_from_db()
        self.assertEqual(export.status, "completed", export.error_message)
        path = Path(default_storage.path(export.output_path))
        probe = json.loads(subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
            check=True, capture_output=True,
        ).stdout)
        return path, probe

    def frame_hash(self, path, at):
        out = subprocess.run(
            [FFMPEG, "-v", "error", "-ss", str(at), "-i", str(path), "-frames:v", "1", "-f", "md5", "-"],
            check=True, capture_output=True,
        )
        return out.stdout.decode().strip()

    def test_trim_overlay_voice_and_label_render_in_a_real_export(self):
        clip = self.make("clip.mp4", "-f", "lavfi", "-i", "color=c=navy:s=640x360:d=6:r=25", "-f", "lavfi",
                         "-i", "sine=frequency=300:duration=6", "-shortest", "-pix_fmt", "yuv420p")
        still = self.make("still.png", "-f", "lavfi", "-i", "color=c=teal:s=320x180", "-frames:v", "1")
        voice = self.make("voice.wav", "-f", "lavfi", "-i", "sine=frequency=800:duration=2.5")
        video_asset, image_asset, voice_asset = self.store(clip, "video"), self.store(still, "image"), self.store(voice, "audio")

        self.scene(video_asset, trim_start=1, trim_end=3.5)
        overlay_scene = self.scene(image_asset, fit_to_audio=True, audio_asset_id=voice_asset.id, audio_start=0.5,
                                   overlays=[{"text": "Muzungu = foreigner", "start": 0.2, "end": 2.5, "position": "center", "size": "large"}])
        plain, _ = self.render(self.create_export())  # exports with overlays, no label
        path, probe = self.render(self.create_export({"burn_ai_label": True}))

        streams = {s["codec_type"]: s for s in probe["streams"]}
        self.assertEqual((streams["video"]["width"], streams["video"]["height"]), (1080, 1920))
        self.assertIn("audio", streams)
        # 2.5 s trimmed clip + voice (0.5 s delay + 2.5 s) = 6.0 s.
        self.assertAlmostEqual(float(probe["format"]["duration"]), 2.5 + 3.0, delta=0.3)

        # The overlay is really drawn: the same frame differs once the overlay is removed.
        overlay_scene.config = {key: value for key, value in overlay_scene.config.items() if key != "overlays"}
        overlay_scene.save()
        bare, _ = self.render(self.create_export())
        at_overlay = 2.5 + 1.0
        self.assertNotEqual(self.frame_hash(plain, at_overlay), self.frame_hash(bare, at_overlay))
        # The AI label is drawn only when requested.
        self.assertNotEqual(self.frame_hash(path, 0.5), self.frame_hash(bare, 0.5))
        self.assertEqual(self.frame_hash(plain, 0.5), self.frame_hash(bare, 0.5))
