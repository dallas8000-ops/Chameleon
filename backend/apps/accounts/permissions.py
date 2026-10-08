from apps.accounts.models import WorkspaceMembership


class WorkspaceScopedPermission:
    @staticmethod
    def has_workspace_access(user, workspace_id: int) -> bool:
        if not getattr(user, "is_authenticated", False):
            return False
        return WorkspaceMembership.objects.filter(
            user=user,
            workspace_id=workspace_id,
        ).exists()

    @staticmethod
    def has_owner_access(user, workspace_id: int) -> bool:
        if not getattr(user, "is_authenticated", False):
            return False
        return WorkspaceMembership.objects.filter(
            user=user,
            workspace_id=workspace_id,
            role=WorkspaceMembership.Role.OWNER,
        ).exists()

