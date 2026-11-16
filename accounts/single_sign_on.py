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
import threading
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
    "password, then link it on Organization sign-in under Account access (unlink an earlier "
    "link there first)."
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
        # No discovery address: client() fetches and checks the document itself and gives the
        # library only the checked keys, so the library never loads an unchecked copy.
        client_kwargs={
            "scope": " ".join(scopes),
            "code_challenge_method": "S256",
            "token_endpoint_auth_method": auth_method,
            "default_timeout": settings.OIDC_TIMEOUT_SECONDS,
        },
    )


# The discovery keys the client uses. Everything else in the document is dropped, so that a key
# such as scope or code_challenge_method cannot override the client's own settings.
METADATA_KEYS = (
    "issuer",
    "authorization_endpoint",
    "token_endpoint",
    "jwks_uri",
    "id_token_signing_alg_values_supported",
    "authorization_response_iss_parameter_supported",
)
ENDPOINTS = ("authorization_endpoint", "token_endpoint", "jwks_uri")
# After a failed discovery, requests wait this long before the provider is asked again, so that
# an unreachable provider does not hold a worker for the full timeout on every request.
RETRY_SECONDS = 30
_unavailable_until = {}
_discovery_lock = threading.Lock()


def _secure_url(value):
    from urllib.parse import urlsplit

    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        url.port  # noqa: B018 - raises ValueError for a port that is not a number.
    except ValueError:
        return False
    loopback = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}
    return bool(url.hostname) and (url.scheme == "https" or loopback) and not url.fragment


def _checked(document):
    """The document's keys the client uses, checked; None when it does not describe OIDC_ISSUER
    (OpenID Connect Discovery 1.0 sections 3 and 4.3)."""
    kept = {key: document[key] for key in METADATA_KEYS if key in document}
    if kept.get("issuer") != settings.OIDC_ISSUER or not all(
        _secure_url(kept.get(key)) for key in ENDPOINTS
    ):
        return None
    offered = kept.get("id_token_signing_alg_values_supported")
    offered = offered if isinstance(offered, list) else ["RS256"]
    kept["id_token_signing_alg_values_supported"] = [
        alg for alg in SIGNING_ALGORITHMS if alg in offered
    ] or ["RS256"]
    kept["authorization_response_iss_parameter_supported"] = (
        kept.get("authorization_response_iss_parameter_supported") is True
    )
    return kept


def client():
    """The provider's client with its checked discovery document (fetched once a process);
    raises ProviderUnavailable."""
    import time

    import requests

    key = (
        settings.OIDC_ISSUER,
        settings.OIDC_CLIENT_ID,
        settings.OIDC_CLIENT_SECRET,
        tuple(settings.OIDC_SCOPES),
        settings.OIDC_TOKEN_AUTH_METHOD,
    )
    app = _client(*key)
    if getattr(app, "checked", False):
        return app
    with _discovery_lock:
        if getattr(app, "checked", False):
            return app
        if _unavailable_until.get(key, 0) > time.monotonic():
            raise ProviderUnavailable
        try:
            response = requests.get(
                settings.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration",
                headers={"Accept": "application/json"},
                timeout=settings.OIDC_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
            response.raise_for_status()
            document = response.json()
            kept = _checked(document) if isinstance(document, dict) else None
        except Exception as exc:
            _unavailable_until[key] = time.monotonic() + RETRY_SECONDS
            logger.warning("Single sign-on discovery failed: %s", type(exc).__name__)
            raise ProviderUnavailable from exc
        if kept is None:
            _unavailable_until[key] = time.monotonic() + RETRY_SECONDS
            logger.warning("Single sign-on discovery document does not match OIDC_ISSUER.")
            raise ProviderUnavailable
        app.server_metadata = kept
        app.checked = True
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
    if "code_challenge_method=S256" not in created["url"] or not created.get("code_verifier"):
        logger.warning("Single sign-on request would not use PKCE with S256.")
        raise ProviderUnavailable
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
    app = client()
    # RFC 9207 section 2.4: an iss parameter in the answer must name this provider, and a
    # provider that says it sends one must send it.
    issuer = params.get("iss")
    if issuer is None and app.server_metadata.get("authorization_response_iss_parameter_supported"):
        logger.warning("Single sign-on answer lacks the issuer the provider says it sends.")
        raise Refused(REFUSED)
    if issuer is not None and issuer != settings.OIDC_ISSUER:
        logger.warning("Single sign-on answer names another issuer.")
        raise Refused(REFUSED)
    error = params.get("error")
    if error:
        code = error if ERROR_CODE.fullmatch(error) else "invalid"
        logger.info("Single sign-on answered with error %s.", code)
        if code in {"access_denied", "login_required", "interaction_required"}:
            raise Refused("Sign-in at your organization was cancelled or not completed.")
        raise Refused(REFUSED)
    code = params.get("code")
    if not isinstance(code, str) or not code or len(code) > 4096:
        raise Refused(REFUSED)
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
                # This client alone: a token that also names other audiences is refused
                # (OpenID Connect Core 1.0 section 3.1.3.7, step 3).
                "aud": {
                    "essential": True,
                    "value": settings.OIDC_CLIENT_ID,
                    "validate": _only_this_client,
                },
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
    # With prompt=login the provider was asked to authenticate the person anew: when the token
    # says when that happened, it must be after this request started.
    stated = claims.get("auth_time") if claims else None
    if (
        "login" in settings.OIDC_PROMPT.split()
        and isinstance(stated, (int, float))
        and stated < float(pending["started"]) - LEEWAY_SECONDS
    ):
        logger.warning("Single sign-on ID token reports an earlier authentication.")
        raise Refused(REFUSED)
    subject = claims.get("sub") if claims else None
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise Refused(REFUSED)
    shown = [c for c in LABEL_CLAIMS if c != "email" or claims.get("email_verified") is True]
    label = next(
        (claims[c] for c in shown if isinstance(claims.get(c), str) and claims[c].strip()),
        subject,
    )
    return Identity(settings.OIDC_ISSUER, subject, label.strip()[:LABEL_LIMIT])


def _only_this_client(claims, value):
    return value == settings.OIDC_CLIENT_ID or value == [settings.OIDC_CLIENT_ID]


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
    if SingleSignOnLink.objects.filter(user_id=actor.pk).exists():
        raise ValidationError(ALREADY_LINKED)  # Before a code is spent.
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
    """Delete the account's link (an administrator's signed change, including a forced password
    reset; caller holds the locks)."""
    SingleSignOnLink.objects.filter(user_id=user.pk).delete()
