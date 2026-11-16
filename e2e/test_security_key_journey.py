"""Security keys and passkeys as a second sign-in factor, in Chromium with virtual
authenticators: registration, signing in with the key, a second key, removal, a lost key
(recovery code), a browser without Web Authentication, and the pages on a phone."""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import expect, sync_playwright

PASSWORD = "Synthetic-security-key-browser-2026!"
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
SHOTS = Path("/tmp/seckey-e2e")


def make_user(django_user_model, username, role="analyst"):
    user = django_user_model.objects.create_user(
        username=username, password=PASSWORD, first_name="Synthetic", last_name=username
    )
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


class Session:
    """A browser context with a page, error collection and virtual authenticators."""

    def __init__(self, browser, base, **context_options):
        self.base = base
        self.context = browser.new_context(**context_options)
        self.errors = []
        self.csp = []
        self.page = None

    def start(self, init_script=None):
        if init_script:
            self.context.add_init_script(init_script)
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on(
            "console",
            lambda m: self.csp.append(m.text) if "Content Security Policy" in m.text else None,
        )
        self.cdp = self.context.new_cdp_session(self.page)
        return self.page

    def add_authenticator(self):
        self.cdp.send("WebAuthn.enable")
        return self.cdp.send("WebAuthn.addVirtualAuthenticator", {"options": AUTHENTICATOR})[
            "authenticatorId"
        ]

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
        """Account access -> Two-factor sign-in -> registration; returns the recovery codes."""
        page = self.page
        self.open_two_factor()
        expect(page.get_by_text("Off", exact=True)).to_be_visible()
        page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Set up with a security key or passkey", exact=True).click()
        expect(page.get_by_role("heading", name="Register the key")).to_be_visible()
        page.get_by_label(re.compile(r"^Name\b")).fill(name)
        page.get_by_role("button", name="Register the key", exact=True).click()
        codes = page.locator("ol.vr-recovery-codes code")
        expect(codes).to_have_count(10)
        return [c.strip() for c in codes.all_inner_texts()]

    def start_adding_key(self):
        """On Two-factor sign-in: confirm with the password and an existing key, then add."""
        page = self.page
        self.open_two_factor()
        page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        page.locator("input[name=otp_code]").fill("")
        page.get_by_role("button", name="Add a security key or passkey", exact=True).click()
        expect(page.get_by_role("heading", name="Register the key")).to_be_visible()


def keys_table(page):
    return page.locator("section[aria-labelledby=security-keys] tbody tr")


@pytest.mark.django_db(transaction=True)
def test_security_key_journey(live_server, django_user_model, artifacts):
    make_user(django_user_model, "analyst.test")
    make_user(django_user_model, "unsupported.test")
    make_user(django_user_model, "phone.test")
    base = live_server.url
    SHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        s = Session(browser, base, viewport={"width": 1440, "height": 1000})
        page = s.start()
        first = s.add_authenticator()

        # 1. Register the first key; two-factor turns on and recovery codes are shown once.
        s.password_sign_in("analyst.test")
        expect(page).not_to_have_url(re.compile(r"/login"))
        codes = s.register_first_key("Desk key")
        assert len(set(codes)) == 10
        assert len(s.credentials(first)) == 1
        page.get_by_role("link", name="I have saved the codes", exact=True).click()
        expect(page.get_by_text("On since", exact=False)).to_be_visible()
        expect(page.get_by_text("10 of 10", exact=False)).to_be_visible()
        expect(keys_table(page)).to_have_count(1)
        row = keys_table(page).first
        expect(row).to_contain_text("Desk key")
        expect(row).to_contain_text("Kept on one device")
        expect(row.get_by_role("button", name="Remove Desk key")).to_be_visible()
        s.sign_out()

        # 2. Password, then the key signs in.
        s.password_sign_in("analyst.test")
        expect(page.get_by_role("heading", name="Two-factor sign-in", exact=True)).to_be_visible()
        use_key = page.get_by_role("button", name="Use your security key", exact=True)
        expect(use_key).to_be_enabled()
        expect(page.get_by_text("This browser cannot use security keys here.")).to_be_hidden()
        use_key.click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        expect(page).not_to_have_url(re.compile(r"/login"))
        page.goto(f"{base}/")
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()

        # 3. A second key: the first authenticator already holds a credential for the
        # account, so the browser refuses it; a second authenticator registers.
        s.start_adding_key()
        page.get_by_label(re.compile(r"^Name\b")).fill("Spare key")
        page.get_by_role("button", name="Register the key", exact=True).click()
        expect(
            page.get_by_text("This key is already registered for your account. Use another key.")
        ).to_be_visible()
        expect(page.get_by_role("button", name="Register the key", exact=True)).to_be_enabled()
        s.remove_authenticator(first)
        second = s.add_authenticator()
        page.get_by_role("button", name="Register the key", exact=True).click()
        expect(page.get_by_role("heading", name="Status")).to_be_visible()
        expect(keys_table(page)).to_have_count(2)
        expect(page.get_by_text("2 of at most", exact=False)).to_be_visible()
        assert len(s.credentials(second)) == 1
        # Remove Desk key, confirmed with the password and a key (the second one answers).
        page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Remove Desk key").click()
        expect(keys_table(page)).to_have_count(1)
        expect(keys_table(page).first).to_contain_text("Spare key")
        expect(page.get_by_text("Desk key")).to_have_count(0)
        s.sign_out()

        # 4. Lost key: only a recovery code is left.
        s.remove_authenticator(second)
        s.password_sign_in("analyst.test")
        expect(page.get_by_role("heading", name="Two-factor sign-in", exact=True)).to_be_visible()
        page.get_by_label(re.compile(r"^Recovery code\b")).fill(codes[0])
        page.get_by_role("button", name="Verify the code and sign in", exact=True).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        expect(
            page.get_by_text(re.compile(r"You signed in with a recovery code\.")).first
        ).to_be_visible()
        s.sign_out()
        assert not s.errors, s.errors
        assert not s.csp, s.csp

        # 5. A browser without Web Authentication: the key button is disabled, codes work.
        # The key is registered first by a supporting context.
        s.context.close()
        enroll = Session(browser, base)
        epage = enroll.start()
        enroll.add_authenticator()
        enroll.password_sign_in("unsupported.test")
        unsupported_codes = enroll.register_first_key("Only key")
        enroll.context.close()
        plain = Session(browser, base)
        ppage = plain.start("delete window.PublicKeyCredential")
        plain.password_sign_in("unsupported.test")
        expect(ppage.get_by_role("heading", name="Two-factor sign-in", exact=True)).to_be_visible()
        expect(ppage.get_by_text("This browser cannot use security keys here.")).to_be_visible()
        expect(
            ppage.get_by_role("button", name="Use your security key", exact=True)
        ).to_be_disabled()
        ppage.get_by_label(re.compile(r"^Recovery code\b")).fill(unsupported_codes[0])
        ppage.get_by_role("button", name="Verify the code and sign in", exact=True).click()
        expect(ppage.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        assert not plain.errors, plain.errors
        assert not plain.csp, plain.csp
        assert not enroll.errors and not enroll.csp, (enroll.errors, enroll.csp)
        plain.context.close()
        del epage

        # 6. The pages on a phone, in both themes.
        phone = Session(browser, base, viewport={"width": 390, "height": 844})
        qpage = phone.start()
        a = phone.add_authenticator()

        def choose_theme(theme):
            qpage.get_by_role("button", name="Theme", exact=True).click()
            qpage.get_by_role("button", name=theme, exact=True).click()
            expect(qpage.locator("html")).to_have_attribute("data-bs-theme", theme.lower())

        def check(name):
            qpage.wait_for_timeout(500)  # let the theme transition finish
            assert qpage.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                name,
                qpage.evaluate(WIDER_THAN_THE_PAGE),
            )
            assert qpage.evaluate(WIDER_THAN_THE_PAGE) == [], (
                name,
                qpage.evaluate(WIDER_THAN_THE_PAGE),
            )
            qpage.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)

        phone.password_sign_in("phone.test")
        phone.register_first_key("Phone desk key")
        qpage.get_by_role("link", name="I have saved the codes", exact=True).click()
        expect(keys_table(qpage)).to_have_count(1)
        phone.sign_out()
        phone.password_sign_in("phone.test")
        expect(qpage.get_by_role("heading", name="Two-factor sign-in", exact=True)).to_be_visible()
        for theme in ("Light", "Dark"):
            choose_theme(theme)
            check(f"second-step-{theme.lower()}")
        qpage.get_by_role("button", name="Use your security key", exact=True).click()
        expect(qpage.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        # Registration page, then the status page with two keys.
        phone.start_adding_key()
        qpage.get_by_label(re.compile(r"^Name\b")).fill("Phone spare key")
        for theme in ("Light", "Dark"):
            choose_theme(theme)
            check(f"register-{theme.lower()}")
        phone.remove_authenticator(a)
        phone.add_authenticator()
        qpage.get_by_role("button", name="Register the key", exact=True).click()
        expect(keys_table(qpage)).to_have_count(2)
        for theme in ("Light", "Dark"):
            choose_theme(theme)
            check(f"two-keys-{theme.lower()}")
        remove = qpage.get_by_role("button", name="Remove Phone spare key")
        box = remove.bounding_box()
        # The whole Remove button is on screen without scrolling the table sideways; a table
        # in a scroll frame passes the overflow check while hiding it.
        frame = qpage.locator("section[aria-labelledby=security-keys]").bounding_box()
        assert box and box["x"] + box["width"] <= min(390, frame["x"] + frame["width"]), box
        no_sideways = qpage.evaluate(
            "() => [...document.querySelectorAll('.table-responsive')]"
            ".every(e => e.scrollWidth <= e.clientWidth + 1)"
        )
        assert no_sideways, "A table scrolls sideways on a phone."
        assert not phone.errors, phone.errors
        assert not phone.csp, phone.csp
        browser.close()
