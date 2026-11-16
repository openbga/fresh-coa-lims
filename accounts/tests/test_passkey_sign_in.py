"""Signing in with a security key or passkey alone, without the password: the key must verify
its holder, the answer names the account by its user handle, refusals count like wrong
passwords, stale answers do not, and the PIN still signs."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.conf import settings as django_settings
from django.db import close_old_connections, connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from webauthn.helpers import bytes_to_base64url

from accounts import security_keys, two_factor
from accounts.models import LoginThrottle, SecurityKey
from accounts.tests.soft_authenticator import SoftKey
from accounts.tests.test_security_keys import (
    LOGIN,
    PASSWORD,
    PIN,
    counts,
    enable_with_key,
    fresh,
    make_user,
    owner_client,
    signed_in,
)
from accounts.views import PASSKEY_CEREMONY
from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin

pytestmark = pytest.mark.django_db(transaction=True)
PASSKEY = "/accounts/login/passkey/"
BUTTON = b"Sign in with a passkey"


@pytest.fixture
def analyst():
    return make_user("analyst.passkey", ["analyst"])


@pytest.fixture
def signin_records(caplog):
    logger = logging.getLogger("openbga.signin")
    logger.addHandler(caplog.handler)  # The logger does not propagate to the root handler.
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def start(client, **data):
    """Press Sign in with a passkey; returns the page with the browser's options."""
    response = client.post(PASSKEY, data)
    assert response.status_code == 200, response.content[:2000]
    return response


def use(client, key, page=None, **answer):
    """Answer the page's request with the key and send the answer."""
    page = page or start(client)
    data = {"security_key_response": key.answer(page.context["key_options"], **answer)}
    if page.context.get("next"):
        data["next"] = page.context["next"]
    return client.post(PASSKEY, data)


def test_a_key_that_verifies_its_holder_signs_in_without_the_password(analyst, signin_records):
    key, _codes = enable_with_key(analyst)
    signin_records.clear()
    client = Client()
    login_page = client.get(LOGIN)
    assert BUTTON in login_page.content and login_page.context["passkey_sign_in"]
    page = start(client)
    options = page.context["key_options"]
    # No account is named: the browser offers the keys it holds for this site, and each must
    # check its holder's PIN, fingerprint or face.
    assert options["rpId"] == "testserver" and options["allowCredentials"] == []
    assert options["userVerification"] == "required"
    assert b"Use your passkey" in page.content and not signed_in(client)
    response = use(client, key, page)
    assert response.status_code == 302 and response["Location"] == "/"
    assert signed_in(client) and int(client.session["_auth_user_id"]) == analyst.pk
    assert client.session["sign_in_factors"] == ["passkey"]
    assert PASSKEY_CEREMONY not in client.session
    stored = SecurityKey.objects.get(user=analyst)
    assert stored.sign_count == 1 and stored.last_used_at is not None
    assert counts(analyst) == (0, 0)
    assert client.get("/").status_code == 200
    lines = [r.getMessage() for r in signin_records.records if r.name == "openbga.signin"]
    assert lines == ["signin.success user=analyst.passkey request_id=-"]


def test_a_successful_sign_in_clears_earlier_failures(analyst):
    key, _codes = enable_with_key(analyst)
    LoginThrottle.objects.update_or_create(
        user=analyst, defaults={"failures": 3, "code_failures": 7}
    )
    assert use(Client(), key).status_code == 302
    assert counts(analyst) == (0, 0)


def test_next_is_kept_when_local_and_dropped_otherwise(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    access = reverse("accounts:access")
    login_page = client.get(LOGIN, {"next": access})
    assert f'name="next" value="{access}"'.encode() in login_page.content
    page = start(client, next=access)
    assert page.context["next"] == access
    assert use(client, key, page)["Location"] == access
    other = Client()
    page = start(other, next="https://elsewhere.example/")
    assert page.context["next"] == ""
    assert use(other, key, page)["Location"] == "/"


def test_opening_the_address_starts_nothing(analyst):
    client = Client()
    response = client.get(PASSKEY)
    assert response.status_code == 302 and response["Location"] == reverse("login")
    # No session is made for an anonymous visit.
    assert django_settings.SESSION_COOKIE_NAME not in client.cookies
    assert client.put(PASSKEY).status_code == 405


def test_turned_off_or_at_an_ip_address_there_is_no_button(analyst, settings):
    key, _codes = enable_with_key(analyst)
    settings.PASSKEY_SIGN_IN = False
    client = Client()
    assert BUTTON not in client.get(LOGIN).content
    response = client.post(PASSKEY)
    assert response.status_code == 302 and response["Location"] == reverse("login")
    assert PASSKEY_CEREMONY not in client.session
    owner = owner_client(analyst)
    assert b"also signs you in on its own" not in owner.get("/accounts/two-factor/").content
    settings.PASSKEY_SIGN_IN = True
    assert b"also signs you in on its own" in owner.get("/accounts/two-factor/").content
    settings.ALLOWED_HOSTS = ["127.0.0.1", "testserver"]
    at_address = Client(HTTP_HOST="127.0.0.1")
    assert BUTTON not in at_address.get(LOGIN).content
    assert at_address.post(PASSKEY)["Location"] == reverse("login")


def test_a_key_that_does_not_verify_its_holder_is_refused(analyst):
    key, _codes = enable_with_key(analyst, SoftKey(verifies=False))
    client = Client()
    response = use(client, key)
    assert response.status_code == 422 and not signed_in(client)
    assert b"The security key was not accepted." in response.content
    assert counts(analyst) == (0, 0)
    # The same key still works as the second factor after the password.
    client.post(LOGIN, {"username": analyst.username, "password": PASSWORD})
    options = client.get("/accounts/login/verify/").context["key_options"]
    response = client.post(
        "/accounts/login/verify/", {"security_key_response": key.answer(options)}
    )
    assert response.status_code == 302 and client.session["sign_in_factors"] == [
        "password",
        "security_key",
    ]


@pytest.mark.parametrize(
    "answer",
    [
        {"handle": False},  # No user handle: the account is not named.
        {"handle": bytes_to_base64url(b"\x01" * 32)},  # Another account's handle.
        {"origin": "https://testserver.example"},  # A look-alike site asked the key.
        {"tamper": True},  # Signature does not match.
        {"count": 0},  # Count did not increase: a copy of the key may exist.
    ],
)
def test_answers_that_prove_nothing_are_refused_without_counting(analyst, answer):
    key, _codes = enable_with_key(analyst)
    if "count" in answer:
        SecurityKey.objects.filter(user=analyst).update(sign_count=5)
    client = Client()
    response = use(client, key, **answer)
    assert response.status_code == 422 and not signed_in(client)
    assert b"The security key was not accepted." in response.content
    # Nothing is counted: an unsigned answer must not let whoever saw a credential ID pause the
    # account (a key's signature cannot be guessed).
    assert counts(analyst) == (0, 0)
    # The refused page offers a new request, and a proper answer signs in.
    response = use(client, key, response, count=10 if "count" in answer else None)
    assert response.status_code == 302 and signed_in(client)


def test_an_unknown_or_removed_key_names_nobody_and_counts_nothing(analyst, signin_records):
    stranger = SoftKey()
    stranger.user_handle = bytes_to_base64url(b"\x02" * 32)
    client = Client()
    response = use(client, stranger)
    assert response.status_code == 422
    assert b"not registered for an account at this address" in response.content
    assert not LoginThrottle.objects.exists()
    # A key registered at another host name is not this site's either.
    key, _codes = enable_with_key(analyst)
    SecurityKey.objects.filter(user=analyst).update(rp_id="lims.example.test")
    response = use(client, key)
    assert b"not registered for an account at this address" in response.content
    assert counts(analyst) == (0, 0) and not signed_in(client)
    lines = [r.getMessage() for r in signin_records.records if r.name == "openbga.signin"]
    lines = [line for line in lines if not line.startswith("signin.success")]  # The setup.
    assert lines == ["signin.passkey_failed user=<unknown> request_id=-"] * 2


def test_refused_answers_are_logged_against_the_keys_account(analyst, signin_records):
    key, _codes = enable_with_key(analyst)
    signin_records.clear()
    use(Client(), key, tamper=True)
    lines = [r.getMessage() for r in signin_records.records if r.name == "openbga.signin"]
    assert lines == ["signin.passkey_failed user=analyst.passkey request_id=-"]
    stored = SecurityKey.objects.get(user=analyst)
    for secret in (key.credential_id.hex(), bytes(stored.public_key).hex()):
        assert secret not in signin_records.text


def test_a_lock_from_wrong_passwords_refuses_a_valid_key(analyst, settings):
    key, _codes = enable_with_key(analyst)
    client = Client()
    for _ in range(settings.LOGIN_FAILURE_LIMIT):
        client.post(LOGIN, {"username": analyst.username, "password": "wrong"})
    throttle = LoginThrottle.objects.get(user=analyst)
    assert throttle.locked_until and throttle.locked_until > timezone.now()
    response = use(client, key)
    assert response.status_code == 422 and not signed_in(client)
    assert b"The security key was not accepted." in response.content
    assert LoginThrottle.objects.get(user=analyst).locked_until == throttle.locked_until


def test_a_credential_id_alone_cannot_pause_or_stop_the_account(analyst, settings):
    """Credential IDs are shown to whoever passes the password step: forged answers carrying
    one, with the session's own challenge, prove nothing and must not count against the key's
    account, however many arrive."""
    victim, _codes = enable_with_key(analyst)
    forger = SoftKey()
    forger.credential_id = victim.credential_id
    forger.user_handle = victim.user_handle
    client = Client()
    page = start(client)
    for _ in range(two_factor.CODE_FAILURE_LIMIT + settings.LOGIN_FAILURE_LIMIT):
        page = use(client, forger, page)
        assert page.status_code == 422
    assert counts(analyst) == (0, 0) and not two_factor.stopped(analyst)
    assert not LoginThrottle.objects.filter(user=analyst, locked_until__isnull=False).exists()
    # The owner's genuine key still signs in.
    assert use(client, victim, page).status_code == 302 and signed_in(client)


def test_only_a_signed_answer_raises_the_warning_about_a_copied_key(analyst, caplog):
    key, _codes = enable_with_key(analyst)
    SecurityKey.objects.filter(user=analyst).update(sign_count=5)
    forger = SoftKey()
    forger.credential_id = key.credential_id
    forger.user_handle = key.user_handle
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="accounts.security_keys"):
        assert use(Client(), forger, count=0).status_code == 422
        assert "a copy of the key may exist" not in caplog.text
        assert use(Client(), key, count=3).status_code == 422
    assert "a copy of the key may exist" in caplog.text
    assert SecurityKey.objects.get(user=analyst).sign_count == 5


def test_a_stopped_second_factor_or_an_inactive_account_refuses_a_valid_key(analyst):
    key, _codes = enable_with_key(analyst)
    LoginThrottle.objects.update_or_create(
        user=analyst, defaults={"code_failures": two_factor.CODE_FAILURE_LIMIT}
    )
    client = Client()
    response = use(client, key)
    assert response.status_code == 422 and b"stopped for this account" in response.content
    LoginThrottle.objects.filter(user=analyst).update(code_failures=0)
    type(analyst).objects.filter(pk=analyst.pk).update(is_active=False)
    response = use(client, key, response)
    assert response.status_code == 422 and b"The security key was not accepted." in (
        response.content
    )
    assert counts(analyst) == (0, 0) and not signed_in(client)


def test_stale_and_expired_answers_are_refused_without_counting(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    first = start(client)
    second = start(client)  # Another tab or a reload replaces the request.
    response = use(client, key, first)
    assert response.status_code == 422 and b"request expired" in response.content
    assert counts(analyst) == (0, 0)
    # An answer arriving where no request was made (sent twice, or the session ended).
    answer = key.answer(second.context["key_options"])
    response = Client().post(PASSKEY, {"security_key_response": answer})
    assert response.status_code == 422 and b"request expired" in response.content
    # A request older than the time limit.
    page = start(client)
    session = client.session
    session[PASSKEY_CEREMONY]["issued"] -= 3600
    session.save()
    response = use(client, key, page)
    assert response.status_code == 422 and b"request expired" in response.content
    assert counts(analyst) == (0, 0) and not signed_in(client)
    # The page after a refusal carries a new request that works.
    assert use(client, key, response).status_code == 302


def test_an_answer_sent_twice_signs_in_once(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    page = start(client)
    answer = key.answer(page.context["key_options"])
    assert client.post(PASSKEY, {"security_key_response": answer}).status_code == 302
    client.logout()
    start(client)
    response = client.post(PASSKEY, {"security_key_response": answer})
    assert response.status_code == 422 and not signed_in(client)
    assert counts(analyst) == (0, 0)


def test_the_same_answer_twice_at_once_is_accepted_once(analyst):
    """A passkey without a counter: the answered challenge kept on the key's row refuses the
    second, concurrent use of the same answer."""
    key, _codes = enable_with_key(analyst, SoftKey(counter=False))
    ceremony = security_keys.begin(
        security_keys.RelyingParty("testserver", "http://testserver"), security_keys.PASSKEY, None
    )
    assertion = security_keys.KeyAssertion(
        key.answer(security_keys.passkey_options(ceremony)), ceremony
    )
    barrier = Barrier(2)

    def attempt():
        close_old_connections()
        try:
            barrier.wait()
            try:
                return two_factor.complete_passkey_sign_in(assertion).username
            except Exception as exc:  # noqa: BLE001 - the refusal is the result
                return type(exc).__name__
        finally:
            connections.close_all()

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(lambda _: attempt(), range(2)))
    assert results == ["ValidationError", analyst.username]


def test_ceremonies_do_not_stand_in_for_each_other(analyst):
    key, _codes = enable_with_key(analyst)
    user = fresh(analyst)
    rp = security_keys.RelyingParty("testserver", "http://testserver")
    after_password = security_keys.begin(rp, "sign_in", user.pk)
    answer = key.answer(security_keys.request_options(user, after_password))
    with pytest.raises(two_factor.ValidationError):
        two_factor.complete_passkey_sign_in(security_keys.KeyAssertion(answer, after_password))
    alone = security_keys.begin(rp, security_keys.PASSKEY, None)
    answer = key.answer(security_keys.passkey_options(alone))
    user.backend = django_settings.AUTHENTICATION_BACKENDS[0]
    pending = two_factor.begin_sign_in(user)
    with pytest.raises(two_factor.ValidationError):
        two_factor.complete_sign_in(pending, security_keys.KeyAssertion(answer, alone))
    with pytest.raises(RuntimeError), two_factor.transaction.atomic():
        two_factor.complete_passkey_sign_in(security_keys.KeyAssertion(answer, alone))


def test_required_two_factor_is_met_and_a_forced_password_change_still_applies(analyst, settings):
    settings.MFA_REQUIRED_ROLES = frozenset({"analyst"})
    key, _codes = enable_with_key(analyst)
    client = Client()
    assert use(client, key).status_code == 302
    assert client.get("/").status_code == 200
    type(analyst).objects.filter(pk=analyst.pk).update(password_change_required=True)
    other = Client()
    assert use(other, key).status_code == 302
    assert other.get("/")["Location"] == reverse("accounts:password_change")


def test_an_administrator_reset_ends_passkey_sign_in(analyst):
    manager = make_user("manager.passkey", ["admin"])
    set_pin(actor=manager, pin=PIN, password=PASSWORD)
    key, _codes = enable_with_key(analyst)
    response = owner_client(manager).post(
        reverse("accounts:user_action", args=[analyst.pk, "reset_two_factor"]),
        {
            "revision": fresh(analyst).management_revision,
            "reason": "Synthetic lost passkey, identity verified",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    response = use(Client(), key)
    assert response.status_code == 422
    assert b"not registered for an account at this address" in response.content


def test_signatures_record_a_sign_in_with_a_key_alone():
    manager = make_user("signer.passkey", ["admin"])
    set_pin(actor=manager, pin=PIN, password=PASSWORD)
    key, _codes = enable_with_key(manager)
    client = Client()
    assert use(client, key).status_code == 302
    target = make_user("target.passkey", ["analyst"])
    response = client.post(
        reverse("accounts:user_action", args=[target.pk, "deactivate"]),
        {
            "revision": target.management_revision,
            "reason": "Synthetic leaver",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    signature = ElectronicSignature.objects.get(audit_event__action="account.deactivate")
    assert signature.authentication_context["sign_in_factors"] == ["passkey"]
    assert signature.authentication_context["components"] == ["username", "pin"]


def test_the_page_loads_its_script_without_inline_code_and_keeps_answers_out_of_audit(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    page = start(client)
    html = page.content.decode()
    for attrs, _body in re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S):
        assert "src=" in attrs or 'type="application/json"' in attrs, attrs
    assert "security-keys" in html and 'id="security-key-options"' in html
    assert 'data-security-key-fallback="sign in with your password"' in html
    use(client, key, page, tamper=True)
    text = json.dumps([[e.before, e.after, e.reason] for e in AuditEvent.objects.all()])
    assert key.credential_id.hex() not in text
