"""The phone shell reserves space for its controls with Linux system-font metrics."""

import re

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import expect, sync_playwright


@pytest.mark.django_db(transaction=True)
def test_shell_controls_fit_the_viewport(live_server, django_user_model, artifacts):
    password = "Synthetic-shell-browser-2026!"
    user = django_user_model.objects.create_user(username="shell", password=password)
    user.groups.add(Group.objects.get_or_create(name="quality")[0])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{live_server.url}/accounts/login/")
        page.get_by_label(re.compile(r"^Username\b")).fill(user.username)
        page.get_by_label(re.compile(r"^Password\b")).fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.get_by_role("heading", name="Material lots", exact=True)).to_be_visible()
        bar = page.locator(".vr-topbar")
        controls = [
            bar.get_by_role("button", name="Theme", exact=True),
            bar.get_by_role("button", name="Sign out", exact=True),
            bar.get_by_role("button", name="Page documentation", exact=True),
        ]
        for width in (320, 390, 768, 1440):
            page.set_viewport_size({"width": width, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            visible_controls = controls[:]
            if width < 992:
                visible_controls.insert(0, bar.get_by_role("button", name="Menu", exact=True))
            previous_right = 0
            for control in visible_controls:
                expect(control).to_be_visible()
                bounds = control.bounding_box()
                assert bounds["x"] >= previous_right
                assert bounds["x"] + bounds["width"] <= width
                assert bounds["y"] + bounds["height"] <= bar.bounding_box()["height"]
                previous_right = bounds["x"] + bounds["width"]
            if width in (390, 1440):
                page.screenshot(path=str(artifacts / f"ci-shell-{width}.png"), full_page=True)
        # Error pages carry the shell, a page title and one level-one heading.
        page.goto(f"{live_server.url}/no-such-synthetic-page/")
        expect(page).to_have_title("Page not found · OpenBGA QLab")
        expect(page.get_by_role("heading", level=1)).to_have_text("Page not found")
        browser.close()
