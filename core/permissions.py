from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOwner(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'OWNER'
        )


class IsWorker(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'WORKER'
        )


class IsVeterinarian(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'VETERINARIAN'
        )


class IsOwnerOrWorker(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ('OWNER', 'WORKER')
        )


class IsOwnerOrVeterinarian(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ('OWNER', 'VETERINARIAN')
        )


class IsAppUser(BasePermission):
    """Any authenticated user with an app role."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ('OWNER', 'WORKER', 'VETERINARIAN')
        )


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class IsOwnerOrReadOnlyAppUser(BasePermission):
    """Owner can write; all app roles can read."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role not in ('OWNER', 'WORKER', 'VETERINARIAN'):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role == 'OWNER'
