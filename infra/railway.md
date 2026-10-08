# Railway deployment runbook (planned, not yet deployed)

Status: **no Railway deployment has been performed or verified.** This is the
intended topology and the checks to run before calling it production-ready.
The local browser harness (`e2e/`) uses SQLite, an in-process cache and eager
Celery, so it is **not** evidence that PostgreSQL, Redis, a separate worker or
Railway storage work.

## Services

| Service | Start command (from `backend/`) | Notes |
| --- | --- | --- |
| `web` | `gunicorn chameleon.wsgi --bind 0.0.0.0:$PORT` (add gunicorn to the image first) | Django/DRF API; run `python manage.py migrate --noinput` as the release/pre-deploy step |
| `worker` | `celery -A chameleon worker -l info` | Needs FFmpeg + FFprobe on PATH and the same media volume as `web` |
| `beat` | `celery -A chameleon beat -l info` | Run exactly **one** instance (export, provider-poll and ingestion recovery sweeps) |
| `postgres` | Railway PostgreSQL plugin | Provides `DATABASE_URL` |
| `redis` | Railway Redis plugin | Provides `REDIS_URL`; also used as the shared throttle cache and broker |
| `frontend` | `npm --prefix frontend ci && npm --prefix frontend run build` | Serve `frontend/dist` same-origin with `/api` (reverse proxy or static host with `/api` routed to `web`). The Vite dev proxy is development only |

## Required environment (secrets only as Railway variables)

- `SECRET_KEY` (long random), `DEBUG=0`, `ALLOWED_HOSTS=<your host>`,
  `CSRF_TRUSTED_ORIGINS=https://<your host>`
- `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL` 
- `MEDIA_ROOT=/data/private_media` on a **persistent volume mounted on both `web` and `worker`**
- `FFMPEG_BINARY` / `FFPROBE_BINARY` only if not on PATH
- Leave `MAGIC_HOUR_API_KEY` empty until the generation gates in
  [the image integration runbook](../docs/generation-image-integration.md) are verified;
  never expose it to the frontend
- Production defaults enable secure cookies, SSL redirect and HSTS; Railway terminates TLS and
  sends `X-Forwarded-Proto`, which `USE_X_FORWARDED_PROTO` (default on) honours

## Pre-launch verification checklist

1. `python manage.py migrate --noinput` succeeds on an empty PostgreSQL database.
2. Run the Django suite against PostgreSQL (`CHAMELEON_TEST_DATABASE_URL` pointing at a **disposable** database).
   Known baseline: the PostgreSQL run has documented auth-throttle/rendering test incompatibilities
   (see the Task 8 report); resolve or explicitly accept them before launch.
3. `web` `/api/health/` returns 200 over HTTPS; register/login sets `Secure` cookies.
4. Upload an image, queue an export, and confirm the **worker** (not the API process) completes it:
   the worker log shows the task and the download returns an MP4 verified with `ffprobe`.
5. Redeploy `web`/`worker` and confirm uploads and exports survive (persistent volume).
6. Confirm exactly one `beat` instance and that killing a worker mid-export is recovered by the sweeper.
7. Only then follow the generation runbook for quotes/tariffs, download origins and storage confirmation.

## Rollback

Redeploy the previous image for `web`, `worker` and `beat` together. Migrations are forward-only;
take a PostgreSQL backup before releasing any migration.

