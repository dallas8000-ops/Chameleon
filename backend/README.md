Chameleon backend package

This directory is the Django backend package root for local development and tests.

Current API foundation:

- `GET /api/health/`
- `GET /api/auth/csrf/`
- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/session/`
- `GET /api/workspaces/`
- `PATCH /api/workspaces/<id>/`
- `POST /api/jobs/image-generation/`
- `POST /api/jobs/presenter-generation/`
- `GET /api/jobs/<id>/`

The backend uses a custom email-based user model in `apps.accounts`, session authentication with CSRF protection, and workspace membership RBAC.

## Studio asset uploads

`POST /api/assets/` accepts multipart uploads for workspace owners and editors.
The default `STUDIO_MAX_UPLOAD_BYTES` limit is 25 MiB and is enforced while
multipart files are being parsed, across all file parts in the request; an
oversized upload returns HTTP 413. The later service-level size check remains
as defense in depth. Supported file signatures are PNG, JPEG, GIF, WebP, MP4,
and WebM, and the declared content type must match the detected signature.
Uploads use private local Django storage and are not durable across Railway
deployments without persistent storage configuration.

## Shared throttling

Non-test processes require `REDIS_URL` for Django's shared Redis cache and
`redis` from `requirements.txt`. Point every API worker at the same Redis
instance/database; `AUTH_THROTTLE_RATE` defaults to `5/minute` for the shared
login/register scope. Prefer a separate Redis database from Celery.
Only tests use an explicit in-memory cache, cleared between auth tests.
DRF's cache-based throttle is an abuse guard, not an exact concurrent request
quota; deployment edge rate limiting should supplement it.

## Generation jobs and provider setup

Generation requests first persist a workspace-scoped job, then submit it to the
Celery worker. The worker uses only Magic Hour's documented
`POST /v1/ai-image-generator`, `POST /v1/ai-talking-photo`, and corresponding
image/video project status endpoints. Configure `MAGIC_HOUR_API_KEY` only in
the backend environment; it is optional. Set `MAGIC_HOUR_WEBHOOK_SECRET` to
enable signed callback handling at `/api/jobs/webhooks/magic-hour/`. The
endpoint verifies Magic Hour's documented HMAC-SHA256 signature and five-minute
timestamp window before applying updates. Without an API key, a request persists a
`blocked_provider_not_configured` job and no provider request or worker task is
made. Run a Celery worker from this directory with
`python -m celery -A chameleon worker -l info`.

Magic Hour Talking Photo animates an existing portrait with an existing audio
file; it does not synthesize a spoken script. Presenter requests therefore need
documented `image_file_path` and `audio_file_path` inputs. The API returns an
honest job state; the worker polls provider status without inventing progress
or completed assets. Provider errors are retained as structured codes and
messages. Usage ledger writes and repeated provider updates are idempotent.
`quoted_credits` is populated from Magic Hour's submission response and may be
adjusted when rendering finishes; it is zero while a job is waiting for provider
acceptance. Completed results retain provider download URLs, which are temporary
(typically expiring within 24 hours); this task does not copy outputs into
durable `Asset` storage.

## Same-origin browser contract

The future Task 6 auth client must call relative `/api/...` URLs from the
frontend origin and include session cookies (`credentials: 'same-origin'`).
First fetch `GET /api/auth/csrf/`, then send the returned `csrfToken` in
`X-CSRFToken` for every unsafe request, including anonymous login/register
and authenticated logout. Django rotates the CSRF secret on login/register;
fetch a fresh token after either succeeds. Session bootstrap is
`GET /api/auth/session/`; wiring its UI/store remains Task 6.

During development, Vite proxies `/api` to `http://127.0.0.1:8000`.
Set `BACKEND_URL` in the frontend environment to choose another backend.
The proxy preserves the browser Host and Origin (`changeOrigin: false`),
so Django's same-origin CSRF checks and cookies work without CORS.
Run the backend with `DEBUG=1` locally and include the frontend hostname
(for example `localhost` or `127.0.0.1`) in `ALLOWED_HOSTS`.
Use the Vite development server, not a direct cross-origin API URL.

On Railway, the public HTTPS origin must serve the frontend and reverse-proxy
`/api` to Django; a Vite development proxy is not a production reverse proxy.
Preserve the public Host/Origin, set `ALLOWED_HOSTS` to that host, and forward
`X-Forwarded-Proto: https` only from the trusted ingress (strip untrusted
client forwarding headers). Keep production secure cookies/TLS enabled.
Separate frontend/API origins require a later approved credentialed CORS
design with exact origins, CSRF trusted origins, and cookie policy; do not
enable wildcard/broad CORS as a workaround.
