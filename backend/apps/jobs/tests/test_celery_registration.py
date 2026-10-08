from django.test import SimpleTestCase


class CeleryRegistrationTests(SimpleTestCase):
    def test_ingestion_recovery_task_is_registered(self):
        from chameleon.celery import app

        app.loader.import_default_modules()
        self.assertIn("apps.jobs.ingestion.recover_ingestions", app.tasks)
