"""Single sign-on with the organization's identity provider, in Chromium against the local
OpenID provider of accounts/tests: linking, signing in without a password, an identity that is
not linked, unlinking, and both pages on a phone."""

import re

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import expect, sync_playwright

from accounts import single_sign_on
from accounts.tests.oidc_provider import CLIENT_ID, CLIENT_SECRET, Provider

PASSWORD = "Synthetic-sso-browser-2026!"
PROVIDER_NAME = "Synthetic Org"
LABEL = "analyst@synthetic.example"
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap, .table-responsive')
    && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""


@pytest.fixture
def provider(settings):
    with Provider() as running:
        settings.OIDC_ISSUER = running.issuer
        settings.OIDC_CLIENT_ID = CLIENT_ID
        settings.OIDC_CLIENT_SECRET = CLIENT_SECRET
        settings.OIDC_PROVIDER_NAME = PROVIDER_NAME
        settings.SINGLE_SIGN_ON = True
        single_sign_on._client.cache_clear()
        yield running
    single_sign_on._client.cache_clear()


def password_sign_in(page, base, username):
    page.goto(f"{base}/accounts/login/")
    page.get_by_label(re.compile(r"^Username\b")).fill(username)
    page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()


def sign_out(page):
    page.get_by_role("button", name="Sign out", exact=True).click()
    expect(page).to_have_url(re.compile(r"/accounts/login/$"))


def sso_sign_in(page, base, provider, subject):
    provider.next_subject = subject
    page.goto(f"{base}/accounts/login/")
    page.get_by_role("link", name=f"Sign in with {PROVIDER_NAME}", exact=True).click()


def facts(page):
    return page.locator("section[aria-labelledby=sso-status] dl")


@pytest.mark.django_db(transaction=True)
def test_single_sign_on_journey(live_server, django_user_model, provider, artifacts):
    analyst = django_user_model.objects.create_user(
        username="analyst.sso", password=PASSWORD, first_name="Synthetic", last_name="Analyst"
    )
    analyst.groups.add(Group.objects.get_or_create(name="analyst")[0])
    provider.claims["sub-analyst"] = {"preferred_username": LABEL}
    base = live_server.url
    shots = artifacts / "single-sign-on"
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("request", lambda r: print("REQ", r.method, r.url))
        page.on("response", lambda r: print("RESP", r.status, r.url))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda m: errors.append(m.text) if m.type == "error" else None,
        )

        # 1. Link the organization account from Account access.
        password_sign_in(page, base, analyst.username)
        page.goto(f"{base}/accounts/access/")
        page.get_by_role("link", name="Organization sign-in", exact=True).click()
        expect(page.get_by_role("heading", name="Status")).to_be_visible()
        expect(facts(page)).to_contain_text("Not linked")
        page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        provider.next_subject = "sub-analyst"
        page.get_by_role("button", name=f"Continue to {PROVIDER_NAME}", exact=True).click()
        expect(page.get_by_text("Your account is linked to", exact=False).first).to_be_visible()
        expect(page).to_have_url(re.compile(r"/accounts/single-sign-on/$"))
        expect(facts(page)).to_contain_text(LABEL)
        expect(facts(page)).not_to_contain_text("Not linked")
        expect(page.get_by_text(f"linked to {LABEL}", exact=False).first).to_be_visible()
        assert len(provider.authorize_requests) == 1
        sign_out(page)

        # 2. Sign in with the provider, without a password.
        sso_sign_in(page, base, provider, "sub-analyst")
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        expect(page).not_to_have_url(re.compile(r"/login"))
        page.goto(f"{base}/accounts/access/")
        expect(page.get_by_text(analyst.username).first).to_be_attached()
        sign_out(page)

        # 3. An identity that is not linked is refused, on the sign-in page.
        sso_sign_in(page, base, provider, "sub-stranger")
        expect(page).to_have_url(re.compile(r"/accounts/login/$"))
        expect(
            page.get_by_text("is not linked to a laboratory account", exact=False)
        ).to_be_visible()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_have_count(0)
        # The way forward is on the page: the password form and the help text.
        expect(page.get_by_label(re.compile(r"^Password\b"))).to_be_visible()
        expect(
            page.get_by_text("Organization sign-in under Account access", exact=False).first
        ).to_be_visible()

        # 4. Unlink with the password; the identity is then refused.
        password_sign_in(page, base, analyst.username)
        page.goto(f"{base}/accounts/single-sign-on/")
        expect(facts(page)).to_contain_text(LABEL)
        page.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Unlink the organization account", exact=True).click()
        expect(
            page.get_by_text("Your account is no longer linked", exact=False).first
        ).to_be_visible()
        expect(facts(page)).to_contain_text("Not linked")
        sign_out(page)
        sso_sign_in(page, base, provider, "sub-analyst")
        expect(page).to_have_url(re.compile(r"/accounts/login/$"))
        expect(
            page.get_by_text("is not linked to a laboratory account", exact=False)
        ).to_be_visible()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_have_count(0)
        assert not errors, errors
        context.close()

        # 5. Both pages on a phone.
        phone = browser.new_context(viewport={"width": 390, "height": 844})
        qpage = phone.new_page()
        phone_errors = []
        qpage.on("pageerror", lambda error: phone_errors.append(str(error)))

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
        expect(
            qpage.get_by_role("link", name=f"Sign in with {PROVIDER_NAME}", exact=True)
        ).to_be_visible()
        check("sign-in")
        password_sign_in(qpage, base, analyst.username)
        qpage.goto(f"{base}/accounts/single-sign-on/")
        expect(facts(qpage)).to_contain_text("Not linked")
        check("organization-sign-in-not-linked")
        qpage.get_by_label(re.compile(r"^Current password\b")).fill(PASSWORD)
        provider.next_subject = "sub-analyst"
        qpage.get_by_role("button", name=f"Continue to {PROVIDER_NAME}", exact=True).click()
        expect(qpage.get_by_text("Your account is linked to", exact=False).first).to_be_visible()
        expect(facts(qpage)).to_contain_text(LABEL)
        check("organization-sign-in-linked")
        assert not phone_errors, phone_errors
        browser.close()
