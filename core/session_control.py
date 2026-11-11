"""HTTP session limits and signing identity context; domain APIs remain request-independent."""

from contextvars import ContextVar

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.db import transaction
from django.dispatch import receiver
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .audit import record_event

current_request = ContextVar("signing_request", default=None)


@receiver(user_logged_in, dispatch_uid="oq_session_started")
def session_started(sender, request, user, **kwargs):
    now = timezone.now().timestamp()
    request.session["authenticated_at"] = now
    request.session["last_activity_at"] = now
    request.session["account_epoch"] = (
        get_user_model().objects.values_list("session_epoch", flat=True).get(pk=user.pk)
    )


class ControlledSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = timezone.now().timestamp()
            started = request.session.get("authenticated_at")
            last = request.session.get("last_activity_at")
            if not isinstance(started, (int, float)) or not isinstance(last, (int, float)):
                expired = True
            else:
                expired = (
                    now - last >= settings.SESSION_IDLE_SECONDS
                    or now - started >= settings.SESSION_ABSOLUTE_SECONDS
                )
            revoked = request.session.get("account_epoch") != request.user.session_epoch
            if expired or revoked:
                with transaction.atomic():
                    record_event(
                        actor=request.user,
                        action="session.revoked" if revoked else "session.expired",
                        obj=request.user,
                        reason="Account security changed; session revoked."
                        if revoked
                        else "Controlled session idle or absolute lifetime exceeded.",
                    )
                logout(request)
                messages.info(
                    request,
                    "Your account security changed. Sign in again to continue."
                    if revoked
                    else "Your session expired. Sign in again to continue.",
                )
            elif request.path not in ("/health/", "/ready/"):
                request.session["last_activity_at"] = now
        token = current_request.set(request)
        try:
            if (
                request.user.is_authenticated
                and request.user.password_change_required
                and request.path
                not in {
                    reverse("accounts:password_change"),
                    reverse("logout"),
                    reverse("pagedocs:doc"),
                    "/health/",
                    "/ready/",
                }
            ):
                response = redirect("accounts:password_change")
            else:
                response = self.get_response(request)
            if request.user.is_authenticated:
                response["Cache-Control"] = "no-store, private"
            return response
        finally:
            current_request.reset(token)


def signing_context(actor):
    request = current_request.get()
    if request is None:
        return {"channel": "trusted-service", "components": ["pin"]}
    if request.method != "POST" or not request.user.is_authenticated or request.user.pk != actor.pk:
        raise ValidationError("Sign in again before signing.")
    if (
        request.session.get("account_epoch") != actor.session_epoch
        or actor.password_change_required
    ):
        raise ValidationError(
            "Account security changed. Sign in and change your password if required."
        )
    if request.POST.get("signature_username", "") != actor.get_username():
        with transaction.atomic():
            record_event(
                actor=actor,
                action="signature.identity_denied",
                obj=actor,
                reason="Signing identification code did not match authenticated account.",
            )
        raise ValidationError("Enter your own signing username and PIN.")
    now = timezone.now().timestamp()
    started = request.session.get("authenticated_at", 0)
    last = request.session.get("last_activity_at", 0)
    if (
        now - started >= settings.SESSION_ABSOLUTE_SECONDS
        or now - last >= settings.SESSION_IDLE_SECONDS
    ):
        raise ValidationError("Session expired. Sign in again before signing.")
    return {"channel": "web", "components": ["username", "pin"], "authenticated_at": started}
