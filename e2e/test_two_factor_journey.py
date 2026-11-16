"""Two-factor sign-in through the pages, in Chromium: an authenticator app, the second sign-in
step, a recovery code, a deployment requirement, and the setup pages on a phone."""

import base64
import re
import time
from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from django_otp.oath import TOTP
from playwright.sync_api import expect, sync_playwright

PASSWORD = "Synthetic-two-factor-browser-2026!"
# What makes a page scroll sideways on a phone: elements that reach past the right edge.
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""


def make_user(django_user_model, username, role):
    user = django_user_model.objects.create_user(
        username=username, password=PASSWORD, first_name="Synthetic", last_name=username
    )
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


def totp_code(key_text, steps=0):
    """The 6-digit code an authenticator app shows for the key text on the page."""
    key = base64.b32decode(key_text.replace(" ", "").upper())
    totp = TOTP(key, 30, 0, 6)
    totp.time = time.time() + steps * 30
    return f"{totp.token():06d}"


@pytest.mark.django_db(transaction=True)
def test_two_factor_sign_in_journey(live_server, django_user_model, settings, artifacts):
    make_user(django_user_model, "analyst.test", "analyst")
    make_user(django_user_model, "reviewer.test", "reviewer")
    make_user(django_user_model, "phone.test", "analyst")
    base = live_server.url
    shots = Path("/tmp/tfa-e2e")
    shots.mkdir(parents=True, exist_ok=True)
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def password_sign_in(username):
            page.goto(f"{base}/accounts/login/")
            page.get_by_label(re.compile(r"^Username\b")).fill(username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()

        def code_field():
            return page.locator("input[name=otp_code]")

        def sign_out():
            page.get_by_role("button", name="Sign out", exact=True).click()
            expect(page).to_have_url(re.compile(r"/accounts/login/$"))

        def set_up():
            """Account access -> Two-factor sign-in -> key page; returns the key text."""
            page.goto(f"{base}/accounts/access/")
            page.get_by_role("link", name="Two-factor sign-in", exact=True).click()
            expect(page.get_by_text("Off", exact=True)).to_be_visible()
            page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Set up with an authenticator app", exact=True).click()
            expect(page.locator("svg.vr-qr")).to_be_visible()
            key = page.locator("code.vr-secret-key").inner_text()
            assert re.fullmatch(r"[A-Z2-7 ]{16,}", key.strip()), key
            return key

        # 1. Set up with the authenticator app and read the recovery codes.
        password_sign_in("analyst.test")
        expect(page).not_to_have_url(re.compile(r"/login"))
        key = set_up()
        expect(page.get_by_role("img", name=re.compile("QR code"))).to_be_visible()
        code_field().fill(totp_code(key))
        page.get_by_role("button", name="Confirm and turn on", exact=True).click()
        expect(page.get_by_text("This is the only time these codes are shown.")).to_be_visible()
        codes = page.locator("ol.vr-recovery-codes code")
        expect(codes).to_have_count(10)
        recovery = codes.first.inner_text().strip()
        page.get_by_role("link", name="I have saved the codes", exact=True).click()
        expect(page.get_by_text("9 of 10", exact=False)).to_have_count(0)
        expect(page.get_by_text("10 of 10", exact=False)).to_be_visible()
        sign_out()

        # 2. Password then code: a wrong code is refused, the next step's code signs in.
        password_sign_in("analyst.test")
        expect(page.get_by_role("heading", name="Two-factor sign-in", exact=True)).to_be_visible()
        verify = page.get_by_role("button", name="Verify and sign in", exact=True)
        code_field().fill("000000" if totp_code(key, 1) != "000000" else "111111")
        verify.click()
        expect(page.get_by_text("The code was not accepted.").first).to_be_visible()
        code_field().fill(totp_code(key, 1))
        verify.click()
        expect(page.get_by_role("heading", name="Two-factor sign-in", exact=True)).to_have_count(0)
        expect(page).not_to_have_url(re.compile(r"/login"))
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        sign_out()

        # 3. A recovery code typed in lower case without hyphens signs in once.
        password_sign_in("analyst.test")
        code_field().fill(recovery.replace("-", "").lower())
        page.get_by_role("button", name="Verify and sign in", exact=True).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        warning = page.get_by_text(
            re.compile(r"You signed in with a recovery code\. 9 unused recovery codes left\.", re.I)
        )
        expect(warning.first).to_be_visible()
        sign_out()

        # 4. A role the deployment requires to use two-factor is sent to set it up.
        settings.MFA_REQUIRED_ROLES = frozenset({"reviewer"})
        password_sign_in("reviewer.test")
        page.goto(f"{base}/")
        expect(page).to_have_url(f"{base}/accounts/two-factor/")
        expect(page.get_by_text("Set up two-factor sign-in before continuing.")).to_be_visible()
        sign_out()
        settings.MFA_REQUIRED_ROLES = frozenset()

        # 5. The setup and recovery pages on a phone, in both themes.
        page.set_viewport_size({"width": 390, "height": 844})
        password_sign_in("phone.test")
        key = set_up()

        def choose_theme(theme):
            page.get_by_role("button", name="Theme", exact=True).click()
            page.get_by_role("button", name=theme, exact=True).click()
            expect(page.locator("html")).to_have_attribute("data-bs-theme", theme.lower())

        def check(name):
            page.wait_for_timeout(500)  # let the theme transition finish
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                name,
                page.evaluate(WIDER_THAN_THE_PAGE),
            )
            assert not page.evaluate(WIDER_THAN_THE_PAGE), (
                name,
                page.evaluate(WIDER_THAN_THE_PAGE),
            )
            page.screenshot(path=str(shots / f"{name}.png"), full_page=True)

        for theme in ("Light", "Dark"):
            choose_theme(theme)
            qr = page.locator("svg.vr-qr").bounding_box()
            assert qr["x"] >= 0 and qr["x"] + qr["width"] <= 390, qr
            assert qr["width"] >= 120, qr
            check(f"setup-{theme.lower()}")
        code_field().fill(totp_code(key))
        page.get_by_role("button", name="Confirm and turn on", exact=True).click()
        expect(page.locator("ol.vr-recovery-codes code")).to_have_count(10)
        for theme in ("Dark", "Light"):
            choose_theme(theme)
            check(f"recovery-{theme.lower()}")
        browser.close()
    assert not errors, errors
