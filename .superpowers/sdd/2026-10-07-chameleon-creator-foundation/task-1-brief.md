### Task 1: Scaffold the monorepo foundation

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/manage.py`
- Create: `backend/chameleon/settings.py`
- Create: `backend/chameleon/urls.py`
- Create: `backend/chameleon/celery.py`
- Create: `backend/chameleon/__init__.py`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/app/providers.tsx`
- Create: `infra/env.backend.example`
- Create: `infra/env.frontend.example`
- Create: `.gitignore`
- Create: `README.md`

**Interfaces:**
- Consumes: none
- Produces:
  - Django health endpoint `GET /api/health/ -> {"status": "ok"}`
  - Frontend app shell route `/` rendering a root heading
  - Celery app import path `chameleon.celery.app`

Follow the exact steps, tests, and commands in the plan section for Task 1. Because this repository is not yet a git repo, initialize git as part of the task per Step 7, then include the resulting commit SHA in your report. You may create additional minimal config files required to make the scaffold runnable (for example Vitest config or package scripts), but keep them within Task 1 scope.
