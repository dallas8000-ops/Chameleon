# Railway manual setup (Chameleon)

Do this once, in the Railway dashboard. It does not involve the Studio or any
automation. The reasoning behind each choice is in [railway.md](./railway.md).

Chameleon takes no payments, so there is nothing to configure for Stripe.

## 1. Create the project and the app service

1. Railway dashboard, **New Project**, **Deploy from GitHub repo**, choose
   `dallas8000-ops/Chameleon`.
2. Set the deploy branch to `main`. Merge
   [PR #1](https://github.com/dallas8000-ops/Chameleon/pull/1) first, because
   `main` does not have the Railway manifests yet.
3. Name the service `chameleon`. Railway builds from the root `Dockerfile` and
   reads `railway.json` for the start command and health check, so no build or
   start command needs entering by hand.

## 2. Add PostgreSQL and Redis

In the same project: **New**, **Database**, **Add PostgreSQL**, then **New**,
**Database**, **Add Redis**. Leave their default service names (`Postgres`,
`Redis`); the references below assume them.

## 3. Attach the volume

On the `chameleon` service: **Settings**, **Volumes**, **Add volume**, mount path
`/data`. A volume can belong to only one service, which is why the API, worker
and Beat share this single service.

## 4. Generate the public domain

On the `chameleon` service: **Settings**, **Networking**, **Generate Domain**.
Note the hostname, for example `chameleon-production.up.railway.app`. Use it as
`<HOST>` below.

## 5. Set the service variables

Generate the secret locally first (never commit it):

```powershell
py -3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

On the `chameleon` service, **Variables**:

| Variable | Value |
| --- | --- |
| `SECRET_KEY` | The generated string (at least 50 characters) |
| `DEBUG` | `0` |
| `ALLOWED_HOSTS` | `<HOST>` (comma separated; `healthcheck.railway.app` is added automatically) |
| `CSRF_TRUSTED_ORIGINS` | `https://<HOST>` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `MEDIA_ROOT` | `/data/private_media` |

Optional: `CELERY_BROKER_URL` (defaults to `REDIS_URL`), `WEB_CONCURRENCY`
(default 3), `CELERY_CONCURRENCY` (default 2).

Do not set `NODE_ENV`; the frontend build needs its dev dependencies.

## 6. Deploy and verify

On start, the container runs `check_deployment`, then `migrate`, then launches the
processes. If a check fails, the deploy fails its health check and the previous
deployment keeps serving. Read the failure list in the deploy log.

Then work through the checklist in [railway.md](./railway.md#pre-launch-verification-checklist):
health endpoint, SPA at the root, register and login, an upload plus an export,
and a redeploy to confirm the volume keeps its files.

## Common failures

| Symptom | Likely cause |
| --- | --- |
| Build fails with `Railpack could not determine how to build the app` | The root `Dockerfile` or `railway.json` is missing from the deployed branch |
| Health check never goes green, log shows `DisallowedHost` | `ALLOWED_HOSTS` empty or wrong in a deployed environment |
| Deploy log lists `MEDIA_ROOT ... is not writable` | Volume not attached, or not mounted at `/data` |
| `check_deployment` reports FFmpeg missing | The image was not built from the `Dockerfile` |
| `DATABASE_URL must point at PostgreSQL` | The variable holds a literal or wrong reference; use `${{Postgres.DATABASE_URL}}` |
