"""E2E-only settings: isolated SQLite, scratch media, in-process cache, and eager Celery.

This is NOT evidence of PostgreSQL/Redis/worker behaviour. Isolation is enforced here, not by
the launcher: the module fails closed unless CHAMELEON_E2E=1 and CHAMELEON_E2E_RUNTIME_DIR points at
the repository's e2e/.runtime scratch directory, and it rejects any configured DATABASE_URL or
MEDIA_ROOT that is not inside that directory. Database and media are then forced to the scratch dir.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ALLOWED_SCRATCH = (_REPO_ROOT / "e2e" / ".runtime").resolve()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent)
        return True
    except ValueError:
        return False


def _enforce_isolation() -> Path:
    if os.environ.get("CHAMELEON_E2E") != "1":
        raise RuntimeError("chameleon.settings_e2e is only for the local E2E harness (CHAMELEON_E2E=1).")
    raw = os.environ.get("CHAMELEON_E2E_RUNTIME_DIR")
    if not raw:
        raise RuntimeError("CHAMELEON_E2E_RUNTIME_DIR must be set to the e2e scratch directory.")
    scratch = Path(raw).resolve()
    if scratch != _ALLOWED_SCRATCH and not _inside(scratch, _ALLOWED_SCRATCH):
        raise RuntimeError(f"CHAMELEON_E2E_RUNTIME_DIR must be inside {_ALLOWED_SCRATCH} (the repo e2e scratch dir).")
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        db_path = Path(unquote(parsed.path.lstrip("/") if os.name == "nt" else parsed.path))
        if parsed.scheme != "sqlite" or not db_path.is_absolute() or not _inside(db_path, scratch):
            raise RuntimeError("DATABASE_URL is not the scratch SQLite database; refusing to run E2E settings.")
    media_root = os.environ.get("MEDIA_ROOT")
    if media_root and not _inside(Path(media_root), scratch):
        raise RuntimeError("MEDIA_ROOT is outside the E2E scratch directory; refusing to run E2E settings.")
    return scratch


_SCRATCH = _enforce_isolation()
_SCRATCH.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (_SCRATCH / "e2e.sqlite3").as_posix()
os.environ["MEDIA_ROOT"] = str(_SCRATCH / "media")

from .settings import *  # noqa: E402,F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(_SCRATCH / "e2e.sqlite3")}}
MEDIA_ROOT = str(_SCRATCH / "media")
(Path(MEDIA_ROOT)).mkdir(parents=True, exist_ok=True)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "chameleon-e2e"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
# Never contact the provider from the harness, whatever the parent environment holds.
MAGIC_HOUR_API_KEY = ""
MAGIC_HOUR_WEBHOOK_SECRET = ""
