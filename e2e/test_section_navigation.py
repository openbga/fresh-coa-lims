"""Section links hold their position across pages, screen sizes and the help panel."""

import re
import secrets
from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from core.models import RuleSet
from quality.models import Lot

ARTIFACTS = Path(".local/qa/layout")


def sign_in(page, live_server, user, password):
    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_label(re.compile(r"^Username\b")).fill(user.username)
    page.get_by_label(re.compile(r"^Password\b")).fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/")


def assert_no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def link_geometry(nav):
    return nav.locator("a").evaluate_all("""links => links.map(link => {
        const row = link.closest('ul');
        const bounds = link.getBoundingClientRect();
        return [bounds.x + row.scrollLeft, bounds.y, bounds.width, bounds.height];
    })""")


@pytest.mark.django_db(transaction=True)
def test_section_navigation_stays_put(live_server, django_user_model):
    password = secrets.token_urlsafe(24)
    user = django_user_model.objects.create_user(username="layout_test", password=password)
    user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in ("analyst", "quality")])
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response",
            lambda response: errors.append(response.url) if response.status >= 400 else None,
        )
        try:
            sign_in(page, live_server, user, password)
            for width in (1440, 768, 390, 320):
                page.set_viewport_size({"width": width, "height": 900})
                tab_top = None
                for root in ("/stability/", "/laboratory/", "/testing/", "/catalog/", "/sampling/"):
                    page.goto(f"{live_server.url}{root}")
                    nav = page.get_by_role("navigation", name="Section navigation", exact=True)
                    links = nav.locator("a").evaluate_all("links => links.map(a => a.pathname)")
                    expected_geometry = link_geometry(nav)
                    if tab_top is None:
                        tab_top = nav.bounding_box()["y"]
                    for path in links:
                        # Follow links to verify routing, selection and scroll reveal.
                        nav.locator(f'a[href="{path}"]').click()
                        expect(page).to_have_url(f"{live_server.url}{path}")
                        expect(nav.locator('[aria-current="page"]')).to_have_attribute("href", path)
                        expect(page.locator("main h1")).to_have_count(1)
                        assert nav.bounding_box()["y"] == tab_top
                        geometry = link_geometry(nav)
                        for actual, expected in zip(geometry, expected_geometry, strict=True):
                            assert actual == pytest.approx(expected, abs=0.5)
                        # One row even where labels would otherwise wrap onto three lines.
                        assert len({round(rect[1]) for rect in geometry}) == 1
                        current = nav.locator('[aria-current="page"]')
                        expect(current).to_be_in_viewport(ratio=1)
                        assert_no_overflow(page)
                        if width in (1440, 390) and path in (
                            "/stability/",
                            "/stability/protocols/",
                            "/laboratory/",
                        ):
                            name = path.strip("/").replace("/", "-")
                            page.screenshot(path=str(ARTIFACTS / f"after-{name}-{width}.png"))

            page.set_viewport_size({"width": 1440, "height": 900})
            page.goto(f"{live_server.url}/laboratory/uses/")
            nav = page.get_by_role("navigation", name="Section navigation", exact=True)
            original_top = nav.bounding_box()["y"]
            page.get_by_role("button", name="Page documentation", exact=True).click()
            panel = page.get_by_role("complementary", name="Page documentation", exact=True)
            expect(panel).to_be_visible()
            splitter = page.get_by_role("separator", name="Resize page documentation")
            splitter.focus()
            splitter.press("End")
            expect(nav.locator('[aria-current="page"]')).to_be_in_viewport(ratio=1)
            assert nav.bounding_box()["y"] == original_top
            assert_no_overflow(page)
            page.screenshot(path=str(ARTIFACTS / "after-help-panel-1440.png"))
            panel.get_by_role("button", name="Close page documentation").click()

            # Keyboard reaches links hidden beyond the scroll edge and activates the destination.
            page.set_viewport_size({"width": 390, "height": 900})
            page.goto(f"{live_server.url}/laboratory/")
            nav.locator("a").first.focus()
            for _ in range(nav.locator("a").count() - 1):
                page.keyboard.press("Tab")
            expect(nav.locator("a").last).to_be_focused()
            expect(nav.locator("a").last).to_be_in_viewport(ratio=1)
            page.keyboard.press("Enter")
            expect(page).to_have_url(f"{live_server.url}/laboratory/uses/")
            page.get_by_role("button", name="Theme", exact=True).click()
            page.get_by_role("button", name="Dark", exact=True).click()
            page.screenshot(path=str(ARTIFACTS / "after-dark-390.png"))
            assert not errors, errors

            # Full-page links and native scrolling still work with progressive enhancement off.
            no_js = browser.new_context(
                java_script_enabled=False,
                storage_state=page.context.storage_state(),
                viewport={"width": 390, "height": 900},
            )
            plain = no_js.new_page()
            plain.goto(f"{live_server.url}/laboratory/")
            plain.get_by_role("navigation", name="Section navigation").get_by_role(
                "link", name="Resource use"
            ).click()
            expect(plain).to_have_url(f"{live_server.url}/laboratory/uses/")
            assert_no_overflow(plain)
            no_js.close()
        except Exception:
            page.screenshot(path=str(ARTIFACTS / "navigation-failure.png"), full_page=True)
            raise
        finally:
            browser.close()


@pytest.mark.django_db(transaction=True)
def test_material_lot_filters_and_paging(live_server, django_user_model):
    password = secrets.token_urlsafe(24)
    user = django_user_model.objects.create_user(username="lot_layout_test", password=password)
    user.groups.add(Group.objects.get_or_create(name="analyst")[0])
    rule = RuleSet.objects.create(
        code="synthetic-layout", segment="chemical", effective_from=timezone.now(), author=user
    )
    Lot.objects.bulk_create(
        [
            Lot(
                number=f"LAYOUT-{i:03}",
                material="Synthetic material with a long descriptive name " * 3,
                rules=rule,
                created_by=user,
            )
            for i in range(31)
        ]
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        try:
            sign_in(page, live_server, user, password)
            page.get_by_label("Find lot", exact=True).fill("LAYOUT-")
            page.get_by_role("button", name="Search", exact=True).click()
            expect(page.locator(".vr-count")).to_contain_text("31")
            page.get_by_role("link", name="Next", exact=True).click()
            expect(page.get_by_label("Find lot", exact=True)).to_have_value("LAYOUT-")
            expect(page.locator("tbody tr")).to_have_count(1)
            page.get_by_role("link", name="Clear filters", exact=True).click()
            expect(page.locator("tbody tr")).to_have_count(30)
            ARTIFACTS.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(ARTIFACTS / "after-lots-1440.png"))
            page.set_viewport_size({"width": 390, "height": 900})
            assert_no_overflow(page)
            page.screenshot(path=str(ARTIFACTS / "after-lots-390.png"))
            page.get_by_label("Find lot", exact=True).fill("no-such-synthetic-lot")
            page.get_by_role("button", name="Search", exact=True).click()
            expect(
                page.get_by_text("No material lots match these filters", exact=True)
            ).to_be_visible()
            page.locator(".vr-empty").get_by_role("link", name="Clear filters").click()
            expect(page.locator("tbody tr")).to_have_count(30)
            page.get_by_role("link", name="New material lot", exact=True).click()
            expect(page.get_by_role("heading", name="New material lot", exact=True)).to_be_visible()
        finally:
            browser.close()
