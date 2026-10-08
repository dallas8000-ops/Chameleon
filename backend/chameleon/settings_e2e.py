"""E2E-only settings: isolated SQLite, in-process cache, and eager Celery.

This is NOT evidence of PostgreSQL/Redis/worker behaviour. It refuses to load
unless CHAMELEON_E2E=1 so it cannot be selected by accident in a deployment.
"""
import os

from .settings import *  # noqa: F401,F403

if os.environ.get("CHAMELEON_E2E") != "1":
    raise RuntimeError("chameleon.settings_e2e is only for the local E2E harness (CHAMELEON_E2E=1).")

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "chameleon-e2e"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
# Never contact the provider from the harness, whatever the parent environment holds.
MAGIC_HOUR_API_KEY = ""
MAGIC_HOUR_WEBHOOK_SECRET = ""
