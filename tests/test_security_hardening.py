"""Sign-in throttling, credential redaction, response headers and production settings."""

import logging
import os
import subprocess
import sys
import time
from collections import namedtuple
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, connection, transaction
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.utils.log import AdminEmailHandler
from django.views.debug import ExceptionReporter, get_default_exception_reporter_filter

from accounts.administration import change_own_password
from accounts.models import LoginThrottle
from core.audit import record_event
from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import approve_rule, save_rule, set_pin

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-throttle-password-2026!"
WRONG = "Synthetic-wrong-password-2026!"
REPLACEMENT = "Synthetic-replacement-password-2027!"
PIN = "73915824"
WRONG_PIN = "26481937"
NEW_PIN = "58203716"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def member(django_user_model):
    user = django_user_model.objects.create_user("throttle.test", password=PASSWORD)
    user.groups.add(Group.objects.get_or_create(name="quality")[0])
    return user


@pytest.fixture
def draft_rule(member):
    author = type(member).objects.create_user("throttle.author", password=PASSWORD)
    author.groups.add(Group.objects.get(name="quality"))
    return save_rule(
        actor=author,
        code="synthetic-report-rule",
        segment="chemical",
        policy={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        effective_from=timezone.now() - timedelta(hours=1),
        effective_until=timezone.now() + timedelta(days=30),
        reason="Synthetic",
    )


def approval(member, rule, pin):
    return {
        "revision": rule.revision,
        "reason": "Synthetic",
        "signature_username": member.username,
        "pin": pin,
    }


@pytest.fixture
def error_mail(settings):
    """Production error reports as operators receive them: emailed text and HTML."""
    settings.DEBUG = False
    settings.ADMINS = [("Operations", "operations@example.invalid")]
    handler = AdminEmailHandler(include_html=True)
    logger = logging.getLogger("django.request")
    logger.addHandler(handler)
    yield mail.outbox
    logger.removeHandler(handler)


def fail_writes(table, captured):
    """Database failure on any write to table, keeping the hashes it was about to store."""
    prefixes = (f'UPDATE "{table}"', f'INSERT INTO "{table}"')

    def wrapper(execute, sql, params, many, context):
        if sql.startswith(prefixes):
            captured.extend(p for p in params or () if isinstance(p, str) and "$" in p)
            raise OperationalError("synthetic database failure while writing a credential")
        return execute(sql, params, many, context)

    return wrapper


def assert_reports_hide(outbox, frame, *secrets):
    reports = [message.body for message in outbox]
    reports += [content for message in outbox for content, _ in message.alternatives]
    assert any("<html" in report for report in reports)
    for report in reports:
        assert frame in report  # A real report that covers the credential frames.
        for secret in secrets:
            assert secret not in report
            if "$" in secret:
                assert secret.rsplit("$", 1)[-1] not in report


def sign_in(client, password, path="/accounts/login/", username="throttle.test"):
    return client.post(path, {"username": username, "password": password})


def signed_in(client):
    return "_auth_user_id" in client.session


def error_text(response):
    return [str(error) for error in response.context["form"].non_field_errors()]


def test_repeated_failures_lock_password_sign_in_without_revealing_it(client, member, settings):
    for _ in range(settings.LOGIN_FAILURE_LIMIT - 1):
        sign_in(client, WRONG)
    wrong = sign_in(client, WRONG)
    throttle = LoginThrottle.objects.get(user=member)
    assert throttle.locked_until > timezone.now()
    locked_until = throttle.locked_until

    refused = sign_in(client, PASSWORD)
    assert refused.status_code == 200 and not signed_in(client)
    # The correct password during a lock looks exactly like a wrong password.
    assert error_text(refused) == error_text(wrong)
    sign_in(client, WRONG)
    throttle.refresh_from_db()
    assert throttle.locked_until == locked_until  # Attempts during a lock do not extend it.

    LoginThrottle.objects.filter(user=member).update(
        locked_until=timezone.now() - timedelta(seconds=1)
    )
    assert sign_in(client, PASSWORD).status_code == 302 and signed_in(client)


def test_success_resets_consecutive_failures_and_unknown_names_store_nothing(client, member):
    sign_in(client, WRONG)
    sign_in(client, WRONG)
    assert LoginThrottle.objects.get(user=member).failures == 2
    sign_in(client, WRONG, username="no-such-account")
    assert LoginThrottle.objects.count() == 1
    assert sign_in(client, PASSWORD).status_code == 302
    assert LoginThrottle.objects.get(user=member).failures == 0


def test_admin_login_shares_the_lock(client, member, settings):
    member.is_staff = True
    member.save(update_fields=["is_staff"])
    for _ in range(settings.LOGIN_FAILURE_LIMIT):
        sign_in(client, WRONG, path="/admin/login/")
    response = sign_in(client, PASSWORD, path="/admin/login/")
    assert response.status_code == 200 and not signed_in(client)


def test_signed_in_password_confirmations_count_and_honor_the_lock(member, settings):
    for _ in range(settings.LOGIN_FAILURE_LIMIT):
        with pytest.raises(PermissionDenied):
            set_pin(actor=member, pin=PIN, password=WRONG)
    # The refused PIN change rolled back, but the failure count and lock were committed.
    assert LoginThrottle.objects.get(user=member).locked_until > timezone.now()
    assert not PINCredential.objects.filter(user=member).exists()
    with pytest.raises(PermissionDenied):
        set_pin(actor=member, pin=PIN, password=PASSWORD)
    with pytest.raises(PermissionDenied):
        change_own_password(
            actor=member, current_password=PASSWORD, password=WRONG, reason="Synthetic"
        )
    member.refresh_from_db()
    assert member.check_password(PASSWORD)
    assert not AuditEvent.objects.filter(
        action__in=["pin.changed", "account.password_changed"]
    ).exists()


def test_password_change_failures_survive_refusal(member):
    with pytest.raises(PermissionDenied):
        change_own_password(actor=member, current_password=WRONG, password=WRONG, reason="Test")
    assert LoginThrottle.objects.get(user=member).failures == 1


@pytest.mark.parametrize(
    ("route", "fields"),
    [
        ("core:pin", ["password", "pin"]),
        ("core:rule_approve", ["pin"]),
        ("quality:review", ["pin"]),
        ("analytical:test_review", ["pin"]),
    ],
)
def test_credentials_are_redacted_from_production_error_reports(
    client, member, settings, route, fields
):
    settings.DEBUG = False
    client.force_login(member)
    url = reverse(route) if route == "core:pin" else reverse(route, args=[1])
    response = client.post(url, {field: "Synthetic-private-value-764!" for field in fields})
    reporter = get_default_exception_reporter_filter()
    filtered = reporter.get_post_parameters(response.wsgi_request)
    for field in fields:
        assert filtered[field] == reporter.cleansed_substitute


def test_credential_locals_are_redacted_from_production_tracebacks(settings):
    settings.DEBUG = False
    request = RequestFactory().post("/", {"pin": "Synthetic-private-value-764!"})

    def failing(pin, password):
        signing_data = {"pin": pin, "reason": "kept"}  # noqa: F841
        raise RuntimeError("synthetic failure")

    try:
        failing("Synthetic-private-value-764!", "Synthetic-private-value-765!")
    except RuntimeError as exc:
        frame = exc.__traceback__.tb_next.tb_frame
    reporter = get_default_exception_reporter_filter()
    variables = dict(reporter.get_traceback_frame_variables(request, frame))
    assert variables["pin"] == variables["password"] == reporter.cleansed_substitute
    assert variables["signing_data"] == {"pin": reporter.cleansed_substitute, "reason": "kept"}
    assert "Synthetic-private-value" not in repr(reporter.get_post_parameters(request))


def test_html_responses_carry_a_strict_content_security_policy(client):
    response = client.get("/accounts/login/")
    policy = response["Content-Security-Policy"]
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ):
        assert directive in policy
    assert "unsafe" not in policy
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"


def test_audit_export_escapes_tab_and_carriage_return_formulas(client, member):
    with transaction.atomic():
        for reason in ("\t=1+1", "\r=1+1"):
            record_event(actor=member, action="synthetic", obj=member, reason=reason)
    auditor = type(member).objects.create_user("throttle.auditor")
    auditor.groups.add(Group.objects.get_or_create(name="auditor")[0])
    client.force_login(auditor)
    body = client.get("/audit/?export=csv").content.decode()
    assert "'\t=1+1" in body and "'\r=1+1" in body


def production_settings(**overrides):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DEBUG", "SECRET_KEY", "SECURE_HSTS_SECONDS"}
    }
    env.update(overrides)
    code = (
        "import config.settings as s; print(s.DEBUG, s.SECURE_HSTS_SECONDS, "
        "s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT)"
    )
    return subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); {code}"],
        env=env,
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


@pytest.mark.django_db(transaction=False)
def test_production_settings_fail_closed_and_enable_transport_security():
    missing = production_settings()
    assert missing.returncode != 0 and "SECRET_KEY must be supplied" in missing.stderr
    configured = production_settings(SECRET_KEY="synthetic-" + "k" * 50)
    assert configured.returncode == 0, configured.stderr
    assert configured.stdout.split() == ["False", "31536000", "True", "True", "True"]


def test_signing_failure_report_hides_pin_and_pin_hash(
    client, member, draft_rule, settings, monkeypatch
):
    import core.services

    set_pin(actor=member, pin=PIN, password=PASSWORD)
    stored = PINCredential.objects.get(user=member).encoded

    def fail_after_verification(**kwargs):
        raise OperationalError("synthetic database failure after PIN verification")

    monkeypatch.setattr(core.services, "record_event", fail_after_verification)
    settings.DEBUG = False
    client.force_login(member)
    url = reverse("core:rule_approve", args=[draft_rule.pk])
    payload = approval(member, draft_rule, PIN)
    with pytest.raises(OperationalError) as failure:
        client.post(url, payload)
    request = RequestFactory().post(url, payload)
    request.user = member
    # A server's report starts at Django's handler; earlier frames are the test client's own.
    traceback = failure.tb
    while "django/core/handlers/exception.py" not in traceback.tb_frame.f_code.co_filename:
        traceback = traceback.tb_next
    reporter = ExceptionReporter(request, failure.type, failure.value, traceback)
    names = {frame["function"] for frame in reporter.get_traceback_frames()}
    assert {"sign_transition", "verify_pin"} & names  # The report covers the signing frames.
    for report in (reporter.get_traceback_text(), reporter.get_traceback_html()):
        assert PIN not in report
        assert stored not in report and stored.rsplit("$", 1)[-1] not in report


def test_successful_confirmations_reset_the_consecutive_failure_count(member, settings):
    for _ in range(settings.LOGIN_FAILURE_LIMIT - 1):
        with pytest.raises(PermissionDenied):
            set_pin(actor=member, pin=PIN, password=WRONG)
        set_pin(actor=member, pin=PIN, password=PASSWORD)
    assert LoginThrottle.objects.get(user=member).failures == 0
    with pytest.raises(PermissionDenied):
        change_own_password(
            actor=member, current_password=WRONG, password=WRONG, reason="Synthetic"
        )
    throttle = LoginThrottle.objects.get(user=member)
    assert (throttle.failures, throttle.locked_until) == (1, None)
    change_own_password(
        actor=member,
        current_password=PASSWORD,
        password="Synthetic-replacement-password-2027!",
        reason="Synthetic",
    )
    assert LoginThrottle.objects.get(user=member).failures == 0


def signed_in_client(member):
    client = Client(raise_request_exception=False)
    client.force_login(member)
    return client, client.cookies["sessionid"].value


@pytest.mark.parametrize("submitted", [WRONG_PIN, PIN], ids=["failure-count", "reset"])
def test_pin_counter_write_failure_report_hides_pin_hash_and_session(
    member, draft_rule, error_mail, submitted
):
    set_pin(actor=member, pin=PIN, password=PASSWORD)
    PINCredential.objects.filter(user=member).update(failures=1)  # The correct PIN writes a reset.
    stored = PINCredential.objects.get(user=member).encoded
    client, session = signed_in_client(member)
    captured = []
    with connection.execute_wrapper(fail_writes("core_pincredential", captured)):
        response = client.post(
            reverse("core:rule_approve", args=[draft_rule.pk]),
            approval(member, draft_rule, submitted),
        )
    assert response.status_code == 500
    assert_reports_hide(error_mail, "verify_pin", submitted, stored, session, *captured)


@pytest.mark.parametrize("replacing", [False, True], ids=["enrollment", "replacement"])
def test_pin_enrollment_write_failure_report_hides_pin_password_and_hashes(
    member, error_mail, replacing
):
    previous = []
    if replacing:
        set_pin(actor=member, pin=PIN, password=PASSWORD)
        previous.append(PINCredential.objects.get(user=member).encoded)
    client, session = signed_in_client(member)
    captured = []
    with connection.execute_wrapper(fail_writes("core_pincredential", captured)):
        response = client.post(reverse("core:pin"), {"password": PASSWORD, "pin": NEW_PIN})
    assert response.status_code == 500 and captured  # The new hash was being written.
    secrets = (NEW_PIN, PASSWORD, session, *previous, *captured)
    assert_reports_hide(error_mail, "set_pin", *secrets)


def test_password_write_failure_report_hides_passwords_and_hashes(member, error_mail):
    stored = type(member).objects.get(pk=member.pk).password
    client, session = signed_in_client(member)
    captured = []
    with connection.execute_wrapper(fail_writes("accounts_user", captured)):
        response = client.post(
            reverse("accounts:password_change"),
            {
                "current_password": PASSWORD,
                "password": REPLACEMENT,
                "password_confirmation": REPLACEMENT,
                "reason": "Synthetic",
            },
        )
    assert response.status_code == 500 and captured  # The new hash was being written.
    secrets = (PASSWORD, REPLACEMENT, stored, session, *captured)
    assert_reports_hide(error_mail, "change_own_password", *secrets)


def violate_check(column):
    """Make PostgreSQL refuse the write with a real CHECK violation on column."""

    def wrapper(execute, sql, params, many, context):
        return execute(
            sql.replace(f'"{column}" = %s', f'"{column}" = %s - 1000'), params, many, context
        )

    return wrapper


@pytest.mark.parametrize("scenario", ["pin-verification", "password-change"])
def test_database_error_text_with_the_stored_row_is_hidden_from_reports(
    member, draft_rule, error_mail, scenario
):
    set_pin(actor=member, pin=PIN, password=PASSWORD)
    client, session = signed_in_client(member)
    if scenario == "pin-verification":
        stored = PINCredential.objects.get(user=member).encoded
        url, column, frame = (
            reverse("core:rule_approve", args=[draft_rule.pk]),
            "failures",
            "verify_pin",
        )
        data, secrets = approval(member, draft_rule, WRONG_PIN), (WRONG_PIN,)
    else:
        stored = type(member).objects.get(pk=member.pk).password
        url, column, frame = (
            reverse("accounts:password_change"),
            "session_epoch",
            "change_own_password",
        )
        data = {
            "current_password": PASSWORD,
            "password": REPLACEMENT,
            "password_confirmation": REPLACEMENT,
            "reason": "Synthetic",
        }
        secrets = (PASSWORD, REPLACEMENT)
    with connection.execute_wrapper(violate_check(column)):
        response = client.post(url, data)
    error = response.exc_info[1]
    assert isinstance(error, IntegrityError)
    # PostgreSQL's "Failing row contains (...)" detail carries the whole row, the hash included
    # (cut to about 64 characters, which still holds the algorithm, salt and part of the digest).
    row = str(error).split("Failing row contains", 1)[1].strip(" ().\n").split(", ")
    hashes = [value.removesuffix("...") for value in row if "$" in value]
    assert hashes and (scenario == "password-change" or stored.startswith(hashes[0]))
    assert_reports_hide(error_mail, frame, stored, session, *secrets, *hashes)


def test_nested_credentials_and_hashes_are_redacted_within_bounds(settings):
    settings.DEBUG = False
    stored = make_password(PIN)
    argon = "argon2$argon2id$v=19$m=102400,t=2,p=8$c3ludGhldGlj$c3ludGhldGljLWhhc2g"
    bcrypt = "bcrypt_sha256$$2b$12$c3ludGhldGljLXNhbHQtYmNyeXB0LWhhc2gtdmFsdWU"
    row_type = namedtuple("Row", "name value")
    cycle = []
    cycle.append(cycle)

    def failing():
        values = [(None, None, stored), ("detail", f"Failing row contains (1, {argon}, 0, null).")]
        nested = {"outer": [{"inner": {"pin": PIN, "kept": "visible"}}], "hashes": {bcrypt}}
        row = row_type("encoded", stored)
        deep = [[[[[[[[[["synthetic"]]]]]]]]]]
        huge = list(range(1_000_000))
        loop = cycle
        raise RuntimeError(f"synthetic failure {len([values, nested, row, deep, huge, loop])}")

    try:
        failing()
    except RuntimeError as exc:
        frame = exc.__traceback__.tb_next.tb_frame
    reporter = get_default_exception_reporter_filter()
    started = time.monotonic()
    variables = dict(reporter.get_traceback_frame_variables(RequestFactory().get("/"), frame))
    assert time.monotonic() - started < 1
    hidden = reporter.cleansed_substitute
    assert variables["values"] == [
        (None, None, hidden),
        ("detail", f"Failing row contains (1, {hidden}, 0, null)."),
    ]
    assert variables["nested"] == {
        "outer": [{"inner": {"pin": hidden, "kept": "visible"}}],
        "hashes": {hidden},
    }
    assert variables["row"] == row_type("encoded", hidden) and type(variables["row"]) is row_type
    # Past the depth or size bound, or around a cycle, the whole value is hidden.
    assert variables["deep"] == variables["huge"] == variables["loop"] == hidden


@pytest.mark.parametrize("refusal", ["same-password", "weak-password", "pin-write-fails"])
def test_a_correct_password_resets_the_count_even_when_the_change_is_refused(
    member, settings, refusal
):
    for _ in range(settings.LOGIN_FAILURE_LIMIT - 1):
        with pytest.raises(PermissionDenied):
            change_own_password(
                actor=member, current_password=WRONG, password=WRONG, reason="Synthetic"
            )
    if refusal == "pin-write-fails":
        with (
            connection.execute_wrapper(fail_writes("core_pincredential", [])),
            pytest.raises(OperationalError),
        ):
            set_pin(actor=member, pin=PIN, password=PASSWORD)
    else:
        with pytest.raises(ValidationError):
            change_own_password(
                actor=member,
                current_password=PASSWORD,
                password=PASSWORD if refusal == "same-password" else "short",
                reason="Synthetic",
            )
    assert LoginThrottle.objects.get(user=member).failures == 0
    with pytest.raises(PermissionDenied):
        set_pin(actor=member, pin=PIN, password=WRONG)
    throttle = LoginThrottle.objects.get(user=member)
    assert (throttle.failures, throttle.locked_until) == (1, None)  # One later slip does not lock.


@pytest.mark.parametrize("change", ["password-replaced", "account-deactivated"])
@pytest.mark.parametrize("operation", ["password-change", "pin-enrollment"])
def test_an_account_change_after_confirmation_refuses_the_request(
    member, monkeypatch, change, operation
):
    import accounts.authentication

    confirm = accounts.authentication.confirm_password

    def confirm_then_change(user, password):
        verified = confirm(user, password)
        accounts = type(member).objects.filter(pk=member.pk)
        if change == "password-replaced":
            accounts.update(password=make_password("Synthetic-other-password-2026!"))
        else:
            accounts.update(is_active=False)
        return verified

    monkeypatch.setattr(accounts.authentication, "confirm_password", confirm_then_change)
    with pytest.raises(PermissionDenied):
        if operation == "password-change":
            change_own_password(
                actor=member, current_password=PASSWORD, password=REPLACEMENT, reason="Synthetic"
            )
        else:
            set_pin(actor=member, pin=PIN, password=PASSWORD)
    member.refresh_from_db()
    assert not member.check_password(REPLACEMENT)
    assert not PINCredential.objects.filter(user=member).exists()
    assert not AuditEvent.objects.filter(
        action__in=["pin.changed", "account.password_changed"]
    ).exists()


def test_reenrollment_between_verification_and_signing_is_refused(member, draft_rule, monkeypatch):
    import core.services

    set_pin(actor=member, pin=PIN, password=PASSWORD)
    verify = core.services.verify_pin

    def verify_then_require_reenrollment(actor, pin):
        encoded = verify(actor, pin)
        PINCredential.objects.filter(user=actor).delete()
        return encoded

    monkeypatch.setattr(core.services, "verify_pin", verify_then_require_reenrollment)
    with pytest.raises(ValidationError, match="Signing credential changed"):
        approve_rule(
            actor=member,
            pin=PIN,
            rule=draft_rule,
            expected_revision=draft_rule.revision,
            reason="Synthetic",
        )
    assert not ElectronicSignature.objects.exists()


def test_log_formatter_hides_hashes_in_logged_database_errors():
    from config.security import CredentialLogFormatter

    stored = make_password(PIN)
    try:
        raise IntegrityError(
            f"check violation\nDETAIL:  Failing row contains (1, {stored[:64]}...)."
        )
    except IntegrityError:
        record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "Failed", (), None)
        record.exc_info = sys.exc_info()
    logged = CredentialLogFormatter().format(record)
    assert "check violation" in logged and "pbkdf2" not in logged and stored[:64] not in logged
