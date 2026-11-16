"""Single sign-on with the organization's identity provider (OpenID Connect).

The deployment registers this site as a confidential client at one provider (OIDC_ISSUER). Sign-in
uses the authorization code flow with PKCE (RFC 7636), a state value bound to the session and a
nonce bound to the ID token. The ID token must be signed with an asymmetric algorithm by a key in
the provider's published key set and name this provider as issuer, this client as audience, a
subject and current times (OpenID Connect Core 1.0 section 3.1.3.7).

The provider identifies a person by issuer and subject, the only claims the specification makes
stable. An account signs in this way only once its owner has linked it: the owner confirms the
password (and a second factor, when two-factor sign-in is on) and then authenticates at the
provider. No account is created or given roles from the provider. A sign-in through the provider
stands for the password: the account's own second factor, when it has one, is still asked, and
the PIN is still entered for every signature.

Linking and unlinking advance the account revision and session generation and write attributed
audit events; an administrator removes another account's link with a reason and a signature.
"""

import logging
import re
import secrets
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables

from .models import SingleSignOnLink

logger = logging.getLogger(__name__)

# Seconds between leaving for the provider and coming back with its answer.
PENDING_SECONDS = 600
LEEWAY_SECONDS = 60
# Asymmetric signature algorithms only: a symmetric one would make the client secret a signing
# key. RS256 is the algorithm every provider must support (OpenID Connect Core section 15.1).
SIGNING_ALGORITHMS = (
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
)
ERROR_CODE = re.compile(r"[a-z_]{1,64}")
LABEL_CLAIMS = ("preferred_username", "email", "name")
LABEL_LIMIT = 254

UNAVAILABLE = "The organization's sign-in service could not be reached. Try again later."
EXPIRED = "The sign-in with your organization expired or was already used. Try again."
REFUSED = "The answer from your organization's sign-in service was not accepted. Try again."
NOT_LINKED = (
    "This organization account is not linked to a laboratory account. Sign in with your "
    "password, then link it on Organization sign-in under Account access."
)
CANNOT_SIGN_IN = (
    "The laboratory account linked to this organization account cannot sign in. Ask your "
    "laboratory administrator."
)
PAUSED = (
    "Sign-in to this laboratory account is paused after repeated failed attempts. Try again later."
)
LINKED_ELSEWHERE = "This organization account is already linked to another laboratory account."
ALREADY_LINKED = "Your account is already linked to an organization account. Unlink it first."
NOT_YOURS = "Linking started in another session or for another account. Start again."
CHANGED = "Your account security changed since you confirmed your password. Start again."


class ProviderUnavailable(Exception):
    """The provider's configuration or keys could not be fetched."""


class Refused(Exception):
    """The provider's answer was refused; the message is safe to show."""


@dataclass(frozen=True)
class Identity:
    issuer: str
    subject: str
    label: str


def configured():
    return settings.SINGLE_SIGN_ON


def provider_name():
    return settings.OIDC_PROVIDER_NAME


@lru_cache(maxsize=4)
def _client(issuer, client_id, client_secret, scopes, auth_method):
    from authlib.integrations.django_client import OAuth

    oauth = OAuth()
    return oauth.register(
        name="organization",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=issuer.rstrip("/") + "/.well-known/openid-configuration",
        client_kwargs={
            "scope": " ".join(scopes),
            "code_challenge_method": "S256",
            "token_endpoint_auth_method": auth_method,
            "default_timeout": settings.OIDC_TIMEOUT_SECONDS,
        },
    )


def client():
    """The provider's client, with its discovery document loaded and checked (once a process)."""
    app = _client(
        settings.OIDC_ISSUER,
        settings.OIDC_CLIENT_ID,
        settings.OIDC_CLIENT_SECRET,
        tuple(settings.OIDC_SCOPES),
        settings.OIDC_TOKEN_AUTH_METHOD,
    )
    try:
        metadata = app.load_server_metadata()
    except Exception as exc:
        # Not cached: the next attempt fetches again.
        app.server_metadata.pop("_loaded_at", None)
        logger.warning("Single sign-on discovery failed: %s", type(exc).__name__)
        raise ProviderUnavailable from exc
    if not metadata.get("_checked"):
        # The document must name the issuer it was fetched for (OpenID Connect Discovery 1.0
        # section 4.3), and the client uses only the endpoints it needs from it.
        if (
            metadata.get("issuer") != settings.OIDC_ISSUER
            or not isinstance(metadata.get("authorization_endpoint"), str)
            or not isinstance(metadata.get("token_endpoint"), str)
            or not isinstance(metadata.get("jwks_uri"), str)
        ):
            app.server_metadata.clear()
            logger.warning("Single sign-on discovery document does not match OIDC_ISSUER.")
            raise ProviderUnavailable
        offered = metadata.get("id_token_signing_alg_values_supported") or ["RS256"]
        allowed = [alg for alg in SIGNING_ALGORITHMS if alg in offered] or ["RS256"]
        metadata["id_token_signing_alg_values_supported"] = allowed
        metadata["_checked"] = True
    return app


def begin(purpose, redirect_uri, **context):
    """Start a sign-in or a link at the provider; returns (provider URL, pending state).

    The caller keeps the pending state in the session and sends the browser to the URL.
    """
    app = client()
    extra = {"prompt": settings.OIDC_PROMPT} if settings.OIDC_PROMPT else {}
    created = app.create_authorization_url(
        redirect_uri, state=secrets.token_urlsafe(32), nonce=secrets.token_urlsafe(32), **extra
    )
    pending = {
        "purpose": purpose,
        "state": created["state"],
        "nonce": created["nonce"],
        "code_verifier": created["code_verifier"],
        "redirect_uri": redirect_uri,
        "started": timezone.now().timestamp(),
        **context,
    }
    return created["url"], pending


def answered(pending, params):
    """Whether the provider's answer is for this pending request and still in time."""
    if not isinstance(pending, dict):
        return False
    state = params.get("state")
    try:
        started = float(pending["started"])
    except KeyError, TypeError, ValueError:
        return False
    return (
        isinstance(state, str)
        and isinstance(pending.get("state"), str)
        and constant_time_compare(state, pending["state"])
        and 0 <= timezone.now().timestamp() - started <= PENDING_SECONDS
    )


@sensitive_variables()
def identity(pending, params):
    """Exchange the provider's code for an ID token and validate it; returns the Identity.

    Raises Refused with a message to show, or ProviderUnavailable.
    """
    error = params.get("error")
    if error:
        code = error if ERROR_CODE.fullmatch(error) else "invalid"
        logger.info("Single sign-on answered with error %s.", code)
        if code in {"access_denied", "login_required", "interaction_required"}:
            raise Refused("Sign-in at your organization was cancelled or not completed.")
        raise Refused(REFUSED)
    # RFC 9207: when the provider names itself in the answer, it must be this provider.
    issuer = params.get("iss")
    if issuer is not None and issuer != settings.OIDC_ISSUER:
        logger.warning("Single sign-on answer names another issuer.")
        raise Refused(REFUSED)
    code = params.get("code")
    if not isinstance(code, str) or not code or len(code) > 4096:
        raise Refused(REFUSED)
    app = client()
    try:
        token = app.fetch_access_token(
            redirect_uri=pending["redirect_uri"],
            code=code,
            code_verifier=pending["code_verifier"],
        )
    except Exception as exc:
        logger.warning("Single sign-on token request refused: %s", type(exc).__name__)
        raise Refused(REFUSED) from exc
    if not isinstance(token, dict) or not isinstance(token.get("id_token"), str):
        logger.warning("Single sign-on token response has no ID token.")
        raise Refused(REFUSED)
    try:
        claims = app.parse_id_token(
            token,
            nonce=pending["nonce"],
            claims_options={
                "iss": {"essential": True, "value": settings.OIDC_ISSUER},
                "aud": {"essential": True, "value": settings.OIDC_CLIENT_ID},
                "sub": {"essential": True},
                "exp": {"essential": True},
                "iat": {"essential": True},
                "nonce": {"essential": True},
            },
            leeway=LEEWAY_SECONDS,
        )
    except Exception as exc:
        logger.warning("Single sign-on ID token refused: %s", type(exc).__name__)
        raise Refused(REFUSED) from exc
    subject = claims.get("sub") if claims else None
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise Refused(REFUSED)
    label = next(
        (claims[c] for c in LABEL_CLAIMS if isinstance(claims.get(c), str) and claims[c].strip()),
        subject,
    )
    return Identity(settings.OIDC_ISSUER, subject, label.strip()[:LABEL_LIMIT])


def link_of(user):
    return SingleSignOnLink.objects.filter(user_id=user.pk).first()


def status(user):
    link = link_of(user)
    return {
        "link": link,
        "current": link is not None and link.issuer == settings.OIDC_ISSUER,
    }


def sign_in(found):
    """The account linked to this identity, ready to sign in; raises ValidationError.

    A refusal is not counted toward the account's lock: the provider authenticated the person,
    and nothing here can be guessed.
    """
    if connection.in_atomic_block:
        raise RuntimeError("Sign in outside an enclosing transaction.")
    from .authentication import password_locked

    owner = (
        SingleSignOnLink.objects.filter(issuer=found.issuer, subject=found.subject)
        .values_list("user_id", flat=True)
        .first()
    )
    if owner is None:
        raise ValidationError(NOT_LINKED)
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().filter(pk=owner).first()
        link = (
            SingleSignOnLink.objects.select_for_update()
            .filter(issuer=found.issuer, subject=found.subject, user_id=owner)
            .first()
        )
        if user is None or link is None:
            raise ValidationError(NOT_LINKED)  # Unlinked meanwhile.
        if not user.is_active:
            raise ValidationError(CANNOT_SIGN_IN)
        if password_locked(user):
            raise ValidationError(PAUSED)
        link.last_used_at = timezone.now()
        link.save(update_fields=["last_used_at"])
    return user


def link(*, actor, pending, found):
    """Link the owner's account to the identity the provider returned; returns the user.

    pending is the session's link request, made after the owner confirmed the password (and a
    second factor); it must be for this account as it still is.
    """
    from .administration import CREDENTIALS_LOCKED, account_lock, safe_snapshot
    from .two_factor import _record

    if not isinstance(pending, dict) or pending.get("user") != actor.pk:
        raise PermissionDenied(NOT_YOURS)
    with transaction.atomic():
        account_lock()
        user = get_user_model().objects.select_for_update().get(pk=actor.pk)
        if not user.is_active:
            raise PermissionDenied("This account is inactive.")
        if user.credentials_locked:
            raise PermissionDenied(CREDENTIALS_LOCKED)
        if user.session_epoch != pending.get("epoch"):
            raise ValidationError(CHANGED)
        if SingleSignOnLink.objects.filter(user_id=user.pk).exists():
            raise ValidationError(ALREADY_LINKED)
        if SingleSignOnLink.objects.filter(issuer=found.issuer, subject=found.subject).exists():
            raise ValidationError(LINKED_ELSEWHERE)
        before = safe_snapshot(user)
        try:
            with transaction.atomic():
                SingleSignOnLink.objects.create(
                    user=user,
                    issuer=found.issuer,
                    subject=found.subject,
                    label=found.label,
                    created_at=timezone.now(),
                )
        except IntegrityError as exc:
            raise ValidationError(LINKED_ELSEWHERE) from exc
        _record(
            user,
            "account.single_sign_on_linked",
            before,
            f"Linked organization account {found.label} for sign-in.",
        )
    return user


@sensitive_variables()
def begin_link(*, actor, current_password, code=None):
    """Confirm the owner (password, and a second factor when two-factor sign-in is on) before
    leaving for the provider; returns what the link request keeps about the account."""
    from .administration import CREDENTIALS_LOCKED
    from .two_factor import _lock_owner, _reauthenticate, enabled

    if actor.credentials_locked:
        raise PermissionDenied(CREDENTIALS_LOCKED)
    on = enabled(actor)
    if on and not code:
        raise ValidationError("Confirm with a code, a recovery code or your security key.")
    verified = _reauthenticate(actor, current_password, code if on else None)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        if enabled(user) and not on:
            raise ValidationError("Two-factor sign-in was set up meanwhile. Start again.")
        if SingleSignOnLink.objects.filter(user_id=user.pk).exists():
            raise ValidationError(ALREADY_LINKED)
        return {"user": user.pk, "epoch": user.session_epoch}


@sensitive_variables()
def unlink(*, actor, current_password, code=None):
    """The owner removes their link; the password (and a second factor) confirm it."""
    from .administration import safe_snapshot
    from .two_factor import _lock_owner, _reauthenticate, enabled

    on = enabled(actor)
    if on and not code:
        raise ValidationError("Confirm with a code, a recovery code or your security key.")
    verified = _reauthenticate(actor, current_password, code if on else None)
    with transaction.atomic():
        user = _lock_owner(actor, verified)
        found = SingleSignOnLink.objects.select_for_update().filter(user_id=user.pk).first()
        if found is None:
            raise ValidationError("Your account is not linked to an organization account.")
        before = safe_snapshot(user)
        label = found.label
        found.delete()
        from .two_factor import _record

        _record(
            user,
            "account.single_sign_on_unlinked",
            before,
            f"Unlinked organization account {label}.",
        )
    return user


def remove(user):
    """Delete the account's link (an administrator's signed change; caller holds the locks)."""
    SingleSignOnLink.objects.filter(user_id=user.pk).delete()
