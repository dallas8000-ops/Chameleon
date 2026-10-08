# Railway deployment runbook

Status: **deployed** to the `chameleon` Railway project (2026-10-08) at
`https://chameleon-production-a448.up.railway.app`, built from the root
`Dockerfile`. Verified live: health, SPA delivery, migrations, worker and Beat
sweepers, and a full register, upload, caption and export flow whose MP4 passes
`ffprobe` and a full decode. See the checklist below for what remains open.

Deployment artifacts live at the repository root. For first-time dashboard setup,
follow [railway-manual-setup.md](./railway-manual-setup.md).

| File | Purpose |
| --- | --- |
| [`Dockerfile`](../Dockerfile) | Builds the image (Python 3.11, FFmpeg, the Vite bundle, `collectstatic`) and holds the start command, so builds and redeploys do not depend on which Railway builder is selected |
| [`railway.json`](../railway.json) | Selects the Dockerfile builder; start command, health check, restart policy, replica count. Keep its start command identical to the Dockerfile `CMD` |
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

The frontend is **not** a separate host. The `Dockerfile` builds `frontend/dist`
in a Node stage and runs `collectstatic` into `backend/staticfiles` during the
image build, so both are image content.
WhiteNoise serves the hashed `/assets/*` bundles with immutable caching, and any
non-`/api`, non-`/static`, non-`/assets` route falls back to the SPA entry
document, which is sent with `Cache-Control: no-store`. Serving the app and
the API from one origin keeps the session cookie and CSRF token first-party; the
Vite dev proxy remains development-only.

The frontend stage installs with `npm ci --include=dev` and never sets
`NODE_ENV=production`: Vite, React and TypeScript are `devDependencies`, so a
production-mode install would skip the entire build toolchain.

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

Secure cookies, SSL redirect and HSTS default to on when `DEBUG=0`. Railway
terminates TLS and forwards `X-Forwarded-Proto`, which `USE_X_FORWARDED_PROTO`
(default on) honours. `/api/health/` is exempt from the SSL redirect so Railway's
plain-HTTP container probe succeeds, and that probe's `Host:
healthcheck.railway.app` header is admitted automatically so it is never
rejected as a disallowed host.

## Start-time checks and migrations

There is deliberately **no** Railway pre-deploy command. Pre-deploy runs in a
separate container without the volume, and on the first real deploy it did not
apply migrations. Instead the start command (in `railway.json` and the
`Dockerfile` `CMD`) runs, in order:

```
check_deployment --role all  &&  migrate --noinput  &&  honcho start -f Procfile
```

so the configuration is verified with the volume mounted and the write probe
enabled, the schema is migrated, and only then do gunicorn, the worker and Beat
launch. `migrate` is idempotent and safe with a single replica. A bad
configuration or failed migration fails the health check and the previous
deployment keeps serving.

`check_deployment --skip-media-write-probe` still exists for environments where
the volume is not mounted.

`check_deployment` fails the release on: `DEBUG` left on, a placeholder or short
`SECRET_KEY`, empty or wildcard `ALLOWED_HOSTS`, non-https
`CSRF_TRUSTED_ORIGINS`, insecure cookie or HSTS settings, a non-PostgreSQL
database, a non-Redis cache, a localhost broker, a `MEDIA_ROOT` that is relative,
inside the rebuilt application directory or unwritable, a missing frontend
bundle, an uncollected `STATIC_ROOT`, an `ALLOWED_HOSTS` that would reject the
Railway health probe, and missing FFmpeg/FFprobe.

Run it against any environment with:

```powershell
& ".\.venv\Scripts\python.exe" backend\manage.py check_deployment --role all
```

## Pre-launch verification checklist

Done on 2026-10-08 against the live service:

- [x] Service, PostgreSQL, Redis and the `/data` volume created; deploy healthy.
- [x] `check_deployment` and `migrate` pass at start.
- [x] `GET /api/health/` is 200, the root URL serves the SPA, and register,
  login and session reload work in a real browser.
- [x] Image upload, scene, captions and export complete; the downloaded MP4 is
  h264/aac 1080x1920 and decodes without errors; a second user is denied the
  first user's project, export and downloads.
- [x] The worker and Beat sweepers run without errors.
- [x] Redeploys work (`railway redeploy`), and an export created before a redeploy
  is byte-identical and downloadable after it (volume persistence).

Still open:

1. Run the Django suite against a **disposable** PostgreSQL database
   (`CHAMELEON_TEST_DATABASE_URL`); the 6 generation-race skips only apply to
   SQLite.
2. Confirm exactly one beat process is running and that killing the worker
   mid-export is recovered by the sweeper.

## Rollback

Redeploy the previous image; all three processes roll back together because they
share one service. Migrations are forward-only, so take a PostgreSQL backup
before releasing any migration.
