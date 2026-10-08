from __future__ import annotations

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.text import slugify


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":
        if not email:
            raise ValueError("email is required")

        normalized_email = self.normalize_email(email).strip().lower()
        user = self.model(email=normalized_email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.email


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.build_unique_slug(self.name, exclude_pk=self.pk)
        super().save(*args, **kwargs)

    @classmethod
    def build_unique_slug(cls, name: str, *, exclude_pk: int | None = None) -> str:
        max_length = cls._meta.get_field("slug").max_length
        base_slug = slugify(name).strip("-") or "workspace"
        base_slug = base_slug[:max_length]
        queryset = cls.objects.all()
        if exclude_pk is not None:
            queryset = queryset.exclude(pk=exclude_pk)

        candidate = base_slug
        suffix = 2
        while queryset.filter(slug=candidate).exists():
            suffix_text = f"-{suffix}"
            candidate = f"{base_slug[: max_length - len(suffix_text)]}{suffix_text}"
            suffix += 1
        return candidate


class WorkspaceMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        EDITOR = "editor", "Editor"
        REVIEWER = "reviewer", "Reviewer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=24, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "workspace"],
                name="unique_workspace_membership",
            ),
        ]
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.workspace_id}:{self.role}"

    @classmethod
    def for_user(cls, user):
        if not getattr(user, "is_authenticated", False):
            return cls.objects.none()
        return cls.objects.select_related("workspace").filter(user=user)
