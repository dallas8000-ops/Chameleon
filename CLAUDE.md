# Chameleon

## Stack constraints (override replica-architect defaults)
- Backend: Django 5 + DRF (or FastAPI + SQLAlchemy/Alembic), PostgreSQL, Celery + Redis
- Frontend: React + Vite + TypeScript, Tailwind, Zustand, React Router
- Hosting: Railway. Do not use Vercel, Supabase, or Next.js.
- Tests: Python unittest, Vitest, Playwright
- Security: session/JWT auth, RBAC, CSRF/SSL, parameterized SQL, secrets only in env vars

## Environment
- Windows host. Run replica tools with `py -3` if `python3` is unavailable.
- Paths contain a space (`C:\Software Projects\...`) — always quote them.

## Third-party skills
- `.claude/skills/replica-*` pinned to Jakeschincariol/replica-skill@77c9436fb3d18c3d58169efb8caf4fe906b0dc51 (audited 2026-10-06).
  Do not update from upstream without re-auditing.
