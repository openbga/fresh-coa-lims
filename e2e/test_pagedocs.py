"""Documentation panel matches navigation and remembers accessible resize controls."""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import expect, sync_playwright


@pytest.mark.django_db(transaction=True)
def test_page_documentation_panel(live_server, django_user_model):
    password = "Synthetic-pagedocs-browser-2026!"
    user = django_user_model.objects.create_user(
        username="synthetic_docs",
        password=password,
        first_name="Synthetic",
        last_name="Documentation Reviewer",
    )
    user.groups.add(Group.objects.get_or_create(name="quality")[0])
    artifacts = Path(".local/qa")
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{live_server.url}/accounts/login/")
            page.get_by_label(re.compile(r"^Username\b")).fill(user.username)
            page.get_by_label(re.compile(r"^Password\b")).fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(live_server.url + "/")
            toggle = page.get_by_role("button", name="Page documentation", exact=True)
            panel = page.get_by_role("complementary", name="Page documentation", exact=True)
            expect(panel).not_to_be_visible()
            toggle.click()
            expect(panel).to_be_visible()
            expect(toggle).to_have_attribute("aria-expanded", "true")
            expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
                "data-pagedocs-for", "quality:lot_list"
            )
            expect(panel.get_by_role("heading", name="Material lots", exact=True)).to_be_focused()
            expect(panel.get_by_role("heading", name="Actions", exact=True)).to_be_visible()
            splitter = page.get_by_role("separator", name="Resize page documentation")
            original_width = int(splitter.get_attribute("aria-valuenow"))
            splitter.focus()
            splitter.press("Shift+ArrowLeft")
            expect(splitter).to_have_attribute("aria-valuenow", str(original_width + 64))
            bounds = splitter.bounding_box()
            page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + 100)
            page.mouse.down()
            page.mouse.move(bounds["x"] - 80, bounds["y"] + 100, steps=8)
            page.mouse.up()
            resized_width = int(splitter.get_attribute("aria-valuenow"))
            assert resized_width > original_width + 64
            assert page.evaluate("localStorage.getItem('openbga-qlab-pagedocs-width')") == str(
                resized_width
            )
            page.reload()
            expect(panel).to_be_visible()
            expect(splitter).to_have_attribute("aria-valuenow", str(resized_width))
            expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
                "data-pagedocs-for", "quality:lot_list"
            )
            page.get_by_role("navigation", name="Primary").get_by_role(
                "link", name="Rule sets", exact=True
            ).click()
            expect(panel).to_be_visible()
            expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
                "data-pagedocs-for", "core:rules"
            )
            expect(panel.get_by_role("heading", name="Rule sets", exact=True)).to_be_visible()
            expect(splitter).to_have_attribute("aria-valuenow", str(resized_width))
            page.screenshot(path=str(artifacts / "pagedocs-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            expect(panel).to_be_visible()
            expect(splitter).not_to_be_visible()
            assert panel.bounding_box()["width"] == 390
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "pagedocs-mobile-open.png"), full_page=True)
            panel.get_by_role("button", name="Close page documentation").click()
            expect(panel).not_to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "pagedocs-mobile-closed.png"), full_page=True)
            toggle.click()
            expect(panel).to_be_visible()
            panel.get_by_role("heading", name="Rule sets", exact=True).press("Escape")
            expect(panel).not_to_be_visible()
            expect(toggle).to_be_focused()
            assert page.evaluate("localStorage.getItem('openbga-qlab-pagedocs-open')") == "0"
            page.set_viewport_size({"width": 1440, "height": 1000})
            toggle.click()
            expect(splitter).to_have_attribute("aria-valuenow", str(resized_width))
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(artifacts / "pagedocs-failure.png"), full_page=True)
            (artifacts / "pagedocs-failure.html").write_text(page.content())
            raise
        finally:
            browser.close()
