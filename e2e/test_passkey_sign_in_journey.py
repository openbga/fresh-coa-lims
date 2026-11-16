"""Signing in with a passkey alone, in Chromium with virtual authenticators on localhost
(an IP address is not a valid RP ID): registration, the passkey sign-in, a key that does
not verify the person, a removed key, and both pages on a phone in both themes."""

import re

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import expect, sync_playwright

PASSWORD = "Synthetic-passkey-browser-2026!"
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap, .table-responsive')
    && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""
AUTHENTICATOR = {
    "protocol": "ctap2",
    "transport": "usb",
    "hasResidentKey": True,
    "hasUserVerification": True,
    "isUserVerified": True,
    "automaticPresenceSimulation": True,
}
NOT_REGISTERED = (
    "This passkey or security key is not registered for an account at this address, "
    "or it was removed. Sign in with your password."
)


def make_user(django_user_model, username, role="analyst"):
    user = django_user_model.objects.create_user(
        username=username, password=PASSWORD, first_name="Synthetic", last_name=username
    )
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


class Session:
    def __init__(self, browser, base, **context_options):
        self.base = base
        self.context = browser.new_context(**context_options)
        self.errors = []
        self.csp = []
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        # Failed resource loads of a deliberate 422 response are not application errors.
        self.page.on(
            "console",
            lambda m: (
                self.csp.append(m.text)
                if "Content Security Policy" in m.text
                else self.errors.append(m.text)
                if m.type == "error" and "status of 422" not in m.text
                else None
            ),
        )
        self.cdp = self.context.new_cdp_session(self.page)
        self.cdp.send("WebAuthn.enable")

    def add_authenticator(self, **options):
        return self.cdp.send(
            "WebAuthn.addVirtualAuthenticator", {"options": {**AUTHENTICATOR, **options}}
        )["authenticatorId"]

    def remove_authenticator(self, authenticator):
        self.cdp.send("WebAuthn.removeVirtualAuthenticator", {"authenticatorId": authenticator})

    def credentials(self, authenticator):
        return self.cdp.send("WebAuthn.getCredentials", {"authenticatorId": authenticator})[
            "credentials"
        ]

    def password_sign_in(self, username):
        page = self.page
        page.goto(f"{self.base}/accounts/login/")
        page.get_by_label(re.compile(r"^Username\b")).fill(username)
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()

    def sign_out(self):
        self.page.get_by_role("button", name="Sign out", exact=True).click()
        expect(self.page).to_have_url(re.compile(r"/accounts/login/$"))

    def open_two_factor(self):
        page = self.page
        page.goto(f"{self.base}/accounts/access/")
        page.get_by_role("link", name="Two-factor sign-in", exact=True).click()
        expect(page.get_by_role("heading", name="Status")).to_be_visible()

    def register_first_key(self, name):
        page = self.page
        self.open_two_factor()
        page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Set up with a security key or passkey", exact=True).click()
        expect(page.get_by_role("heading", name="Register the key")).to_be_visible()
        page.get_by_label(re.compile(r"^Name\b")).fill(name)
        page.get_by_role("button", name="Register the key", exact=True).click()
        expect(page.locator("ol.vr-recovery-codes code")).to_have_count(10)
        page.get_by_role("link", name="I have saved the codes", exact=True).click()
        expect(page.get_by_text("On since", exact=False)).to_be_visible()

    def start_adding_key(self, name):
        """Confirm with the password and an existing key, then fill in the name."""
        page = self.page
        self.open_two_factor()
        page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Add a security key or passkey", exact=True).click()
        expect(page.get_by_role("heading", name="Register the key")).to_be_visible()
        page.get_by_label(re.compile(r"^Name\b")).fill(name)
        page.get_by_role("button", name="Register the key", exact=True).click()

    def open_passkey_page(self):
        page = self.page
        page.goto(f"{self.base}/accounts/login/")
        page.get_by_role("button", name="Sign in with a passkey", exact=True).click()
        expect(page.get_by_role("heading", name="Sign in with a passkey")).to_be_visible()
        assert not page.get_by_label(re.compile(r"^Password\b")).count()

    def signed_in_as(self, user):
        page = self.page
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        expect(page).not_to_have_url(re.compile(r"/login"))
        page.goto(f"{self.base}/accounts/access/")
        expect(page.get_by_text(user.username).first).to_be_attached()


def keys_table(page):
    return page.locator("section[aria-labelledby=security-keys] tbody tr")


@pytest.mark.django_db(transaction=True)
def test_passkey_sign_in_journey(live_server, django_user_model, artifacts):
    analyst = make_user(django_user_model, "analyst.passkey")
    make_user(django_user_model, "removed.passkey")
    make_user(django_user_model, "phone.passkey")
    base = live_server.url.replace("127.0.0.1", "localhost")
    shots = artifacts / "passkey-sign-in"
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        # 1-2. Register a passkey, sign out, sign in with the passkey alone.
        s = Session(browser, base, viewport={"width": 1440, "height": 1000})
        page = s.page
        auth = s.add_authenticator()
        s.password_sign_in(analyst.username)
        expect(page).not_to_have_url(re.compile(r"/login"))
        s.register_first_key("Desk passkey")
        assert len(s.credentials(auth)) == 1
        s.sign_out()

        s.open_passkey_page()
        use = page.get_by_role("button", name="Use your passkey", exact=True)
        expect(use).to_be_enabled()
        expect(page.get_by_text("This browser cannot use passkeys here.")).to_be_hidden()
        use.click()
        s.signed_in_as(analyst)
        s.sign_out()

        # 3a. A key that does not check the person is refused in the browser; no sign-in.
        s.cdp.send("WebAuthn.setUserVerified", {"authenticatorId": auth, "isUserVerified": False})
        s.open_passkey_page()
        s.page.get_by_role("button", name="Use your passkey", exact=True).click()
        status = page.locator("[data-security-key-status]")
        expect(status).to_contain_text("The security key was not used, or the request timed out.")
        expect(status).to_contain_text("sign in with your password")
        expect(page.get_by_role("heading", name="Sign in with a passkey")).to_be_visible()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="Use your passkey", exact=True)).to_be_enabled()
        # Verified again: the same page works on a retry.
        s.cdp.send("WebAuthn.setUserVerified", {"authenticatorId": auth, "isUserVerified": True})
        page.get_by_role("button", name="Use your passkey", exact=True).click()
        s.signed_in_as(analyst)
        s.sign_out()
        assert not s.errors, s.errors
        assert not s.csp, s.csp
        s.context.close()

        # 3b. A removed key: the stale credential on the authenticator is not registered.
        r = Session(browser, base)
        rpage = r.page
        first = r.add_authenticator()
        r.password_sign_in("removed.passkey")
        r.register_first_key("Old passkey")
        stale = r.credentials(first)
        assert len(stale) == 1
        # The first authenticator refuses a second registration for the same account.
        r.start_adding_key("Newer passkey")
        expect(
            rpage.get_by_text("This key is already registered for your account.")
        ).to_be_visible()
        r.remove_authenticator(first)
        second = r.add_authenticator()
        rpage.get_by_role("button", name="Register the key", exact=True).click()
        expect(rpage.get_by_role("heading", name="Status")).to_be_visible()
        assert len(r.credentials(second)) == 1
        expect(keys_table(rpage)).to_have_count(2)
        # Remove the old key, confirmed with the password and the newer key.
        rpage.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        rpage.get_by_role("button", name="Remove Old passkey").click()
        expect(keys_table(rpage)).to_have_count(1)
        expect(rpage.get_by_text("Old passkey")).to_have_count(0)
        r.sign_out()
        r.remove_authenticator(second)
        third = r.add_authenticator()
        for credential in stale:
            r.cdp.send(
                "WebAuthn.addCredential", {"authenticatorId": third, "credential": credential}
            )
        r.open_passkey_page()
        rpage.get_by_role("button", name="Use your passkey", exact=True).click()
        expect(rpage.get_by_text(NOT_REGISTERED)).to_be_visible()
        expect(rpage.get_by_role("button", name="Sign out", exact=True)).to_have_count(0)
        assert rpage.url.endswith("/accounts/login/passkey/") or "passkey" in rpage.url
        assert not r.errors, r.errors
        assert not r.csp, r.csp
        r.context.close()

        # 4. Both pages on a phone in both themes.
        phone = Session(browser, base, viewport={"width": 390, "height": 844})
        qpage = phone.page
        phone.add_authenticator()
        phone.password_sign_in("phone.passkey")
        phone.register_first_key("Phone passkey")
        phone.sign_out()

        def choose_theme(theme):
            qpage.get_by_role("button", name="Theme", exact=True).click()
            qpage.get_by_role("button", name=theme, exact=True).click()
            expect(qpage.locator("html")).to_have_attribute("data-bs-theme", theme.lower())

        def check(name):
            qpage.wait_for_timeout(500)
            wider = qpage.evaluate(WIDER_THAN_THE_PAGE)
            assert qpage.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                name,
                wider,
            )
            assert wider == [], (name, wider)
            qpage.screenshot(path=str(shots / f"{name}.png"), full_page=True)

        qpage.goto(f"{base}/accounts/login/")
        for theme in ("Light", "Dark"):
            choose_theme(theme)
            check(f"sign-in-{theme.lower()}")
        qpage.get_by_role("button", name="Sign in with a passkey", exact=True).click()
        expect(qpage.get_by_role("heading", name="Sign in with a passkey")).to_be_visible()
        for theme in ("Light", "Dark"):
            choose_theme(theme)
            check(f"passkey-{theme.lower()}")
        qpage.get_by_role("button", name="Use your passkey", exact=True).click()
        expect(qpage.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        assert not phone.errors, phone.errors
        assert not phone.csp, phone.csp
        browser.close()
