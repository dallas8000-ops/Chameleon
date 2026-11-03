"""Lists every account in the local database with its workspaces and projects, and optionally sets a
password (RESET_EMAIL / RESET_PASSWORD env vars). Run via find-account.ps1."""
import os

import django

django.setup()

from django.contrib.auth import authenticate  # noqa: E402

from apps.accounts.models import User, WorkspaceMembership  # noqa: E402
from apps.studio.models import Project  # noqa: E402

users = User.objects.order_by("id")
if not users:
    print("No accounts in this database.")
for user in users:
    print()
    print(f"{user.email}{'' if user.is_active else '  (INACTIVE)'}")
    for m in WorkspaceMembership.objects.filter(user=user).select_related("workspace"):
        projects = Project.objects.filter(workspace=m.workspace).order_by("id")
        print(f"  workspace '{m.workspace.name}' ({m.role}): {projects.count()} project(s)")
        for p in projects:
            print(f"    - {p.title} [{p.format}, {p.status}]")

email = os.environ.get("RESET_EMAIL")
password = os.environ.get("RESET_PASSWORD")
if email and password:
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        raise SystemExit(f"\nNo account with email {email}.")
    user.set_password(password)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])
    ok = authenticate(username=user.email, password=password) is not None
    print(f"\nPassword for {user.email} updated. Sign-in check: {'OK' if ok else 'FAILED'}")
