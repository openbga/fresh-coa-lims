"""A fresh bootstrap login has a useful landing page, without implicit lab authority."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.mark.django_db(transaction=True)
def test_bootstrap_account_access(live_server, django_user_model):
    password = "Synthetic-account-browser-2026!"
    django_user_model.objects.create_superuser("bootstrap", password=password)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(f"{live_server.url}/accounts/login/")
        page.get_by_label(re.compile(r"^Username\b")).fill("bootstrap")
        page.get_by_label(re.compile(r"^Password\b")).fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(f"{live_server.url}/accounts/access/")
        expect(
            page.get_by_role("heading", name="No laboratory role assigned", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_text("Ask your organization's account administrator", exact=False)
        ).to_be_visible()
        expect(page.get_by_role("link", name="Open workspace", exact=True)).to_have_count(0)
        page.get_by_role("link", name="View accounts in Django admin", exact=True).click()
        expect(page).to_have_url(f"{live_server.url}/admin/accounts/user/")
        expect(page.get_by_role("link", name="bootstrap", exact=True)).to_be_visible()
        page.goto(f"{live_server.url}/rules/")
        expect(
            page.get_by_role("heading", name="No laboratory role assigned", exact=True)
        ).to_be_visible()
        page.get_by_role("link", name="View account access", exact=True).click()
        expect(page).to_have_url(f"{live_server.url}/accounts/access/")
        page.get_by_role("button", name="Page documentation", exact=True).click()
        panel = page.get_by_role("complementary", name="Page documentation", exact=True)
        expect(panel.get_by_role("heading", name="Account access", exact=True)).to_be_visible()
        panel.get_by_role("button", name="Close page documentation", exact=True).click()
        artifacts = Path(".local/qa")
        artifacts.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(artifacts / "account-access-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(artifacts / "account-access-mobile.png"), full_page=True)
        page.get_by_role("button", name="Sign out", exact=True).click()
        expect(page).to_have_url(f"{live_server.url}/accounts/login/")
        browser.close()
