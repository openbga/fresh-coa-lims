from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.views.decorators.debug import sensitive_variables

from core.audit import record_event

ROLES = frozenset({"analyst", "reviewer", "quality", "admin", "auditor"})


@transaction.atomic
def assign_roles(*, actor, user, roles, reason):
    """Explicit audited replacement; bootstrap administrators may provision the first roles."""
    from .administration import account_lock, check_role_change, safe_snapshot

    account_lock()
    roles = set(roles)
    if not reason.strip() or not roles.issubset(ROLES):
        raise ValidationError("Supply a reason and recognized laboratory roles.")
    users = get_user_model().objects.select_for_update().filter(pk__in=[actor.pk, user.pk])
    locked = {entry.pk: entry for entry in users.order_by("pk")}
    actor = locked[actor.pk]
    user = locked[user.pk]
    if not actor.is_active or not (
        actor.is_superuser or actor.groups.filter(name="admin").exists()
    ):
        raise PermissionDenied("Only active account administrators can assign roles.")
    check_role_change(actor, user, roles, bootstrap=True)
    before = safe_snapshot(user)
    groups = [Group.objects.get_or_create(name=role)[0] for role in sorted(roles)]
    user.groups.set(groups)
    user.management_revision += 1
    user.session_epoch += 1
    user.save(update_fields=["management_revision", "session_epoch"])
    record_event(
        actor=actor,
        action="account.roles_changed",
        obj=user,
        before=before,
        after=safe_snapshot(user),
        reason=reason,
    )
    return user


@sensitive_variables()
@transaction.atomic
def provision_account(*, actor, username, password, first_name, last_name, roles, reason):
    from .administration import account_lock

    account_lock()
    user = get_user_model()(username=username, first_name=first_name, last_name=last_name)
    validate_password(password, user)
    user.full_clean(exclude=["password"])
    user.set_password(password)
    user.save()
    assign_roles(actor=actor, user=user, roles=roles, reason=reason)
    record_event(
        actor=actor,
        action="account.created",
        obj=user,
        after={
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        reason=reason,
    )
    return user
