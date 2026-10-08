# Chameleon

![Python 3.11 tested](https://img.shields.io/badge/Python-3.11%20tested-3776AB)
![Django 5](https://img.shields.io/badge/Django-5-092E20)
![React and TypeScript](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-3178C6)
![License proprietary](https://img.shields.io/badge/License-Proprietary-lightgrey)

Chameleon is a scene-based video studio for social creators and small marketing
teams, designed to turn a script into a finished vertical video in one workflow.
Instead of assembling assets in scattered AI tools and rebuilding the edit in
CapCut, the product goal is to keep scenes, reusable media, captions, generation
history, and exports together in an editable project. Today's development build
supports the uploaded-media workflow; automated script-to-video creation and
realistic presenter/body-motion production are later milestones.

**Why now:** AI tools can create individual media pieces, but moving those pieces
into a consistent, editable social-video project still adds work. Chameleon
focuses on that missing continuity rather than another isolated generator.

## Capability status

Status describes the local development branch, not a released or deployed app.
Backend export, frontend auth, studio workflow and gated image-integration
reviews are complete. Local browser end-to-end verification now passes in both
the original SQLite/eager harness and a separate production-like harness with an
owned PostgreSQL cluster, owned Redis, a separate Celery worker and Celery Beat.
Railway deployment manifests, the release configuration check and same-origin
frontend delivery are now in the repository and verified locally; no Railway
environment has been created, so the deployment itself is still unverified.

| Capability | Status | Notes |
| --- | --- | --- |
| Accounts, workspaces, roles | Available in development | Email login, CSRF-protected sessions, owner/editor/viewer access |
| Projects and ordered scenes | Available APIs | Workspace-scoped persistence |
| Private asset uploads | Available APIs | Media-signature checks, content-type matching, 25 MiB default limit |
| Generation jobs and usage ledger | Available APIs | Signed webhooks, durable polling, idempotent ledger updates and interrupted-submission recovery |
| React authentication and dashboard | Reviewed | Session bootstrap, expiry recovery, project creation and studio navigation |
| Creator studio | Reviewed | Uploaded-asset picker, image/video scenes, captions, job status refresh and export screens |
| Caption tracks | Reviewed APIs and UI | Validated segments, track creation/editing and export selection |
| FFmpeg export assembly | Locally verified (uploaded image) | Private MP4 and subtitle downloads; real FFmpeg/FFprobe checked in the E2E run (H.264 1080x1920 + AAC) with the export executed by a separate Redis-backed Celery worker; unit tests still mock subprocesses |
| Provider-backed image generation (prior direction) | Present but inactive | Existing code is retained unchanged; it was not exercised by the provider-independent local infrastructure verification |
| Presenter generation (prior direction) | Disabled | Existing path remains unchanged pending a separate inference-architecture decision |
| Generated media to editable scenes | Implemented; activation gated | Bounded private ingestion and recovery; download origins and durable storage need operator verification |
| Browser end-to-end verification | Passing locally | Unmocked register, login, project, upload, scene, captions and export via Playwright; verified in both the SQLite/eager harness and an isolated PostgreSQL/Redis/worker/Beat harness |
| Same-origin frontend delivery | Locally verified | Django/WhiteNoise serves the built Vite bundle: hashed `/assets/*` cached immutably, client routes fall back to an uncached entry document, `/api` unaffected |
| Railway deployment manifests | Deployed and verified live (2026-10-08) | `Dockerfile`, `railway.json` and `Procfile` describe one service running gunicorn, the Celery worker and Beat under `honcho` with a single `/data` volume; the start command runs `check_deployment` and `migrate` before launching |
| Railway production deployment | Planned | No environment created yet; volume persistence, worker execution and storage still need deployment verification |

The existing provider-backed generation code reflects a prior direction, not
the target architecture. Chameleon-owned inference is intended; its design is
being decided separately. The local production-like smoke uses uploaded media
only and makes no inference-service calls.

**Latest recorded checks:** the default backend suite completed with 218 tests
(6 skipped); the isolated PostgreSQL integration suite completed with 173 tests,
the focused PostgreSQL export plus Celery-registration coverage completed with
29 tests, and 79 frontend tests passed. Frontend typecheck and build were clean,
migration drift check was clean, the helper-script tests passed, and the local
browser E2E run passed against the isolated PostgreSQL/Redis/worker/Beat stack.
Provider calls were mocked or disabled; unit-test FFmpeg subprocesses are mocked,
while the E2E export used real FFmpeg. The 6 skips are all `apps.jobs.tests.test_generation_races`
(PostgreSQL row locks; set `CHAMELEON_TEST_DATABASE_URL`); an earlier note of 3 skips predates
three race tests added later, so 6 is the current count.
These are recorded local results, not a live CI badge: this repository does not
yet have a CI workflow.

## Roadmap

These are dependency-based phases, not promised delivery dates.

| Phase | Milestone | Acceptance boundary |
| --- | --- | --- |
| P0 - creator foundation | Browser and local production-like runtime checks complete | Sign up, create a project, upload media, assemble scenes, edit captions and verify export with real FFmpeg plus isolated PostgreSQL/Redis/worker/Beat wiring |
| P1 - Chameleon-owned inference and deployment | Separately decide the self-hosted inference architecture, then define its acceptance checks alongside Railway deployment | Chameleon-owned inference fits the product's requirements; outputs persist privately and operate with the API, worker and storage |
| P2 - creator quality and workflow depth | Script-to-video orchestration, realistic scene/body-motion controls, localization and team/agency tools | Evaluate with authorized quality, latency and cost benchmarks before making performance claims |

Detailed scope and acceptance boundaries:
[creator studio design](./docs/superpowers/specs/2026-10-07-chameleon-premier-creator-studio-design.md)
and [implementation plan](./docs/superpowers/plans/2026-10-07-chameleon-creator-foundation.md).

## Architecture

```mermaid
flowchart LR
    Browser["Browser: React studio"] -->|"Same-origin /api + session + CSRF"| API["Django / DRF API"]
    API --> DB[("PostgreSQL")]
    API -->|"Queue"| Redis["Redis"]
    Redis --> Worker["Celery worker"]
    Beat["Celery Beat: recovery sweeps"] --> Redis
    Worker -->|"Authorized generation"| Provider["Magic Hour"]
    Provider -->|"Status / temporary results"| Worker
    Provider -->|"Signed webhook"| API
    API --> Storage["Private media storage"]
    Worker -->|"Uploaded scene assets"| Storage
    Worker --> FFmpeg["FFmpeg export assembly"]
    FFmpeg -->|"MP4 + subtitles"| Storage
    Storage -->|"Authorized download through API"| API
    API --> Browser
```

The provider-to-private-asset bridge is implemented with separate provider and
asset-readiness states. It remains gated until authorized download origins and
durable storage are verified; live provider downloads have not been exercised.

- **Backend:** Django 5, DRF, PostgreSQL, Celery and Redis.
- **Frontend:** React, Vite, TypeScript, Tailwind CSS, Zustand and React Router.
  The built bundle is served same-origin by the API in deployment.
- **Rendering:** FFmpeg and FFprobe, executed by background workers.
- **Hosting target:** Railway. Because a Railway volume attaches to exactly one
  service, the API, Celery worker and Celery Beat run together in a single
  service sharing one private media volume; splitting them apart requires shared
  object storage. See the [Railway runbook](./infra/railway.md).

## Five-minute quickstart

**For the local UI/API, once prerequisites are ready.** First-time PostgreSQL,
Redis or toolchain installation takes additional time. Use Python 3.11 (the
tested interpreter), Node/npm, a running PostgreSQL service with an existing
`chameleon` database, and reachable Redis. The credentials below are examples
for a local database you control; substitute your own.

From PowerShell in the repository root:

```powershell
Set-Location "C:\Software Projects\Chameleon"
py -3.11 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r ".\backend\requirements.txt"
npm --prefix ".\frontend" ci

# Development settings belong to this terminal only.
$env:SECRET_KEY = ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N"))
$env:DEBUG = "1"
$env:DATABASE_URL = "postgresql://postgres:YOUR_LOCAL_PASSWORD@127.0.0.1:5432/chameleon"
$env:REDIS_URL = "redis://127.0.0.1:6379/1"
$env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:CSRF_TRUSTED_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"
$env:MAGIC_HOUR_API_KEY = ""

Set-Location ".\backend"
& "..\.venv\Scripts\python.exe" manage.py migrate
& "..\.venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
```

In a second PowerShell terminal:

```powershell
Set-Location "C:\Software Projects\Chameleon"
npm --prefix ".\frontend" run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173**, choose **Get started**, and create your workspace.
The frontend proxies relative API requests to Django; use the frontend origin
for the browser workflow. Environment example files are references, not
automatically loaded settings.

**Rendering is an additional setup step:** install FFmpeg/FFprobe on the worker
PATH, then start a Celery worker and one Beat scheduler, each from the backend
directory with the same backend environment. On Windows, use the worker's solo
pool for local development:

```powershell
# Separate terminal, after applying the same backend environment values:
Set-Location "C:\Software Projects\Chameleon\backend"
& "..\.venv\Scripts\python.exe" -m celery -A chameleon worker --pool=solo -l info

# Another terminal with those environment values:
Set-Location "C:\Software Projects\Chameleon\backend"
& "..\.venv\Scripts\python.exe" -m celery -A chameleon beat -l info
```

Missing rendering binaries produce explicit failures. Generation credentials
are optional for exploring the uploaded-media workflow; enabling provider-backed
API requests can incur charges. See [backend setup and recovery](./backend/README.md)
and [environment examples](./infra/) for configuration details. The Railway
topology, deployment manifests and pre-launch checks are in the
[Railway runbook](./infra/railway.md).
For inactive-by-default generation gates, tariff verification and private
ingestion operations, see [image integration runbook](./docs/generation-image-integration.md).

### Validation

```powershell
Set-Location "C:\Software Projects\Chameleon\backend"
& "..\.venv\Scripts\python.exe" manage.py test

Set-Location "C:\Software Projects\Chameleon"
npm --prefix ".\frontend" run test -- --run
npm --prefix ".\frontend" run typecheck
npm --prefix ".\frontend" run build
```

Deployment configuration is checked separately, against whatever environment
variables are loaded in the current terminal (this is also the Railway release
step):

```powershell
Set-Location "C:\Software Projects\Chameleon\backend"
& "..\.venv\Scripts\python.exe" manage.py check_deployment --role all
```

Backend tests use isolated SQLite/cache settings and controlled provider/broker
doubles. Live PostgreSQL concurrency, provider quality and production operation
require their own integration checks.

### Browser end-to-end test

The Playwright suite in `e2e/` starts its own Django API (port 18000) and Vite
dev server (port 15173) with a scratch SQLite database and media directory under
`e2e/.runtime/`, eager Celery and an in-process cache (`chameleon.settings_e2e`,
refuses to load without `CHAMELEON_E2E=1` and enforces the scratch SQLite/media itself:
it requires `CHAMELEON_E2E_RUNTIME_DIR` inside `e2e/.runtime` and rejects any other
`DATABASE_URL` or `MEDIA_ROOT`). It sets an empty provider key and
makes no paid generation calls. FFmpeg/FFprobe come from project-local npm
packages (`ffmpeg-static`, `ffprobe-static`), so nothing global is installed.
The scratch SQLite database, in-process cache and eager Celery do **not** prove
PostgreSQL, Redis or a separate worker; the exported file is an uploaded-image
clip, not the future cinematic storytelling output.

```powershell
npm --prefix ".\e2e" ci
# Python is resolved portably: $env:E2E_PYTHON (must import Django/Celery/DRF), else
# the repo .venv, else py -3 / python3 / python. Use an installed browser (or run
# `npx playwright install chromium` in e2e/ once):
$env:PLAYWRIGHT_CHANNEL = "msedge"
npm --prefix ".\e2e" run test
```

The test registers and re-logs in (the re-login follows clearing cookies, i.e. an expired
session; there is no logout UI yet), builds captions only through the UI (add, validate,
remove, save), reloads to prove the scene's asset and duration persisted, then checks the
downloaded MP4 with `ffprobe` (H.264 1080x1920 plus AAC) and a full `ffmpeg` decode, and
confirms a second registered user gets 404/empty results for the first user's asset,
project, export and downloads. The MP4 and `ffprobe` output are written to
`e2e/.runtime/artifacts/`. `npm --prefix .\e2e run test:scripts` unit-tests Python resolution.

## Engineering principles

- **Private by design:** workspace membership and roles govern access; uploads
  use controlled storage references and authorized download endpoints.
- **Honest asynchronous work:** job states reflect real provider outcomes.
  Uncertain paid submissions are surfaced for reconciliation rather than
  automatically resubmitted.
- **Backend-owned credentials:** provider keys and authorization decisions stay
  on the server.
- **Durable production inputs:** local private media needs persistent storage
  on Railway; temporary provider links are not treated as renderable assets.
- **Responsible media creation:** likeness and voice workflows depend on rights
  and consent. Integrations use documented APIs and appropriate commercial
  permissions; the product uses original branding and assets.

## Repository layout

```text
backend/   Django API, Celery configuration, domain apps and tests
frontend/  React + Vite + TypeScript studio
e2e/       Playwright browser end-to-end tests and local harness
infra/     Backend and frontend environment examples
docs/      Product design and implementation plan
replica/   Competitive and compliance research from public sources
```

The [replica research](./replica/) records public feature comparisons and
integration/compliance constraints. It informed an original product design;
it is not copied competitor code or a collection of private APIs.

## Contributing and branch policy

Chameleon is proprietary; participation and code use require the owner's
permission. Authorized contributors should:

1. Branch from the agreed development base and keep changes scoped to an issue
   or milestone. `feature/creator-foundation` currently holds the active work;
   `main` contains the initial scaffold until reviewed changes are merged.
2. Open a PR to the owner-agreed target branch with a description of behavior,
   tests run and any unverified integration steps.
3. Run the relevant validation commands above, preserve workspace isolation and
   capability gates, and document changes to API/setup contracts.
4. Keep secrets and private media out of source control. Coordinate schema,
   provider-cost and storage changes before implementing them.

Merges, pushes to shared branches and releases require owner approval. CI is a
planned automation step; local test evidence should be attached to PRs meanwhile.

## License

**Proprietary - all rights reserved.** No open-source license is granted.
Use, redistribution and contributions require explicit permission from the
repository owner. See [LICENSE](./LICENSE).
