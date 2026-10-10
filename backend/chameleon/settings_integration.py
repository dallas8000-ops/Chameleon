"""Fail-closed local integration settings for owned Postgres/Redis/worker verification.

This harness is for local production-like verification only. It must never fall back to a shared
developer service, a production database, or the SQLite/eager E2E harness.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ALLOWED_SCRATCH = (_REPO_ROOT / "e2e" / ".runtime-integration").resolve()
_EXPECTED_DB_NAME = "chameleon_integration"
_EXPECTED_CACHE_DB = "15"
_EXPECTED_BROKER_DB = "14"


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent)
        return True
    except ValueError:
        return False


def _parse_redis(name: str, expected_port: str, expected_db: str) -> None:
    raw = os.environ.get(name, "")
    parsed = urlparse(raw)
    db = parsed.path.lstrip("/")
    if (
        parsed.scheme != "redis"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or str(parsed.port or "") != expected_port
        or db != expected_db
    ):
        raise RuntimeError(f"{name} is not the owned local Redis URL for integration verification.")


def _enforce_isolation() -> Path:
    if os.environ.get("CHAMELEON_INTEGRATION") != "1":
        raise RuntimeError("chameleon.settings_integration requires CHAMELEON_INTEGRATION=1.")
    raw_runtime = os.environ.get("CHAMELEON_INTEGRATION_RUNTIME_DIR")
    if not raw_runtime:
        raise RuntimeError("CHAMELEON_INTEGRATION_RUNTIME_DIR must point at the integration scratch directory.")
    runtime = Path(raw_runtime).resolve()
    if runtime != _ALLOWED_SCRATCH and not _inside(runtime, _ALLOWED_SCRATCH):
        raise RuntimeError(f"CHAMELEON_INTEGRATION_RUNTIME_DIR must stay inside {_ALLOWED_SCRATCH}.")
    expected_pg_port = os.environ.get("CHAMELEON_INTEGRATION_POSTGRES_PORT")
    expected_redis_port = os.environ.get("CHAMELEON_INTEGRATION_REDIS_PORT")
    if not expected_pg_port or expected_pg_port == "5432":
        raise RuntimeError("CHAMELEON_INTEGRATION_POSTGRES_PORT must be set to an owned non-default local port.")
    if not expected_redis_port or expected_redis_port == "6379":
        raise RuntimeError("CHAMELEON_INTEGRATION_REDIS_PORT must be set to an owned non-default local port.")

    database_url = os.environ.get("DATABASE_URL", "")
    parsed_db = urlparse(database_url)
    database_name = Path(unquote(parsed_db.path.lstrip("/"))).name
    if (
        parsed_db.scheme not in {"postgres", "postgresql"}
        or parsed_db.hostname not in {"127.0.0.1", "localhost"}
        or str(parsed_db.port or "") != expected_pg_port
        or database_name != _EXPECTED_DB_NAME
    ):
        raise RuntimeError("DATABASE_URL is not the owned local PostgreSQL integration database.")

    media_root = os.environ.get("MEDIA_ROOT")
    if media_root and not _inside(Path(media_root), runtime):
        raise RuntimeError("MEDIA_ROOT is outside the integration scratch directory.")

    _parse_redis("REDIS_URL", expected_redis_port, _EXPECTED_CACHE_DB)
    _parse_redis("CELERY_BROKER_URL", expected_redis_port, _EXPECTED_BROKER_DB)
    return runtime


_SCRATCH = _enforce_isolation()
_SCRATCH.mkdir(parents=True, exist_ok=True)
os.environ["MEDIA_ROOT"] = str(_SCRATCH / "media")

from .settings import *  # noqa: E402,F401,F403

MEDIA_ROOT = str(_SCRATCH / "media")
Path(MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
