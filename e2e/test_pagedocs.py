"""Documentation panel matches navigation and remembers accessible resize controls.

Its open state and width are the signed-in person's preferences, kept on the server
(core/preferences.py), never in the browser: lab workstations are shared."""

import re
import time

import pytest
from django.contrib.auth.models import Group
from helpers import db_call
from playwright.sync_api import expect, sync_playwright

from core.models import UserPreference


def saved(user, key, expected, timeout=5.0):
    """The server-side preference once the page's background save has arrived (read off the
    Playwright thread)."""

    def stored():
        rows = UserPreference.objects.filter(user=user, key=key)
        return rows.values_list("value", flat=True).first()

    deadline = time.monotonic() + timeout
    while True:
        value = db_call(stored)
        if value == expected or time.monotonic() > deadline:
            return value
        time.sleep(0.1)


@pytest.mark.django_db(transaction=True)
def test_page_documentation_panel(live_server, django_user_model, artifacts):
    password = "Synthetic-pagedocs-browser-2026!"
    user = django_user_model.objects.create_user(
        username="synthetic_docs",
        password=password,
        first_name="Synthetic",
        last_name="Documentation Reviewer",
    )
    user.groups.add(Group.objects.get_or_create(name="quality")[0])
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
            page.goto(live_server.url + "/lots/")  # the lot list's documentation
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
            # Friendly layer first; the reference sections are collapsed under a filter.
            expect(panel.get_by_role("heading", name="Common tasks", exact=True)).to_be_visible()
            expect(panel.get_by_role("heading", name="Good to know", exact=True)).to_be_visible()
            expect(
                panel.locator("[data-pagedocs-tasks] .pagedocs-label", has_text="New material lot")
            ).to_be_visible()
            # The drawer runs the full height of the window under the top bar.
            box = panel.bounding_box()
            assert box["y"] + box["height"] == 1000
            # Jump links scroll the drawer to a part without changing the page or its address.
            address = page.url
            panel.get_by_role("link", name="All fields and actions", exact=True).click()
            expect(
                panel.get_by_role("heading", name="All fields and actions", exact=True)
            ).to_be_focused()
            assert page.url == address
            sections = panel.locator("[data-pagedocs-section]")
            expect(sections).to_have_count(7)
            actions = sections.filter(has=page.locator("summary", has_text="Actions"))
            purpose = sections.filter(has=page.locator("summary", has_text="Purpose"))
            expect(actions).to_have_js_property("open", False)
            find = panel.get_by_label("Find a field or action")
            find.fill("clear filters")
            expect(actions).to_have_js_property("open", True)
            expect(actions.locator("mark.pagedocs-hit").first).to_have_text(
                re.compile("^clear filters$", re.I)
            )
            expect(actions.locator("tbody tr", has_text="Source code")).to_be_hidden()
            expect(purpose).to_be_hidden()
            find.fill("no-such-synthetic-term")
            expect(panel.get_by_text("No field or action matches.")).to_be_visible()
            find.press("Escape")  # clears the filter; the panel stays open
            expect(find).to_have_value("")
            expect(panel).to_be_visible()
            expect(actions).to_have_js_property("open", False)
            expect(purpose).to_be_visible()
            expect(panel.locator("mark.pagedocs-hit")).to_have_count(0)
            panel.get_by_role("heading", name="Material lots", exact=True).focus()
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
            assert saved(user, "pagedocs.width", resized_width) == resized_width
            assert (
                page.evaluate("Object.keys(localStorage).filter(k => k.includes('pagedocs'))") == []
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
            # The panel covers the page: Tab cycles through the panel and the top bar only.
            panel.get_by_role("heading", name="Rule sets", exact=True).focus()
            for _ in range(30):
                page.keyboard.press("Tab")
                place = page.evaluate(
                    """() => {
                        const el = document.activeElement;
                        if (el.closest("#pagedocs-panel")) return "panel";
                        if (el.closest(".vr-topbar") || el === document.body) return "top bar";
                        return "covered: " + el.outerHTML.slice(0, 80);
                    }"""
                )
                assert place in ("panel", "top bar"), place
            panel.get_by_role("button", name="Close page documentation").click()
            expect(panel).not_to_be_visible()
            expect(page.locator("#main")).to_have_js_property("inert", False)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "pagedocs-mobile-closed.png"), full_page=True)
            toggle.click()
            expect(panel).to_be_visible()
            panel.get_by_role("heading", name="Rule sets", exact=True).press("Escape")
            expect(panel).not_to_be_visible()
            expect(toggle).to_be_focused()
            expect(page.locator("#main")).to_have_js_property("inert", False)
            assert saved(user, "pagedocs.open", False) is False
            toggle.click()
            expect(page.locator("#main")).to_have_js_property("inert", True)
            # Growing past the breakpoint restores the side-by-side page with the panel open.
            page.set_viewport_size({"width": 1440, "height": 1000})
            expect(panel).to_be_visible()
            expect(page.locator("#main")).to_have_js_property("inert", False)
            expect(splitter).to_have_attribute("aria-valuenow", str(resized_width))
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(artifacts / "pagedocs-failure.png"), full_page=True)
            (artifacts / "pagedocs-failure.html").write_text(page.content())
            raise
        finally:
            browser.close()
