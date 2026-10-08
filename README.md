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
reviews are complete. Live browser and media-runtime checks are the next milestone.

| Capability | Status | Notes |
| --- | --- | --- |
| Accounts, workspaces, roles | Available in development | Email login, CSRF-protected sessions, owner/editor/viewer access |
| Projects and ordered scenes | Available APIs | Workspace-scoped persistence |
| Private asset uploads | Available APIs | Media-signature checks, content-type matching, 25 MiB default limit |
| Generation jobs and usage ledger | Available APIs | Signed webhooks, durable polling, idempotent ledger updates and interrupted-submission recovery |
| React authentication and dashboard | Reviewed | Session bootstrap, expiry recovery, project creation and studio navigation |
| Creator studio | Reviewed | Uploaded-asset picker, image/video scenes, captions, job status refresh and export screens |
| Caption tracks | Reviewed APIs and UI | Validated segments, track creation/editing and export selection |
| FFmpeg export assembly | Reviewed implementation; runtime unverified | Private MP4 and subtitle downloads; mocked subprocess tests, no real render yet |
| Image generation from the studio | Implemented; activation gated | Versioned credit estimates, explicit confirmation, duplicate-submit protection; requires verified operator configuration |
| Presenter generation | Intentionally disabled | Needs secure workspace image/audio transfer and audio ingestion |
| Generated media to editable scenes | Implemented; activation gated | Bounded private ingestion and recovery; download origins and durable storage need operator verification |
| Browser end-to-end verification | Next milestone | Real cookies, CSRF, proxy, studio and export workflow |
| Railway production deployment | Planned | Persistent private storage and worker infrastructure need deployment verification |

**Latest recorded checks:** the default backend suite completed with 151 tests
and 3 PostgreSQL-only skips; the latest scoped PostgreSQL jobs/provider run passed
90 tests, and 73 frontend tests passed. Frontend typecheck and build were clean.
The full PostgreSQL suite still has documented baseline auth/rendering test
failures. Provider calls and FFmpeg subprocesses were mocked where applicable.
These are recorded local results, not a live CI badge: this repository does not
yet have a CI workflow.

## Roadmap

These are dependency-based phases, not promised delivery dates.

| Phase | Milestone | Acceptance boundary |
| --- | --- | --- |
| P0 - creator foundation | Task 8 browser and runtime checks | Sign up, create a project, upload media, assemble scenes, edit captions and verify export with real FFmpeg |
| P1 - generation activation and deployment | Verify configured credit quotes, authorized provider integration and durable generated assets; add audio transfer and Railway deployment | Paid actions show a trustworthy estimate before submission; outputs persist privately; API, worker, scheduler and storage operate together |
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
- **Rendering:** FFmpeg and FFprobe, executed by background workers.
- **Hosting target:** Railway, with persistent private media storage shared by
  the API and rendering workers.

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
and [environment examples](./infra/) for configuration details.
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

Backend tests use isolated SQLite/cache settings and controlled provider/broker
doubles. Live PostgreSQL concurrency, provider quality, real FFmpeg rendering
and production operation require their own integration checks.

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
