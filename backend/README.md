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
