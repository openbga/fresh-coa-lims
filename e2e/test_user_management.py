"""Named-account administration uses explicit admin authority and signed, audited changes."""

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import connections
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import set_pin, verify_pin

pytestmark = pytest.mark.django_db(transaction=True)
ADMIN_PASSWORD = "Synthetic-admin-browser-2026!"
ADMIN_PIN = "73918462"
INITIAL_PASSWORD = "Starting-lab-member-2026!"
FIRST_PASSWORD = "Private-lab-member-2026!"
TEMP_PASSWORD = "Replacement-lab-member-2026!"
FINAL_PASSWORD = "Renewed-private-member-2026!"
USER_PIN = "48261937"
NEW_USER_PIN = "59827146"
ARTIFACTS = Path(".local/qa")


@pytest.fixture
def account_admin(django_user_model):
    admin = django_user_model.objects.create_user(
        username="synthetic_account_admin",
        password=ADMIN_PASSWORD,
        first_name="Synthetic",
        last_name="Account Administrator",
    )
    admin.groups.add(Group.objects.get_or_create(name="admin")[0])
    set_pin(actor=admin, pin=ADMIN_PIN, password=ADMIN_PASSWORD)
    assert not admin.is_staff and not admin.is_superuser
    return admin


def db_call(callback):
    """Keep Django ORM work off Playwright's synchronous event-loop thread."""

    def work():
        try:
            return callback()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(work).result()


def login(page, server, username, password):
    page.goto(server.url + reverse("login"))
    page.get_by_label(re.compile(r"^Username\b")).fill(username)
    page.get_by_label(re.compile(r"^Password\b")).fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()


def sign(page, admin, button, reason):
    page.get_by_label(re.compile(r"^Reason\b")).fill(reason)
    page.get_by_label(re.compile(r"^Signing username\b")).fill(admin.username)
    page.get_by_label(re.compile(r"^Signature PIN\b")).fill(ADMIN_PIN)
    path = urlsplit(page.url).path
    with page.expect_response(
        lambda r: urlsplit(r.url).path == path and r.request.method == "POST"
    ) as response:
        page.get_by_role("button", name=button, exact=True).click()
    return response.value.status


def change_password(page, server, current, new):
    expect(page).to_have_url(server.url + reverse("accounts:password_change"))
    expect(
        page.get_by_text("Choose a new password before continuing.", exact=False)
    ).to_be_visible()
    # Even an explicit workspace navigation cannot bypass the required password change.
    page.goto(server.url + "/")
    expect(page).to_have_url(server.url + reverse("accounts:password_change"))
    page.get_by_label(re.compile(r"^Current password\b")).fill(current)
    page.get_by_label(re.compile(r"^New password\b")).fill(new)
    page.get_by_label(re.compile(r"^Confirm new password\b")).fill(new)
    page.get_by_label(re.compile(r"^Reason\b")).fill("Replace private synthetic credential")
    page.get_by_role("button", name="Change password", exact=True).click()
    expect(page).to_have_url(server.url + "/")


def enroll_pin(page, server, password, pin):
    page.goto(server.url + reverse("core:pin"))
    page.get_by_label(re.compile(r"^Current login password\b")).fill(password)
    page.get_by_label(re.compile(r"^New signature PIN\b")).fill(pin)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_text("Signature PIN saved.", exact=True)).to_be_visible()


def test_signed_account_lifecycle(live_server, account_admin, django_user_model):
    admin = account_admin
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        admin_context = browser.new_context(viewport={"width": 1440, "height": 1000})
        member_context = browser.new_context(viewport={"width": 1280, "height": 900})
        page, member = admin_context.new_page(), member_context.new_page()
        try:
            login(page, live_server, admin.username, ADMIN_PASSWORD)
            page.goto(live_server.url + reverse("accounts:user_list"))
            page.get_by_role("link", name="Create account", exact=True).click()
            for label, value in [
                ("Username", "synthetic_named_member"),
                ("First name", "Synthetic"),
                ("Last name", "Named Member"),
                ("Email", "named-member@example.invalid"),
                ("Initial password", INITIAL_PASSWORD),
                ("Confirm initial password", INITIAL_PASSWORD),
            ]:
                page.get_by_label(re.compile(r"^" + label + r"\b")).fill(value)
            page.get_by_role("checkbox", name="Analyst", exact=True).check()
            assert (
                sign(page, admin, "Sign and create account", "Provision synthetic named analyst")
                == 302
            )
            expect(
                page.get_by_role("heading", name="synthetic_named_member", exact=True)
            ).to_be_visible()
            expect(page.get_by_text("account.created", exact=True)).to_be_visible()
            expect(
                page.get_by_text(
                    "Signed by Synthetic Account Administrator · account_authorized", exact=False
                )
            ).to_be_visible()
            member_id = int(urlsplit(page.url).path.strip("/").split("/")[-1])
            detail_url = page.url
            page.get_by_role("link", name="Assign roles", exact=True).click()
            page.get_by_role("checkbox", name="Reviewer", exact=True).check()
            assert (
                sign(page, admin, "Sign and assign roles", "Authorize independent review role")
                == 302
            )
            expect(page.get_by_text("analyst, reviewer", exact=True)).to_be_visible()

            login(member, live_server, "synthetic_named_member", INITIAL_PASSWORD)
            change_password(member, live_server, INITIAL_PASSWORD, FIRST_PASSWORD)
            # The member has a live workspace session before the administrator forces a reset.
            page.get_by_role("link", name="Force password reset", exact=True).click()
            page.get_by_label(re.compile(r"^Temporary password\b")).fill(TEMP_PASSWORD)
            page.get_by_label(re.compile(r"^Confirm temporary password\b")).fill(TEMP_PASSWORD)
            assert (
                sign(page, admin, "Sign and force password reset", "Synthetic recovery credential")
                == 302
            )
            member.goto(live_server.url + "/")
            expect(member).to_have_url(re.compile(r"/accounts/login/\?next="))
            login(member, live_server, "synthetic_named_member", TEMP_PASSWORD)
            change_password(member, live_server, TEMP_PASSWORD, FINAL_PASSWORD)
            enroll_pin(member, live_server, FINAL_PASSWORD, USER_PIN)

            def lock_member_pin():
                user = django_user_model.objects.get(pk=member_id)
                for _ in range(5):
                    with pytest.raises(ValidationError):
                        verify_pin(user, "00000000")
                return PINCredential.objects.get(user=user).locked_until is not None

            assert db_call(lock_member_pin)
            page.goto(detail_url)
            expect(page.get_by_text("lock until", exact=False)).to_be_visible()
            page.get_by_role("link", name="Clear PIN lockout", exact=True).click()
            assert (
                sign(
                    page,
                    admin,
                    "Sign and clear pin lockout",
                    "Verified synthetic identity before unlock",
                )
                == 302
            )
            assert (
                db_call(lambda: PINCredential.objects.get(user_id=member_id).locked_until) is None
            )
            page.get_by_role("link", name="Require PIN re-enrollment", exact=True).click()
            assert (
                sign(
                    page,
                    admin,
                    "Sign and require pin re-enrollment",
                    "Synthetic PIN compromise response",
                )
                == 302
            )
            expect(
                page.get_by_text("Enrollment required; 0 failed attempts", exact=True)
            ).to_be_visible()
            assert not db_call(lambda: PINCredential.objects.filter(user_id=member_id).exists())
            member.goto(live_server.url + reverse("core:pin"))
            expect(member).to_have_url(re.compile(r"/accounts/login/\?next="))
            login(member, live_server, "synthetic_named_member", FINAL_PASSWORD)
            enroll_pin(member, live_server, FINAL_PASSWORD, NEW_USER_PIN)

            page.goto(detail_url)
            page.get_by_role("link", name="Deactivate account", exact=True).click()
            assert (
                sign(page, admin, "Sign and deactivate account", "Synthetic leave of absence")
                == 302
            )
            expect(page.get_by_text("Inactive", exact=True)).to_be_visible()
            member.goto(live_server.url + "/")
            expect(member).to_have_url(re.compile(r"/accounts/login/\?next="))
            login(member, live_server, "synthetic_named_member", FINAL_PASSWORD)
            expect(member.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
            expect(member).to_have_url(live_server.url + reverse("login"))
            page.get_by_role("link", name="Reactivate account", exact=True).click()
            assert (
                sign(page, admin, "Sign and reactivate account", "Synthetic return to laboratory")
                == 302
            )
            expect(page.get_by_text("Active", exact=True)).to_be_visible()
            login(member, live_server, "synthetic_named_member", FINAL_PASSWORD)
            expect(member).to_have_url(live_server.url + "/")
            page.screenshot(path=str(ARTIFACTS / "admin-management-history.png"), full_page=True)
            page.get_by_role("button", name="Page documentation", exact=True).click()
            panel = page.get_by_role("complementary", name="Page documentation", exact=True)
            expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
                "data-pagedocs-for", "accounts:user_detail"
            )
            expect(panel.get_by_role("heading", name="Account record", exact=True)).to_be_visible()
            expect(panel).to_contain_text("account_authorized")
            expect(panel).to_contain_text("Force password reset")
            expect(
                panel.get_by_role("heading", name="Not documented yet", exact=True)
            ).to_have_count(0)
            page.screenshot(
                path=str(ARTIFACTS / "admin-management-documentation.png"), full_page=True
            )
            panel.get_by_role("button", name="Close page documentation", exact=True).click()
            expect(panel).not_to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(ARTIFACTS / "admin-management-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.goto(live_server.url + reverse("accounts:user_list"))
            expect(page.get_by_role("heading", name="Users and roles", exact=True)).to_be_visible()
            page.screenshot(
                path=str(ARTIFACTS / "admin-management-list-mobile.png"), full_page=True
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.goto(
                live_server.url + reverse("accounts:user_action", args=[member_id, "identity"])
            )
            expect(page.get_by_label(re.compile(r"^First name\b"))).to_have_value("Synthetic")
            page.screenshot(
                path=str(ARTIFACTS / "admin-management-form-mobile.png"), full_page=True
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        except Exception:
            page.screenshot(path=str(ARTIFACTS / "admin-management-failure.png"), full_page=True)
            (ARTIFACTS / "admin-management-failure.html").write_text(page.content())
            member.screenshot(
                path=str(ARTIFACTS / "admin-management-member-failure.png"), full_page=True
            )
            raise
        finally:
            browser.close()
    target = django_user_model.objects.get(username="synthetic_named_member")
    assert target.is_active and not target.password_change_required
    assert not target.is_staff and not target.is_superuser
    assert set(target.groups.values_list("name", flat=True)) == {"analyst", "reviewer"}
    assert target.check_password(FINAL_PASSWORD)
    credential = PINCredential.objects.get(user=target)
    assert check_password(NEW_USER_PIN, credential.encoded)
    assert credential.failures == 0 and credential.locked_until is None
    actions = set(
        AuditEvent.objects.filter(
            object_type="accounts.user", object_id=str(target.pk)
        ).values_list("action", flat=True)
    )
    assert {
        "account.created",
        "account.roles",
        "account.reset_password",
        "account.password_changed",
        "account.unlock_pin",
        "account.reenroll_pin",
        "account.deactivate",
        "account.reactivate",
    } <= actions
    signatures = ElectronicSignature.objects.filter(
        object_type="accounts.user", object_id=str(target.pk)
    )
    assert signatures.count() == 7
    assert set(signatures.values_list("meaning", flat=True)) == {"account_authorized"}
    for signature in signatures:
        assert signature.signer_id == admin.pk
        assert signature.authentication_context["components"] == ["username", "pin"]
        assert signature.audit_event.after["revision"] == signature.revision
        for secret in [
            INITIAL_PASSWORD,
            FIRST_PASSWORD,
            TEMP_PASSWORD,
            FINAL_PASSWORD,
            USER_PIN,
            NEW_USER_PIN,
            ADMIN_PIN,
            credential.encoded,
        ]:
            assert secret not in str(signature.content)


def test_admin_cannot_remove_last_admin_or_self_escalate(live_server, account_admin):
    admin = account_admin
    before_revision = admin.management_revision
    before_signatures = ElectronicSignature.objects.count()
    before_events = AuditEvent.objects.filter(action__startswith="account.").count()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            login(page, live_server, admin.username, ADMIN_PASSWORD)
            detail = live_server.url + reverse("accounts:user_detail", args=[admin.pk])
            page.goto(detail)
            page.get_by_role("link", name="Assign roles", exact=True).click()
            page.get_by_role("checkbox", name="Admin", exact=True).uncheck()
            assert (
                sign(page, admin, "Sign and assign roles", "Attempt removal of final administrator")
                == 422
            )
            expect(
                page.get_by_text(
                    "Keep at least one active account with the admin role.", exact=True
                )
            ).to_be_visible()
            page.screenshot(path=str(ARTIFACTS / "admin-last-admin-denied.png"), full_page=True)
            page.goto(detail)
            page.get_by_role("link", name="Assign roles", exact=True).click()
            page.get_by_role("checkbox", name="Quality", exact=True).check()
            assert (
                sign(
                    page, admin, "Sign and assign roles", "Attempt self-granted scientific approval"
                )
                == 403
            )
            expect(
                page.get_by_role("heading", name="Access not permitted", exact=True)
            ).to_be_visible()
            page.screenshot(
                path=str(ARTIFACTS / "admin-self-escalation-denied.png"), full_page=True
            )
        finally:
            browser.close()
    admin.refresh_from_db()
    assert admin.is_active and admin.management_revision == before_revision
    assert set(admin.groups.values_list("name", flat=True)) == {"admin"}
    assert ElectronicSignature.objects.count() == before_signatures
    assert AuditEvent.objects.filter(action__startswith="account.").count() == before_events
