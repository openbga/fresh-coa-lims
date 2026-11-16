"""One operational log line per sign-in, failed attempt and sign-out, and per second-factor step.

The lines go to standard output, not the database, so they outlive database resets and follow the
deployment's log retention. They name the account (only when it exists, so text typed into the
username field is never written) and the platform request ID, which joins the line to the
platform's own request log and its client address. Passwords are never logged.
"""

import logging
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

logger = logging.getLogger("openbga.signin")
REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


def _request_id(request):
    """Render's per-request ID; header text is accepted only in its expected shape."""
    value = request.META.get("HTTP_RNDR_ID", "") if request is not None else ""
    return value if REQUEST_ID.fullmatch(value) else "-"


def _log(event, username, request):
    logger.info("%s user=%s request_id=%s", event, username, _request_id(request))


@receiver(user_logged_in, dispatch_uid="oq_signin_log_success")
def log_sign_in(sender, request, user, **kwargs):
    _log("signin.success", user.get_username(), request)


@receiver(user_login_failed, dispatch_uid="oq_signin_log_failure")
def log_sign_in_failure(sender, credentials, request=None, **kwargs):
    users = get_user_model()
    username = credentials.get(users.USERNAME_FIELD, credentials.get("username"))
    known = isinstance(username, str) and (
        users._default_manager.filter(**{users.USERNAME_FIELD: username}).exists()
    )
    _log("signin.failed", username if known else "<unknown>", request)


@receiver(user_logged_out, dispatch_uid="oq_signin_log_signout")
def log_sign_out(sender, request, user, **kwargs):
    if user is not None:
        _log("signout", user.get_username(), request)


def log_second_factor_requested(user, request):
    """The password was accepted; the sign-in waits for the authenticator or a recovery code."""
    _log("signin.second_factor_requested", user.get_username(), request)


def log_second_factor_failed(pending, request):
    """A refused second factor; the pending sign-in names an existing account."""
    users = get_user_model()
    username = (
        users._default_manager.filter(pk=pending.get("user"))
        .values_list(users.USERNAME_FIELD, flat=True)
        .first()
    )
    _log("signin.second_factor_failed", username or "<unknown>", request)


def log_passkey_failed(assertion, request):
    """A refused security key or passkey without the password; names the account only when the
    answer came from one of its keys (key_owner), never text from the request."""
    from .security_keys import key_owner

    users = get_user_model()
    owner = key_owner(assertion)
    username = (
        users._default_manager.filter(pk=owner).values_list(users.USERNAME_FIELD, flat=True).first()
        if owner is not None
        else None
    )
    _log("signin.passkey_failed", username or "<unknown>", request)


def log_single_sign_on_failed(found, request, reason):
    """A refused or expired answer from the identity provider, or an identity that cannot sign
    in. Names the laboratory account only when the identity is linked to one; never the
    provider's claims or text from the request."""
    from .models import SingleSignOnLink

    username = None
    if found is not None:
        username = (
            SingleSignOnLink.objects.filter(issuer=found.issuer, subject=found.subject)
            .values_list("user__username", flat=True)
            .first()
        )
    logger.info(
        "signin.single_sign_on_failed reason=%s user=%s request_id=%s",
        reason,
        username or "<unknown>",
        _request_id(request),
    )
