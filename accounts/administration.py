"""Signed account administration with safe snapshots and serialized administrator guards.

Never use the generic model snapshot on User or PINCredential: hashes are secrets too.
"""

import hashlib
import json
from copy import copy

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from core.audit import record_event
from core.models import ElectronicSignature, PINCredential
from core.services import require_role, verify_pin
from core.session_control import signing_context

from .services import ROLES

ACCOUNT_LOCK = 681241
ACTIONS = {
    "identity": "Update identity",
    "roles": "Assign roles",
    "deactivate": "Deactivate account",
    "reactivate": "Reactivate account",
    "unlock_pin": "Clear PIN lockout",
    "reenroll_pin": "Require PIN re-enrollment",
    "reset_password": "Force password reset",
}


CREDENTIALS_LOCKED = (
    "This is a shared demonstration account. Its password and signature PIN are published on "
    "the sign-in page and cannot be changed here."
)


def account_lock():
    # Serializes the last-admin predicate, including changes targeting different users.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ACCOUNT_LOCK])


def reason_required(reason):
    if not reason.strip() or len(reason) > 2000:
        raise ValidationError("Provide a reason of at most 2000 characters.")


def role_names(user):
    return set(user.groups.values_list("name", flat=True))


def last_admin(user):
    return (
        user.is_active
        and "admin" in role_names(user)
        and not get_user_model()
        .objects.filter(is_active=True, groups__name="admin")
        .exclude(pk=user.pk)
        .exists()
    )


def check_role_change(actor, user, roles, *, bootstrap=False):
    if not roles.issubset(ROLES):
        raise ValidationError("Choose recognized laboratory roles.")
    before = role_names(user)
    initial_bootstrap = (
        bootstrap
        and actor.is_superuser
        and actor.pk == user.pk
        and not before
        and roles == {"admin"}
        and not get_user_model().objects.filter(is_active=True, groups__name="admin").exists()
    )
    if actor.pk == user.pk and roles - before and not initial_bootstrap:
        raise PermissionDenied(
            "You cannot grant yourself additional roles. Ask another administrator."
        )
    if "admin" not in roles and last_admin(user):
        raise ValidationError("Keep at least one active account with the admin role.")


def safe_snapshot(user):
    credential = PINCredential.objects.filter(user=user).first()
    return {
        "id": user.pk,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_active": user.is_active,
        "roles": sorted(role_names(user)),
        "revision": user.management_revision,
        "password_change_required": user.password_change_required,
        "credentials_locked": user.credentials_locked,
        "session_epoch": user.session_epoch,
        "pin_enrolled": credential is not None,
        "pin_failures": credential.failures if credential else 0,
        "pin_locked_until": credential.locked_until.isoformat()
        if credential and credential.locked_until
        else None,
    }


def _signer(actor, encoded):
    require_role(actor, "admin")
    credential = PINCredential.objects.select_for_update().filter(user=actor).first()
    if (
        credential is None
        or credential.encoded != encoded
        or (credential.locked_until and credential.locked_until > timezone.now())
    ):
        raise ValidationError("Signing credential changed. Try again.")
    signing_context(actor)
    # Actor stays row-locked through commit. Retain its authorized state for the final
    # lifetime check: an intentional change to one's own account revokes future sessions,
    # not the signature authorizing that very change.
    return copy(actor)


def _record(actor, user, action, before, reason, signer_state):
    after = safe_snapshot(user)
    event = record_event(
        actor=actor, obj=user, action=action, before=before, after=after, reason=reason
    )
    content = {"action": action, "account": after}
    ElectronicSignature.objects.create(
        signer=actor,
        signer_name=actor.get_full_name() or actor.username,
        meaning="account_authorized",
        object_type=user._meta.label_lower,
        object_id=str(user.pk),
        revision=user.management_revision,
        authentication_context=signing_context(signer_state),
        content=content,
        content_hash=hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        audit_event=event,
    )
    return user


@sensitive_variables()
def create_account(*, actor, pin, username, first_name, last_name, email, password, roles, reason):
    require_role(actor, "admin")
    reason_required(reason)
    roles = set(roles)
    if not roles.issubset(ROLES):
        raise ValidationError("Choose recognized laboratory roles.")
    signing_context(actor)
    encoded = verify_pin(actor, pin)  # Failure counters survive a rejected account transaction.
    with transaction.atomic():
        account_lock()
        actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
        signer_state = _signer(actor, encoded)
        user = get_user_model()(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_change_required=True,
        )
        validate_password(password, user)
        user.set_password(password)
        user.full_clean()
        user.save()
        from django.contrib.auth.models import Group

        user.groups.set([Group.objects.get_or_create(name=role)[0] for role in sorted(roles)])
        return _record(actor, user, "account.created", {}, reason, signer_state)


@sensitive_variables()
def change_account(
    *,
    actor,
    user,
    expected_revision,
    action,
    pin,
    reason,
    roles=None,
    first_name=None,
    last_name=None,
    email=None,
    temporary_password=None,
):
    require_role(actor, "admin")
    reason_required(reason)
    if action not in ACTIONS:
        raise ValidationError("Choose an account action.")
    signing_context(actor)
    encoded = verify_pin(actor, pin)
    with transaction.atomic():
        account_lock()
        locked = {
            u.pk: u
            for u in get_user_model()
            .objects.select_for_update()
            .filter(pk__in=[actor.pk, user.pk])
            .order_by("pk")
        }
        actor, user = locked[actor.pk], locked[user.pk]
        signer_state = _signer(actor, encoded)
        if user.management_revision != expected_revision:
            raise ValidationError("Account changed. Reload and review before signing.")
        before = safe_snapshot(user)
        # Written columns; the stored password hash is written only when it is being replaced.
        changed = ["management_revision", "session_epoch"]
        if action == "roles":
            from django.contrib.auth.models import Group

            roles = set(roles or [])
            check_role_change(actor, user, roles)
            user.groups.set([Group.objects.get_or_create(name=r)[0] for r in sorted(roles)])
        elif action == "identity":
            user.first_name, user.last_name, user.email = first_name, last_name, email
            changed += ["first_name", "last_name", "email"]
        elif action == "deactivate":
            if not user.is_active:
                raise ValidationError("This account is already inactive.")
            if last_admin(user):
                raise ValidationError("Keep at least one active account with the admin role.")
            user.is_active = False
            changed.append("is_active")
        elif action == "reactivate":
            if user.is_active:
                raise ValidationError("This account is already active.")
            user.is_active = True
            changed.append("is_active")
        elif action in {"unlock_pin", "reenroll_pin"}:
            credential = PINCredential.objects.select_for_update().filter(user=user).first()
            if credential is None:
                raise ValidationError("This account has no enrolled PIN.")
            if action == "reenroll_pin":
                credential.delete()
            else:
                credential.failures, credential.locked_until = 0, None
                credential.save(update_fields=["failures", "locked_until"])
        elif action == "reset_password":
            if temporary_password:
                validate_password(temporary_password, user)
                user.set_password(temporary_password)
                changed.append("password")
            elif not user.has_usable_password():
                raise ValidationError(
                    "Set a temporary password for an account without a usable password."
                )
            user.password_change_required = True
            changed.append("password_change_required")
        if action in {"reenroll_pin", "reset_password"} and user.credentials_locked:
            # The administrator replaces a published credential, so the owner must be able to
            # set the next one; the account stops being a shared demonstration account.
            user.credentials_locked = False
            changed.append("credentials_locked")
        user.management_revision += 1
        user.session_epoch += 1
        user.full_clean()
        user.save(update_fields=changed)
        return _record(actor, user, f"account.{action}", before, reason, signer_state)


@sensitive_variables()
def change_own_password(*, actor, current_password, password, reason):
    from .authentication import confirm_password

    reason_required(reason)
    # Commits the failure count or the reset first, so refusing the new password cannot undo it.
    verified = confirm_password(actor, current_password)
    if verified is None:
        raise PermissionDenied("Current password was not accepted.")
    with transaction.atomic():
        account_lock()
        user = get_user_model().objects.select_for_update().get(pk=actor.pk)
        if not user.is_active or user.password != verified:  # Changed since the confirmation.
            raise PermissionDenied("Current password was not accepted.")
        if user.credentials_locked:
            raise PermissionDenied(CREDENTIALS_LOCKED)
        validate_password(password, user)
        if user.check_password(password):
            raise ValidationError("Choose a different password.")
        before = safe_snapshot(user)
        user.set_password(password)
        user.password_change_required = False
        user.management_revision += 1
        user.session_epoch += 1
        user.save(
            update_fields=[
                "password",
                "password_change_required",
                "management_revision",
                "session_epoch",
            ]
        )
        record_event(
            actor=user,
            obj=user,
            action="account.password_changed",
            before=before,
            after=safe_snapshot(user),
            reason=reason,
        )
    return user


@transaction.atomic
def lock_credentials(*, actor, users, reason):
    """Stop shared demonstration accounts changing their own password and PIN.

    For accounts whose credentials are about to be published in the sign-in announcement. An
    administrator's forced password reset or PIN re-enrollment ends the lock.
    """
    require_role(actor, "admin")
    reason_required(reason)
    account_lock()
    locked = (
        get_user_model()
        .objects.select_for_update()
        .filter(pk__in=[user.pk for user in users], credentials_locked=False)
        .order_by("pk")
    )
    for user in locked:
        before = safe_snapshot(user)
        user.credentials_locked = True
        user.management_revision += 1
        user.save(update_fields=["credentials_locked", "management_revision"])
        record_event(
            actor=actor,
            obj=user,
            action="account.credentials_locked",
            before=before,
            after=safe_snapshot(user),
            reason=reason,
        )
