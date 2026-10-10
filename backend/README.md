# Chameleon backend

Django 5 + DRF backend. Run commands from this directory; see the root README for environment setup.

## API

- `GET /api/health/`
- `GET /api/auth/csrf/`, `POST /api/auth/register/`, `POST /api/auth/login/`, `POST /api/auth/logout/`, `GET /api/auth/session/`
- `GET /api/workspaces/`, `PATCH /api/workspaces/<id>/`
- Projects, scenes, captions, assets and exports: see `apps/studio/urls.py`

Authentication uses a custom email-based user model (`apps.accounts`), session cookies with CSRF
protection, and workspace membership roles. The frontend calls relative `/api/...` URLs with
`credentials: "same-origin"`.

## Apps

- `accounts`: users, workspaces, memberships and permissions
- `studio`: projects, scenes, assets, caption tracks and export records
- `rendering`: Celery export tasks and FFmpeg assembly
- `api`: health check, deployment checks and the SPA entry view

Generation (image, voice, presenter and video models on a GPU worker) is planned in
[docs/rebuild-plan.md](../docs/rebuild-plan.md) and is not part of the backend yet.

## Uploads

Uploads are stored privately and served only through authorized endpoints. The default limit is
25 MiB, with media-signature and content-type checks.

## Throttling

Authentication endpoints use a shared throttle (`AUTH_THROTTLE_RATE`, default `5/minute`) backed by
Redis in deployment.

## Tests

```powershell
python manage.py test
```

Backend tests use isolated SQLite and cache settings. Set `CHAMELEON_TEST_DATABASE_URL` to run them
against PostgreSQL.
