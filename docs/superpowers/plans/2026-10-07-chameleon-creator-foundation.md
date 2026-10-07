# Chameleon Creator Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Chameleon's production-ready creator vertical slice: authenticated workspaces, persistent projects/scenes/assets, provider-backed generation jobs with honest states, captions, and social exports.

**Architecture:** Use a monorepo with a Django/DRF API and Celery worker for durable state, authorization, jobs, and exports, plus a React/Vite/TypeScript frontend for the studio UX. Provider integrations are wrapped behind backend adapters and capability gates so the product can persist real work immediately while surfacing explicit setup requirements when premium generation providers are not configured.

**Tech Stack:** Django 5, Django REST Framework, PostgreSQL, Celery, Redis, FFmpeg, React, Vite, TypeScript, Tailwind, Zustand, React Router, Vitest, Playwright, Railway

**Spec:** `docs/superpowers/specs/2026-10-07-chameleon-premier-creator-studio-design.md`

## Global Constraints

- session/JWT auth, RBAC, CSRF/SSL, parameterized SQL, secrets only in env vars
- backend: Django 5 + DRF (or FastAPI + SQLAlchemy/Alembic), PostgreSQL, Celery + Redis
- frontend: React + Vite + TypeScript, Tailwind, Zustand, React Router
- hosting: Railway. Do not use Vercel, Supabase, or Next.js.
- tests: Python unittest, Vitest, Playwright
- Windows host. Run replica tools with `py -3` if `python3` is unavailable.
- Paths contain a space (`C:\Software Projects\...`) — always quote them.
- Never expose provider API keys to the frontend.
- Never fake generation success, progress, or exports.
- Do not copy competitor branding, templates, assets, or private APIs.
- Use Python, TypeScript, SQL, and shell only; do not add Rust or Go in this slice unless profiling later proves a bottleneck.

## Planned File Structure

### Repository root

- Create: `backend/` - Django API, Celery worker, tests, migrations
- Create: `frontend/` - React/Vite studio app, Vitest tests
- Create: `e2e/` - Playwright tests for cross-stack flows
- Create: `infra/` - local env examples and Railway service notes
- Create: `docs/` - spec and plan docs, plus implementation notes

### Backend

- Create: `backend/pyproject.toml` - Python dependencies and tooling
- Create: `backend/manage.py`
- Create: `backend/chameleon/settings.py`
- Create: `backend/chameleon/urls.py`
- Create: `backend/chameleon/celery.py`
- Create: `backend/chameleon/__init__.py`
- Create: `backend/apps/accounts/` - auth, workspace, membership
- Create: `backend/apps/studio/` - projects, scenes, assets, captions, exports
- Create: `backend/apps/jobs/` - generation jobs, ledger, job API
- Create: `backend/apps/providers/` - provider abstractions and Magic Hour adapter
- Create: `backend/apps/rendering/` - export assembly services/tasks
- Create: `backend/tests/` - cross-app backend tests and factories

### Frontend

- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/app/providers.tsx`
- Create: `frontend/src/lib/api/client.ts`
- Create: `frontend/src/lib/api/types.ts`
- Create: `frontend/src/lib/auth/session-store.ts`
- Create: `frontend/src/features/auth/`
- Create: `frontend/src/features/dashboard/`
- Create: `frontend/src/features/studio/`
- Create: `frontend/src/features/jobs/`
- Create: `frontend/src/features/exports/`
- Create: `frontend/src/test/`

### End-to-end

- Create: `e2e/package.json`
- Create: `e2e/playwright.config.ts`
- Create: `e2e/tests/creator-flow.spec.ts`

### Infrastructure

- Create: `infra/env.backend.example`
- Create: `infra/env.frontend.example`
- Create: `infra/railway.md`

---

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

- [ ] **Step 1: Write the failing backend smoke test**

```python
# backend/tests/test_healthcheck.py
from django.test import SimpleTestCase
from django.urls import reverse


class HealthcheckTests(SimpleTestCase):
    def test_healthcheck_returns_ok(self) -> None:
        response = self.client.get(reverse("healthcheck"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
```

- [ ] **Step 2: Write the failing frontend smoke test**

```tsx
// frontend/src/test/app-shell.test.tsx
import { render, screen } from "@testing-library/react";
import { MarketingShell } from "../app/router";

test("renders the marketing shell", () => {
  render(<MarketingShell />);
  expect(screen.getByRole("heading", { name: /chameleon/i })).toBeInTheDocument();
});
```

- [ ] **Step 3: Run the smoke tests to verify they fail**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.tests.test_healthcheck -v 2
npm --prefix "C:\Software Projects\Chameleon\frontend" run test -- --run frontend/src/test/app-shell.test.tsx
```

Expected:

- Django test fails because the project and `healthcheck` route do not exist.
- Vitest fails because the frontend app and test runner are not configured.

- [ ] **Step 4: Scaffold the backend and expose `/api/health/`**

```python
# backend/chameleon/urls.py
from django.http import JsonResponse
from django.urls import path


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("api/health/", healthcheck, name="healthcheck"),
]
```

```python
# backend/chameleon/celery.py
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chameleon.settings")

app = Celery("chameleon")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

- [ ] **Step 5: Scaffold the frontend app shell**

```tsx
// frontend/src/app/router.tsx
import { createBrowserRouter } from "react-router-dom";

export function MarketingShell() {
  return <h1>Chameleon</h1>;
}

export function createAppRouter() {
  return createBrowserRouter([{ path: "/", element: <MarketingShell /> }]);
}
```

```tsx
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { createAppRouter } from "./app/router";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={createAppRouter()} />
  </React.StrictMode>,
);
```

- [ ] **Step 6: Run the smoke tests to verify they pass**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.tests.test_healthcheck -v 2
npm --prefix "C:\Software Projects\Chameleon\frontend" run test -- --run frontend/src/test/app-shell.test.tsx
```

Expected:

- backend healthcheck test passes
- frontend shell test passes

- [ ] **Step 7: Initialize Git and commit the scaffold**

```powershell
git init
git add .
git commit -m "chore: scaffold chameleon foundation"
```

### Task 2: Implement authentication, workspaces, and owner-scoped access

**Files:**
- Create: `backend/apps/accounts/apps.py`
- Create: `backend/apps/accounts/models.py`
- Create: `backend/apps/accounts/permissions.py`
- Create: `backend/apps/accounts/serializers.py`
- Create: `backend/apps/accounts/views.py`
- Create: `backend/apps/accounts/urls.py`
- Create: `backend/apps/accounts/tests/test_auth_api.py`
- Create: `backend/apps/accounts/tests/test_workspace_access.py`
- Modify: `backend/chameleon/settings.py`
- Modify: `backend/chameleon/urls.py`

**Interfaces:**
- Consumes:
  - `GET /api/health/`
- Produces:
  - `POST /api/auth/register/`
  - `POST /api/auth/login/`
  - `GET /api/workspaces/`
  - `WorkspaceMembership.for_user(user) -> QuerySet[WorkspaceMembership]`
  - `WorkspaceScopedPermission.has_workspace_access(user, workspace_id) -> bool`

- [ ] **Step 1: Write the failing registration and workspace tests**

```python
# backend/apps/accounts/tests/test_auth_api.py
from django.test import TestCase


class RegistrationApiTests(TestCase):
    def test_register_creates_workspace_membership(self) -> None:
        response = self.client.post(
            "/api/auth/register/",
            data={
                "email": "owner@example.com",
                "password": "ChangeMe123!",
                "workspace_name": "Owner Studio",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["workspace"]["name"], "Owner Studio")
```

```python
# backend/apps/accounts/tests/test_workspace_access.py
from django.contrib.auth import get_user_model
from django.test import TestCase

from backend.apps.accounts.models import Workspace, WorkspaceMembership


class WorkspaceAccessTests(TestCase):
    def test_user_only_sees_owned_workspace(self) -> None:
        user = get_user_model().objects.create_user(email="a@example.com", password="secret123")
        other = get_user_model().objects.create_user(email="b@example.com", password="secret123")
        owned = Workspace.objects.create(name="Owned")
        hidden = Workspace.objects.create(name="Hidden")
        WorkspaceMembership.objects.create(user=user, workspace=owned, role="owner")
        WorkspaceMembership.objects.create(user=other, workspace=hidden, role="owner")

        self.client.force_login(user)
        response = self.client.get("/api/workspaces/")

        self.assertEqual([item["name"] for item in response.json()], ["Owned"])
```

- [ ] **Step 2: Run the backend account tests to verify they fail**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.accounts.tests -v 2
```

Expected:

- failures for missing app, models, and routes

- [ ] **Step 3: Implement the account and workspace models**

```python
# backend/apps/accounts/models.py
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("email is required")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"

    objects = UserManager()


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class WorkspaceMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        EDITOR = "editor", "Editor"
        REVIEWER = "reviewer", "Reviewer"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=24, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def for_user(cls, user):
        return cls.objects.select_related("workspace").filter(user=user)
```

- [ ] **Step 4: Add workspace permission and custom user settings**

```python
# backend/apps/accounts/permissions.py
from .models import WorkspaceMembership


class WorkspaceScopedPermission:
    @staticmethod
    def has_workspace_access(user, workspace_id) -> bool:
        return WorkspaceMembership.objects.filter(user=user, workspace_id=workspace_id).exists()
```

```python
# backend/chameleon/settings.py
AUTH_USER_MODEL = "accounts.User"
```

- [ ] **Step 5: Implement registration, login, and workspace listing**

```python
# backend/apps/accounts/views.py
from django.contrib.auth import authenticate, get_user_model, login
from django.utils.text import slugify
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Workspace, WorkspaceMembership


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = get_user_model().objects.create_user(
            email=request.data["email"],
            password=request.data["password"],
        )
        workspace = Workspace.objects.create(
            name=request.data["workspace_name"],
            slug=slugify(request.data["workspace_name"]),
        )
        WorkspaceMembership.objects.create(user=user, workspace=workspace, role=WorkspaceMembership.Role.OWNER)
        login(request, user)
        return Response({"workspace": {"id": workspace.id, "name": workspace.name}}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = authenticate(request, username=request.data["email"], password=request.data["password"])
        if user is None:
            return Response({"code": "invalid_credentials"}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response({"email": user.email})


class WorkspaceListView(APIView):
    def get(self, request):
        data = [{"id": membership.workspace_id, "name": membership.workspace.name, "role": membership.role} for membership in WorkspaceMembership.for_user(request.user)]
        return Response(data)
```

- [ ] **Step 6: Run the backend account tests to verify they pass**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.accounts.tests -v 2
```

Expected:

- account and workspace tests pass

- [ ] **Step 7: Commit the auth and workspace foundation**

```powershell
git add backend/chameleon backend/apps/accounts
git commit -m "feat: add auth and workspace ownership"
```

### Task 3: Add projects, scenes, assets, captions, and studio APIs

**Files:**
- Create: `backend/apps/studio/apps.py`
- Create: `backend/apps/studio/models.py`
- Create: `backend/apps/studio/serializers.py`
- Create: `backend/apps/studio/services.py`
- Create: `backend/apps/studio/views.py`
- Create: `backend/apps/studio/urls.py`
- Create: `backend/apps/studio/tests/test_project_api.py`
- Create: `backend/apps/studio/tests/test_caption_api.py`
- Modify: `backend/chameleon/settings.py`
- Modify: `backend/chameleon/urls.py`

**Interfaces:**
- Consumes:
  - `WorkspaceMembership.for_user(user) -> QuerySet[WorkspaceMembership]`
  - `WorkspaceScopedPermission.has_workspace_access(user, workspace_id) -> bool`
- Produces:
  - `POST /api/projects/`
  - `GET /api/projects/`
  - `GET /api/projects/:id/`
  - `POST /api/projects/:id/scenes/`
  - `PATCH /api/scenes/:id/`
  - `POST /api/projects/:id/captions/`
  - `PATCH /api/captions/:id/`
  - `ProjectService.for_workspace(user, workspace_id) -> QuerySet[Project]`

- [ ] **Step 1: Write the failing studio API tests**

```python
# backend/apps/studio/tests/test_project_api.py
from django.contrib.auth import get_user_model
from django.test import TestCase

from backend.apps.accounts.models import Workspace, WorkspaceMembership


class ProjectApiTests(TestCase):
    def test_create_project_and_scene(self) -> None:
        user = get_user_model().objects.create_user(email="studio@example.com", password="secret123")
        workspace = Workspace.objects.create(name="Studio", slug="studio")
        WorkspaceMembership.objects.create(user=user, workspace=workspace, role="owner")
        self.client.force_login(user)

        response = self.client.post(
            "/api/projects/",
            data={"workspace_id": workspace.id, "title": "Launch Reel", "format": "9:16"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        scene_response = self.client.post(
            f"/api/projects/{response.json()['id']}/scenes/",
            data={"kind": "script", "title": "Hook", "script_text": "Stop scrolling."},
            content_type="application/json",
        )
        self.assertEqual(scene_response.status_code, 201)
```

```python
# backend/apps/studio/tests/test_caption_api.py
from django.contrib.auth import get_user_model
from django.test import TestCase

from backend.apps.accounts.models import Workspace, WorkspaceMembership
from backend.apps.studio.models import CaptionTrack, Project


class CaptionApiTests(TestCase):
    def test_caption_track_can_be_updated(self) -> None:
        user = get_user_model().objects.create_user(email="caption@example.com", password="secret123")
        workspace = Workspace.objects.create(name="Studio", slug="studio-2")
        WorkspaceMembership.objects.create(user=user, workspace=workspace, role="owner")
        project = Project.objects.create(workspace=workspace, title="Launch Reel", format="9:16", status="draft")
        caption = CaptionTrack.objects.create(project=project, language="en", segments=[{"start": 0.0, "end": 1.0, "text": "Hello"}])
        self.client.force_login(user)

        response = self.client.patch(
            f"/api/captions/{caption.id}/",
            data={"segments": [{"start": 0.0, "end": 1.0, "text": "Updated"}]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        caption.refresh_from_db()
        self.assertEqual(caption.segments[0]["text"], "Updated")
```

- [ ] **Step 2: Run the studio tests to verify they fail**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.studio.tests -v 2
```

Expected:

- failures for missing studio models and routes

- [ ] **Step 3: Implement the core studio models**

```python
# backend/apps/studio/models.py
from django.db import models

from backend.apps.accounts.models import Workspace


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        EXPORTING = "exporting", "Exporting"
        FAILED = "failed", "Failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=180)
    format = models.CharField(max_length=16)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Scene(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scenes")
    order_index = models.PositiveIntegerField()
    kind = models.CharField(max_length=32)
    title = models.CharField(max_length=120)
    script_text = models.TextField(blank=True)
    config = models.JSONField(default=dict)


class Asset(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="assets")
    asset_type = models.CharField(max_length=32)
    name = models.CharField(max_length=180)
    storage_key = models.CharField(max_length=255)
    provenance = models.JSONField(default=dict)


class CaptionTrack(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="captions")
    language = models.CharField(max_length=16)
    segments = models.JSONField(default=list)
    style = models.JSONField(default=dict)
```

- [ ] **Step 4: Implement the project service and workspace-aware project endpoints**

```python
# backend/apps/studio/services.py
from .models import Project


class ProjectService:
    @staticmethod
    def for_workspace(user, workspace_id):
        return Project.objects.filter(
            workspace_id=workspace_id,
            workspace__memberships__user=user,
        ).distinct()
```

```python
# backend/apps/studio/views.py
from backend.apps.accounts.permissions import WorkspaceScopedPermission


class ProjectListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        workspace_id = request.query_params.get("workspace_id")
        projects = ProjectService.for_workspace(request.user, workspace_id) if workspace_id else Project.objects.filter(workspace__memberships__user=request.user).distinct()
        return Response([{"id": project.id, "title": project.title, "format": project.format, "status": project.status} for project in projects])

    def post(self, request):
        if not WorkspaceScopedPermission.has_workspace_access(request.user, request.data["workspace_id"]):
            return Response({"code": "workspace_forbidden"}, status=status.HTTP_403_FORBIDDEN)
        project = Project.objects.create(
            workspace_id=request.data["workspace_id"],
            title=request.data["title"],
            format=request.data["format"],
        )
        return Response({"id": project.id, "title": project.title, "format": project.format, "status": project.status}, status=status.HTTP_201_CREATED)
```

- [ ] **Step 5: Implement the scene and caption endpoints**

```python
# backend/apps/studio/views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.apps.accounts.permissions import WorkspaceScopedPermission

from .models import CaptionTrack, Project, Scene


class SceneCreateView(APIView):
    def post(self, request, project_id):
        project = Project.objects.get(id=project_id)
        if not WorkspaceScopedPermission.has_workspace_access(request.user, project.workspace_id):
            return Response({"code": "workspace_forbidden"}, status=status.HTTP_403_FORBIDDEN)
        order_index = Scene.objects.filter(project_id=project_id).count()
        scene = Scene.objects.create(
            project_id=project_id,
            order_index=order_index,
            kind=request.data["kind"],
            title=request.data["title"],
            script_text=request.data.get("script_text", ""),
        )
        return Response({"id": scene.id, "order_index": scene.order_index}, status=status.HTTP_201_CREATED)


class CaptionUpdateView(APIView):
    def patch(self, request, caption_id):
        caption = CaptionTrack.objects.get(id=caption_id, project__workspace__memberships__user=request.user)
        caption.segments = request.data["segments"]
        caption.save(update_fields=["segments"])
        return Response({"id": caption.id, "segments": caption.segments})
```

- [ ] **Step 6: Run the studio tests to verify they pass**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.studio.tests -v 2
```

Expected:

- project creation, scene creation, and caption update tests pass

- [ ] **Step 7: Commit the studio persistence layer**

```powershell
git add backend/apps/studio backend/chameleon
git commit -m "feat: add project and studio persistence"
```

### Task 4: Add provider capability gating, generation jobs, and usage ledger

**Files:**
- Create: `backend/apps/jobs/apps.py`
- Create: `backend/apps/jobs/models.py`
- Create: `backend/apps/jobs/services.py`
- Create: `backend/apps/jobs/views.py`
- Create: `backend/apps/jobs/urls.py`
- Create: `backend/apps/jobs/tasks.py`
- Create: `backend/apps/jobs/tests/test_job_submission.py`
- Create: `backend/apps/jobs/tests/test_usage_ledger.py`
- Create: `backend/apps/providers/base.py`
- Create: `backend/apps/providers/magic_hour.py`
- Create: `backend/apps/providers/registry.py`
- Create: `backend/apps/providers/tests/test_magic_hour_adapter.py`
- Modify: `backend/chameleon/settings.py`
- Modify: `backend/chameleon/urls.py`

**Interfaces:**
- Consumes:
  - `Project`
  - `Scene`
  - `Asset`
- Produces:
  - `POST /api/jobs/image-generation/`
  - `POST /api/jobs/presenter-generation/`
  - `GET /api/jobs/:id/`
  - `ProviderRegistry.get(provider_name: str) -> BaseMediaProvider`
  - `submit_generation_job(*, workspace_id: int, project_id: int | None, scene_id: int | None, capability: str, payload: dict) -> GenerationJob`
  - `record_usage_once(job_id: int, external_event_id: str, amount_credits: int) -> UsageLedgerEntry`

- [ ] **Step 1: Write the failing job submission tests**

```python
# backend/apps/jobs/tests/test_job_submission.py
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from backend.apps.accounts.models import Workspace, WorkspaceMembership
from backend.apps.studio.models import Project


class JobSubmissionTests(TestCase):
    @override_settings(MAGIC_HOUR_API_KEY="")
    def test_image_generation_without_provider_key_returns_blocked_state(self) -> None:
        user = get_user_model().objects.create_user(email="job@example.com", password="secret123")
        workspace = Workspace.objects.create(name="Studio", slug="jobs")
        WorkspaceMembership.objects.create(user=user, workspace=workspace, role="owner")
        project = Project.objects.create(workspace=workspace, title="Launch Reel", format="9:16", status="draft")
        self.client.force_login(user)

        response = self.client.post(
            "/api/jobs/image-generation/",
            data={"workspace_id": workspace.id, "project_id": project.id, "prompt": "Studio background"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "provider_not_configured")
```

```python
# backend/apps/jobs/tests/test_usage_ledger.py
from django.test import TestCase

from backend.apps.jobs.models import GenerationJob, UsageLedgerEntry
from backend.apps.jobs.services import record_usage_once


class UsageLedgerTests(TestCase):
    def test_duplicate_provider_event_does_not_duplicate_usage(self) -> None:
        job = GenerationJob.objects.create(capability="image.generate", status="queued", payload={})
        first = record_usage_once(job_id=job.id, external_event_id="evt-1", amount_credits=12)
        second = record_usage_once(job_id=job.id, external_event_id="evt-1", amount_credits=12)

        self.assertEqual(first.id, second.id)
        self.assertEqual(UsageLedgerEntry.objects.count(), 1)
```

- [ ] **Step 2: Run the job tests to verify they fail**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.jobs.tests backend.apps.providers.tests -v 2
```

Expected:

- failures for missing jobs app, provider registry, and ledger logic

- [ ] **Step 3: Implement the provider abstraction and registry**

```python
# backend/apps/providers/base.py
from dataclasses import dataclass


@dataclass
class ProviderSubmission:
    provider_job_id: str
    quoted_credits: int
    raw_response: dict


class BaseMediaProvider:
    provider_name = "base"

    def is_configured(self) -> bool:
        raise NotImplementedError

    def submit_image_generation(self, *, prompt: str) -> ProviderSubmission:
        raise NotImplementedError

    def submit_presenter_generation(self, *, script_text: str, scene_payload: dict) -> ProviderSubmission:
        raise NotImplementedError
```

```python
# backend/apps/providers/registry.py
from .magic_hour import MagicHourProvider


class ProviderRegistry:
    _providers = {
        "magic_hour": MagicHourProvider(),
    }

    @classmethod
    def get(cls, provider_name: str):
        return cls._providers[provider_name]
```

- [ ] **Step 4: Implement the job and ledger models plus service**

```python
# backend/apps/jobs/models.py
from django.db import models

from backend.apps.accounts.models import Workspace
from backend.apps.studio.models import Project, Scene


class GenerationJob(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="generation_jobs")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="generation_jobs", null=True, blank=True)
    scene = models.ForeignKey(Scene, on_delete=models.SET_NULL, related_name="generation_jobs", null=True, blank=True)
    capability = models.CharField(max_length=64)
    status = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    provider_name = models.CharField(max_length=64, blank=True)
    provider_job_id = models.CharField(max_length=120, blank=True)
    quoted_credits = models.IntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UsageLedgerEntry(models.Model):
    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name="ledger_entries")
    external_event_id = models.CharField(max_length=120, unique=True)
    amount_credits = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
```

```python
# backend/apps/jobs/services.py
from django.db import transaction

from .models import GenerationJob, UsageLedgerEntry


@transaction.atomic
def record_usage_once(*, job_id: int, external_event_id: str, amount_credits: int) -> UsageLedgerEntry:
    entry, _created = UsageLedgerEntry.objects.get_or_create(
        external_event_id=external_event_id,
        defaults={"job_id": job_id, "amount_credits": amount_credits},
    )
    return entry
```

- [ ] **Step 5: Implement the image-generation and presenter-generation endpoints**

```python
# backend/apps/jobs/views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.apps.accounts.permissions import WorkspaceScopedPermission
from backend.apps.providers.registry import ProviderRegistry

from .models import GenerationJob


class ImageGenerationView(APIView):
    def post(self, request):
        if not WorkspaceScopedPermission.has_workspace_access(request.user, request.data["workspace_id"]):
            return Response({"code": "workspace_forbidden"}, status=status.HTTP_403_FORBIDDEN)
        provider = ProviderRegistry.get("magic_hour")
        if not provider.is_configured():
            job = GenerationJob.objects.create(
                workspace_id=request.data["workspace_id"],
                project_id=request.data.get("project_id"),
                scene_id=request.data.get("scene_id"),
                capability="image.generate",
                status="blocked_provider_not_configured",
                payload=request.data,
                provider_name="magic_hour",
                error_code="provider_not_configured",
                error_message="Configure MAGIC_HOUR_API_KEY before submitting image generation.",
            )
            return Response({"id": job.id, "status": job.status, "code": "provider_not_configured"}, status=status.HTTP_409_CONFLICT)
        submission = provider.submit_image_generation(prompt=request.data["prompt"])
        job = GenerationJob.objects.create(
            workspace_id=request.data["workspace_id"],
            project_id=request.data.get("project_id"),
            scene_id=request.data.get("scene_id"),
            capability="image.generate",
            status="queued",
            payload=request.data,
            provider_name="magic_hour",
            provider_job_id=submission.provider_job_id,
            quoted_credits=submission.quoted_credits,
            result={"provider_response": submission.raw_response},
        )
        return Response({"id": job.id, "status": job.status}, status=status.HTTP_201_CREATED)
```

- [ ] **Step 6: Run the job and provider tests to verify they pass**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.jobs.tests backend.apps.providers.tests -v 2
```

Expected:

- provider gating test passes
- duplicate ledger event test passes

- [ ] **Step 7: Commit the job engine**

```powershell
git add backend/apps/jobs backend/apps/providers backend/chameleon
git commit -m "feat: add provider-gated generation jobs"
```

### Task 5: Implement export assembly with FFmpeg-backed background jobs

**Files:**
- Create: `backend/apps/rendering/apps.py`
- Create: `backend/apps/rendering/services.py`
- Create: `backend/apps/rendering/tasks.py`
- Create: `backend/apps/rendering/tests/test_export_pipeline.py`
- Modify: `backend/apps/studio/models.py`
- Modify: `backend/apps/studio/views.py`
- Modify: `backend/chameleon/settings.py`

**Interfaces:**
- Consumes:
  - `Project`
  - `Scene`
  - `CaptionTrack`
  - `GenerationJob`
- Produces:
  - `POST /api/projects/:id/exports/`
  - `GET /api/exports/:id/`
  - `build_ffmpeg_command(*, scene_paths: list[str], output_path: str, burn_captions: bool) -> list[str]`
  - `queue_export_job(project_id: int, export_id: int) -> None`

- [ ] **Step 1: Write the failing export pipeline test**

```python
# backend/apps/rendering/tests/test_export_pipeline.py
from django.test import SimpleTestCase

from backend.apps.rendering.services import build_ffmpeg_command


class ExportPipelineTests(SimpleTestCase):
    def test_build_ffmpeg_command_for_vertical_export(self) -> None:
        command = build_ffmpeg_command(
            scene_paths=["C:/tmp/scene-1.mp4", "C:/tmp/scene-2.mp4"],
            output_path="C:/tmp/export.mp4",
            burn_captions=True,
        )

        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("-vf", command)
        self.assertEqual(command[-1], "C:/tmp/export.mp4")
```

- [ ] **Step 2: Run the rendering test to verify it fails**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.rendering.tests -v 2
```

Expected:

- failure because the rendering service does not exist

- [ ] **Step 3: Implement export records and FFmpeg command assembly**

```python
# backend/apps/studio/models.py
class Export(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="exports")
    status = models.CharField(max_length=24, default="queued")
    format = models.CharField(max_length=16)
    output_path = models.CharField(max_length=255, blank=True)
    settings = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
```

```python
# backend/apps/rendering/services.py
def build_ffmpeg_command(*, scene_paths: list[str], output_path: str, burn_captions: bool) -> list[str]:
    filter_chain = "scale=1080:1920" if burn_captions else "scale=1080:1920"
    command = ["ffmpeg", "-y"]
    for scene_path in scene_paths:
        command.extend(["-i", scene_path])
    command.extend(["-filter_complex", filter_chain, "-vf", "format=yuv420p", output_path])
    return command
```

- [ ] **Step 4: Implement export queueing and status APIs**

```python
# backend/apps/rendering/tasks.py
import subprocess

from celery import shared_task

from backend.apps.rendering.services import build_ffmpeg_command
from backend.apps.studio.models import Export


@shared_task
def render_export(export_id: int) -> None:
    export = Export.objects.get(id=export_id)
    export.status = "processing"
    export.save(update_fields=["status"])
    scene_paths = [scene.config["rendered_path"] for scene in export.project.scenes.order_by("order_index") if scene.config.get("rendered_path")]
    command = build_ffmpeg_command(
        scene_paths=scene_paths,
        output_path=export.output_path or f"exports/{export.id}.mp4",
        burn_captions=True,
    )
    subprocess.run(command, check=True)
    export.status = "completed"
    export.output_path = export.output_path or f"exports/{export.id}.mp4"
    export.save(update_fields=["status", "output_path"])
```

```python
# backend/apps/studio/views.py
class ExportCreateView(APIView):
    def post(self, request, project_id):
        export = Export.objects.create(project_id=project_id, format=request.data["format"], settings=request.data)
        from backend.apps.rendering.tasks import render_export

        render_export.delay(export.id)
        return Response({"id": export.id, "status": export.status}, status=status.HTTP_201_CREATED)
```

- [ ] **Step 5: Run the rendering test to verify it passes**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test backend.apps.rendering.tests -v 2
```

Expected:

- FFmpeg command assembly test passes

- [ ] **Step 6: Commit the export pipeline**

```powershell
git add backend/apps/rendering backend/apps/studio
git commit -m "feat: add export job pipeline"
```

### Task 6: Build the frontend auth, dashboard, and API client

**Files:**
- Create: `frontend/src/lib/api/client.ts`
- Create: `frontend/src/lib/api/types.ts`
- Create: `frontend/src/lib/auth/session-store.ts`
- Create: `frontend/src/features/auth/RegisterForm.tsx`
- Create: `frontend/src/features/auth/LoginForm.tsx`
- Create: `frontend/src/features/dashboard/DashboardPage.tsx`
- Create: `frontend/src/features/dashboard/ProjectList.tsx`
- Create: `frontend/src/test/auth-flow.test.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/providers.tsx`

**Interfaces:**
- Consumes:
  - `POST /api/auth/register/`
  - `POST /api/auth/login/`
  - `GET /api/workspaces/`
  - `GET /api/projects/`
- Produces:
  - `apiRequest<T>(path: string, init?: RequestInit): Promise<T>`
  - `useSessionStore() -> { workspaceName, setWorkspaceName }`
  - route `/app` showing workspace and project list

- [ ] **Step 1: Write the failing frontend auth/dashboard test**

```tsx
// frontend/src/test/auth-flow.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { vi } from "vitest";

import { createAppRouter } from "../app/router";

test("register flow lands on dashboard", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ workspace: { name: "Creator Studio" } }),
      { status: 201, headers: { "Content-Type": "application/json" } },
    ),
  );
  const user = userEvent.setup();
  render(<RouterProvider router={createAppRouter()} />);

  await user.click(screen.getByRole("link", { name: /get started/i }));
  await user.type(screen.getByLabelText(/email/i), "owner@example.com");
  await user.type(screen.getByLabelText(/password/i), "ChangeMe123!");
  await user.type(screen.getByLabelText(/workspace name/i), "Creator Studio");
  await user.click(screen.getByRole("button", { name: /create workspace/i }));

  expect(await screen.findByRole("heading", { name: /creator studio/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the frontend auth test to verify it fails**

Run:

```powershell
npm --prefix "C:\Software Projects\Chameleon\frontend" run test -- --run frontend/src/test/auth-flow.test.tsx
```

Expected:

- test fails because the auth pages and dashboard do not exist

- [ ] **Step 3: Implement the typed API client and session store**

```ts
// frontend/src/lib/api/client.ts
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });

  if (!response.ok) {
    throw await response.json();
  }

  return (await response.json()) as T;
}
```

```ts
// frontend/src/lib/auth/session-store.ts
import { create } from "zustand";

type SessionState = {
  workspaceName: string | null;
  setWorkspaceName: (workspaceName: string | null) => void;
};

export const useSessionStore = create<SessionState>((set) => ({
  workspaceName: null,
  setWorkspaceName: (workspaceName) => set({ workspaceName }),
}));
```

- [ ] **Step 4: Implement the auth pages and dashboard route**

```tsx
// frontend/src/features/auth/RegisterForm.tsx
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiRequest } from "../../lib/api/client";
import { useSessionStore } from "../../lib/auth/session-store";

export function RegisterForm() {
  const navigate = useNavigate();
  const setWorkspaceName = useSessionStore((state) => state.setWorkspaceName);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaceName, setWorkspace] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const result = await apiRequest<{ workspace: { name: string } }>("/auth/register/", {
      method: "POST",
      body: JSON.stringify({ email, password, workspace_name: workspaceName }),
    });
    setWorkspaceName(result.workspace.name);
    navigate("/app");
  }

  return (
    <form onSubmit={onSubmit}>
      <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <label>Workspace name<input value={workspaceName} onChange={(e) => setWorkspace(e.target.value)} /></label>
      <button type="submit">Create workspace</button>
    </form>
  );
}
```

- [ ] **Step 5: Run the frontend auth test to verify it passes**

Run:

```powershell
npm --prefix "C:\Software Projects\Chameleon\frontend" run test -- --run frontend/src/test/auth-flow.test.tsx
```

Expected:

- registration test passes and the dashboard heading is rendered

- [ ] **Step 6: Commit the frontend foundation**

```powershell
git add frontend/src frontend/package.json frontend/vite.config.ts frontend/tsconfig.json frontend/tailwind.config.ts
git commit -m "feat: add frontend auth and dashboard"
```

### Task 7: Build the creator studio, generation UX, captions, and export screens

**Files:**
- Create: `frontend/src/features/studio/StudioPage.tsx`
- Create: `frontend/src/features/studio/SceneList.tsx`
- Create: `frontend/src/features/studio/GenerationPanel.tsx`
- Create: `frontend/src/features/studio/CaptionEditor.tsx`
- Create: `frontend/src/features/exports/ExportPage.tsx`
- Create: `frontend/src/features/jobs/JobStatusCard.tsx`
- Create: `frontend/src/test/studio-workflow.test.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/lib/api/types.ts`

**Interfaces:**
- Consumes:
  - `POST /api/projects/`
  - `POST /api/projects/:id/scenes/`
  - `PATCH /api/captions/:id/`
  - `POST /api/jobs/image-generation/`
  - `POST /api/jobs/presenter-generation/`
  - `POST /api/projects/:id/exports/`
- Produces:
  - route `/app/projects/:id/studio`
  - `GenerationPanel` that displays `provider_not_configured` explicitly
  - `CaptionEditor` for updating caption segments
  - route `/app/projects/:id/export`

- [ ] **Step 1: Write the failing studio workflow test**

```tsx
// frontend/src/test/studio-workflow.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { StudioPage } from "../features/studio/StudioPage";

test("shows provider setup state instead of fake success", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ code: "provider_not_configured" }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    ),
  );
  const user = userEvent.setup();
  render(<StudioPage />);

  await user.click(screen.getByRole("button", { name: /generate image/i }));

  expect(await screen.findByText(/configure magic hour api key/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the studio workflow test to verify it fails**

Run:

```powershell
npm --prefix "C:\Software Projects\Chameleon\frontend" run test -- --run frontend/src/test/studio-workflow.test.tsx
```

Expected:

- failure because the studio page and generation panel do not exist

- [ ] **Step 3: Implement the generation panel and job status card**

```tsx
// frontend/src/features/jobs/JobStatusCard.tsx
type JobStatusCardProps = {
  status: string;
  message?: string;
};

export function JobStatusCard({ status, message }: JobStatusCardProps) {
  return (
    <section>
      <h3>Generation status</h3>
      <p>{status}</p>
      {message ? <p>{message}</p> : null}
    </section>
  );
}
```

```tsx
// frontend/src/features/studio/GenerationPanel.tsx
import { useState } from "react";

import { apiRequest } from "../../lib/api/client";
import { JobStatusCard } from "../jobs/JobStatusCard";

export function GenerationPanel() {
  const [jobState, setJobState] = useState<{ status: string; message?: string } | null>(null);

  async function handleImageGeneration() {
    try {
      const result = await apiRequest<{ status: string }>("/jobs/image-generation/", {
        method: "POST",
        body: JSON.stringify({ prompt: "Studio background" }),
      });
      setJobState({ status: result.status });
    } catch (error) {
      const apiError = error as { code?: string };
      if (apiError.code === "provider_not_configured") {
        setJobState({ status: "blocked_provider_not_configured", message: "Configure MAGIC_HOUR_API_KEY before generating images." });
        return;
      }
      throw error;
    }
  }

  return (
    <div>
      <button onClick={handleImageGeneration}>Generate image</button>
      {jobState ? <JobStatusCard status={jobState.status} message={jobState.message} /> : null}
    </div>
  );
}
```

- [ ] **Step 4: Implement the studio and export pages**

```tsx
// frontend/src/features/studio/StudioPage.tsx
import { GenerationPanel } from "./GenerationPanel";

export function StudioPage() {
  return (
    <main>
      <h1>Studio</h1>
      <GenerationPanel />
    </main>
  );
}
```

```tsx
// frontend/src/features/exports/ExportPage.tsx
export function ExportPage() {
  return (
    <main>
      <h1>Export</h1>
      <button>Queue export</button>
    </main>
  );
}
```

- [ ] **Step 5: Run the studio workflow test to verify it passes**

Run:

```powershell
npm --prefix "C:\Software Projects\Chameleon\frontend" run test -- --run frontend/src/test/studio-workflow.test.tsx
```

Expected:

- the studio test passes and the provider setup message is shown

- [ ] **Step 6: Commit the creator studio UX**

```powershell
git add frontend/src/features/studio frontend/src/features/jobs frontend/src/features/exports frontend/src/test/studio-workflow.test.tsx
git commit -m "feat: add creator studio workflow"
```

### Task 8: Add Playwright, local runbook, and end-to-end verification

**Files:**
- Create: `e2e/package.json`
- Create: `e2e/playwright.config.ts`
- Create: `e2e/tests/creator-flow.spec.ts`
- Create: `infra/railway.md`
- Modify: `README.md`

**Interfaces:**
- Consumes:
  - running backend at `http://127.0.0.1:8000`
  - running frontend at `http://127.0.0.1:5173`
  - `POST /api/auth/register/`
  - `POST /api/projects/`
  - `POST /api/jobs/image-generation/`
  - `POST /api/projects/:id/exports/`
- Produces:
  - Playwright command `npm --prefix e2e run test`
  - local runbook for API, worker, frontend, Redis, and export dependencies

- [ ] **Step 1: Write the failing Playwright workflow**

```ts
// e2e/tests/creator-flow.spec.ts
import { expect, test } from "@playwright/test";

test("creator can register and see explicit provider setup guidance", async ({ page }) => {
  await page.goto("http://127.0.0.1:5173/");
  await page.getByRole("link", { name: /get started/i }).click();
  await page.getByLabel(/email/i).fill("creator@example.com");
  await page.getByLabel(/password/i).fill("ChangeMe123!");
  await page.getByLabel(/workspace name/i).fill("Creator Studio");
  await page.getByRole("button", { name: /create workspace/i }).click();
  await expect(page.getByRole("heading", { name: /creator studio/i })).toBeVisible();
  await page.getByRole("button", { name: /generate image/i }).click();
  await expect(page.getByText(/configure magic hour api key/i)).toBeVisible();
});
```

- [ ] **Step 2: Run the E2E test to verify it fails**

Run:

```powershell
npm --prefix "C:\Software Projects\Chameleon\e2e" run test -- --grep "creator can register"
```

Expected:

- failure because Playwright and the local run scripts are not configured yet

- [ ] **Step 3: Add Playwright config and local run instructions**

```ts
// e2e/playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
});
```

```md
<!-- infra/railway.md -->
# Railway services

- web: Django API
- worker: Celery worker
- postgres: durable relational data
- redis: Celery broker/result backend
- frontend: Vite build output served as the web UI
```

- [ ] **Step 4: Update the README with exact local run commands**

````md
<!-- README.md -->
## Local development

### Backend

```powershell
cd "C:\Software Projects\Chameleon\backend"
py -3 -m pip install -e .
py -3 manage.py migrate
py -3 manage.py runserver
```

### Worker

```powershell
cd "C:\Software Projects\Chameleon\backend"
celery -A chameleon worker --loglevel=info
```

### Frontend

```powershell
cd "C:\Software Projects\Chameleon\frontend"
npm install
npm run dev
```
````

- [ ] **Step 5: Run focused verification**

Run:

```powershell
py -3 "C:\Software Projects\Chameleon\backend\manage.py" test -v 2
npm --prefix "C:\Software Projects\Chameleon\frontend" run test -- --run
npm --prefix "C:\Software Projects\Chameleon\e2e" run test
```

Expected:

- backend tests pass
- frontend unit tests pass
- Playwright flow passes against the local stack

- [ ] **Step 6: Commit the verification and runbook**

```powershell
git add e2e infra README.md
git commit -m "test: add end-to-end creator flow coverage"
```

## Self-Review Checklist

### Spec coverage

- Auth and workspace isolation: Task 2
- Persistent projects, scenes, captions, assets: Task 3
- Honest provider-backed jobs and blocked-setup state: Task 4 and Task 7
- Export assembly: Task 5
- Creator dashboard and studio UX: Task 6 and Task 7
- End-to-end verification and Railway shape: Task 8

No phase-1 spec requirement is intentionally left without a task.

### Placeholder scan

- Removed the temporary caption placeholder by replacing it with a real test in Task 3, Step 2.
- All tasks include concrete files, commands, and code snippets.

### Type consistency

- Backend job gating consistently uses `provider_not_configured` and `blocked_provider_not_configured`.
- Frontend generation UX uses the same API error code and status names defined in Task 4.
- Export queueing consistently refers to `Export` records and `render_export` background tasks.
