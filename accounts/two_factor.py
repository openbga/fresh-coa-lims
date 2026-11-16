"""Two-factor sign-in: an authenticator app (TOTP, RFC 6238), security keys and passkeys (Web
Authentication, see accounts.security_keys) and one-time recovery codes.

Once an account has a confirmed authenticator or a security key, an accepted password no longer
signs it in: the sign-in waits for a current code from the app, an answer from one of the
account's keys or an unused recovery code. A wrong code or a refused key answer counts
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
import logging
import re
import secrets
from base64 import b32encode
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Value
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.html import escape
from django.views.decorators.debug import sensitive_variables
from django_otp.plugins.otp_totp.models import TOTPDevice
from webauthn.helpers import bytes_to_base64url

from core.audit import record_event

from .authentication import (
    confirm_password,
    password_locked,
    record_password_failure,
    reset_password_failures,
)
from .models import LoginThrottle, RecoveryCode, SecurityKey
from .security_keys import KEY_LIMIT, KeyAssertion, KeyRefused

logger = logging.getLogger(__name__)

DEVICE_NAME = "Authenticator app"
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 24  # Crockford base32 characters: 120 bits.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Letters people read for digits, as Crockford base32 decodes them.
_READ_AS = str.maketrans({"O": "0", "I": "1", "L": "1"})
AUTHENTICATOR_CODE = re.compile(r"[0-9]{6}")
SETUP_SECONDS = 600
# Consecutive wrong codes, across sign-in locks, after which the second factor stops working
# until an administrator resets it (NIST SP 800-63B-4 section 3.2.2 allows at most 100).
CODE_FAILURE_LIMIT = 100

CODE_REFUSED = "The code was not accepted."
KEY_REFUSED = "The security key was not accepted."
PASSKEY_UNKNOWN = (
    "This passkey or security key is not registered for an account at this address, or it was "
    "removed. Sign in with your password."
)
KEY_EXPIRED = "The security key request expired. Try again."
NAME_TAKEN = "You already have a key with this name. Choose another name."
PASSWORD_REFUSED = "Current password was not accepted."
STOPPED = (
    "Two-factor sign-in is stopped for this account after too many wrong codes or refused "
    "security keys. Ask an administrator to reset it."
)
REQUIRED = (
    "Two-factor sign-in is required for your account, so it cannot be turned off. Set up a new "
    "authenticator app instead."
)
REQUIRED_LAST = (
    "Two-factor sign-in is required for your account, and this is its only second factor. Add "
    "another security key or an authenticator app first."
)


class Concealed:
    """A secret shown once on its owner's page: templates render it, but its repr, which error
    reports and debuggers print for frame variables and template contexts, does not show it."""

    def __init__(self, value, *, html=False):
        self._value = value
        self._html = html

    def __str__(self):
        return str(self._value)

    def __html__(self):
        return str(self._value) if self._html else str(escape(self._value))

    def __iter__(self):
        return iter(self._value)

    def __len__(self):
        return len(self._value)

    def __getitem__(self, index):
        return self._value[index]

    def __repr__(self):
        return "<concealed>"


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


def has_app(user):
    return TOTPDevice.objects.filter(user_id=user.pk, confirmed=True).exists()


def has_keys(user):
    return SecurityKey.objects.filter(user_id=user.pk).exists()


def enabled(user):
    """A confirmed authenticator app or at least one security key."""
    return has_app(user) or has_keys(user)


def missing(user):
    """Required for the account but not set up: the workspace stays closed until it is."""
    return required(user) and not enabled(user)


def stopped(user):
    """Too many consecutive wrong codes: no code is accepted until an administrator resets it."""
    return LoginThrottle.objects.filter(
        user_id=user.pk, code_failures__gte=CODE_FAILURE_LIMIT
    ).exists()


def snapshot(user):
    """The second-factor state recorded in account audit values; never a secret."""
    return {
        "two_factor": enabled(user),
        "two_factor_stopped": stopped(user),
        "recovery_codes_left": RecoveryCode.objects.filter(user_id=user.pk, used_at=None).count(),
        "authenticator_app": has_app(user),
        "security_keys": SecurityKey.objects.filter(user_id=user.pk).count(),
    }


def status(user):
    device = authenticator(user)
    keys = list(SecurityKey.objects.filter(user_id=user.pk).order_by("created_at", "pk"))
    on = device is not None or bool(keys)
    started = [k.created_at for k in keys] + ([device.created_at] if device else [])
    return {
        "enabled": on,
        "since": min(started, default=None),
        "app": device is not None,
        "app_since": device.created_at if device else None,
        "last_used_at": device.last_used_at if device else None,
        "keys": keys,
        "key_limit": KEY_LIMIT,
        "recovery_codes_left": RecoveryCode.objects.filter(user_id=user.pk, used_at=None).count(),
        "required": required(user),
        "stopped": on and stopped(user),
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
def _accept(user, device, code, *, purpose):
    """Check a code against the locked device and the account's unused recovery codes, or a key's
    answer (KeyAssertion) against the account's keys.

    Runs inside the caller's transaction with the account and the device locked. Returns the
    factor used ('totp', 'recovery_code' or 'security_key') or None. A used recovery code is
    marked and recorded.
    """
    factor = _match(user, device, code, purpose)
    if factor is not None:
        LoginThrottle.objects.filter(user_id=user.pk, code_failures__gt=0).update(code_failures=0)
    return factor


def _expired(code, seconds):
    """A key's answer to a ceremony older than seconds, or to another challenge than the
    ceremony's current one (a second tab, a reload, a repeated send): refused without
    counting, since a key's answer cannot be guessed."""
    from .security_keys import answers_ceremony

    if not isinstance(code, KeyAssertion):
        return False
    if not answers_ceremony(code):
        return True
    try:
        issued = float(code.ceremony["issued"])
    except KeyError, TypeError, ValueError:
        return False  # Malformed: refused and counted by the check itself.
    return timezone.now().timestamp() - issued > seconds


def _refused(code):
    return KEY_REFUSED if isinstance(code, KeyAssertion) else CODE_REFUSED


@sensitive_variables()
def _match(user, device, code, purpose):
    from .security_keys import verify_assertion

    if isinstance(code, KeyAssertion):
        try:
            verify_assertion(user, code, purpose=purpose)
        except KeyRefused:
            return None
        return "security_key"
    kind, value = code_kind(code)
    if kind == "totp":
        return "totp" if device is not None and device.verify_token(value) else None
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


def _count_wrong_code(user, *, second_factor=True):
    """Count a wrong code inside the caller's transaction, while the account row is still locked,
    so parallel attempts are counted one after another and none passes a limit unchecked. The
    caller lets that transaction commit and raises the refusal after it.

    Every wrong code counts toward the sign-in lock; a wrong code for the account's confirmed
    authenticator also counts toward CODE_FAILURE_LIMIT.
    """
    record_password_failure(user)
    if second_factor:
        with transaction.atomic():
            LoginThrottle.objects.get_or_create(user_id=user.pk)
            throttle = LoginThrottle.objects.select_for_update().get(user_id=user.pk)
            throttle.code_failures += 1
            throttle.save(update_fields=["code_failures"])
            if throttle.code_failures == CODE_FAILURE_LIMIT:
                logger.warning(
                    "Two-factor sign-in stopped for account id %s after %s wrong codes.",
                    user.pk,
                    CODE_FAILURE_LIMIT,
                )
                record_event(
                    actor=user,
                    action="account.two_factor_stopped",
                    obj=user,
                    after=snapshot(user),
                    reason=f"{CODE_FAILURE_LIMIT} consecutive wrong codes; an administrator "
                    "must reset two-factor sign-in.",
                )


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
        if device is None and not has_keys(user):
            raise SignInRestart
        if stopped(user):
            raise ValidationError(STOPPED)
        if password_locked(user):
            # Refused without counting, as a password is during a lock.
            raise ValidationError(_refused(code))
        if _expired(code, settings.MFA_PENDING_SECONDS):
            raise ValidationError(KEY_EXPIRED)
        factor = _accept(user, device, code, purpose="sign_in")
        if factor is None:
            _count_wrong_code(user)
    if factor is None:
        raise ValidationError(_refused(code))
    return user, factor


@sensitive_variables()
def complete_passkey_sign_in(assertion):
    """Sign in with a security key or passkey alone, without the password; returns the user.

    The key must verify its holder (its PIN, fingerprint or face), so it stands for both
    factors. The account is the one whose key has the answer's credential ID; the answer must
    carry that account's user handle. While the account is locked or its second factor is
    stopped even a valid answer is refused. A refused answer is not counted: a key's signature
    cannot be guessed and the key checks the PIN or biometric itself, while anyone who has seen
    a key's credential ID (it is public to whoever passed the password step) could otherwise
    send unsigned answers to lock the account and stop its second factor without its password.
    Raises ValidationError when refused.
    """
    from .security_keys import PASSKEY, key_owner, verify_assertion

    if connection.in_atomic_block:
        raise RuntimeError("Check sign-in answers outside an enclosing transaction.")
    if _expired(assertion, settings.MFA_PENDING_SECONDS):
        raise ValidationError(KEY_EXPIRED)
    owner = key_owner(assertion)
    if owner is None:
        raise ValidationError(PASSKEY_UNKNOWN)
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().filter(pk=owner).first()
        if user is None or not user.is_active:
            raise ValidationError(KEY_REFUSED)
        if stopped(user):
            raise ValidationError(STOPPED)
        if password_locked(user):
            raise ValidationError(KEY_REFUSED)
        if key_owner(assertion) != user.pk:
            raise ValidationError(PASSKEY_UNKNOWN)  # Removed meanwhile; removals hold this lock.
        try:
            verify_assertion(user, assertion, purpose=PASSKEY)
        except KeyRefused as exc:
            raise ValidationError(KEY_REFUSED) from exc
        LoginThrottle.objects.filter(user_id=user.pk, code_failures__gt=0).update(code_failures=0)
    return user


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
        if device is None and not has_keys(user):
            raise ValidationError("Two-factor sign-in is not set up for your account.")
        if stopped(user):
            raise ValidationError(STOPPED)
        if password_locked(user):
            raise ValidationError(_refused(code))
        if _expired(code, SETUP_SECONDS):
            raise ValidationError(KEY_EXPIRED)
        factor = _accept(user, device, code, purpose="confirm")
        if factor is None:
            _count_wrong_code(user)
    if factor is None:
        raise ValidationError(_refused(code))
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
        raise ValidationError("Confirm with a code, a recovery code or your security key.")
    verified = _reauthenticate(actor, current_password, code if replacing else None)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        if enabled(user) and not replacing:
            # Set up in another session meanwhile: replacing it needs a code from it.
            raise ValidationError("Two-factor sign-in was set up meanwhile. Start again.")
        TOTPDevice.objects.filter(user_id=user.pk, confirmed=False).delete()
        _discard_expired_setups()
        return TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=False)


def _discard_expired_setups():
    """Unconfirmed keys older than SETUP_SECONDS can no longer be confirmed; drop them."""
    since = timezone.now() - timedelta(seconds=SETUP_SECONDS)
    TOTPDevice.objects.filter(confirmed=False, created_at__lte=since).delete()


def discard_setup(user):
    """Drop the owner's unconfirmed keys that can no longer be confirmed (expired setups); a
    setup still in time, perhaps in another session, is left alone."""
    since = timezone.now() - timedelta(seconds=SETUP_SECONDS)
    TOTPDevice.objects.filter(user_id=user.pk, confirmed=False, created_at__lte=since).delete()


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
        if stopped(user):
            # A setup started before the stop must not clear it: only an administrator does.
            raise ValidationError(STOPPED)
        device = TOTPDevice.objects.select_for_update().get(pk=device_pk)
        if password_locked(user):
            raise ValidationError(CODE_REFUSED)
        accepted = kind == "totp" and device.verify_token(value)
        if not accepted:
            # A key the owner was just given is not guessed: only the sign-in lock counts this.
            _count_wrong_code(user, second_factor=False)
        else:
            before = safe_snapshot(user)
            replaced = TOTPDevice.objects.filter(user_id=user.pk, confirmed=True).exists()
            keys = has_keys(user)
            TOTPDevice.objects.filter(user_id=user.pk).exclude(pk=device.pk).delete()
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            codes = _new_recovery_codes(user, timezone.now())
            LoginThrottle.objects.filter(user_id=user.pk).update(code_failures=0)
            if replaced:
                action, reason = (
                    "account.two_factor_replaced",
                    "The owner set up a new authenticator app.",
                )
            elif keys:
                action, reason = (
                    "account.authenticator_added",
                    "The owner added an authenticator app beside their security keys.",
                )
            else:
                action, reason = (
                    "account.two_factor_enabled",
                    "The owner set up two-factor sign-in.",
                )
            _record(user, action, before, reason)
    if not accepted:
        raise ValidationError(CODE_REFUSED)
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
    """Delete the account's authenticator keys, security keys and recovery codes and clear its
    count of wrong codes (caller holds the locks)."""
    TOTPDevice.objects.filter(user_id=user.pk).delete()
    SecurityKey.objects.filter(user_id=user.pk).delete()
    RecoveryCode.objects.filter(user_id=user.pk).delete()
    LoginThrottle.objects.filter(user_id=user.pk).update(code_failures=0)


def reset(user):
    """An administrator's reset (signed in the workspace, or the operator command): remove() and
    also the organization sign-in link, because whoever linked it may have known only the
    password before the second factor was set up; the owner links again afterwards."""
    from .models import SingleSignOnLink

    remove(user)
    SingleSignOnLink.objects.filter(user_id=user.pk).delete()


def set_up_anything(user):
    """Whether an administrator reset has anything to remove: a confirmed authenticator, a
    security key or recovery codes (an unconfirmed setup changes nothing for sign-in)."""
    return enabled(user) or RecoveryCode.objects.filter(user_id=user.pk).exists() or stopped(user)


@sensitive_variables()
def begin_key_registration(*, actor, current_password, rp, code=None):
    """Confirm the owner and start registering a security key; returns the ceremony to keep in
    the session. Once two-factor sign-in is on, this needs a current second factor too."""
    from .administration import CREDENTIALS_LOCKED
    from .security_keys import UNAVAILABLE_HOST, begin, user_handle

    if actor.credentials_locked:
        raise PermissionDenied(CREDENTIALS_LOCKED)
    if rp is None:
        raise ValidationError(UNAVAILABLE_HOST)
    on = enabled(actor)
    if on and not code:
        raise ValidationError("Confirm with a code, a recovery code or your security key.")
    verified = _reauthenticate(actor, current_password, code if on else None)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        if enabled(user) and not on:
            raise ValidationError("Two-factor sign-in was set up meanwhile. Start again.")
        if SecurityKey.objects.filter(user_id=user.pk).count() >= KEY_LIMIT:
            raise ValidationError(f"An account can have at most {KEY_LIMIT} security keys.")
        ceremony = begin(rp, "register", user.pk)
        ceremony["user_handle"] = bytes_to_base64url(user_handle(user))
        ceremony["epoch"] = user.session_epoch
        return ceremony


def pending_registration(user, ceremony):
    """The session's registration ceremony for this owner, started less than SETUP_SECONDS ago
    and for the account as it still is, or None."""
    if not isinstance(ceremony, dict) or ceremony.get("user") != user.pk:
        return None
    try:
        issued = float(ceremony["issued"])
    except KeyError, TypeError, ValueError:
        return None
    if timezone.now().timestamp() - issued > SETUP_SECONDS:
        return None
    if ceremony.get("epoch") != get_user_model().objects.get(pk=user.pk).session_epoch:
        return None
    return ceremony


@sensitive_variables()
def register_key(*, actor, ceremony, response, name):
    """Store the key that answered the registration ceremony; returns (user, key, codes).

    The first second factor of an account turns two-factor sign-in on and comes with a new set
    of recovery codes (codes); a key added beside others leaves the codes as they are (None).
    """
    if connection.in_atomic_block:
        raise RuntimeError("Register keys outside an enclosing transaction.")
    from .administration import CREDENTIALS_LOCKED, account_lock, safe_snapshot
    from .security_keys import verify_registration

    with transaction.atomic():
        account_lock()
        user = get_user_model().objects.select_for_update().get(pk=actor.pk)
        if not user.is_active:
            raise PermissionDenied("This account is inactive.")
        if user.credentials_locked:
            raise PermissionDenied(CREDENTIALS_LOCKED)
        if pending_registration(user, ceremony) is None:
            raise ValidationError("Registration expired or your account changed. Start again.")
        if stopped(user):
            raise ValidationError(STOPPED)
        if password_locked(user):
            raise ValidationError(KEY_REFUSED)
        keys = SecurityKey.objects.select_for_update().filter(user_id=user.pk)
        if len(keys) >= KEY_LIMIT:
            raise ValidationError(f"An account can have at most {KEY_LIMIT} security keys.")
        # Compared as the database's unique constraint compares, with its lower().
        if keys.annotate(folded=Lower("name")).filter(folded=Lower(Value(name))).exists():
            raise ValidationError(NAME_TAKEN)
        try:
            fields = verify_registration(user, ceremony, response)
        except KeyRefused as exc:
            raise ValidationError(
                "The key's answer was not accepted. Start again; if it happens again, use "
                "another key or browser."
            ) from exc
        if SecurityKey.objects.filter(credential_id=fields["credential_id"]).exists():
            raise ValidationError("This key is already registered.")
        before = safe_snapshot(user)
        on = enabled(user)
        now = timezone.now()
        try:
            with transaction.atomic():
                key = SecurityKey.objects.create(user=user, name=name, created_at=now, **fields)
        except IntegrityError as exc:  # A name or key the checks above did not see.
            raise ValidationError(NAME_TAKEN) from exc
        codes = None
        if not on:
            codes = _new_recovery_codes(user, now)
            LoginThrottle.objects.filter(user_id=user.pk).update(code_failures=0)
        _record(
            user,
            "account.security_key_added" if on else "account.two_factor_enabled",
            before,
            f"The owner added security key {name!r}."
            if on
            else f"The owner set up two-factor sign-in with security key {name!r}.",
        )
    return user, key, codes


@sensitive_variables()
def remove_key(*, actor, current_password, code, key_pk):
    """Remove one of the owner's keys. Removing the last second factor turns two-factor sign-in
    off, which a deployment that requires it refuses."""
    from .administration import safe_snapshot

    verified = _reauthenticate(actor, current_password, code)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        key = SecurityKey.objects.select_for_update().filter(pk=key_pk, user_id=user.pk).first()
        if key is None:
            raise ValidationError("That key is no longer registered.")
        before = safe_snapshot(user)
        last = not has_app(user) and SecurityKey.objects.filter(user_id=user.pk).count() == 1
        if last:
            if required(user):
                raise PermissionDenied(REQUIRED_LAST)
            remove(user)
            _record(
                user,
                "account.two_factor_disabled",
                before,
                f"The owner removed security key {key.name!r}, their last second factor.",
            )
        else:
            key.delete()
            _record(
                user,
                "account.security_key_removed",
                before,
                f"The owner removed security key {key.name!r}.",
            )
    return user, last


@sensitive_variables()
def remove_app(*, actor, current_password, code):
    """Remove the owner's authenticator app while a security key remains."""
    from .administration import safe_snapshot

    verified = _reauthenticate(actor, current_password, code)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        if not has_app(user):
            raise ValidationError("No authenticator app is set up for your account.")
        if not has_keys(user):
            raise ValidationError(
                "The authenticator app is your only second factor. Turn off two-factor sign-in "
                "instead, or add a security key first."
            )
        before = safe_snapshot(user)
        TOTPDevice.objects.filter(user_id=user.pk).delete()
        _record(
            user,
            "account.authenticator_removed",
            before,
            "The owner removed the authenticator app; their security keys remain.",
        )
    return user
