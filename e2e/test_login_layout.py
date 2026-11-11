"""The illustrated entrance keeps sign-in usable across themes and narrow viewports."""

import re

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import expect, sync_playwright


@pytest.mark.django_db(transaction=True)
def test_login_themes_layout_and_keyboard_submission(live_server, django_user_model, artifacts):
    password = "Synthetic-login-layout-2026!"
    user = django_user_model.objects.create_user("login-layout", password=password)
    user.groups.add(Group.objects.get_or_create(name="auditor")[0])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(f"{live_server.url}/accounts/login/?next=/audit/")
        username = page.get_by_label(re.compile(r"^Username\b"))
        secret = page.get_by_label(re.compile(r"^Password\b"))
        submit = page.get_by_role("button", name="Sign in", exact=True)
        for theme in ("Dark", "Light"):
            page.get_by_role("button", name="Theme", exact=True).click()
            page.get_by_role("button", name=theme, exact=True).click()
            expect(page.locator("html")).to_have_attribute("data-bs-theme", theme.lower())
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-bs-theme", theme.lower())
            for width, height in (
                (1505, 1045),
                (1280, 800),
                (992, 768),
                (768, 844),
                (390, 844),
                (320, 568),
            ):
                page.set_viewport_size({"width": width, "height": height})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                expect(submit).to_be_visible()
                for control in (username, secret, submit):
                    box = control.bounding_box()
                    assert 0 <= box["x"] < box["x"] + box["width"] <= width
                scene = page.locator(".vr-login-scene")
                if width >= 992:
                    expect(scene).to_be_visible()
                    image_name = "night.webp" if theme == "Dark" else "day.webp"
                    assert image_name in scene.evaluate("e => getComputedStyle(e).backgroundImage")
                else:
                    expect(scene).to_be_hidden()
                if width in (1505, 390):
                    page.screenshot(
                        path=str(artifacts / f"login-{theme.lower()}-{width}.png"), full_page=True
                    )

        username.fill(user.username)
        secret.fill("Synthetic-wrong-password!")
        secret.press("Enter")
        expect(page.get_by_role("alert")).to_contain_text("correct username and password")
        expect(username).to_have_value(user.username)
        expect(secret).to_have_value("")
        assert page.locator('input[name="next"]').input_value() == "/audit/"
        expect(page.get_by_role("link", name="Source code")).to_be_visible()
        page.screenshot(path=str(artifacts / "login-error-320.png"), full_page=True)

        username.focus()
        page.keyboard.press("Tab")
        expect(secret).to_be_focused()
        secret.fill(password)
        page.keyboard.press("Tab")
        expect(submit).to_be_focused()
        page.keyboard.press("Enter")
        expect(page).to_have_url(f"{live_server.url}/audit/")
        browser.close()
