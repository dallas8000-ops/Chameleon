# Chameleon

Chameleon is being rebuilt as one creator studio that combines what AI avatar-video and AI image/video
tools do separately: talking-presenter videos, voiceover, captions, translation, image generation,
image-to-video, talking photos, background removal and upscaling, all in one project and scene
editor with export. It does not use HeyGen or Magic Hour. Generation runs on open-source models
hosted on a serverless GPU service (RunPod or Modal), called only from the backend.

See [docs/rebuild-plan.md](./docs/rebuild-plan.md) for the phased plan and current status.

## Status

| Area | State |
| --- | --- |
| Accounts, workspaces, roles | Working: email login, CSRF-protected sessions, owner/editor/viewer access |
| Projects, scenes, uploads, captions | Working: workspace-scoped APIs and an uploaded-media studio |
| FFmpeg export | Working: private MP4 and subtitle downloads |
| Media generation | **Not built yet** (Phase 2 and 3 of the plan) |
| UI design | Being rebuilt (Phase 1) |
| Deployment | Railway, single service; see [infra/railway.md](./infra/railway.md) |

## Stack

- **Backend:** Django 5, DRF, PostgreSQL, Celery, Redis
- **Frontend:** React, Vite, TypeScript, Tailwind, Zustand, React Router (built bundle served same-origin by Django)
- **Rendering:** FFmpeg/FFprobe on the Celery worker
- **Hosting:** Railway. Keys live in environment variables only.

## Local quickstart

Use Python 3.11, Node/npm, a local PostgreSQL database named `chameleon`, and Redis.

```powershell
Set-Location "C:\Software Projects\Chameleon"
py -3.11 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r ".\backend\requirements.txt"
npm --prefix ".\frontend" ci

$env:SECRET_KEY = ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N"))
$env:DEBUG = "1"
$env:DATABASE_URL = "postgresql://USER:PASSWORD@127.0.0.1:5432/chameleon"
$env:REDIS_URL = "redis://127.0.0.1:6379/1"
$env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:CSRF_TRUSTED_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"

Set-Location ".\backend"
& "..\.venv\Scripts\python.exe" manage.py migrate
& "..\.venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
```

In a second terminal:

```powershell
npm --prefix ".\frontend" run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173. Exports also need FFmpeg on PATH and a Celery worker
(`python -m celery -A chameleon worker --pool=solo -l info`) plus one Beat scheduler
(`python -m celery -A chameleon beat -l info`), both run from `backend/` with the same environment.

## Validation

```powershell
Set-Location "C:\Software Projects\Chameleon\backend"
& "..\.venv\Scripts\python.exe" manage.py test

Set-Location "C:\Software Projects\Chameleon"
npm --prefix ".\frontend" run test -- --run
npm --prefix ".\frontend" run typecheck
npm --prefix ".\frontend" run build

# Release configuration check (also the Railway pre-deploy step)
Set-Location ".\backend"
& "..\.venv\Scripts\python.exe" manage.py check_deployment --role all
```

Browser end-to-end tests live in `e2e/` (`npm --prefix ".\e2e" ci`, then `npm --prefix ".\e2e" run test`).
They start their own isolated API and Vite server under `e2e/.runtime/`.

## Repository layout

```text
backend/   Django API, Celery configuration, domain apps and tests
frontend/  React + Vite + TypeScript studio
e2e/       Playwright browser tests and local harness
infra/     Environment examples and the Railway runbook
docs/      Rebuild plan
```

## License

**Proprietary - all rights reserved.** See [LICENSE](./LICENSE).
