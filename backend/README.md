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
