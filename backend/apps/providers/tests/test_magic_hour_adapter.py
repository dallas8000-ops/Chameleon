import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.providers.base import ProviderError
from apps.providers.magic_hour import MagicHourProvider


class MagicHourAdapterTests(SimpleTestCase):
    @override_settings(MAGIC_HOUR_API_KEY="private-test-key")
    @patch("apps.providers.magic_hour.urlopen")
    def test_status_read_rejects_mismatched_provider_id(self, urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {"id": "wrong-project", "status": "complete", "credits_charged": 5, "downloads": []}
        ).encode()
        urlopen.return_value = response
        with self.assertRaises(ProviderError) as context:
            MagicHourProvider().get_generation_update(
                job=SimpleNamespace(capability="image.generate", provider_job_id="expected-project")
            )
        self.assertEqual(context.exception.code, "provider_response_invalid")
        self.assertEqual(urlopen.call_args.args[0].method, "GET")

    @override_settings(MAGIC_HOUR_API_KEY="")
    def test_missing_key_disables_provider(self):
        provider = MagicHourProvider()
        self.assertFalse(provider.is_configured())

    @override_settings(MAGIC_HOUR_API_KEY="private-test-key")
    @patch("apps.providers.magic_hour.urlopen")
    def test_image_submission_uses_documented_endpoint_and_bearer_auth(self, urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"id": "img-42", "credits_charged": 5}).encode()
        urlopen.return_value = response

        submission = MagicHourProvider().submit_image_generation(
            prompt="A warm studio",
            aspect_ratio="16:9",
            name="Background",
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.magichour.ai/v1/ai-image-generator")
        self.assertEqual(request.get_header("Authorization"), "Bearer private-test-key")
        self.assertEqual(
            json.loads(request.data),
            {
                "image_count": 1,
                "model": "z-image-turbo",
                "aspect_ratio": "16:9",
                "resolution": "640px",
                "style": {"prompt": "A warm studio"},
                "name": "Background",
            },
        )
        self.assertEqual(submission.provider_job_id, "img-42")
        self.assertEqual(submission.quoted_credits, 5)

    @override_settings(MAGIC_HOUR_API_KEY="private-test-key")
    @patch("apps.providers.magic_hour.urlopen")
    def test_presenter_submission_uses_talking_photo_contract(self, urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"id": "vid-12", "credits_charged": 400}).encode()
        urlopen.return_value = response

        MagicHourProvider().submit_presenter_generation(
            script_text="Hello",
            scene_payload={
                "image_file_path": "api-assets/person.png",
                "audio_file_path": "api-assets/voice.mp3",
                "start_seconds": 0,
                "end_seconds": 5,
            },
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.magichour.ai/v1/ai-talking-photo")
        self.assertEqual(
            json.loads(request.data),
            {
                "start_seconds": 0,
                "end_seconds": 5,
                "assets": {
                    "image_file_path": "api-assets/person.png",
                    "audio_file_path": "api-assets/voice.mp3",
                },
                "style": {"generation_mode": "realistic"},
            },
        )

    @override_settings(MAGIC_HOUR_API_KEY="private-test-key")
    @patch("apps.providers.magic_hour.urlopen")
    def test_provider_error_code_and_message_are_preserved(self, urlopen):
        error = Mock()
        error.code = 422
        error.read.return_value = json.dumps(
            {"code": "invalid_request", "message": "The source image is not supported."}
        ).encode()
        urlopen.side_effect = __import__("urllib.error").error.HTTPError(
            "https://api.magichour.ai/v1/ai-image-generator", 422, "Unprocessable", {}, error
        )

        with self.assertRaises(ProviderError) as context:
            MagicHourProvider().submit_image_generation(prompt="A warm studio")
        self.assertEqual(context.exception.code, "invalid_request")
        self.assertEqual(context.exception.message, "The source image is not supported.")

    @override_settings(MAGIC_HOUR_API_KEY="private-test-key")
    @patch("apps.providers.magic_hour.urlopen")
    def test_polling_maps_documented_failure_without_fabricating_result(self, urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {
                "id": "img-42",
                "status": "error",
                "error": {"code": "no_source_face", "message": "Use an image with a detectable face."},
                "downloads": [],
            }
        ).encode()
        urlopen.return_value = response

        update = MagicHourProvider().get_generation_update(
            job=SimpleNamespace(capability="image.generate", provider_job_id="img-42")
        )

        self.assertEqual(update.status, "failed")
        self.assertEqual(update.error_code, "no_source_face")
        self.assertEqual(update.error_message, "Use an image with a detectable face.")
        self.assertEqual(update.result, {})
