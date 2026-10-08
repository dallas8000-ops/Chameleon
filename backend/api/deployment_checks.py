"""Production configuration checks for the Railway deployment.

These complement ``manage.py check --deploy``: they assert the runtime wiring the
product depends on (PostgreSQL, Redis, persistent private media, FFmpeg, built
frontend) rather than Django's generic security advice.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

ROLES = ("web", "worker", "beat")
WEAK_SECRET_KEYS = {"test-secret", "change-me", "secret", "django-insecure"}
MINIMUM_SECRET_KEY_LENGTH = 50


def _problem(problems: list[str], message: str) -> None:
    problems.append(message)


def _check_core(problems: list[str]) -> None:
    if settings.DEBUG:
        _problem(problems, "DEBUG must be disabled in production (set DEBUG=0).")

    secret_key = settings.SECRET_KEY or ""
    if secret_key in WEAK_SECRET_KEYS or secret_key.startswith("django-insecure"):
        _problem(problems, "SECRET_KEY is a known placeholder value; generate a unique secret.")
    elif len(secret_key) < MINIMUM_SECRET_KEY_LENGTH:
        _problem(
            problems,
            f"SECRET_KEY must be at least {MINIMUM_SECRET_KEY_LENGTH} characters long.",
        )

    if not settings.ALLOWED_HOSTS:
        _problem(problems, "ALLOWED_HOSTS is empty; set it to the deployed hostname(s).")
    elif "*" in settings.ALLOWED_HOSTS:
        _problem(problems, "ALLOWED_HOSTS must not contain the '*' wildcard in production.")

    if not settings.CSRF_TRUSTED_ORIGINS:
        _problem(
            problems,
            "CSRF_TRUSTED_ORIGINS is empty; set it to the https origin(s) serving the app.",
        )
    for origin in settings.CSRF_TRUSTED_ORIGINS:
        if not origin.startswith("https://"):
            _problem(problems, f"CSRF_TRUSTED_ORIGINS entry '{origin}' must use https.")


def _check_security_headers(problems: list[str]) -> None:
    if not settings.SESSION_COOKIE_SECURE:
        _problem(problems, "SESSION_COOKIE_SECURE must be enabled behind HTTPS.")
    if not settings.CSRF_COOKIE_SECURE:
        _problem(problems, "CSRF_COOKIE_SECURE must be enabled behind HTTPS.")
    if not settings.SECURE_SSL_REDIRECT:
        _problem(problems, "SECURE_SSL_REDIRECT must be enabled behind HTTPS.")
    if settings.SECURE_HSTS_SECONDS < 3600:
        _problem(problems, "SECURE_HSTS_SECONDS must be at least 3600 in production.")
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None) is None:
        _problem(
            problems,
            "SECURE_PROXY_SSL_HEADER is unset; Railway terminates TLS and forwards "
            "X-Forwarded-Proto (keep USE_X_FORWARDED_PROTO enabled).",
        )


def _check_backing_services(problems: list[str]) -> None:
    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if engine != "django.db.backends.postgresql":
        _problem(problems, f"DATABASE_URL must point at PostgreSQL; got engine '{engine or 'unset'}'.")

    cache_backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if "redis" not in cache_backend.lower():
        _problem(
            problems,
            "The default cache must be Redis so auth throttling is shared across web processes.",
        )

    broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
    broker_host = urlparse(broker).hostname or ""
    if not broker:
        _problem(problems, "CELERY_BROKER_URL (or REDIS_URL) must be set.")
    elif broker_host in {"localhost", "127.0.0.1"}:
        _problem(
            problems,
            "CELERY_BROKER_URL points at localhost; the worker runs in a separate service.",
        )


def _check_media_root(problems: list[str], probe_write: bool) -> None:
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.is_absolute():
        _problem(problems, "MEDIA_ROOT must be an absolute path on the mounted volume.")
        return

    base_dir = Path(settings.BASE_DIR).resolve()
    try:
        media_root.resolve().relative_to(base_dir)
    except ValueError:
        pass
    else:
        _problem(
            problems,
            "MEDIA_ROOT is inside the application directory, which is rebuilt on each deploy; "
            "point it at a persistent volume such as /data/private_media.",
        )
        return

    if not probe_write:
        return

    try:
        media_root.mkdir(parents=True, exist_ok=True)
        probe = media_root / ".chameleon-write-probe"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        _problem(problems, f"MEDIA_ROOT '{media_root}' is not writable: {exc}.")


def _check_frontend_bundle(problems: list[str]) -> None:
    index = Path(settings.FRONTEND_DIST_DIR) / "index.html"
    if not index.is_file():
        _problem(
            problems,
            f"Frontend bundle missing at '{index}'; run the frontend build before serving web.",
        )
    if not Path(settings.STATIC_ROOT).is_dir():
        _problem(
            problems,
            f"STATIC_ROOT '{settings.STATIC_ROOT}' does not exist; "
            "run collectstatic during the image build.",
        )


def _check_healthcheck_host(problems: list[str]) -> None:
    if settings.RAILWAY_HEALTHCHECK_HOST not in settings.ALLOWED_HOSTS:
        _problem(
            problems,
            f"ALLOWED_HOSTS must include '{settings.RAILWAY_HEALTHCHECK_HOST}'; "
            "Railway's container probe sends that Host header.",
        )


def _check_render_tools(problems: list[str]) -> None:
    for setting_name, label in (("FFMPEG_BINARY", "FFmpeg"), ("FFPROBE_BINARY", "FFprobe")):
        binary = getattr(settings, setting_name)
        if shutil.which(binary) is None and not Path(binary).is_file():
            _problem(
                problems,
                f"{label} binary '{binary}' was not found; exports cannot be assembled.",
            )


def _check_generation_gates(problems: list[str]) -> None:
    if not settings.MAGIC_HOUR_API_KEY:
        return
    if not settings.GENERATION_DOWNLOAD_ORIGINS:
        _problem(
            problems,
            "MAGIC_HOUR_API_KEY is set but GENERATION_DOWNLOAD_ORIGINS is empty; "
            "authorized download origins must be verified first.",
        )
    if not settings.GENERATION_STORAGE_CONFIRMED:
        _problem(
            problems,
            "MAGIC_HOUR_API_KEY is set but GENERATION_STORAGE_CONFIRMED is false; "
            "durable private storage must be confirmed first.",
        )
    if not settings.MAGIC_HOUR_WEBHOOK_SECRET:
        _problem(
            problems,
            "MAGIC_HOUR_API_KEY is set but MAGIC_HOUR_WEBHOOK_SECRET is empty; "
            "provider webhooks would be unauthenticated.",
        )


def collect_deployment_problems(role: str = "all") -> list[str]:
    """Return every production misconfiguration found for ``role``.

    ``role`` is one of ``web``, ``worker``, ``beat`` or ``all``. The deployed
    Railway service runs all three processes in one container and uses ``all``;
    the narrower roles exist so the checks stay meaningful if the processes are
    ever split onto shared object storage.
    """
    if role not in ROLES + ("all",):
        raise ValueError(f"Unknown role '{role}'; expected one of {', '.join(ROLES + ('all',))}.")

    problems: list[str] = []
    _check_core(problems)
    _check_security_headers(problems)
    _check_backing_services(problems)
    _check_media_root(problems, probe_write=role in {"web", "worker", "all"})
    _check_generation_gates(problems)
    if role in {"web", "all"}:
        _check_frontend_bundle(problems)
        _check_healthcheck_host(problems)
    if role in {"worker", "all"}:
        _check_render_tools(problems)
    return problems
