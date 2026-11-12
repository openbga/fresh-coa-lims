from core.services import AUDIT_READ_ROLES

from .services import ROLES


def account_navigation(request):
    roles = set()
    if request.user.is_authenticated and request.user.is_active:
        roles = set(request.user.groups.filter(name__in=ROLES).values_list("name", flat=True))
    return {
        "can_view_workspace": bool(roles),
        "can_view_audit": bool(roles & AUDIT_READ_ROLES),
        "can_manage_accounts": "admin" in roles,
    }
