from io import StringIO

import pytest
from django.contrib.auth.hashers import check_password
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from accounts.administration import change_account, change_own_password
from accounts.models import LoginAnnouncement
from catalog.models import Material
from catalog.services import create_material
from core.models import AuditEvent, ElectronicSignature, PINCredential, RuleSet
from core.services import set_pin
from quality.models import Lot

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-demo-password-2026!"
PIN = "84621357"
ADMIN_PASSWORD = "Synthetic-demo-admin-password-2026!"
ADMIN_PIN = "51739264"
NOTE = "Everything entered here is erased every day at 08:00 UTC."
LISTED = ["demo_analyst", "demo_auditor", "demo_config_author", "demo_quality", "demo_reviewer"]
SECRETS = (PASSWORD, PIN, ADMIN_PASSWORD, ADMIN_PIN)


@pytest.fixture
def demo_env(settings, monkeypatch):
    settings.DEBUG = False  # The hosted demonstration runs without DEBUG.
    monkeypatch.setenv("ALLOW_DEMO_RESET", "true")
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    monkeypatch.setenv("DEMO_PIN", PIN)
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("DEMO_ADMIN_PIN", ADMIN_PIN)
    monkeypatch.setenv("DEMO_RESET_NOTE", NOTE)


def reset(**options):
    output = StringIO()
    call_command("reset_demo", interactive=False, stdout=output, stderr=StringIO(), **options)
    printed = output.getvalue()
    assert not any(secret in printed for secret in SECRETS)
    return printed


def seeded_by_a_maintainer(django_user_model):
    """A demonstration as it is before its first reset: a maintainer's account and the seed."""
    maintainer = django_user_model.objects.create_user("maintainer", is_superuser=True)
    call_command("seed_demo", actor=maintainer.username, stdout=StringIO(), stderr=StringIO())
    return maintainer


def accepts(user, password, pin):
    return (
        user.check_password(password),
        check_password(pin, PINCredential.objects.get(user=user).encoded),
    )


def state():
    return (
        AuditEvent.objects.count(),
        sorted(LoginAnnouncement.objects.values_list("body", flat=True)),
        sorted(Material.objects.values_list("code", flat=True)),
    )


def test_reset_erases_the_demonstration_and_publishes_the_seeded_accounts(
    demo_env, django_user_model, client
):
    seeded_by_a_maintainer(django_user_model)
    assert client.login(username="demo_analyst", password=PASSWORD)
    assert Session.objects.exists()

    for _ in range(2):  # Every night: a reset of a demonstration that was reset before.
        quality = django_user_model.objects.get(username="demo_quality")
        create_material(
            actor=quality,
            code="visitor-material",
            name="Entered by a visitor",
            kind="raw_material",
            reason="Synthetic visitor entry",
        )
        printed = reset(publish_accounts=True)
        assert "Demonstration reset complete." in printed

        accounts = {user.username: user for user in django_user_model.objects.all()}
        assert sorted(accounts) == ["demo_admin", *LISTED]
        admin = accounts["demo_admin"]
        assert admin.pk == 1  # Identifiers start again.
        assert not admin.is_superuser and not admin.is_staff and not admin.credentials_locked
        assert list(admin.groups.values_list("name", flat=True)) == ["admin"]
        assert accepts(admin, ADMIN_PASSWORD, ADMIN_PIN) == (True, True)
        assert accepts(admin, PASSWORD, PIN) == (False, False)
        for username in LISTED:
            assert accepts(accounts[username], PASSWORD, PIN) == (True, True)
            assert accounts[username].credentials_locked

        assert not Material.objects.filter(code="visitor-material").exists()
        assert not Session.objects.exists()
        assert not AuditEvent.objects.filter(reason="Synthetic visitor entry").exists()
        assert RuleSet.objects.count() == 5 and not RuleSet.objects.exclude(status="draft").exists()
        assert not Lot.objects.exists()

        announcement = LoginAnnouncement.objects.get()
        assert announcement.published and announcement.body.endswith(NOTE)
        assert PASSWORD in announcement.body and PIN in announcement.body
        assert ADMIN_PASSWORD not in announcement.body and ADMIN_PIN not in announcement.body
        signature = ElectronicSignature.objects.get(meaning="announcement_authorized")
        assert signature.signer == admin
        assert signature.authentication_context["channel"] == "trusted-service"
        locked = AuditEvent.objects.filter(action="account.credentials_locked")
        assert locked.count() == len(LISTED) and {event.actor for event in locked} == {admin}
        for event in AuditEvent.objects.all():
            assert "pbkdf2" not in str((event.before, event.after, event.reason))

    page = client.get("/accounts/login/").content.decode()
    assert NOTE in page and f"<pre><code>{PASSWORD}</code></pre>" in page
    assert "<td><code>demo_analyst</code></td><td>Analyst</td><td>Receive lots" in page
    assert "demo_admin" not in page


@pytest.mark.parametrize(
    ("debug", "journey", "change", "message"),
    [
        (True, False, {"ALLOW_DEMO_RESET": None}, "ALLOW_DEMO_RESET=true"),  # DEBUG is not enough.
        (False, False, {"ALLOW_DEMO_RESET": "false"}, "ALLOW_DEMO_RESET=true"),
        (False, True, {}, "--journey .* needs DEBUG=true"),
        (False, False, {"DEMO_ADMIN_PIN": None}, "set DEMO_ADMIN_PIN"),
        (False, False, {"DEMO_PASSWORD": None, "DEMO_PIN": None}, "set DEMO_PASSWORD, DEMO_PIN"),
        (False, False, {"DEMO_PIN": "1234"}, "8–32"),
        (False, False, {"DEMO_ADMIN_PIN": PIN}, "different from the published accounts"),
        (False, False, {"DEMO_ADMIN_PASSWORD": PASSWORD}, "different from the published accounts"),
        (False, False, {"DEMO_PASSWORD": PASSWORD + " "}, "cannot be shown exactly"),
        (False, False, {"DEMO_RESET_NOTE": "Long. " * 800}, "too long"),
    ],
)
def test_reset_refuses_before_anything_is_erased(
    demo_env, django_user_model, monkeypatch, settings, debug, journey, change, message
):
    seeded_by_a_maintainer(django_user_model)
    before = state()
    settings.DEBUG = debug
    for name, value in change.items():
        if value is None:
            monkeypatch.delenv(name)
        else:
            monkeypatch.setenv(name, value)
    with pytest.raises(CommandError, match=message):
        reset(journey=journey, publish_accounts=True)
    assert state() == before
    assert django_user_model.objects.filter(username="maintainer").exists()


def test_reset_refuses_a_database_that_is_not_the_demonstration(demo_env, django_user_model):
    # A laboratory's accounts, one of which happens to carry the seed's username.
    django_user_model.objects.create_user("lab.admin", is_superuser=True)
    django_user_model.objects.create_user("demo_admin", password=ADMIN_PASSWORD)
    with pytest.raises(CommandError, match="not a demonstration"):
        reset(publish_accounts=True)
    assert django_user_model.objects.count() == 2
    assert not AuditEvent.objects.exists() and not LoginAnnouncement.objects.exists()


def test_reset_refuses_another_release_schema(demo_env, django_user_model, monkeypatch):
    seeded_by_a_maintainer(django_user_model)
    before = state()
    recorder = MigrationRecorder(connection)
    recorder.record_applied("accounts", "9999_from_a_later_release")
    try:
        with pytest.raises(CommandError, match="migrations this release does not know"):
            reset()
    finally:
        recorder.record_unapplied("accounts", "9999_from_a_later_release")
    monkeypatch.setattr(
        MigrationExecutor, "migration_plan", lambda self, targets: [("pending", False)]
    )
    with pytest.raises(CommandError, match="migrations the database lacks"):
        reset()
    assert state() == before
    assert django_user_model.objects.filter(username="maintainer").exists()


def test_a_seed_that_fails_rolls_the_erase_back(demo_env, django_user_model, monkeypatch):
    seeded_by_a_maintainer(django_user_model)
    before = state()
    monkeypatch.setenv("DEMO_PASSWORD", "password")  # Refused by the password validators.
    with pytest.raises(CommandError, match="too common"):
        reset(publish_accounts=True)
    assert state() == before
    assert django_user_model.objects.count() == 7
    assert django_user_model.objects.get(username="demo_reviewer").check_password(PASSWORD)


def test_the_journey_is_seeded_only_with_debug(demo_env, django_user_model, settings):
    settings.DEBUG = True  # A developer's own demonstration database.
    reset(journey=True, publish_accounts=True)
    assert RuleSet.objects.get(code="chemical").status == "approved"
    assert Lot.objects.count() == 1 and LoginAnnouncement.objects.get().published
    settings.DEBUG = False
    before = state()
    with pytest.raises(CommandError, match="--journey .* needs DEBUG=true"):
        call_command("seed_demo", actor="demo_admin", journey=True, stdout=StringIO())
    assert state() == before


def test_published_accounts_cannot_change_their_password_or_pin(
    demo_env, django_user_model, client
):
    reset(publish_accounts=True)
    admin = django_user_model.objects.get(username="demo_admin")
    reviewer = django_user_model.objects.get(username="demo_reviewer")
    quality = django_user_model.objects.get(username="demo_quality")
    stored = (reviewer.password, PINCredential.objects.get(user=reviewer).encoded)

    with pytest.raises(PermissionDenied, match="shared demonstration account"):
        change_own_password(
            actor=reviewer,
            current_password=PASSWORD,
            password="Changed-by-a-visitor-2026!",
            reason="Synthetic visitor attempt",
        )
    with pytest.raises(PermissionDenied, match="shared demonstration account"):
        set_pin(actor=reviewer, pin="11223344", password=PASSWORD)

    assert client.login(username="demo_reviewer", password=PASSWORD)
    for path, fields in (
        (
            "/accounts/password/",
            {
                "current_password": PASSWORD,
                "password": "Changed-by-a-visitor-2026!",
                "password_confirmation": "Changed-by-a-visitor-2026!",
                "reason": "Synthetic visitor attempt",
            },
        ),
        ("/signature-pin/", {"password": PASSWORD, "pin": "11223344"}),
    ):
        shown = client.get(path)
        assert shown.status_code == 200
        assert "shared demonstration account" in shown.content.decode()
        assert 'type="password"' not in shown.content.decode()
        assert client.post(path, fields).status_code == 403
    reviewer.refresh_from_db()
    assert stored == (reviewer.password, PINCredential.objects.get(user=reviewer).encoded)
    assert accepts(reviewer, PASSWORD, PIN) == (True, True)
    client.logout()

    # demo_admin's own credentials are private and stay its own to change.
    set_pin(actor=admin, pin="64827193", password=ADMIN_PASSWORD)
    assert client.login(username="demo_admin", password=ADMIN_PASSWORD)
    detail = client.get(f"/accounts/users/{reviewer.pk}/").content.decode()
    assert "Shared demonstration account" in detail
    assert (
        "Shared demonstration account"
        not in client.get(f"/accounts/users/{admin.pk}/").content.decode()
    )

    # Clearing a PIN lockout keeps the lock; an administrator replacing a credential ends it.
    change_account(
        actor=admin,
        user=reviewer,
        expected_revision=reviewer.management_revision,
        action="unlock_pin",
        pin="64827193",
        reason="Synthetic lockout cleared",
    )
    reviewer.refresh_from_db()
    assert reviewer.credentials_locked
    change_account(
        actor=admin,
        user=reviewer,
        expected_revision=reviewer.management_revision,
        action="reset_password",
        pin="64827193",
        reason="Synthetic takeover of a published account",
        temporary_password="Temporary-synthetic-2026!",
    )
    reviewer.refresh_from_db()
    assert not reviewer.credentials_locked and reviewer.password_change_required
    event = AuditEvent.objects.get(action="account.reset_password")
    assert (event.before["credentials_locked"], event.after["credentials_locked"]) == (True, False)
    change_own_password(
        actor=reviewer,
        current_password="Temporary-synthetic-2026!",
        password="Individual-synthetic-2026!",
        reason="Synthetic required change",
    )
    change_account(
        actor=admin,
        user=quality,
        expected_revision=quality.management_revision,
        action="reenroll_pin",
        pin="64827193",
        reason="Synthetic takeover of a published account",
    )
    quality.refresh_from_db()
    assert not quality.credentials_locked
    set_pin(actor=quality, pin="11223344", password=PASSWORD)
