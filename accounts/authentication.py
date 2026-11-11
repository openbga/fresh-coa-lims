"""Password throttling on top of Django's ModelBackend.

Consecutive failed password checks for an existing account are counted in PostgreSQL. Reaching
the limit locks password authentication for that account for a fixed period; while locked, even
the correct password is refused with the same message as a wrong one. Usernames that do not exist
are not stored. Submitted passwords are never stored or logged.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .models import LoginThrottle

logger = logging.getLogger(__name__)


def password_locked(user):
    return LoginThrottle.objects.filter(user_id=user.pk, locked_until__gt=timezone.now()).exists()


def record_password_failure(user):
    """Count one failed password check; callers must not roll this back with the request."""
    now = timezone.now()
    with transaction.atomic():
        LoginThrottle.objects.get_or_create(user_id=user.pk)
        throttle = LoginThrottle.objects.select_for_update().get(user_id=user.pk)
        if throttle.locked_until and throttle.locked_until > now:
            return  # Attempts during a lock are refused without extending it.
        throttle.failures += 1
        if throttle.failures >= settings.LOGIN_FAILURE_LIMIT:
            throttle.failures = 0
            throttle.locked_until = now + timedelta(seconds=settings.LOGIN_LOCK_SECONDS)
            logger.warning(
                "Password sign-in locked for account id %s after repeated failures.", user.pk
            )
        throttle.save(update_fields=["failures", "locked_until"])


def reset_password_failures(user):
    """A correct password ends the consecutive-failure run (same row lock as a failure)."""
    with transaction.atomic():
        throttle = LoginThrottle.objects.select_for_update().filter(user_id=user.pk).first()
        if throttle is not None and throttle.failures:
            throttle.failures = 0
            throttle.save(update_fields=["failures"])


@sensitive_variables()
def confirm_password(user, password):
    """Re-authenticate a signed-in owner, sharing the sign-in failure counter and lock.

    Runs in a transaction of its own, so the failure count or the success reset commits before,
    and regardless of, the requested change; callers invoke it outside any transaction. Returns
    the verified password hash, which the caller rechecks under its own lock because the account
    may change in between, or None when refused.
    """
    with transaction.atomic():
        account = get_user_model().objects.select_for_update().get(pk=user.pk)
        if not account.is_active:
            return None
        if password_locked(account):
            account.check_password(password)  # Keep timing comparable with an ordinary refusal.
            return None
        if not account.check_password(password):
            record_password_failure(account)
            return None
        reset_password_failures(account)
        return account.password


class ThrottledModelBackend(ModelBackend):
    @sensitive_variables()
    def authenticate(self, request, username=None, password=None, **kwargs):
        # The password check always runs, so a lock does not change response timing.
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is not None and password_locked(user):
            # PermissionDenied stops any later backend from accepting the same credentials.
            raise PermissionDenied
        return user


@receiver(user_login_failed, dispatch_uid="oq_password_failure")
def count_login_failure(sender, credentials, request=None, **kwargs):
    users = get_user_model()
    username = credentials.get(users.USERNAME_FIELD, credentials.get("username"))
    if not isinstance(username, str):
        return
    user = users._default_manager.filter(**{users.USERNAME_FIELD: username}).first()
    if user is not None:
        record_password_failure(user)


@receiver(user_logged_in, dispatch_uid="oq_password_success")
def reset_login_failures(sender, request, user, **kwargs):
    reset_password_failures(user)
