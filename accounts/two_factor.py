"""Two-factor sign-in: an authenticator app (TOTP, RFC 6238) and one-time recovery codes.

Once an account has a confirmed authenticator, an accepted password no longer signs it in: the
sign-in waits for a current code from the app or an unused recovery code. A wrong code counts
toward the account's consecutive sign-in failures, like a wrong password, and while the account
is locked even a correct code is refused. A code from the app is accepted once: the device keeps
the time step of the last code it accepted and refuses that step and earlier ones.

The authenticator key is stored, because the server computes the same codes as the app; it is
shown only to its owner while setting up and never enters audit values, signatures or logs.
Recovery codes carry 120 random bits and only their SHA-256 digests are stored.

Every change to an account's second factor increments its management revision and session
generation, so other sessions sign in again, and writes an attributed audit event.
"""

import hashlib
import re
import secrets
from base64 import b32encode
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.audit import record_event

from .authentication import (
    confirm_password,
    password_locked,
    record_password_failure,
    reset_password_failures,
)
from .models import RecoveryCode

DEVICE_NAME = "Authenticator app"
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 24  # Crockford base32 characters: 120 bits.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Letters people read for digits, as Crockford base32 decodes them.
_READ_AS = str.maketrans({"O": "0", "I": "1", "L": "1"})
AUTHENTICATOR_CODE = re.compile(r"[0-9]{6}")
SETUP_SECONDS = 600

CODE_REFUSED = "The code was not accepted."
PASSWORD_REFUSED = "Current password was not accepted."
REQUIRED = (
    "Two-factor sign-in is required for your account, so it cannot be turned off. Set up a new "
    "authenticator app instead."
)


class SignInRestart(Exception):
    """The pending sign-in no longer matches the account; the password must be entered again."""


def required(user):
    """Whether the deployment requires a second factor for this account (MFA_REQUIRED_ROLES).

    A shared demonstration account cannot set one up and is never required to.
    """
    roles = settings.MFA_REQUIRED_ROLES
    if not roles or user.credentials_locked:
        return False
    if "all" in roles:
        return True
    return user.groups.filter(name__in=roles).exists()


def authenticator(user, *, for_update=False):
    devices = TOTPDevice.objects.filter(user_id=user.pk, confirmed=True)
    if for_update:
        devices = devices.select_for_update()
    return devices.order_by("pk").first()


def enabled(user):
    return TOTPDevice.objects.filter(user_id=user.pk, confirmed=True).exists()


def missing(user):
    """Required for the account but not set up: the workspace stays closed until it is."""
    return required(user) and not enabled(user)


def snapshot(user):
    """The second-factor state recorded in account audit values; never a secret."""
    return {
        "two_factor": enabled(user),
        "recovery_codes_left": RecoveryCode.objects.filter(user_id=user.pk, used_at=None).count(),
    }


def status(user):
    device = authenticator(user)
    return {
        "enabled": device is not None,
        "since": device.created_at if device else None,
        "last_used_at": device.last_used_at if device else None,
        "recovery_codes_left": RecoveryCode.objects.filter(user_id=user.pk, used_at=None).count(),
        "required": required(user),
    }


def code_kind(code):
    """('totp', digits), ('recovery', normalized) or (None, None) for text of neither shape."""
    text = "".join(str(code).split())
    if AUTHENTICATOR_CODE.fullmatch(text):
        return "totp", text
    normalized = text.replace("-", "").upper().translate(_READ_AS)
    if len(normalized) == RECOVERY_CODE_LENGTH and all(c in ALPHABET for c in normalized):
        return "recovery", normalized
    return None, None


def _digest(user_pk, normalized):
    return hashlib.sha256(f"openbga-recovery-code:{user_pk}:{normalized}".encode()).hexdigest()


@sensitive_variables()
def _new_recovery_codes(user, now):
    """Replace the account's recovery codes; returns the new codes for one display."""
    RecoveryCode.objects.filter(user_id=user.pk).delete()
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        codes.append("-".join(raw[i : i + 4] for i in range(0, RECOVERY_CODE_LENGTH, 4)))
    RecoveryCode.objects.bulk_create(
        [
            RecoveryCode(
                user_id=user.pk, digest=_digest(user.pk, c.replace("-", "")), created_at=now
            )
            for c in codes
        ]
    )
    return codes


@sensitive_variables()
def _accept(user, device, code):
    """Check a code against the locked device and the account's unused recovery codes.

    Runs inside the caller's transaction with the account and the device locked. Returns the
    factor used ('totp' or 'recovery_code') or None. A used recovery code is marked and recorded.
    """
    kind, value = code_kind(code)
    if kind == "totp":
        return "totp" if device.verify_token(value) else None
    if kind == "recovery":
        entry = (
            RecoveryCode.objects.select_for_update()
            .filter(user_id=user.pk, digest=_digest(user.pk, value), used_at=None)
            .first()
        )
        if entry is None:
            return None
        entry.used_at = timezone.now()
        entry.save(update_fields=["used_at"])
        record_event(
            actor=user,
            action="account.recovery_code_used",
            obj=user,
            after=snapshot(user),
            reason="A recovery code was used in place of the authenticator code.",
        )
        return "recovery_code"
    return None


def _refuse(user, message=CODE_REFUSED):
    """Count the failed code in its own transaction, so the refusal cannot roll it back."""
    record_password_failure(user)
    raise ValidationError(message)


def begin_sign_in(user):
    """What the session keeps between an accepted password and the second factor."""
    return {
        "user": user.pk,
        "backend": user.backend,
        "epoch": user.session_epoch,
        "auth_hash": user.get_session_auth_hash(),
        "started": timezone.now().timestamp(),
    }


@sensitive_variables()
def complete_sign_in(pending, code):
    """Check the second factor of a pending sign-in; returns (user, factor).

    Raises SignInRestart when the pending sign-in expired or the account changed since the
    password was accepted, and ValidationError when the code is refused (counted as a failure).
    """
    if connection.in_atomic_block:
        raise RuntimeError("Check sign-in codes outside an enclosing transaction.")
    try:
        started = float(pending["started"])
        user_pk, epoch, auth_hash = int(pending["user"]), pending["epoch"], pending["auth_hash"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SignInRestart from exc
    if timezone.now().timestamp() - started > settings.MFA_PENDING_SECONDS:
        raise SignInRestart
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().filter(pk=user_pk).first()
        if (
            user is None
            or not user.is_active
            or user.session_epoch != epoch
            or not isinstance(auth_hash, str)
            or not constant_time_compare(user.get_session_auth_hash(), auth_hash)
        ):
            raise SignInRestart
        device = authenticator(user, for_update=True)
        if device is None:
            raise SignInRestart
        if password_locked(user):
            # Refused without counting, as a password is during a lock.
            raise ValidationError(CODE_REFUSED)
        factor = _accept(user, device, code)
    if factor is None:
        _refuse(user)
    return user, factor


@sensitive_variables()
def _reauthenticate(actor, current_password, code=None):
    """Confirm the owner's password and, when given, a current second-factor code.

    Each check commits its failure count before the change runs. When a code is checked, the
    count is reset only once both pass, so a known password cannot clear the count between
    guessed codes. Returns the verified password hash, which the change rechecks under its own
    lock.
    """
    if connection.in_atomic_block:
        raise RuntimeError("Confirm credentials outside an enclosing transaction.")
    verified = confirm_password(actor, current_password, reset=code is None)
    if verified is None:
        raise PermissionDenied(PASSWORD_REFUSED)
    if code is None:
        return verified
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=actor.pk)
        device = authenticator(user, for_update=True)
        if device is None:
            raise ValidationError("Two-factor sign-in is not set up for your account.")
        if password_locked(user):
            raise ValidationError(CODE_REFUSED)
        factor = _accept(user, device, code)
    if factor is None:
        _refuse(user)
    reset_password_failures(user)
    return verified


def _lock_owner(actor, verified):
    from .administration import CREDENTIALS_LOCKED, account_lock

    account_lock()
    user = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not user.is_active or user.password != verified:  # Changed since the confirmation.
        raise PermissionDenied(PASSWORD_REFUSED)
    if user.credentials_locked:
        raise PermissionDenied(CREDENTIALS_LOCKED)
    return user


def _record(user, action, before, reason, *, sessions=True):
    from .administration import safe_snapshot

    user.management_revision += 1
    fields = ["management_revision"]
    if sessions:
        user.session_epoch += 1
        fields.append("session_epoch")
    user.save(update_fields=fields)
    record_event(
        actor=user, obj=user, action=action, before=before, after=safe_snapshot(user), reason=reason
    )


@sensitive_variables()
def begin_setup(*, actor, current_password, code=None):
    """Make a new, unconfirmed authenticator key for the owner to add to their app.

    Replacing a confirmed authenticator also needs a current code from it or a recovery code.
    Nothing changes for sign-in until the new key is confirmed with a code it produces.
    """
    from .administration import CREDENTIALS_LOCKED

    if actor.credentials_locked:
        raise PermissionDenied(CREDENTIALS_LOCKED)
    replacing = enabled(actor)
    if replacing and not code:
        raise ValidationError("Enter a code from your authenticator app or a recovery code.")
    verified = _reauthenticate(actor, current_password, code if replacing else None)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        if enabled(user) and not replacing:
            # Set up in another session meanwhile: replacing it needs a code from it.
            raise ValidationError("Two-factor sign-in was set up meanwhile. Start again.")
        TOTPDevice.objects.filter(user_id=user.pk, confirmed=False).delete()
        return TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=False)


def pending_setup(user, device_pk):
    """The owner's unconfirmed key started less than SETUP_SECONDS ago, or None."""
    if not isinstance(device_pk, int):
        return None
    since = timezone.now() - timedelta(seconds=SETUP_SECONDS)
    return TOTPDevice.objects.filter(
        pk=device_pk, user_id=user.pk, confirmed=False, created_at__gt=since
    ).first()


def secret_key(device):
    """The key in the base32 form authenticator apps accept, in groups of four."""
    text = b32encode(device.bin_key).decode().rstrip("=")
    return " ".join(text[i : i + 4] for i in range(0, len(text), 4))


@sensitive_variables()
def confirm_setup(*, actor, device_pk, code):
    """Confirm the new key with a code from the app; returns (user, recovery codes).

    The new key replaces any earlier authenticator, and a new set of recovery codes replaces
    the old one. A wrong code counts as a failed sign-in attempt.
    """
    if connection.in_atomic_block:
        raise RuntimeError("Confirm setup outside an enclosing transaction.")
    from .administration import CREDENTIALS_LOCKED, account_lock, safe_snapshot

    kind, value = code_kind(code)
    with transaction.atomic():
        account_lock()
        user = get_user_model().objects.select_for_update().get(pk=actor.pk)
        if not user.is_active:
            raise PermissionDenied("This account is inactive.")
        if user.credentials_locked:
            raise PermissionDenied(CREDENTIALS_LOCKED)
        if pending_setup(user, device_pk) is None:
            raise ValidationError("Setup expired. Start again.")
        device = TOTPDevice.objects.select_for_update().get(pk=device_pk)
        if password_locked(user):
            raise ValidationError(CODE_REFUSED)
        accepted = kind == "totp" and device.verify_token(value)
        if accepted:
            before = safe_snapshot(user)
            replaced = TOTPDevice.objects.filter(user_id=user.pk, confirmed=True).exists()
            TOTPDevice.objects.filter(user_id=user.pk).exclude(pk=device.pk).delete()
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            codes = _new_recovery_codes(user, timezone.now())
            _record(
                user,
                "account.two_factor_replaced" if replaced else "account.two_factor_enabled",
                before,
                "The owner set up a new authenticator app."
                if replaced
                else "The owner set up two-factor sign-in.",
            )
    if not accepted:
        _refuse(user)
    return user, codes


@sensitive_variables()
def replace_recovery_codes(*, actor, current_password, code):
    """A new set of recovery codes; the old ones stop working. Returns (user, codes)."""
    from .administration import safe_snapshot

    verified = _reauthenticate(actor, current_password, code)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        if not enabled(user):
            raise ValidationError("Two-factor sign-in is not set up for your account.")
        before = safe_snapshot(user)
        codes = _new_recovery_codes(user, timezone.now())
        _record(
            user,
            "account.recovery_codes_replaced",
            before,
            "The owner replaced the recovery codes.",
            sessions=False,
        )
    return user, codes


@sensitive_variables()
def disable(*, actor, current_password, code):
    """Turn two-factor sign-in off for the owner, unless the deployment requires it."""
    from .administration import safe_snapshot

    if required(actor):
        raise PermissionDenied(REQUIRED)
    verified = _reauthenticate(actor, current_password, code)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        if required(user):
            raise PermissionDenied(REQUIRED)
        if not enabled(user):
            raise ValidationError("Two-factor sign-in is not set up for your account.")
        before = safe_snapshot(user)
        remove(user)
        _record(
            user, "account.two_factor_disabled", before, "The owner turned off two-factor sign-in."
        )
    return user


def remove(user):
    """Delete the account's authenticator keys and recovery codes (caller holds the locks)."""
    TOTPDevice.objects.filter(user_id=user.pk).delete()
    RecoveryCode.objects.filter(user_id=user.pk).delete()


def set_up_anything(user):
    """Whether an administrator reset has anything to remove."""
    return (
        TOTPDevice.objects.filter(user_id=user.pk).exists()
        or RecoveryCode.objects.filter(user_id=user.pk).exists()
    )
