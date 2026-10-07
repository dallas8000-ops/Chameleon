# Chameleon Premier Creator Studio Design

Date: 2026-10-07
Status: approved in chat for implementation planning

## Product Goal

Build Chameleon as a premium creator studio for realistic social and marketing video creation: project-based, scene-based, and export-ready for channels such as Facebook, Instagram, and YouTube.

The product is not a single avatar generator. It combines:

- realistic presenter clips
- generated and edited backgrounds/scenes
- reusable image and video assets
- editable scripts and captions
- social-friendly export formats
- persistent projects, reviews, and usage tracking

The main differentiator is continuity across the workflow. A creator should be able to move from idea to assets to assembled video to export inside one workspace without restarting in separate tools.

## Product Positioning

Chameleon targets:

1. individual creators and personal/business users
2. small marketing teams
3. agencies serving multiple clients

The first implemented slice prioritizes the creator workflow while preserving the architectural seams needed for teams and agencies.

## Scope and Phase Boundaries

### Phase 1: production foundation and creator vertical slice

Deliver:

- account authentication
- workspace-aware authorization
- persistent projects and ordered scenes
- owned uploads and asset library
- image generation request flow
- presenter generation request flow
- generated scene insertion into a project
- explicit async job tracking with honest states
- editable captions and subtitle export
- social exports
- cost/usage tracking
- explicit "provider not configured" or "capability unavailable" UX instead of fake output

### Phase 2: premium workflow depth

Add after the vertical slice works end to end:

- image editing, upscaling, and background removal
- image-to-video and start/end-frame guidance
- localization and translated variants
- brand presets and original/licensed templates
- team invitations, comments, approvals
- agency client workspaces

### Phase 3: advanced motion and scale

Add only after provider quality and system performance are benchmarked:

- richer body-performance controls
- higher-end scene composition controls
- batch variant generation
- public developer API
- collaborative editing improvements

## Non-Goals

The first implementation will not:

- copy competitor branding, templates, demos, copy, assets, or private APIs
- reproduce proprietary foundation models or promise equal model quality
- include native mobile apps
- include live avatars or real-time conversation agents
- include a public marketplace
- claim unlimited rendering, universal language support, or enterprise compliance not actually verified

## Legal and Provider Constraints

- Only licensed, supported provider integrations may be used.
- Do not use HeyGen's services to build a competing product without separate legal review and written authorization.
- Magic Hour is a documented candidate provider for supported API-backed generation, subject to its terms and commercial requirements.
- No provider API keys may be exposed to the frontend.
- All face, voice, and likeness use must be backed by user-held rights and recorded consent where required.
- The app must surface policy or rights failures explicitly.

## Quality Bar

Chameleon should feel like a serious production tool, not a toy interface around APIs.

That means:

- persistent projects, not single-fire prompts
- revision-safe scene assembly
- explicit job, cost, and failure states
- real exports with valid dimensions/codecs
- brand-safe and consent-aware asset handling
- social-ready previews and crops

Quality claims about realism, scene continuity, body motion, or creator-level output must be based on measured provider evaluations, not assumed from marketing pages.

## Architecture Overview

Use a monorepo with:

- React + Vite + TypeScript frontend
- Django 5 + Django REST Framework backend
- PostgreSQL for durable application state
- Celery + Redis for asynchronous jobs
- FFmpeg-driven assembly/export worker
- Python provider adapters for image, video, voice, and presenter capabilities

Avoid unnecessary polyglot complexity. Use Python, TypeScript, SQL, and shell by default. Add Rust or Go only if profiling proves a renderer/transcoder bottleneck that Python orchestration cannot meet cleanly.

## Core User Experience

### Primary workflow

1. Sign in
2. Create a project
3. Add scenes and script content
4. Request assets or presenter clips
5. Track honest job progress
6. Assemble scenes in the studio
7. Edit captions
8. Export social-ready outputs

### UX rules

- Never fake generation results.
- Never display invented progress percentages.
- Every failed or blocked action must explain what the user can do next.
- Every paid operation must have a clear pre-submit estimate or quoted basis.
- Every asset in a project must keep provenance to the input and job that created it.

## Proposed Routes

### Marketing

- `/`
- `/pricing`
- `/auth`

### Application

- `/app`
- `/app/projects/new`
- `/app/projects/:id/studio`
- `/app/assets`
- `/app/tools/image`
- `/app/tools/presenter`
- `/app/jobs/:id`
- `/app/projects/:id/captions`
- `/app/projects/:id/export`
- `/app/exports/:id`
- `/app/settings/billing`

### Deferred but architected-for routes

- `/app/tools/video`
- `/app/tools/image-edit`
- `/app/projects/:id/localize`
- `/app/projects/:id/review`
- `/app/settings/members`
- `/app/clients`

## Backend Responsibilities

### Backend owns

- auth and RBAC
- workspace isolation
- project, scene, asset, job, consent, export, and usage records
- provider capability gating
- signed upload/download orchestration
- async execution
- idempotency for webhook and retry paths
- billing/usage ledger entries
- export assembly

### Frontend owns

- creator workflow UX
- form state
- scene editing interactions
- capability-aware controls
- honest status presentation
- preview and export flows

The frontend must not contain provider credentials or business-critical authorization logic.

## Core Domain Model

The first slice requires these durable entities:

- User
- Workspace
- Membership
- Project
- Scene
- Asset
- GenerationJob
- ConsentRecord
- CaptionTrack
- UsageLedgerEntry
- Export

Deferred but expected later:

- LocaleVariant
- BrandKit
- Review
- Client
- Template
- VoiceProfile

## Job Lifecycle

All provider-backed media generation uses asynchronous jobs with durable local records.

States:

- `pending_provider`
- `queued`
- `processing`
- `completed`
- `failed`
- `canceled`
- `blocked_provider_not_configured`

Rules:

- create the local job record before contacting a provider
- preserve the request snapshot used for submission
- store provider job IDs when available
- treat webhooks and polling as idempotent state updates
- never double-charge local usage on duplicate callbacks
- copy completed artifacts into controlled storage when allowed
- preserve error codes/messages in structured form for UI display

## Export Pipeline

Phase 1 export is an assembled render, not a full nonlinear editor.

Support:

- 9:16 and 16:9 outputs
- ordered scenes
- image and video scene assets
- presenter/video overlays when available
- caption burn-in and subtitle file output
- deterministic export settings persisted with each render request

FFmpeg is used for final assembly. Export jobs must be background tasks with durable state and retry-safe storage handling.

## Security and Compliance Requirements

- session/JWT auth, RBAC, CSRF/SSL, parameterized SQL, secrets only in env vars
- backend: Django 5 + DRF (or FastAPI + SQLAlchemy/Alembic), PostgreSQL, Celery + Redis
- frontend: React + Vite + TypeScript, Tailwind, Zustand, React Router
- hosting: Railway. Do not use Vercel, Supabase, or Next.js.
- tests: Python unittest, Vitest, Playwright
- Windows host. Run replica tools with `py -3` if `python3` is unavailable.
- Paths contain a space (`C:\Software Projects\...`) — always quote them.

Additional application requirements:

- owner-scoped access checks on every project, scene, asset, job, export, and ledger read/write
- upload validation for file type and size
- explicit consent capture for likeness-sensitive flows
- no silent fallback to unlicensed provider behavior
- audit-friendly usage history

## Validation Requirements

Before calling the foundation complete, the implementation must prove:

1. a user can create a project, persist scenes, and reload them
2. image generation requests create durable jobs and honest states
3. presenter generation requests either submit successfully or show a provider-setup block with no fake results
4. captions can be edited and exported
5. exports produce a playable file with valid dimensions
6. duplicate job updates do not create duplicate ledger entries
7. one workspace cannot access another workspace's data

## Deployment Shape

Deploy to Railway with:

- web service for Django API
- worker service for Celery
- PostgreSQL
- Redis
- frontend static/app service

External object storage may be introduced if Railway volume/storage requirements exceed acceptable limits.

## Riskiest Parts

1. provider quality versus promised realism
2. async job, billing, and retry correctness
3. export composition reliability under real media inputs

## Approved Next Step

Write and execute an implementation plan for the production foundation and creator vertical slice first, leaving team/agency depth and advanced body-performance controls for later phases.
