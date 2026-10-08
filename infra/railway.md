# Railway deployment runbook

Status: **not yet deployed.** The manifests, release checks and same-origin
frontend delivery in this repository have been exercised locally; no Railway
environment has been created, so nothing here is production-verified yet.

Deployment artifacts live at the repository root so Railway picks them up
automatically:

| File | Purpose |
| --- | --- |
| [`railway.json`](../railway.json) | Builder, release (pre-deploy) command, start command, health check, replica count |
| [`nixpacks.toml`](../nixpacks.toml) | Build image: Python 3.11, Node 20, FFmpeg; installs backend requirements and builds the frontend bundle |
| [`Procfile`](../Procfile) | The three processes (`web`, `worker`, `beat`) supervised by `honcho` inside the single service |

## Topology: one service, one volume

Railway volumes are **one volume per service and one service per volume**; a
volume cannot be mounted on two services. The API writes uploads, the Celery
worker writes exports, and the API streams both back to the browser, so all
three processes must see the same private media directory. They therefore run in
a **single Railway service** under `honcho`, with one volume mounted at `/data`.

```
Railway service "chameleon"      Railway plugins
+-------------------------+      +-------------+
| honcho                  |      | PostgreSQL  |
|  - gunicorn (API + SPA) | <--> | Redis       |
|  - celery worker        |      +-------------+
|  - celery beat          |
+-----------+-------------+
            | volume
      /data (private media + beat schedule)
```

`restartPolicyType` is `ALWAYS`: `honcho start` terminates when any child process
exits — including a clean exit — so a dead worker or beat restarts the whole
service rather than silently degrading it. `numReplicas` is pinned to **1**
because Celery Beat must be a singleton and the volume is single-attach.

Splitting `web`, `worker` and `beat` into separate services requires shared
object storage for private media instead of a filesystem volume. That is P1
work, not a configuration change.

## Frontend delivery

The frontend is **not** a separate host. `nixpacks.toml` builds `frontend/dist`
during the image build and runs `collectstatic` into `backend/staticfiles` (the
build phase, not pre-deploy, because pre-deploy runs in a throwaway container).
WhiteNoise serves the hashed `/assets/*` bundles with immutable caching, and any
non-`/api`, non-`/static`, non-`/assets` route falls back to the SPA entry
document, which is sent with `Cache-Control: no-store`. Serving the app and
the API from one origin keeps the session cookie and CSRF token first-party; the
Vite dev proxy remains development-only.

Node's `NODE_ENV` is deliberately left unset during the build: Vite, React and
TypeScript are `devDependencies`, so `npm ci` would skip the entire build
toolchain in production mode.

## Required environment

Set these as Railway service variables (secrets never in source):

| Variable | Value |
| --- | --- |
| `SECRET_KEY` | Unique random string, at least 50 characters |
| `DEBUG` | `0` |
| `ALLOWED_HOSTS` | The deployed hostname, no `*` wildcard. `healthcheck.railway.app` is appended automatically for Railway's container probe. |
| `CSRF_TRUSTED_ORIGINS` | `https://<your host>` |
| `DATABASE_URL` | From the Railway PostgreSQL plugin |
| `REDIS_URL` | From the Railway Redis plugin (shared throttle cache) |
| `CELERY_BROKER_URL` | The Redis URL (defaults to `REDIS_URL`) |
| `MEDIA_ROOT` | `/data/private_media` on the mounted volume |
| `CELERY_BEAT_SCHEDULE_FILE` | Optional; defaults to `/data/celerybeat-schedule` |
| `WEB_CONCURRENCY` / `CELERY_CONCURRENCY` | Optional process counts (default 3 and 2) |
| `MAGIC_HOUR_API_KEY` | Leave **empty**; see the gating note below |

Secure cookies, SSL redirect and HSTS default to on when `DEBUG=0`. Railway
terminates TLS and forwards `X-Forwarded-Proto`, which `USE_X_FORWARDED_PROTO`
(default on) honours. `/api/health/` is exempt from the SSL redirect so Railway's
plain-HTTP container probe succeeds, and that probe's `Host:
healthcheck.railway.app` header is admitted automatically so it is never
rejected as a disallowed host.

## Release step

`railway.json` runs this before each deploy becomes active:

```
python manage.py migrate --noinput && python manage.py check_deployment --role all --skip-media-write-probe
```

Railway does **not** mount volumes during pre-deploy, so the `MEDIA_ROOT` write
test is skipped there (it would only exercise throwaway disk). The start command
runs `check_deployment --role all` again, with the volume mounted and the write
probe enabled, before `honcho` launches the processes. A misconfigured volume
therefore fails the health check and the previous deployment keeps serving.

`check_deployment` fails the release on: `DEBUG` left on, a placeholder or short
`SECRET_KEY`, empty or wildcard `ALLOWED_HOSTS`, non-https
`CSRF_TRUSTED_ORIGINS`, insecure cookie or HSTS settings, a non-PostgreSQL
database, a non-Redis cache, a localhost broker, a `MEDIA_ROOT` that is relative,
inside the rebuilt application directory or unwritable, a missing frontend
bundle, an uncollected `STATIC_ROOT`, an `ALLOWED_HOSTS` that would reject the
Railway health probe, missing FFmpeg/FFprobe, and a provider API key set while
its download-origin, storage and webhook-secret gates are unverified.

Run it against any environment with:

```powershell
& ".\.venv\Scripts\python.exe" backend\manage.py check_deployment --role all
```

## Pre-launch verification checklist

Nothing below has been performed yet.

1. Create the service, attach PostgreSQL and Redis, and mount a volume at `/data`.
2. Deploy; confirm the release step ran migrations and that `check_deployment`
   passed (it fails the deploy otherwise).
3. Run the Django suite against a **disposable** PostgreSQL database
   (`CHAMELEON_TEST_DATABASE_URL`); the 6 generation-race skips only apply to
   SQLite.
4. `GET https://<host>/api/health/` returns 200; the root URL returns the studio
   SPA; register/login sets `Secure` cookies.
5. Upload an image and queue an export; confirm the **worker** process log shows
   the task and the download returns an MP4 that `ffprobe` validates.
6. Redeploy and confirm uploads and exports survive (volume persistence).
7. Confirm exactly one beat process is running and that killing the worker
   mid-export is recovered by the sweeper.
8. Only then follow the
   [generation runbook](../docs/generation-image-integration.md) for quotes,
   tariffs, download origins and storage confirmation before setting
   `MAGIC_HOUR_API_KEY`.

## Rollback

Redeploy the previous image; all three processes roll back together because they
share one service. Migrations are forward-only, so take a PostgreSQL backup
before releasing any migration.
