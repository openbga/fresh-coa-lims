"""Security keys and passkeys (W3C Web Authentication) as a sign-in factor.

A key answers a random challenge with a signature that also covers the site's host name (the
relying party ID) and the page's origin as the browser reports them, so an answer given to a
look-alike site does not work here. The server keeps each key's public key and signature count;
py_webauthn checks the answer. After the password a key is the second factor: user verification
(the key's own PIN or fingerprint) is asked for when the key has it, not required. Without the
password (purpose PASSKEY) the key must verify its holder, so it proves both who holds it and
something only that person knows or is; the browser offers the keys stored for this site and
the answer's user handle names the account.

Each challenge belongs to one ceremony kept in the session (sign-in, a confirmation on the
owner's page or a registration) and expires with it. The key's row keeps the digest of the
challenge it last answered, so the same answer is refused when it arrives twice at once.
"""

import hashlib
import ipaddress
import json
import logging
import secrets
from dataclasses import dataclass

from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import SecurityKey

logger = logging.getLogger(__name__)

RP_NAME = "OpenBGA QM LIMS"
# The ceremony of a sign-in with a key alone, without the password.
PASSKEY = "passkey"
KEY_LIMIT = 10
# How long the browser waits for the key; the ceremony itself expires with its sign-in or setup.
BROWSER_TIMEOUT_MS = 120_000
RESPONSE_LIMIT = 64 * 1024
CREDENTIAL_ID_LIMIT = 1023
TRANSPORTS = frozenset(t.value for t in AuthenticatorTransport)
UNAVAILABLE_HOST = (
    "Security keys work only when this site is opened by its host name over HTTPS, not by an IP "
    "address."
)


class KeyRefused(Exception):
    """The answer was not accepted (wrong key, wrong site, replayed or not a valid response)."""


@dataclass(frozen=True)
class RelyingParty:
    id: str
    origin: str


@dataclass(frozen=True)
class KeyAssertion:
    """A key's answer to a ceremony's challenge, submitted in place of a code."""

    response: str
    ceremony: dict

    def __repr__(self):
        return "<KeyAssertion>"


def relying_party(request):
    """The relying party for this request's host name, or None when the host is an IP address
    (Web Authentication accepts host names only). The host is one ALLOWED_HOSTS accepted."""
    host = request.get_host()
    name = host.rsplit(":", 1)[0] if not host.endswith("]") else host
    name = name.strip("[]").lower()
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return RelyingParty(id=name, origin=f"{request.scheme}://{host}")
    return None


def begin(rp, purpose, user_pk):
    """A new ceremony for the session: a random challenge bound to one purpose and account."""
    return {
        "purpose": purpose,
        "user": user_pk,
        "challenge": bytes_to_base64url(secrets.token_bytes(32)),
        "rp_id": rp.id,
        "origin": rp.origin,
        "issued": timezone.now().timestamp(),
    }


def passkey_options(ceremony):
    """Options for a sign-in without the password: no account is known yet, so the browser
    offers the keys it holds for this site (discoverable credentials), and each must verify its
    holder."""
    options = generate_authentication_options(
        rp_id=ceremony["rp_id"],
        challenge=base64url_to_bytes(ceremony["challenge"]),
        timeout=BROWSER_TIMEOUT_MS,
        allow_credentials=[],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return json.loads(options_to_json(options))


def key_owner(assertion):
    """The account whose key gave this answer to a sign-in without the password, or None when
    no key registered at the ceremony's host has the answer's credential ID. The caller locks
    the account and checks the answer with verify_assertion."""
    ceremony = assertion.ceremony
    if not isinstance(ceremony, dict) or ceremony.get("purpose") != PASSKEY:
        return None
    try:
        _data, raw_id, _handle = _parse(assertion.response)
    except KeyRefused:
        return None
    return (
        SecurityKey.objects.filter(rp_id=ceremony.get("rp_id"), credential_id=raw_id)
        .values_list("user_id", flat=True)
        .first()
    )


def usable_keys(user, rp_id):
    return SecurityKey.objects.filter(user_id=user.pk, rp_id=rp_id).order_by("pk")


def _descriptor(key):
    return PublicKeyCredentialDescriptor(
        id=bytes(key.credential_id),
        transports=[AuthenticatorTransport(t) for t in key.transports if t in TRANSPORTS],
    )


def request_options(user, ceremony):
    """Options for navigator.credentials.get(): the owner's keys registered at this host."""
    options = generate_authentication_options(
        rp_id=ceremony["rp_id"],
        challenge=base64url_to_bytes(ceremony["challenge"]),
        timeout=BROWSER_TIMEOUT_MS,
        allow_credentials=[_descriptor(k) for k in usable_keys(user, ceremony["rp_id"])],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return json.loads(options_to_json(options))


def user_handle(user):
    """The handle the owner's keys share; a new random one when they have none."""
    existing = SecurityKey.objects.filter(user_id=user.pk).order_by("pk").first()
    return bytes(existing.user_handle) if existing else secrets.token_bytes(32)


def creation_options(user, ceremony):
    """Options for navigator.credentials.create(); keys already registered are excluded."""
    options = generate_registration_options(
        rp_id=ceremony["rp_id"],
        rp_name=RP_NAME,
        user_name=user.username,
        user_id=base64url_to_bytes(ceremony["user_handle"]),
        user_display_name=user.get_full_name() or user.username,
        challenge=base64url_to_bytes(ceremony["challenge"]),
        timeout=BROWSER_TIMEOUT_MS,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[
            _descriptor(k) for k in SecurityKey.objects.filter(user_id=user.pk).order_by("pk")
        ],
    )
    return json.loads(options_to_json(options))


def _challenge_digest(ceremony):
    return hashlib.sha256(ceremony["challenge"].encode()).hexdigest()


def answers_ceremony(assertion):
    """Whether the answer was given to this ceremony's challenge, as the browser reports it.

    An answer to an earlier or replaced challenge (a second tab, a reload, a repeated send) is
    stale rather than wrong: it is refused without counting, which is safe because a key's
    answer cannot be guessed. So is an answer when the session holds no challenge (sent twice).
    An unreadable answer, or one whose challenge is not text, returns True, so the check
    refuses and counts it.
    """
    ceremony = assertion.ceremony
    expected = ceremony.get("challenge") if isinstance(ceremony, dict) else None
    try:
        data = json.loads(assertion.response)
        client = json.loads(base64url_to_bytes(data["response"]["clientDataJSON"]))
        given = client["challenge"]
    except ValueError, TypeError, KeyError, AttributeError:
        return True
    if not isinstance(given, str):
        return True  # Not an answer a browser gives: refused and counted by the check.
    return bool(expected) and given == expected


def _parse(response):
    if not isinstance(response, str) or not response or len(response) > RESPONSE_LIMIT:
        raise KeyRefused
    try:
        data = json.loads(response)
        raw_id = base64url_to_bytes(data["rawId"])
        handle = data.get("response", {}).get("userHandle")
        handle = base64url_to_bytes(handle) if handle else None
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise KeyRefused from exc
    return data, raw_id, handle


def verify_assertion(user, assertion, *, purpose):
    """Check a key's answer inside the caller's transaction, with the account locked.

    Returns the key, with its count, last use and answered challenge updated. Raises KeyRefused
    for an answer from a key the account does not have here, to another challenge or site, a
    replayed one, or one whose signature count did not increase (a copied key may exist).
    Without the password (purpose PASSKEY) the answer must also carry the account's user handle
    (Web Authentication Level 3, section 7.2) and show that the key verified its holder.
    """
    ceremony = assertion.ceremony
    if not isinstance(ceremony, dict) or ceremony.get("purpose") != purpose:
        raise KeyRefused
    alone = purpose == PASSKEY
    if ceremony.get("user") != (None if alone else user.pk):
        raise KeyRefused
    _data, raw_id, handle = _parse(assertion.response)
    if alone and handle is None:
        raise KeyRefused
    key = (
        SecurityKey.objects.select_for_update()
        .filter(user_id=user.pk, rp_id=ceremony["rp_id"], credential_id=raw_id)
        .first()
    )
    if key is None or (handle is not None and handle != bytes(key.user_handle)):
        raise KeyRefused
    digest = _challenge_digest(ceremony)
    if key.last_challenge == digest:
        raise KeyRefused
    try:
        # The count is compared below, once the signature is known to be the key's: the library
        # compares it first, so an unsigned answer could raise the warning about a copy.
        verified = verify_authentication_response(
            credential=assertion.response,
            expected_challenge=base64url_to_bytes(ceremony["challenge"]),
            expected_rp_id=ceremony["rp_id"],
            expected_origin=ceremony["origin"],
            credential_public_key=bytes(key.public_key),
            credential_current_sign_count=0,
            require_user_verification=alone,
        )
    except WebAuthnException as exc:
        raise KeyRefused from exc
    count = verified.new_sign_count
    if (count > 0 or key.sign_count > 0) and count <= key.sign_count:
        # Web Authentication Level 3, section 6.1.1: a signal that a copy of the key may exist.
        logger.warning(
            "Security key id %s of account id %s answered with a signature count that did not "
            "increase; a copy of the key may exist.",
            key.pk,
            user.pk,
        )
        raise KeyRefused
    key.sign_count = verified.new_sign_count
    key.last_used_at = timezone.now()
    key.last_challenge = digest
    key.save(update_fields=["sign_count", "last_used_at", "last_challenge"])
    return key


def verify_registration(user, ceremony, response):
    """Check a new key's registration answer; returns the fields of the key to store."""
    if not isinstance(ceremony, dict) or ceremony.get("purpose") != "register":
        raise KeyRefused
    if ceremony.get("user") != user.pk:
        raise KeyRefused
    data, _raw_id, _handle = _parse(response)
    try:
        verified = verify_registration_response(
            credential=response,
            expected_challenge=base64url_to_bytes(ceremony["challenge"]),
            expected_rp_id=ceremony["rp_id"],
            expected_origin=ceremony["origin"],
            require_user_verification=False,
        )
    except WebAuthnException as exc:
        raise KeyRefused from exc
    if len(verified.credential_id) > CREDENTIAL_ID_LIMIT:
        raise KeyRefused  # Web Authentication Level 3, section 7.1: at most 1023 bytes.
    transports = data.get("response", {}).get("transports") or []
    if not isinstance(transports, list):
        transports = []
    return {
        "credential_id": verified.credential_id,
        "public_key": verified.credential_public_key,
        "sign_count": verified.sign_count,
        "user_handle": base64url_to_bytes(ceremony["user_handle"]),
        "rp_id": ceremony["rp_id"],
        "transports": sorted({t for t in transports if t in TRANSPORTS}),
        "backup_eligible": verified.credential_device_type == "multi_device",
    }
