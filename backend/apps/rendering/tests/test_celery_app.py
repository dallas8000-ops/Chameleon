from celery import current_app
from django.test import SimpleTestCase

import chameleon


class CeleryAppLoadedTests(SimpleTestCase):
    def test_django_process_binds_shared_tasks_to_project_celery_app(self):
        # Without this, API-side .delay() would use Celery's default AMQP app, not the configured broker.
        self.assertTrue(hasattr(chameleon, "celery_app"))
        self.assertEqual(chameleon.celery_app.main, "chameleon")
        self.assertIs(current_app._get_current_object(), chameleon.celery_app)
