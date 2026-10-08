# Local infrastructure verification

This document records the follow-up local production-like verification for the
creator-studio foundation. It does **not** rely on the earlier SQLite/eager
E2E harness as infrastructure proof.

## Scope

Goal: verify, on one Windows workstation and without touching existing shared
localhost services, that Chameleon can run with:

- a fresh owned PostgreSQL cluster
- a fresh owned Redis instance
- a Django API process
- a separate Celery worker process
- a separate Celery Beat process
- the React/Vite frontend
- project-local FFmpeg/FFprobe for a real export

Constraints respected during this run:

- existing PostgreSQL on `127.0.0.1:5432` was left untouched
- existing Redis on `127.0.0.1:6379` (PID 6584) was left untouched
- no deployment, no push, and no paid provider calls
- provider activation remained disabled
- media, database files, Redis files, logs, and Beat schedule were confined to
  the project-owned integration runtime

## Harness added

### Integration settings

[`backend/chameleon/settings_integration.py`](</C:/Software Projects/Chameleon/backend/chameleon/settings_integration.py>)
adds a fail-closed Django settings module that requires:

- `CHAMELEON_INTEGRATION=1`
- a runtime directory under [`e2e/.runtime-integration/`](</C:/Software Projects/Chameleon/e2e/.runtime-integration>)
- non-default owned PostgreSQL and Redis ports
- a local PostgreSQL URL targeting `chameleon_integration`
- Redis cache DB `/15`
- Celery broker DB `/14`
- provider secrets blanked
- media confined to the integration runtime

If those conditions are not met, the process aborts rather than silently
falling back to development defaults.

### Integration stack launcher

[`e2e/scripts/start-integration-stack.mjs`](</C:/Software Projects/Chameleon/e2e/scripts/start-integration-stack.mjs>)
owns the local runtime and launches:

- PostgreSQL 16 binaries from `C:\Program Files\PostgreSQL\16\bin`
- Redis on `127.0.0.1:56379`
- Django on `127.0.0.1:18080`
- Celery worker (`-P solo`) in a separate process
- Celery Beat in a separate process with its schedule file inside the runtime
- Vite on `127.0.0.1:15174`

Runtime outputs live under [`e2e/.runtime-integration/`](</C:/Software Projects/Chameleon/e2e/.runtime-integration>) and are ignored by git.

## Tightly coupled fixes made during verification

### 1. PostgreSQL duplicate-registration handling

[`backend/apps/accounts/views.py`](</C:/Software Projects/Chameleon/backend/apps/accounts/views.py>)
now treats psycopg3 duplicate-key failures as conflicts when the backend
exposes `sqlstate=23505` instead of the older `pgcode` field.

Locked in by
[`backend/apps/accounts/tests/test_auth_api.py`](</C:/Software Projects/Chameleon/backend/apps/accounts/tests/test_auth_api.py>).

### 2. PostgreSQL export download regression in a test

[`backend/apps/rendering/tests/test_export_pipeline.py`](</C:/Software Projects/Chameleon/backend/apps/rendering/tests/test_export_pipeline.py>)
no longer manually calls `response.close()` after already exhausting a
streamed response. Under psycopg3/PostgreSQL this left the next request in the
same test client using a closed DB-backed session connection.

### 3. Celery Beat ingestion recovery registration

[`backend/apps/jobs/tasks.py`](</C:/Software Projects/Chameleon/backend/apps/jobs/tasks.py>)
now imports `recover_ingestions` so the worker registers the Beat-scheduled
ingestion recovery task through Celery autodiscovery.

Locked in by
[`backend/apps/jobs/tests/test_celery_registration.py`](</C:/Software Projects/Chameleon/backend/apps/jobs/tests/test_celery_registration.py>).

### 4. PostgreSQL connection health checks

[`backend/chameleon/settings.py`](</C:/Software Projects/Chameleon/backend/chameleon/settings.py>)
now enables PostgreSQL `CONN_HEALTH_CHECKS`. This was a hardening change found
while investigating the PostgreSQL failures; it was not the sole fix for the
download-test regression above.

## Commands run

All commands below were run locally from
[`C:\Software Projects\Chameleon`](</C:/Software Projects/Chameleon>).

### Stack bootstrap

```powershell
npm --prefix ".\e2e" run stack:integration
```

The Playwright integration command also bootstraps that same stack automatically.

### Focused and full backend verification

```powershell
Set-Location ".\backend"
$env:CHAMELEON_TEST_DATABASE_URL = "postgresql://postgres@127.0.0.1:55449/chameleon_integration"
$env:DJANGO_SETTINGS_MODULE = "chameleon.settings_test"
& "..\.venv\Scripts\python.exe" -m unittest apps.rendering.tests.test_settings_integration
& "..\.venv\Scripts\python.exe" -m unittest `
  apps.rendering.tests.test_export_pipeline `
  apps.jobs.tests.test_celery_registration
& "..\.venv\Scripts\python.exe" -m unittest
```

### Frontend and helper-script checks

```powershell
npm --prefix ".\frontend" run typecheck
npm --prefix ".\frontend" run build
npm --prefix ".\e2e" run test:scripts
```

### Full local production-like browser run

```powershell
$env:PLAYWRIGHT_CHANNEL = "msedge"
npm --prefix ".\e2e" run test:integration -- --grep "creator registers"
```

That command booted the owned integration stack automatically and exercised the
full browser flow.

### Shared throttle proof across two API processes

After the integration stack was running, a second Django API process was started
on `127.0.0.1:18081` against the same isolated PostgreSQL and Redis. Alternating
anonymous invalid registration requests across both API processes produced:

```text
400, 400, 400, 400, 400, 429
```

This verified that throttling is shared through Redis, not kept in per-process
memory.

## Results

### Backend

- integration settings tests: **8 passed**
- focused PostgreSQL export + Celery registration run: **29 passed**
- full backend suite against isolated PostgreSQL: **173 passed**

### Frontend

- `npm --prefix ".\frontend" run typecheck`: **passed**
- `npm --prefix ".\frontend" run build`: **passed**

### E2E helper scripts

- `npm --prefix ".\e2e" run test:scripts`: **4 passed**

### Browser export workflow

Playwright passed the register/login/project/upload/scenes/captions/export flow
against the isolated PostgreSQL/Redis/worker/Beat stack: **1 passed**.

The separate worker advertised and consumed the production-like tasks, including:

- `apps.rendering.tasks.render_export`
- `apps.rendering.tasks.recover_exports`
- `apps.jobs.ingestion.recover_ingestions`
- `apps.jobs.tasks.recover_provider_polls`

### FFmpeg/FFprobe smoke

The produced export artifact was checked with the project-local binaries under
[`e2e/node_modules/`](</C:/Software Projects/Chameleon/e2e/node_modules>):

- video codec: **H.264**
- resolution: **1080x1920**
- audio codec: **AAC**
- duration: **2.006s**
- full FFmpeg decode: **succeeded**
- subtitle content included the expected `Hello Chameleon` text

## Beat recovery evidence

What was fully verified:

- Celery Beat periodically dispatched `recover_exports`,
  `recover_ingestions`, and `recover_provider_polls`.
- the separate worker consumed those Beat-published tasks
- the worker registration gap for `recover_ingestions` was fixed and covered by
  a regression test
- a synthetic overdue export caused `recover_exports` to return `1` and enqueue
  `render_export`, which the worker received

What I am **not** overstating:

- I did **not** use that synthetic overdue export as the primary success proof
  for rendering completion, because during observation it remained `processing`
  after the recovery enqueue. The production-like browser export already proved
  end-to-end rendering completion with the real isolated API/worker stack.

## Files added for this verification

- [`backend/chameleon/settings_integration.py`](</C:/Software Projects/Chameleon/backend/chameleon/settings_integration.py>)
- [`backend/apps/rendering/tests/test_settings_integration.py`](</C:/Software Projects/Chameleon/backend/apps/rendering/tests/test_settings_integration.py>)
- [`backend/apps/jobs/tests/test_celery_registration.py`](</C:/Software Projects/Chameleon/backend/apps/jobs/tests/test_celery_registration.py>)
- [`e2e/playwright.integration.config.ts`](</C:/Software Projects/Chameleon/e2e/playwright.integration.config.ts>)
- [`e2e/scripts/start-integration-stack.mjs`](</C:/Software Projects/Chameleon/e2e/scripts/start-integration-stack.mjs>)

## Remaining limitations

- Railway deployment and persistent hosted storage are still unverified.
- Provider-paid image/presenter generation remains intentionally gated off in
  this follow-up.
- The synthetic overdue-export recovery probe provided dispatch evidence, not a
  completed render artifact, so hosted scheduler-recovery behavior should still
  be re-checked in deployment.
