# Chameleon

Chameleon is an original, project-based creator studio being built for social
and marketing video production. The goal is to bring asset creation, scene
editing, captions, presenter workflows, and export into one continuous
workspace for formats used by platforms such as Instagram, Facebook, and
YouTube.

This repository is under active development. It currently contains the
backend product foundation and APIs; the complete creator-facing web app is
not yet implemented or deployed. Features below are labeled by their current
status so the product vision is not confused with working functionality.

## Product direction

Chameleon is intended to help a creator move from an idea to a finished,
platform-ready video without rebuilding the project in separate tools. The
product is being designed around:

- Persistent projects with ordered scenes.
- Reusable images and video assets.
- Script and caption editing, including subtitles.
- Provider-backed media generation with clear capability and setup states.
- Assembled social-format video exports.
- Workspace roles, job history, and usage tracking.

The differentiator is workflow continuity and editable scene-based production,
not copying another product's branding, templates, assets, or private APIs.

## Current implementation

### Implemented backend foundation

- Email-based account registration, login, logout, and session bootstrap.
- CSRF-protected session authentication and workspace membership roles.
- Workspace-scoped project and ordered scene APIs.
- Private asset uploads with content-signature checks and configured size
  limits.
- Caption tracks with validated, ordered, non-overlapping segments.
- Generation-job records, provider gating, status tracking, webhook
  verification, and an idempotent usage ledger.
- Recovery for interrupted provider submissions and provider polling; uncertain
  paid outcomes are surfaced for operator reconciliation rather than
  automatically resubmitted.
- A server-side Magic Hour adapter for documented API operations. Provider
  credentials stay on the backend.

These APIs are a foundation, not yet a finished user experience. In
particular, the presenter flow is intentionally unavailable until Chameleon
can securely transfer workspace-owned image and audio assets to the provider.
Script-only speech generation is not claimed.

### In progress

- FFmpeg-backed export assembly is being developed. Its local changes are not
  yet reviewed or complete; do not treat exports as a released feature.

### Not yet implemented

- The React creator dashboard and studio screens.
- End-to-end browser sign-up, project editing, and export flows.
- Secure asset transfer and durable storage for generated provider results.
- Verified production deployment and live provider quality/performance
  benchmarks.
- Advanced body-motion controls, localization, and team/agency workflow depth.

For the staged product plan and acceptance boundaries, see the
[creator studio design](./docs/superpowers/specs/2026-10-07-chameleon-premier-creator-studio-design.md)
and [implementation plan](./docs/superpowers/plans/2026-10-07-chameleon-creator-foundation.md).

## Architecture

- **Backend:** Django 5, Django REST Framework, PostgreSQL, Celery, and Redis.
- **Frontend:** React, Vite, TypeScript, Tailwind CSS, Zustand, and React Router.
- **Media assembly:** FFmpeg, with background work handled by Celery.
- **Hosting target:** Railway.

Provider API keys and authorization decisions belong on the backend. The
frontend must not receive provider credentials. The project does not use
Next.js, Vercel, or Supabase.

## Repository layout

```text
backend/   Django API, Celery configuration, domain apps, and backend tests
frontend/  React + Vite + TypeScript application
infra/     Environment examples and Railway notes
docs/      Product design and implementation plan
replica/   Public-source product reconnaissance and feature matrix
```

## Local development

Use the setup guidance in [backend/README.md](./backend/README.md) and the
environment templates in [infra/](./infra/). The backend requires
`SECRET_KEY`, `DATABASE_URL`, and `REDIS_URL` outside test runs. Local
development also needs the frontend toolchain and, when running background
jobs, a Celery worker. Configure any provider key only in the backend
environment; image-generation API requests can incur provider charges.

From PowerShell, for example:

```powershell
Set-Location "C:\Software Projects\Chameleon\backend"
py -3 manage.py test
```

The automated tests use isolated test settings and provider/broker mocks; they
do not demonstrate live provider output or production service readiness.

## Security and responsible use

- Workspace data is isolated by membership and role.
- Media inputs and generated outputs must use controlled storage references;
  arbitrary client paths and provider URLs are not trusted as local files.
- Generation and export states must reflect actual work; the app must never
  fabricate success or progress.
- Use only provider integrations that are documented, licensed, and approved
  for the intended commercial use.
- Face, voice, and likeness workflows require appropriate rights and consent.
- Do not use competitor branding, templates, assets, or private APIs.

## Project status

The repository is on the `feature/creator-foundation` development branch.
Backend tests and checks have been run during implementation, but the current
uncommitted export work still needs to pass its review and verification.
There has been no claim of production readiness, completed UI, verified
presenter generation, or measured superiority over other products.
