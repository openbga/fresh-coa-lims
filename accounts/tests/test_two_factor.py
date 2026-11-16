"""Two-factor sign-in: setup, the second sign-in step, recovery codes, requirement and resets."""

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.conf import settings
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts import two_factor
from accounts.models import LoginThrottle, RecoveryCode
from accounts.views import PENDING_SETUP, PENDING_SIGN_IN
from config.security import CREDENTIAL_FIELDS
from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-two-factor-pass-318!"
PIN = "73519246"
LOGIN = "/accounts/login/"
VERIFY = "/accounts/login/verify/"
PAGE = "/accounts/two-factor/"
SETUP = "/accounts/two-factor/setup/"


def make_user(username, roles=(), **extra):
    user = get_user_model().objects.create_user(
        username=username, password=PASSWORD, first_name="Synthetic", last_name=username, **extra
    )
    user.groups.set([Group.objects.get_or_create(name=role)[0] for role in roles])
    return user


def fresh(user):
    return get_user_model().objects.get(pk=user.pk)


def code(device, steps=0):
    """The code the app shows now (steps=0) or that many 30-second steps later."""
    device = TOTPDevice.objects.get(pk=device.pk)
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time() + steps * device.step
    return f"{totp.token():06d}"


def used_code(device):
    """The code of the last time step the device accepted: refused from then on."""
    device = TOTPDevice.objects.get(pk=device.pk)
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, 0)
    totp.time = device.last_t * device.step + device.t0
    return f"{totp.token():06d}"


def enable(user):
    """Set up two-factor sign-in through the owner's pages; returns (device, recovery codes)."""
    client = Client()
    client.force_login(user)
    response = client.post(PAGE, {"current_password": PASSWORD, "action": "setup"})
    assert response.status_code == 302 and response["Location"] == SETUP
    device = TOTPDevice.objects.get(user=user, confirmed=False)
    response = client.post(SETUP, {"otp_code": code(device)})
    assert response.status_code == 200, response.content
    return TOTPDevice.objects.get(pk=device.pk), list(response.context["codes"])


def password_step(client, username, next_url=""):
    data = {"username": username, "password": PASSWORD}
    if next_url:
        data["next"] = next_url
    return client.post(LOGIN, data)


def signed_in(client):
    return "_auth_user_id" in client.session


@pytest.fixture
def analyst():
    return make_user("analyst.test", ["analyst"])


@pytest.fixture
def manager():
    user = make_user("manager.test", ["admin"])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


def test_setup_turns_on_two_factor_and_shows_recovery_codes_once(analyst):
    client = Client()
    client.force_login(analyst)
    other = Client()
    other.force_login(analyst)
    page = client.get(PAGE)
    assert page.status_code == 200 and page.context["state"]["enabled"] is False
    assert b"Set up two-factor sign-in" in page.content

    refused = client.post(PAGE, {"current_password": "wrong-password", "action": "setup"})
    assert refused.status_code == 422
    assert b"Current password was not accepted." in refused.content
    assert LoginThrottle.objects.get(user=analyst).failures == 1
    assert not TOTPDevice.objects.exists()

    response = client.post(PAGE, {"current_password": PASSWORD, "action": "setup"})
    assert response["Location"] == SETUP
    assert LoginThrottle.objects.get(user=analyst).failures == 0
    device = TOTPDevice.objects.get(user=analyst)
    assert device.confirmed is False
    setup = client.get(SETUP)
    assert setup.status_code == 200
    assert b"<svg" in setup.content and b'class="vr-qr"' in setup.content
    assert str(setup.context["secret_key"]) == two_factor.secret_key(device)
    assert repr(setup.context["secret_key"]) == "<concealed>"
    # Nothing changes for sign-in before the key is confirmed.
    assert not two_factor.enabled(analyst)

    wrong = client.post(SETUP, {"otp_code": "000000" if code(device) != "000000" else "111111"})
    assert wrong.status_code == 422
    assert b"The code was not accepted." in wrong.content
    assert LoginThrottle.objects.get(user=analyst).failures == 1
    assert client.post(SETUP, {"otp_code": "12345"}).status_code == 422  # Wrong shape, not counted.
    assert LoginThrottle.objects.get(user=analyst).failures == 1

    done = client.post(SETUP, {"otp_code": code(device)})
    assert done.status_code == 200
    codes = done.context["codes"]
    assert len(codes) == two_factor.RECOVERY_CODE_COUNT == len(set(codes))
    assert all(len(c.replace("-", "")) == two_factor.RECOVERY_CODE_LENGTH for c in codes)
    assert b"This is the only time these codes are shown." in done.content
    assert TOTPDevice.objects.get(pk=device.pk).confirmed is True
    stored = list(RecoveryCode.objects.filter(user=analyst).values_list("digest", flat=True))
    assert len(stored) == 10 and not set(stored) & {c.replace("-", "") for c in codes}
    event = AuditEvent.objects.get(action="account.two_factor_enabled")
    assert event.actor == analyst and event.after["two_factor"] is True
    assert event.before["two_factor"] is False and event.after["recovery_codes_left"] == 10
    # This session continues; the other session must sign in again.
    assert client.get(PAGE).status_code == 200 and signed_in(client)
    # The session keeps what its sign-in proved: the password only.
    assert client.session["sign_in_factors"] == ["password"]
    assert other.get(PAGE).status_code == 302 and not signed_in(other)
    # The setup page cannot be replayed once the key is confirmed.
    assert client.get(SETUP)["Location"] == PAGE


def test_sign_in_waits_for_the_second_factor(analyst):
    device, _ = enable(analyst)
    client = Client()
    response = password_step(client, analyst.username, "/accounts/access/")
    assert response.status_code == 302 and response["Location"] == VERIFY
    assert not signed_in(client)
    assert client.get("/accounts/access/").status_code == 302  # Not signed in yet.
    page = client.get(VERIFY)
    assert page.status_code == 200 and b"Verify and sign in" in page.content

    assert client.post(VERIFY, {"otp_code": "not a code"}).status_code == 422
    assert not LoginThrottle.objects.filter(user=analyst, failures__gt=0).exists()
    wrong = "000000" if code(device) != "000000" else "111111"
    response = client.post(VERIFY, {"otp_code": wrong})
    assert response.status_code == 422 and b"The code was not accepted." in response.content
    assert LoginThrottle.objects.get(user=analyst).failures == 1
    assert not signed_in(client)

    # The code that confirmed the setup was used already; the app's next code signs in.
    assert client.post(VERIFY, {"otp_code": used_code(device)}).status_code == 422
    response = client.post(VERIFY, {"otp_code": code(device, 1)})
    assert response.status_code == 302 and response["Location"] == "/accounts/access/"
    assert signed_in(client)
    assert client.session["sign_in_factors"] == ["password", "totp"]
    assert PENDING_SIGN_IN not in client.session
    assert LoginThrottle.objects.get(user=analyst).failures == 0
    assert fresh(analyst).last_login is not None

    # The same code is refused at the next sign-in (one use per time step).
    replay = Client()
    password_step(replay, analyst.username)
    assert replay.post(VERIFY, {"otp_code": used_code(device)}).status_code == 422
    assert not signed_in(replay)
    # The code of the next time step is still accepted.
    assert replay.post(VERIFY, {"otp_code": code(device, 1)}).status_code == 302
    assert signed_in(replay)


def test_account_without_two_factor_signs_in_with_the_password(analyst):
    client = Client()
    response = password_step(client, analyst.username)
    assert response.status_code == 302 and response["Location"] == "/"
    assert signed_in(client) and client.session["sign_in_factors"] == ["password"]
    assert client.get(VERIFY)["Location"] == LOGIN


def test_recovery_code_signs_in_once(analyst):
    device, codes = enable(analyst)
    client = Client()
    password_step(client, analyst.username)
    typed = codes[0].replace("-", " ").lower().replace("0", "o")
    response = client.post(VERIFY, {"otp_code": typed}, follow=True)
    assert signed_in(client)
    assert client.session["sign_in_factors"] == ["password", "recovery_code"]
    assert b"You signed in with a recovery code. 9 unused recovery codes left." in response.content
    event = AuditEvent.objects.get(action="account.recovery_code_used")
    assert event.actor == analyst and event.after["recovery_codes_left"] == 9
    assert codes[0] not in json.dumps([event.before, event.after, event.reason])

    again = Client()
    password_step(again, analyst.username)
    assert again.post(VERIFY, {"otp_code": codes[0]}).status_code == 422
    assert not signed_in(again)
    assert LoginThrottle.objects.get(user=analyst).failures == 1
    # A code of another account is refused too.
    other = make_user("reviewer.test", ["reviewer"])
    _, other_codes = enable(other)
    assert again.post(VERIFY, {"otp_code": other_codes[0]}).status_code == 422
    assert again.post(VERIFY, {"otp_code": codes[1]}).status_code == 302


def test_lock_after_repeated_wrong_codes_refuses_the_correct_code(analyst):
    device, codes = enable(analyst)
    client = Client()
    password_step(client, analyst.username)
    wrong = "000000" if code(device) != "000000" else "111111"
    for _ in range(settings.LOGIN_FAILURE_LIMIT):
        assert client.post(VERIFY, {"otp_code": wrong}).status_code == 422
    assert LoginThrottle.objects.get(user=analyst).locked_until > timezone.now()
    assert client.post(VERIFY, {"otp_code": code(device)}).status_code == 422
    assert client.post(VERIFY, {"otp_code": codes[0]}).status_code == 422
    assert not signed_in(client)
    assert RecoveryCode.objects.filter(user=analyst, used_at=None).count() == 10
    # The password step is locked as well.
    assert (
        Client().post(LOGIN, {"username": analyst.username, "password": PASSWORD}).status_code
        == 200
    )


@pytest.mark.parametrize("change", ["expired", "epoch", "password", "deactivated", "removed"])
def test_pending_sign_in_restarts_when_stale(analyst, change):
    device, _ = enable(analyst)
    client = Client()
    password_step(client, analyst.username)
    user = fresh(analyst)
    if change == "expired":
        session = client.session
        session[PENDING_SIGN_IN]["started"] -= settings.MFA_PENDING_SECONDS + 1
        session.save()
    elif change == "epoch":
        user.session_epoch += 1
        user.save(update_fields=["session_epoch"])
    elif change == "password":
        user.set_password("Another-synthetic-pass-552!")
        user.save(update_fields=["password"])
    elif change == "deactivated":
        user.is_active = False
        user.save(update_fields=["is_active"])
    token = code(device, 1)
    if change == "removed":
        two_factor.remove(user)
    response = client.post(VERIFY, {"otp_code": token})
    assert response.status_code == 302 and response["Location"] == LOGIN
    assert not signed_in(client) and PENDING_SIGN_IN not in client.session
    assert not LoginThrottle.objects.filter(user=analyst, failures__gt=0).exists()


def test_opening_sign_in_again_drops_the_pending_step(analyst):
    enable(analyst)
    client = Client()
    password_step(client, analyst.username)
    assert PENDING_SIGN_IN in client.session
    client.get(LOGIN)
    assert PENDING_SIGN_IN not in client.session
    assert client.get(VERIFY)["Location"] == LOGIN


def test_concurrent_submissions_of_one_code_sign_in_once(analyst):
    device, _ = enable(analyst)
    clients = [Client(), Client()]
    for client in clients:
        password_step(client, analyst.username)
    token = code(device, 1)
    barrier = Barrier(2)

    def submit(client):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return client.post(VERIFY, {"otp_code": token}).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(2) as pool:
        statuses = sorted(pool.map(submit, clients))
    assert statuses == [302, 422]


def test_owner_changes_need_password_and_a_current_code(analyst):
    device, codes = enable(analyst)
    client = Client()
    client.force_login(analyst)
    wrong = "000000" if code(device, 1) != "000000" else "111111"
    for action in ("codes", "setup", "disable"):
        missing = client.post(PAGE, {"current_password": PASSWORD, "action": action})
        assert missing.status_code == 422
        refused = client.post(
            PAGE, {"current_password": PASSWORD, "otp_code": wrong, "action": action}
        )
        assert refused.status_code == 422 and b"The code was not accepted." in refused.content
    assert LoginThrottle.objects.get(user=analyst).failures == 3
    assert two_factor.enabled(analyst) and RecoveryCode.objects.filter(user=analyst).count() == 10

    response = client.post(
        PAGE, {"current_password": PASSWORD, "otp_code": code(device, 1), "action": "codes"}
    )
    assert response.status_code == 200
    new_codes = response.context["codes"]
    assert not set(new_codes) & set(codes)
    assert AuditEvent.objects.filter(action="account.recovery_codes_replaced").count() == 1
    # Old codes no longer sign in; new ones do.
    old = Client()
    password_step(old, analyst.username)
    assert old.post(VERIFY, {"otp_code": codes[0]}).status_code == 422
    assert old.post(VERIFY, {"otp_code": new_codes[0]}).status_code == 302


def test_new_authenticator_replaces_the_old_one_only_when_confirmed(analyst):
    old_device, codes = enable(analyst)
    client = Client()
    client.force_login(analyst)
    response = client.post(
        PAGE, {"current_password": PASSWORD, "otp_code": codes[0], "action": "setup"}
    )
    assert response["Location"] == SETUP
    new_device = TOTPDevice.objects.get(user=analyst, confirmed=False)
    assert new_device.key != old_device.key
    assert b"keeps working until you confirm" in client.get(SETUP).content
    # The old app still signs in until the new key is confirmed.
    other = Client()
    password_step(other, analyst.username)
    assert other.post(VERIFY, {"otp_code": code(old_device, 1)}).status_code == 302

    done = client.post(SETUP, {"otp_code": code(new_device)})
    assert done.status_code == 200
    assert list(TOTPDevice.objects.filter(user=analyst).values_list("pk", flat=True)) == [
        new_device.pk
    ]
    assert AuditEvent.objects.filter(action="account.two_factor_replaced").count() == 1
    assert not set(done.context["codes"]) & set(codes)
    assert other.get(PAGE).status_code == 302  # Other sessions sign in again.


def test_setup_expires_and_is_bound_to_its_owner(analyst):
    client = Client()
    client.force_login(analyst)
    client.post(PAGE, {"current_password": PASSWORD, "action": "setup"})
    device = TOTPDevice.objects.get(user=analyst)
    token = code(device)
    intruder = make_user("intruder.test", ["analyst"])
    with pytest.raises(ValidationError, match="Setup expired"):
        two_factor.confirm_setup(actor=intruder, device_pk=device.pk, code=token)
    TOTPDevice.objects.filter(pk=device.pk).update(
        created_at=timezone.now() - timedelta(seconds=two_factor.SETUP_SECONDS + 1)
    )
    with pytest.raises(ValidationError, match="Setup expired"):
        two_factor.confirm_setup(actor=analyst, device_pk=device.pk, code=token)
    assert client.get(SETUP)["Location"] == PAGE
    assert PENDING_SETUP not in client.session
    assert not TOTPDevice.objects.filter(pk=device.pk).exists()
    assert not two_factor.enabled(analyst)


def test_turning_off_is_refused_when_required(analyst, settings):
    device, codes = enable(analyst)
    client = Client()
    client.force_login(analyst)
    settings.MFA_REQUIRED_ROLES = frozenset({"analyst"})
    page = client.get(PAGE)
    assert b'value="disable"' not in page.content
    with pytest.raises(PermissionDenied, match="required for your account"):
        two_factor.disable(actor=analyst, current_password=PASSWORD, code=codes[0])
    assert RecoveryCode.objects.filter(user=analyst, used_at=None).count() == 10  # Not spent.
    settings.MFA_REQUIRED_ROLES = frozenset()
    response = client.post(
        PAGE, {"current_password": PASSWORD, "otp_code": code(device, 1), "action": "disable"}
    )
    assert response.status_code == 302
    assert not TOTPDevice.objects.filter(user=analyst).exists()
    assert not RecoveryCode.objects.filter(user=analyst).exists()
    event = AuditEvent.objects.get(action="account.two_factor_disabled")
    assert event.before["two_factor"] is True and event.after["two_factor"] is False
    assert signed_in(client) and client.session["sign_in_factors"] == ["password"]
    signed = Client()
    assert password_step(signed, analyst.username)["Location"] == "/"


def test_required_roles_keep_the_workspace_closed_until_set_up(analyst, settings):
    settings.MFA_REQUIRED_ROLES = frozenset({"analyst"})
    client = Client()
    password_step(client, analyst.username)
    assert signed_in(client)
    for url in ("/", "/accounts/access/", "/testing/"):
        response = client.get(url)
        assert response.status_code == 302 and response["Location"] == PAGE, url
    page = client.get(PAGE)
    assert page.status_code == 200
    assert b"Set up two-factor sign-in before continuing." in page.content
    assert client.get(reverse("pagedocs:doc"), {"path": PAGE}).status_code == 200
    assert client.get("/health/").status_code == 200
    # Password replacement comes first when both are due.
    get_user_model().objects.filter(pk=analyst.pk).update(password_change_required=True)
    assert client.get("/")["Location"] == reverse("accounts:password_change")
    get_user_model().objects.filter(pk=analyst.pk).update(password_change_required=False)
    # Other roles are not required.
    reviewer = make_user("reviewer.test", ["reviewer"])
    other = Client()
    other.force_login(reviewer)
    assert other.get("/accounts/access/").status_code == 200
    settings.MFA_REQUIRED_ROLES = frozenset({"all"})
    assert other.get("/accounts/access/")["Location"] == PAGE
    # Once set up, the workspace opens.
    enable(analyst)
    client = Client()
    password_step(client, analyst.username)
    device = TOTPDevice.objects.get(user=analyst)
    client.post(VERIFY, {"otp_code": code(device, 1)})
    assert client.get("/accounts/access/").status_code == 200


def test_shared_demonstration_account_cannot_set_up(analyst, settings):
    get_user_model().objects.filter(pk=analyst.pk).update(credentials_locked=True)
    settings.MFA_REQUIRED_ROLES = frozenset({"all"})
    client = Client()
    client.force_login(analyst)
    assert client.get("/accounts/access/").status_code == 200  # Not required.
    page = client.get(PAGE)
    assert b"shared demonstration account" in page.content
    assert b'name="current_password"' not in page.content
    assert client.post(PAGE, {"current_password": PASSWORD, "action": "setup"}).status_code == 403
    with pytest.raises(PermissionDenied):
        two_factor.begin_setup(actor=fresh(analyst), current_password=PASSWORD)
    assert not TOTPDevice.objects.exists()


def test_administrator_reset_is_signed_and_not_for_oneself(analyst, manager):
    enable(analyst)
    client = Client()
    client.force_login(manager)
    detail = client.get(reverse("accounts:user_detail", args=[analyst.pk]))
    url = reverse("accounts:user_action", args=[analyst.pk, "reset_two_factor"])
    assert url.encode() in detail.content and b"On since" in detail.content
    listing = client.get(reverse("accounts:user_list"), {"two_factor": "on"})
    assert [u.username for u in listing.context["page"]] == [analyst.username]
    payload = {
        "revision": fresh(analyst).management_revision,
        "reason": "Synthetic lost phone, identity verified",
        "signature_username": manager.username,
        "pin": PIN,
    }
    response = client.post(url, payload)
    assert response.status_code == 302
    assert not TOTPDevice.objects.filter(user=analyst).exists()
    assert not RecoveryCode.objects.filter(user=analyst).exists()
    event = AuditEvent.objects.get(action="account.reset_two_factor")
    assert event.actor == manager and event.before["two_factor"] is True
    signature = ElectronicSignature.objects.get(audit_event=event)
    assert signature.meaning == "account_authorized"
    assert signature.authentication_context["sign_in_factors"] == ["password"]
    assert fresh(analyst).session_epoch > analyst.session_epoch
    assert client.get(url).context["unavailable"] == (
        "This account has not set up two-factor sign-in."
    )

    enable(manager)
    own = reverse("accounts:user_action", args=[manager.pk, "reset_two_factor"])
    manager_client = Client()
    manager_client.force_login(manager)
    assert (
        own.encode()
        not in manager_client.get(reverse("accounts:user_detail", args=[manager.pk])).content
    )
    assert "own two-factor" in manager_client.get(own).context["unavailable"]
    payload["revision"] = fresh(manager).management_revision
    assert manager_client.post(own, payload).status_code == 403
    assert two_factor.enabled(manager)


def test_operator_command_resets_with_attribution(analyst, manager):
    enable(analyst)
    with pytest.raises(CommandError, match="Only active account administrators"):
        call_command("reset_two_factor", analyst.username, actor=analyst.username, reason="Test")
    call_command(
        "reset_two_factor", analyst.username, actor=manager.username, reason="Synthetic recovery"
    )
    assert not two_factor.set_up_anything(analyst)
    event = AuditEvent.objects.get(action="account.reset_two_factor")
    assert event.actor == manager and event.reason == "Synthetic recovery"
    with pytest.raises(CommandError, match="has not set up"):
        call_command("reset_two_factor", analyst.username, actor=manager.username, reason="Again")


def test_secrets_stay_out_of_audit_signatures_and_admin(analyst, manager):
    device, codes = enable(analyst)
    client = Client()
    client.force_login(analyst)
    response = client.post(
        PAGE, {"current_password": PASSWORD, "otp_code": code(device, 1), "action": "codes"}
    )
    codes += response.context["codes"]
    secrets = [device.key, two_factor.secret_key(device).replace(" ", "")]
    secrets += [c.replace("-", "") for c in codes] + codes
    payloads = []
    for event in AuditEvent.objects.all():
        payloads.extend([event.before, event.after, event.reason])
    for signature in ElectronicSignature.objects.all():
        payloads.extend([signature.content, signature.authentication_context])
    serialized = json.dumps(payloads)
    for secret in secrets:
        assert secret not in serialized
    assert TOTPDevice not in django_admin.site._registry
    assert "otp_code" in CREDENTIAL_FIELDS
    manager_client = Client()
    manager_client.force_login(manager)
    detail = manager_client.get(reverse("accounts:user_detail", args=[analyst.pk])).content
    for secret in secrets:
        assert secret.encode() not in detail


def test_signature_records_how_the_session_signed_in(manager):
    from core.session_control import signing_context

    class Request:
        method = "POST"
        user = manager
        POST = {"signature_username": manager.username}
        session = {
            "account_epoch": manager.session_epoch,
            "authenticated_at": timezone.now().timestamp(),
            "last_activity_at": timezone.now().timestamp(),
            "sign_in_factors": ["password", "totp"],
        }

    from core.session_control import current_request

    token = current_request.set(Request())
    try:
        context = signing_context(manager)
    finally:
        current_request.reset(token)
    assert context["sign_in_factors"] == ["password", "totp"]
    assert context["components"] == ["username", "pin"]


def test_required_roles_setting_is_validated():
    script = "import config.settings"
    for value, ok in (("admin, quality", True), ("all", True), ("superuser", False)):
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={"MFA_REQUIRED_ROLES": value, "DEBUG": "true", "PATH": ""},
            capture_output=True,
            text=True,
            cwd=settings.BASE_DIR,
        )
        assert (result.returncode == 0) is ok, result.stderr
    from accounts.services import ROLES

    assert {"all", *ROLES} == {"all", "admin", "analyst", "auditor", "quality", "reviewer"}


def test_refused_forms_never_show_a_submitted_code_again(analyst):
    _, codes = enable(analyst)
    client = Client()
    client.force_login(analyst)
    response = client.post(
        PAGE, {"current_password": "wrong-password", "otp_code": codes[0], "action": "codes"}
    )
    assert response.status_code == 422
    assert codes[0].encode() not in response.content
    assert RecoveryCode.objects.filter(user=analyst, used_at=None).count() == 10  # Not spent.
    signing_in = Client()
    password_step(signing_in, analyst.username)
    wrong = "ZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZ"
    response = signing_in.post(VERIFY, {"otp_code": wrong})
    assert response.status_code == 422 and wrong.encode() not in response.content


def test_django_admin_sign_in_cannot_skip_the_second_factor():
    staff = make_user("staff.test", ["admin"], is_staff=True, is_superuser=True)
    enable(staff)
    client = Client()
    response = client.post(
        "/admin/login/?next=/admin/", {"username": staff.username, "password": PASSWORD}
    )
    assert response.status_code == 302
    assert response["Location"] == "/accounts/login/?next=/admin/"
    assert not signed_in(client)
    assert client.get("/admin/login/?next=https://elsewhere.invalid/")["Location"] == (
        "/accounts/login/?next=/admin/"
    )
    assert client.get("/admin/")["Location"].startswith("/admin/login/")


def test_password_only_confirmations_do_not_clear_the_count_of_wrong_codes(analyst):
    from accounts.administration import change_own_password

    device, _ = enable(analyst)
    client = Client()
    client.force_login(analyst)
    wrong = "000000" if code(device, 1) != "000000" else "111111"
    for _ in range(settings.LOGIN_FAILURE_LIMIT - 1):
        client.post(PAGE, {"current_password": PASSWORD, "otp_code": wrong, "action": "codes"})
    assert LoginThrottle.objects.get(user=analyst).failures == settings.LOGIN_FAILURE_LIMIT - 1
    # A correct password on another form, refused for another reason, leaves the count alone.
    with pytest.raises(ValidationError):
        change_own_password(
            actor=fresh(analyst), current_password=PASSWORD, password="short", reason="Test"
        )
    with pytest.raises(ValidationError):
        set_pin(actor=fresh(analyst), pin="12", password=PASSWORD)
    assert LoginThrottle.objects.get(user=analyst).failures == settings.LOGIN_FAILURE_LIMIT - 1
    client.post(PAGE, {"current_password": PASSWORD, "otp_code": wrong, "action": "codes"})
    assert LoginThrottle.objects.get(user=analyst).locked_until > timezone.now()
    assert LoginThrottle.objects.get(user=analyst).code_failures == settings.LOGIN_FAILURE_LIMIT


def test_second_factor_stops_after_the_consecutive_failure_limit(analyst, manager):
    device, codes = enable(analyst)
    LoginThrottle.objects.update_or_create(
        user=analyst, defaults={"code_failures": two_factor.CODE_FAILURE_LIMIT - 2}
    )
    client = Client()
    password_step(client, analyst.username)
    # An accepted code clears the count.
    assert client.post(VERIFY, {"otp_code": code(device, 1)}).status_code == 302
    assert LoginThrottle.objects.get(user=analyst).code_failures == 0
    LoginThrottle.objects.filter(user=analyst).update(
        code_failures=two_factor.CODE_FAILURE_LIMIT - 1
    )
    client = Client()
    password_step(client, analyst.username)
    wrong = "000000" if code(device, 2) != "000000" else "111111"
    assert client.post(VERIFY, {"otp_code": wrong}).status_code == 422
    event = AuditEvent.objects.get(action="account.two_factor_stopped")
    assert event.after["two_factor_stopped"] is True
    LoginThrottle.objects.filter(user=analyst).update(failures=0, locked_until=None)
    for valid in (code(device, 2), codes[0]):
        response = client.post(VERIFY, {"otp_code": valid})
        assert response.status_code == 422 and b"Ask an" in response.content
    assert not signed_in(client)
    assert RecoveryCode.objects.filter(user=analyst, used_at=None).count() == 10
    # The owner, signed in elsewhere, cannot use a code either; the page says why.
    owner = Client()
    owner.force_login(analyst)
    assert b"stopped for this account" in owner.get(PAGE).content
    refused = owner.post(
        PAGE, {"current_password": PASSWORD, "otp_code": codes[1], "action": "codes"}
    )
    assert refused.status_code == 422
    # The way forward: an administrator's reset, then setting it up again.
    admin = Client()
    admin.force_login(manager)
    detail = admin.get(reverse("accounts:user_detail", args=[analyst.pk]))
    assert b"stopped after too many wrong codes" in detail.content
    response = admin.post(
        reverse("accounts:user_action", args=[analyst.pk, "reset_two_factor"]),
        {
            "revision": fresh(analyst).management_revision,
            "reason": "Synthetic repeated wrong codes, identity verified",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    assert LoginThrottle.objects.get(user=analyst).code_failures == 0
    assert not two_factor.stopped(analyst)
    assert password_step(Client(), analyst.username)["Location"] == "/"


def test_session_keeps_the_generation_read_with_the_password(analyst, monkeypatch):
    real_enabled = two_factor.enabled

    def enabled_meanwhile(user):
        # Another session turns two-factor sign-in on between the check and the login.
        answer = real_enabled(user)
        get_user_model().objects.filter(pk=user.pk).update(session_epoch=user.session_epoch + 1)
        return answer

    monkeypatch.setattr(two_factor, "enabled", enabled_meanwhile)
    client = Client()
    assert password_step(client, analyst.username)["Location"] == "/"
    monkeypatch.setattr(two_factor, "enabled", real_enabled)
    assert client.get("/accounts/access/").status_code == 302
    assert not signed_in(client)


SYNTHETIC_CODES = ("AAAA-BBBB-CCCC-DDDD-EEEE-FFFF", "GGGG-HHHH-JJJJ-KKKK-MMMM-NNNN")


def synthetic_codes():
    return list(SYNTHETIC_CODES)


def test_error_reports_do_not_print_recovery_codes(analyst, monkeypatch, rf):
    from django.views.debug import ExceptionReporter

    from accounts import views

    def broken_render(*args, **kwargs):
        raise RuntimeError("synthetic template failure")

    request = rf.get(PAGE)
    request.user = analyst
    request.session = {}
    request._messages = type("Messages", (), {"add": lambda *a, **k: None})()
    codes = list(SYNTHETIC_CODES)
    monkeypatch.setattr(views, "render", broken_render)

    def report():
        # The traceback starts here; this frame holds no reference to the codes.
        try:
            views._show_recovery_codes(request, synthetic_codes(), replaced=True)
        except RuntimeError:
            reporter = ExceptionReporter(request, *sys.exc_info(), is_email=True)
            return reporter.get_traceback_html(), reporter.get_traceback_text()

    html, text = report()
    assert "synthetic template failure" in html
    for value in codes:
        assert value not in html and value not in text
    assert repr(two_factor.Concealed(codes)) == "<concealed>"


def test_abandoned_setups_are_discarded_and_offer_no_reset(analyst, manager):
    client = Client()
    client.force_login(analyst)
    client.post(PAGE, {"current_password": PASSWORD, "action": "setup"})
    assert not two_factor.set_up_anything(analyst)
    admin = Client()
    admin.force_login(manager)
    reset = reverse("accounts:user_action", args=[analyst.pk, "reset_two_factor"])
    assert (
        reset.encode() not in admin.get(reverse("accounts:user_detail", args=[analyst.pk])).content
    )
    TOTPDevice.objects.update(
        created_at=timezone.now() - timedelta(seconds=two_factor.SETUP_SECONDS + 1)
    )
    # Starting another account's setup drops expired keys of every account.
    other = make_user("other.test", ["analyst"])
    two_factor.begin_setup(actor=other, current_password=PASSWORD)
    assert list(TOTPDevice.objects.values_list("user__username", flat=True)) == ["other.test"]
    # Opening an expired setup page drops the owner's key.
    TOTPDevice.objects.update(
        created_at=timezone.now() - timedelta(seconds=two_factor.SETUP_SECONDS + 1)
    )
    owner = Client()
    owner.force_login(other)
    session = owner.session
    session[PENDING_SETUP] = TOTPDevice.objects.get().pk
    session.save()
    assert owner.get(SETUP)["Location"] == PAGE
    assert not TOTPDevice.objects.exists()


def test_parallel_wrong_codes_are_counted_one_after_another(analyst):
    device, _ = enable(analyst)
    LoginThrottle.objects.update_or_create(
        user=analyst, defaults={"code_failures": two_factor.CODE_FAILURE_LIMIT - 1}
    )
    clients = [Client() for _ in range(3)]
    for client in clients:
        password_step(client, analyst.username)
    wrong = "000000" if code(device, 1) != "000000" else "111111"
    barrier = Barrier(len(clients))

    def submit(client):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return client.post(VERIFY, {"otp_code": wrong}).content
        finally:
            connections.close_all()

    with ThreadPoolExecutor(len(clients)) as pool:
        pages = list(pool.map(submit, clients))
    # The first wrong code reaches the limit; the others meet a stopped factor, uncounted.
    assert LoginThrottle.objects.get(user=analyst).code_failures == two_factor.CODE_FAILURE_LIMIT
    assert sum(b"stopped for this account" in page for page in pages) == len(clients) - 1
    assert AuditEvent.objects.filter(action="account.two_factor_stopped").count() == 1


def test_opening_setup_elsewhere_leaves_a_setup_in_time(analyst):
    client = Client()
    client.force_login(analyst)
    client.post(PAGE, {"current_password": PASSWORD, "action": "setup"})
    device = TOTPDevice.objects.get(user=analyst)
    elsewhere = Client()
    elsewhere.force_login(analyst)
    assert elsewhere.get(SETUP)["Location"] == PAGE
    assert TOTPDevice.objects.filter(pk=device.pk).exists()
    assert client.post(SETUP, {"otp_code": code(device)}).status_code == 200
    assert two_factor.enabled(analyst)
