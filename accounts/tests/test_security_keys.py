"""Security keys and passkeys as a second sign-in factor: registration, sign-in, what a key's
answer must prove, owner changes confirmed with a key, removal, requirement and resets."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections, connection, connections, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts import security_keys, two_factor
from accounts.models import LoginThrottle, RecoveryCode, SecurityKey
from accounts.tests.soft_authenticator import SoftKey
from accounts.views import CONFIRM_CEREMONY, PENDING_KEY, PENDING_SIGN_IN
from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-security-key-pass-614!"
PIN = "61853247"
LOGIN = "/accounts/login/"
VERIFY = "/accounts/login/verify/"
PAGE = "/accounts/two-factor/"
ADD = "/accounts/two-factor/security-key/"
SETUP = "/accounts/two-factor/setup/"


def make_user(username, roles=(), **extra):
    user = get_user_model().objects.create_user(
        username=username, password=PASSWORD, first_name="Synthetic", last_name=username, **extra
    )
    user.groups.set([Group.objects.get_or_create(name=role)[0] for role in roles])
    return user


def fresh(user):
    return get_user_model().objects.get(pk=user.pk)


def owner_client(user):
    client = Client()
    client.force_login(user)
    return client


def confirm_with(client, key):
    """The answer the key gives to the owner page's confirmation challenge."""
    page = client.get(PAGE)
    return key.answer(page.context["key_options"])


def add_key(client, key, *, name="Synthetic key A", proof=None):
    """Start on the owner's page and register key; returns the registration response."""
    data = {"current_password": PASSWORD, "action": "add_key", **(proof or {})}
    response = client.post(PAGE, data)
    assert response.status_code == 302 and response["Location"] == ADD, response.content[:2000]
    options = client.get(ADD).context["key_options"]
    return client.post(ADD, {"name": name, "security_key_response": key.register(options)})


def enable_with_key(user, key=None, name="Synthetic key A"):
    """Turn two-factor sign-in on with a first key; returns (key, recovery codes)."""
    key = key or SoftKey()
    response = add_key(owner_client(user), key, name=name)
    assert response.status_code == 200, response.content[:2000]
    return key, list(response.context["codes"])


def password_step(client, username):
    response = client.post(LOGIN, {"username": username, "password": PASSWORD})
    assert response.status_code == 302 and response["Location"] == VERIFY
    return response


def key_step(client, key, **answer):
    options = client.get(VERIFY).context["key_options"]
    return client.post(VERIFY, {"security_key_response": key.answer(options, **answer)})


def signed_in(client):
    return "_auth_user_id" in client.session


def counts(user):
    throttle = LoginThrottle.objects.filter(user=user).first()
    return (throttle.failures, throttle.code_failures) if throttle else (0, 0)


@pytest.fixture
def analyst():
    return make_user("analyst.keys", ["analyst"])


@pytest.fixture
def manager():
    user = make_user("manager.keys", ["admin"])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


def test_first_key_turns_on_two_factor_with_recovery_codes(analyst):
    client = owner_client(analyst)
    other = owner_client(analyst)
    page = client.get(PAGE)
    assert b"Set up with a security key or passkey" in page.content
    # A wrong password starts nothing and counts as a failed attempt.
    response = client.post(PAGE, {"current_password": "wrong", "action": "add_key"})
    assert response.status_code == 422 and PENDING_KEY not in client.session
    assert counts(analyst)[0] == 1

    key = SoftKey(synced=True)
    response = add_key(client, key)
    assert response.status_code == 200
    codes = list(response.context["codes"])
    assert len(codes) == 10 and RecoveryCode.objects.filter(user=analyst, used_at=None).count()
    stored = SecurityKey.objects.get(user=analyst)
    assert stored.name == "Synthetic key A" and stored.rp_id == "testserver"
    assert bytes(stored.credential_id) == key.credential_id
    assert stored.backup_eligible and stored.transports == ["nfc", "usb"]
    assert two_factor.enabled(analyst) and not two_factor.has_app(analyst)
    event = AuditEvent.objects.get(action="account.two_factor_enabled")
    assert event.before["two_factor"] is False and event.after["security_keys"] == 1
    assert "Synthetic key A" in event.reason
    assert PENDING_KEY not in client.session
    # Only the public key is kept, and nothing of the key reaches the audit values.
    assert key.credential_id.hex() not in json.dumps([event.before, event.after])
    # This session continues; the others sign in again.
    assert client.get(PAGE).status_code == 200
    assert other.get(PAGE).status_code == 302
    listing = owner_client(make_user("admin.keys", ["admin"])).get(
        reverse("accounts:user_list"), {"two_factor": "on"}
    )
    assert [u.username for u in listing.context["page"]] == [analyst.username]
    assert b"On: security key" in listing.content


def test_sign_in_with_a_key(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    assert not signed_in(client)
    page = client.get(VERIFY)
    assert b"Use your security key" in page.content and b"Recovery code" in page.content
    options = page.context["key_options"]
    assert options["rpId"] == "testserver"
    assert [c["id"] for c in options["allowCredentials"]] == [
        security_keys.bytes_to_base64url(key.credential_id)
    ]
    response = client.post(VERIFY, {"security_key_response": key.answer(options)})
    assert response.status_code == 302 and response["Location"] == "/"
    assert signed_in(client) and PENDING_SIGN_IN not in client.session
    assert client.session["sign_in_factors"] == ["password", "security_key"]
    stored = SecurityKey.objects.get(user=analyst)
    assert stored.sign_count == 1 and stored.last_used_at is not None
    assert counts(analyst) == (0, 0)


@pytest.mark.parametrize(
    "answer",
    [
        {"origin": "https://testserver.example"},  # A look-alike site asked the key.
        {"rp_id": "example.test"},  # Registered at another site.
        {"tamper": True},  # Signature does not match.
        {"count": 0},  # Count did not increase: a copy of the key may exist.
    ],
)
def test_key_answers_that_prove_nothing_are_refused_and_counted(analyst, answer):
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    if "count" in answer:
        key.answer(client.get(VERIFY).context["key_options"])  # Count 1, never submitted.
        SecurityKey.objects.filter(user=analyst).update(sign_count=5)
    response = key_step(client, key, **answer)
    assert response.status_code == 422 and not signed_in(client)
    assert b"The security key was not accepted." in response.content
    assert counts(analyst) == (1, 1)
    # A new challenge is offered and a proper answer still signs in.
    response = key_step(client, key, count=10 if "count" in answer else None)
    assert response.status_code == 302 and signed_in(client)
    assert counts(analyst) == (0, 0)


def test_another_accounts_key_and_replayed_answers_are_refused(analyst):
    key, _codes = enable_with_key(analyst)
    other = make_user("other.keys", ["analyst"])
    other_key, _ = enable_with_key(other)
    client = Client()
    password_step(client, analyst.username)
    response = key_step(client, other_key)
    assert response.status_code == 422 and not signed_in(client)
    assert counts(analyst) == (1, 1)

    # An answer to an earlier challenge does not work again.
    options = client.get(VERIFY).context["key_options"]
    spent = key.answer(options)
    assert client.post(VERIFY, {"security_key_response": spent}).status_code == 302
    client.logout()
    password_step(client, analyst.username)
    client.get(VERIFY)
    response = client.post(VERIFY, {"security_key_response": spent})
    assert response.status_code == 422 and not signed_in(client)
    # Stale, not wrong: an answer cannot be guessed, so it is not counted.
    assert b"request expired" in response.content and counts(analyst) == (0, 0)


def test_same_answer_twice_at_once_is_accepted_once(analyst):
    """A key without a counter (count 0, as many passkeys send): the answered challenge on the
    key's row refuses the second, concurrent use of the same answer."""
    key, _codes = enable_with_key(analyst, SoftKey(counter=False))
    user = fresh(analyst)
    ceremony = security_keys.begin(
        security_keys.RelyingParty("testserver", "http://testserver"), "sign_in", user.pk
    )
    assertion = security_keys.KeyAssertion(
        key.answer(security_keys.request_options(user, ceremony)), ceremony
    )
    pending = {
        "user": user.pk,
        "backend": "accounts.authentication.ThrottledModelBackend",
        "epoch": user.session_epoch,
        "auth_hash": user.get_session_auth_hash(),
        "started": timezone.now().timestamp(),
    }
    barrier = Barrier(2)

    def attempt():
        close_old_connections()
        try:
            barrier.wait()
            try:
                return two_factor.complete_sign_in(pending, assertion)[1]
            except Exception as exc:  # noqa: BLE001 - the refusal is the result
                return type(exc).__name__
        finally:
            connections.close_all()

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(lambda _: attempt(), range(2)))
    assert results == ["ValidationError", "security_key"]


def test_lock_and_stop_refuse_even_a_correct_key(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    LoginThrottle.objects.update_or_create(
        user=analyst, defaults={"locked_until": timezone.now() + timezone.timedelta(minutes=5)}
    )
    response = key_step(client, key)
    assert response.status_code == 422 and not signed_in(client)
    assert counts(analyst) == (0, 0)  # Refused during the lock without counting.
    LoginThrottle.objects.filter(user=analyst).update(
        locked_until=None, code_failures=two_factor.CODE_FAILURE_LIMIT
    )
    response = key_step(client, key)
    assert response.status_code == 422 and b"stopped for this account" in response.content
    assert not signed_in(client)


def test_expired_challenge_is_refused_without_counting(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    options = client.get(VERIFY).context["key_options"]
    session = client.session
    pending = session[PENDING_SIGN_IN]
    pending["key_ceremony"]["issued"] -= 3600
    pending["started"] = timezone.now().timestamp()
    session[PENDING_SIGN_IN] = pending
    session.save()
    response = client.post(VERIFY, {"security_key_response": key.answer(options)})
    assert response.status_code == 422 and b"request expired" in response.content
    assert counts(analyst) == (0, 0) and not signed_in(client)


def test_keys_only_account_accepts_recovery_codes_but_not_app_codes(analyst):
    _key, codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    response = client.post(VERIFY, {"otp_code": "123456"})
    assert response.status_code == 422 and not signed_in(client)
    assert counts(analyst) == (1, 1)
    response = client.post(VERIFY, {"otp_code": codes[0]})
    assert response.status_code == 302 and signed_in(client)
    assert client.session["sign_in_factors"] == ["password", "recovery_code"]
    # Nothing at all is not an attempt.
    client.logout()
    password_step(client, analyst.username)
    response = client.post(VERIFY, {})
    assert response.status_code == 422 and b"Use your security key, or enter a code." in (
        response.content
    )
    assert counts(analyst) == (0, 0)


def test_owner_changes_can_be_confirmed_with_a_key(analyst):
    key, first_codes = enable_with_key(analyst)
    client = owner_client(analyst)
    # Without a second factor nothing changes.
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "codes"})
    assert response.status_code == 422
    response = client.post(
        PAGE,
        {
            "current_password": PASSWORD,
            "action": "codes",
            "security_key_response": confirm_with(client, key),
        },
    )
    assert response.status_code == 200 and len(response.context["codes"]) == 10
    assert not RecoveryCode.objects.filter(user=analyst, digest__in=first_codes).exists()
    # The confirmation challenge is answered once.
    spent = confirm_with(client, key)
    data = {"current_password": PASSWORD, "action": "codes", "security_key_response": spent}
    assert client.post(PAGE, data).status_code == 200
    assert CONFIRM_CEREMONY not in client.session or client.session[CONFIRM_CEREMONY]
    response = client.post(PAGE, data)
    assert response.status_code == 422 and b"request expired" in response.content
    assert counts(analyst) == (0, 0)
    # A wrong password with a good key changes nothing and counts the password.
    data = {
        "current_password": "wrong",
        "action": "codes",
        "security_key_response": confirm_with(client, key),
    }
    assert client.post(PAGE, data).status_code == 422


def test_a_second_key_needs_a_second_factor_and_keeps_the_codes(analyst):
    key, codes = enable_with_key(analyst)
    client = owner_client(analyst)
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "add_key"})
    assert response.status_code == 422 and PENDING_KEY not in client.session
    second = SoftKey()
    proof = {"security_key_response": confirm_with(client, key)}
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "add_key", **proof})
    assert response.status_code == 302
    page = client.get(ADD)
    options = page.context["key_options"]
    assert [c["id"] for c in options["excludeCredentials"]] == [
        security_keys.bytes_to_base64url(key.credential_id)
    ]
    assert options["user"]["id"] == key.user_handle  # One handle for the owner's keys.
    # A name already used is refused; a new challenge is offered for the next try.
    response = client.post(
        ADD, {"name": "synthetic KEY a", "security_key_response": second.register(options)}
    )
    assert response.status_code == 422 and b"already have a key with this name" in (
        response.content
    )
    options = client.get(ADD).context["key_options"]
    response = client.post(
        ADD, {"name": "Synthetic key B", "security_key_response": second.register(options)}
    )
    assert response.status_code == 302 and response["Location"] == PAGE
    assert SecurityKey.objects.filter(user=analyst).count() == 2
    assert RecoveryCode.objects.filter(user=analyst, used_at=None).count() == len(codes)
    assert AuditEvent.objects.filter(action="account.security_key_added").count() == 1
    # The same key cannot be registered twice.
    proof = {"security_key_response": confirm_with(client, key)}
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key", **proof})
    options = client.get(ADD).context["key_options"]
    response = client.post(
        ADD, {"name": "Synthetic key C", "security_key_response": second.register(options)}
    )
    assert response.status_code == 422 and b"already registered" in response.content


def test_registration_must_answer_its_own_challenge_at_this_site(analyst):
    client = owner_client(analyst)
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key"})
    options = client.get(ADD).context["key_options"]
    for answer in (
        {"origin": "https://testserver.example"},
        {"rp_id": "example.test"},
    ):
        response = client.post(
            ADD,
            {"name": "Synthetic", "security_key_response": SoftKey().register(options, **answer)},
        )
        assert response.status_code == 422 and b"was not accepted" in response.content
    stale = dict(options, challenge=security_keys.bytes_to_base64url(b"0" * 32))
    response = client.post(
        ADD, {"name": "Synthetic", "security_key_response": SoftKey().register(stale)}
    )
    assert response.status_code == 422
    # No answer at all: the browser did not return a key.
    response = client.post(ADD, {"name": "Synthetic"})
    assert response.status_code == 422 and b"did not return the new key" in response.content
    assert not SecurityKey.objects.exists() and not two_factor.enabled(analyst)
    # The registration expires, and ends when the account changes meanwhile.
    session = client.session
    session[PENDING_KEY] = dict(session[PENDING_KEY], issued=0)
    session.save()
    assert client.get(ADD)["Location"] == PAGE
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key"})
    options = client.get(ADD).context["key_options"]
    get_user_model().objects.filter(pk=analyst.pk).update(session_epoch=99)
    client.force_login(fresh(analyst))
    session = client.session
    response = client.post(ADD, {"name": "Synthetic", "security_key_response": "{}"})
    assert response.status_code == 302 and not SecurityKey.objects.exists()


def test_removing_keys_and_the_last_factor(analyst, settings):
    key, _codes = enable_with_key(analyst)
    client = owner_client(analyst)
    second = SoftKey()
    proof = {"security_key_response": confirm_with(client, key)}
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key", **proof})
    options = client.get(ADD).context["key_options"]
    client.post(ADD, {"name": "Synthetic key B", "security_key_response": second.register(options)})
    first_pk = SecurityKey.objects.get(user=analyst, name="Synthetic key A").pk
    second_pk = SecurityKey.objects.get(user=analyst, name="Synthetic key B").pk

    # The key being removed may confirm its own removal.
    data = {
        "current_password": PASSWORD,
        "action": f"remove_key:{first_pk}",
        "security_key_response": confirm_with(client, key),
    }
    assert client.post(PAGE, data).status_code == 302
    assert list(SecurityKey.objects.filter(user=analyst).values_list("pk", flat=True)) == [
        second_pk
    ]
    assert AuditEvent.objects.filter(action="account.security_key_removed").count() == 1
    # Another account's key is not offered and cannot be removed.
    other = make_user("other.keys", ["analyst"])
    enable_with_key(other)
    other_pk = SecurityKey.objects.get(user=other).pk
    data = {
        "current_password": PASSWORD,
        "action": f"remove_key:{other_pk}",
        "security_key_response": confirm_with(client, second),
    }
    assert client.post(PAGE, data).status_code == 422
    assert SecurityKey.objects.filter(pk=other_pk).exists()

    # The last factor: refused while required, otherwise two-factor sign-in turns off.
    settings.MFA_REQUIRED_ROLES = frozenset({"analyst"})
    data = {
        "current_password": PASSWORD,
        "action": f"remove_key:{second_pk}",
        "security_key_response": confirm_with(client, second),
    }
    response = client.post(PAGE, data)
    assert response.status_code == 422 and SecurityKey.objects.filter(pk=second_pk).exists()
    settings.MFA_REQUIRED_ROLES = frozenset()
    data["security_key_response"] = confirm_with(client, second)
    assert client.post(PAGE, data).status_code == 302
    assert not two_factor.enabled(analyst)
    assert not RecoveryCode.objects.filter(user=analyst).exists()
    event = AuditEvent.objects.filter(action="account.two_factor_disabled").get()
    assert event.after["two_factor"] is False and "last second factor" in event.reason


def test_app_and_keys_side_by_side(analyst):
    key, _codes = enable_with_key(analyst)
    client = owner_client(analyst)
    proof = {"security_key_response": confirm_with(client, key)}
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "setup", **proof})
    assert response.status_code == 302 and response["Location"] == SETUP
    device = TOTPDevice.objects.get(user=analyst, confirmed=False)
    from accounts.tests.test_two_factor import code

    response = client.post(SETUP, {"otp_code": code(device)})
    assert response.status_code == 200
    assert AuditEvent.objects.filter(action="account.authenticator_added").count() == 1
    assert two_factor.has_app(analyst) and two_factor.has_keys(analyst)
    # Sign-in offers both.
    signer = Client()
    password_step(signer, analyst.username)
    page = signer.get(VERIFY)
    assert b"Use your security key" in page.content
    assert b"Code" in page.content and b"authenticator app" in page.content
    # The app can go while a key remains.
    proof = {"security_key_response": confirm_with(client, key)}
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "remove_app", **proof})
    assert response.status_code == 302
    assert not two_factor.has_app(analyst) and two_factor.enabled(analyst)
    assert AuditEvent.objects.filter(action="account.authenticator_removed").count() == 1


def test_required_role_is_satisfied_by_a_key(analyst, settings):
    settings.MFA_REQUIRED_ROLES = frozenset({"analyst"})
    client = owner_client(analyst)
    assert client.get("/")["Location"] == PAGE
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key"})
    page = client.get(ADD)  # Reachable while the workspace is closed.
    assert page.status_code == 200 and b"Register the key" in page.content
    response = client.post(
        ADD,
        {
            "name": "Synthetic key A",
            "security_key_response": SoftKey().register(page.context["key_options"]),
        },
    )
    assert response.status_code == 200
    assert client.get("/").status_code == 200


def test_shared_demonstration_account_cannot_add_keys(analyst):
    get_user_model().objects.filter(pk=analyst.pk).update(credentials_locked=True)
    client = owner_client(fresh(analyst))
    page = client.get(PAGE)
    assert b"Set up with a security key" not in page.content
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "add_key"})
    assert response.status_code == 403 and PENDING_KEY not in client.session
    with pytest.raises(Exception, match="shared demonstration"):
        two_factor.begin_key_registration(
            actor=fresh(analyst),
            current_password=PASSWORD,
            rp=security_keys.RelyingParty("testserver", "http://testserver"),
        )


def test_an_ip_address_host_offers_no_keys(analyst, settings):
    settings.ALLOWED_HOSTS = ["127.0.0.1", "testserver"]
    client = Client(HTTP_HOST="127.0.0.1")
    client.force_login(analyst)
    page = client.get(PAGE)
    assert b"not by an IP address" in page.content
    assert b"Set up with a security key" not in page.content
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "add_key"})
    assert response.status_code == 422 and b"not by an IP address" in response.content
    # Keys registered at the host name are not offered at the address; codes still work.
    _key, codes = enable_with_key(analyst)
    signer = Client(HTTP_HOST="127.0.0.1")
    password_step(signer, analyst.username)
    page = signer.get(VERIFY)
    assert "key_options" not in page.context and b"cannot be used at this address" in (page.content)
    assert signer.post(VERIFY, {"otp_code": codes[0]}).status_code == 302


def test_administrator_reset_removes_keys(analyst, manager):
    enable_with_key(analyst)
    client = owner_client(manager)
    detail = client.get(reverse("accounts:user_detail", args=[analyst.pk]))
    assert b"1 security key;" in detail.content
    response = client.post(
        reverse("accounts:user_action", args=[analyst.pk, "reset_two_factor"]),
        {
            "revision": fresh(analyst).management_revision,
            "reason": "Synthetic lost key, identity verified",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    assert not SecurityKey.objects.filter(user=analyst).exists()
    assert not RecoveryCode.objects.filter(user=analyst).exists()
    event = AuditEvent.objects.get(action="account.reset_two_factor")
    assert event.before["security_keys"] == 1 and event.after["security_keys"] == 0
    assert ElectronicSignature.objects.filter(audit_event=event).exists()


def test_signature_records_a_key_sign_in(manager):
    key, _codes = enable_with_key(manager)
    client = Client()
    password_step(client, manager.username)
    assert key_step(client, key).status_code == 302
    target = make_user("target.keys", ["analyst"])
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
    assert signature.authentication_context["sign_in_factors"] == ["password", "security_key"]


def test_pages_load_their_script_without_inline_code(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    for response in (client.get(VERIFY),):
        html = response.content.decode()
        scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
        for attrs, _body in scripts:
            assert "src=" in attrs or 'type="application/json"' in attrs, attrs
        assert "security-keys" in html and 'id="security-key-options"' in html
    key_step(client, key)
    for response in (client.get(PAGE),):
        assert 'id="security-key-options"' in response.content.decode()


def test_options_and_responses_stay_out_of_audit_and_logs(analyst, caplog):
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    key_step(client, key, tamper=True)
    stored = SecurityKey.objects.get(user=analyst)
    text = json.dumps([[e.before, e.after, e.reason] for e in AuditEvent.objects.all()])
    text += caplog.text
    for secret in (bytes(stored.public_key).hex(), key.credential_id.hex(), stored.last_challenge):
        if secret:
            assert secret not in text


def test_verify_assertion_needs_the_account_lock_transaction(analyst):
    """verify_assertion locks the key row; called inside the caller's transaction."""
    key, _codes = enable_with_key(analyst)
    user = fresh(analyst)
    ceremony = security_keys.begin(
        security_keys.RelyingParty("testserver", "http://testserver"), "confirm", user.pk
    )
    assertion = security_keys.KeyAssertion(
        key.answer(security_keys.request_options(user, ceremony)), ceremony
    )
    with pytest.raises(security_keys.KeyRefused), transaction.atomic():
        security_keys.verify_assertion(user, assertion, purpose="sign_in")  # Wrong purpose.
    with transaction.atomic():
        assert security_keys.verify_assertion(user, assertion, purpose="confirm").pk
    assert repr(assertion) == "<KeyAssertion>"


def test_answers_to_a_replaced_challenge_are_refused_without_counting(analyst):
    """A second tab or a reload replaces the challenge; the genuine key's answer to the earlier
    page is refused as expired and not counted, and the current page still works."""
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    first = client.get(VERIFY).context["key_options"]
    second = client.get(VERIFY).context["key_options"]
    response = client.post(VERIFY, {"security_key_response": key.answer(first)})
    assert response.status_code == 422 and b"request expired" in response.content
    assert counts(analyst) == (0, 0) and not signed_in(client)
    # The same answer sent twice: the second finds no challenge; nothing is counted.
    owner = owner_client(analyst)
    answer = confirm_with(owner, key)
    data = {"current_password": PASSWORD, "action": "codes", "security_key_response": answer}
    assert owner.post(PAGE, data).status_code == 200
    response = owner.post(PAGE, data)
    assert response.status_code == 422 and counts(analyst) == (0, 0)
    assert second["challenge"] != first["challenge"]
    assert key_step(client, key).status_code == 302  # A fresh page signs in.


def test_registration_refuses_an_oversized_credential_id(analyst):
    client = owner_client(analyst)
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key"})
    options = client.get(ADD).context["key_options"]
    key = SoftKey()
    key.credential_id = bytes(1100)
    response = client.post(
        ADD, {"name": "Synthetic", "security_key_response": key.register(options)}
    )
    assert response.status_code == 422 and b"was not accepted" in response.content
    assert not SecurityKey.objects.exists()


def test_names_are_compared_as_the_database_compares_them(analyst):
    """Python and PostgreSQL fold some letters differently ("İ"); the database decides."""
    key, _codes = enable_with_key(analyst, name="Synthetic key i")
    client = owner_client(analyst)
    proof = {"security_key_response": confirm_with(client, key)}
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key", **proof})
    options = client.get(ADD).context["key_options"]
    response = client.post(
        ADD, {"name": "Synthetic key İ", "security_key_response": SoftKey().register(options)}
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT lower(%s) = lower(%s)", ["Synthetic key i", "Synthetic key İ"])
        folded_equal = cursor.fetchone()[0]
    if folded_equal:
        assert response.status_code == 422 and b"already have a key with this name" in (
            response.content
        )
    else:
        assert response.status_code == 302


def test_registration_is_refused_once_the_second_factor_stopped(analyst):
    key, _codes = enable_with_key(analyst)
    client = owner_client(analyst)
    proof = {"security_key_response": confirm_with(client, key)}
    client.post(PAGE, {"current_password": PASSWORD, "action": "add_key", **proof})
    options = client.get(ADD).context["key_options"]
    LoginThrottle.objects.update_or_create(
        user=analyst, defaults={"code_failures": two_factor.CODE_FAILURE_LIMIT}
    )
    response = client.post(
        ADD, {"name": "Synthetic key B", "security_key_response": SoftKey().register(options)}
    )
    assert response.status_code == 422 and b"stopped for this account" in response.content
    assert SecurityKey.objects.filter(user=analyst).count() == 1


def test_enter_on_the_owner_page_presses_no_action(analyst):
    """The disabled guard is the change form's first submit button in page order, so the
    browser's implicit submission (Enter) presses nothing, never Remove."""
    enable_with_key(analyst)
    html = owner_client(analyst).get(PAGE).content.decode()
    buttons = re.findall(r"<button\b[^>]*>", html)
    for_form = [
        b
        for b in buttons
        if 'type="submit"' in b and ('form="two-factor-change"' in b or 'name="action"' in b)
    ]
    assert "data-default-guard" in for_form[0] and "disabled" in for_form[0]
    assert html.index("data-default-guard") < html.index('id="two-factor-change"')


def test_an_app_setup_confirmed_after_the_stop_does_not_clear_it(analyst):
    """A setup started before 100 failures stopped the second factor cannot finish after it:
    only an administrator's reset clears the stop."""
    from accounts.tests.test_two_factor import code

    key, _codes = enable_with_key(analyst)
    client = owner_client(analyst)
    proof = {"security_key_response": confirm_with(client, key)}
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "setup", **proof})
    assert response.status_code == 302 and response["Location"] == SETUP
    device = TOTPDevice.objects.get(user=analyst, confirmed=False)
    LoginThrottle.objects.update_or_create(
        user=analyst, defaults={"code_failures": two_factor.CODE_FAILURE_LIMIT}
    )
    response = client.post(SETUP, {"otp_code": code(device)})
    assert response.status_code == 422 and b"stopped for this account" in response.content
    assert two_factor.stopped(analyst) and not two_factor.has_app(analyst)


def test_an_answer_whose_challenge_is_not_text_is_refused_and_counted(analyst):
    key, _codes = enable_with_key(analyst)
    client = Client()
    password_step(client, analyst.username)
    options = client.get(VERIFY).context["key_options"]
    answer = json.loads(key.answer(options))
    client_data = {"type": "webauthn.get", "challenge": 12, "origin": "http://testserver"}
    answer["response"]["clientDataJSON"] = security_keys.bytes_to_base64url(
        json.dumps(client_data).encode()
    )
    response = client.post(VERIFY, {"security_key_response": json.dumps(answer)})
    assert response.status_code == 422 and b"The security key was not accepted." in (
        response.content
    )
    assert counts(analyst) == (1, 1)
