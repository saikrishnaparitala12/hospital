from rest_framework.permissions import BasePermission
from .models import Role


class IsTokenAdmin(BasePermission):
    """Allows access only to token_admin role users."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.TOKEN_ADMIN)


class IsTokenAdminOrAdmin(BasePermission):
    """Allows access to token_admin or admin (staff/superuser) users."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in (Role.TOKEN_ADMIN, Role.ADMIN) or request.user.is_staff


class IsAmbulance(BasePermission):
    """Allows access only to ambulance role users."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.AMBULANCE)


class IsAmbulanceOrAdmin(BasePermission):
    """Allows access to ambulance or admin users."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in (Role.AMBULANCE, Role.ADMIN) or request.user.is_staff
