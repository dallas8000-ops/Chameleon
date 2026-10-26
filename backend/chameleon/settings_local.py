"""Local single-machine settings: SQLite, private media and in-process cache under one data directory,
and eager Celery, so the studio runs without PostgreSQL, Redis or a worker.

The data directory comes from CHAMELEON_LOCAL_DATA_DIR (run-api.ps1 uses <repo>/.local-data). It is
deliberately separate from e2e/.runtime, which the Playwright harness deletes on every run.
"""
import os
from pathlib import Path

_raw = os.environ.get("CHAMELEON_LOCAL_DATA_DIR")
if not _raw:
    raise RuntimeError("CHAMELEON_LOCAL_DATA_DIR must be set to use chameleon.settings_local.")
_DATA = Path(_raw).resolve()
(_DATA / "media").mkdir(parents=True, exist_ok=True)

# The base settings require these to be present; point them at the local directory.
os.environ["DATABASE_URL"] = "sqlite:///" + (_DATA / "chameleon.sqlite3").as_posix()
os.environ["MEDIA_ROOT"] = str(_DATA / "media")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")

from .settings import *  # noqa: E402,F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(_DATA / "chameleon.sqlite3")}}
MEDIA_ROOT = str(_DATA / "media")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "chameleon-local"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
# Eager Celery cannot wait between polls; the frontend's status reads drive generation jobs instead.
GENERATION_POLL_ON_READ = True
