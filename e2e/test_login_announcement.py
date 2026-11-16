"""An administrator signs the sign-in announcement; visitors read it before signing in."""

import re
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from core.management.commands.seed_demo import ANNOUNCEMENT_TITLE, _announcement_text
from core.services import set_pin

pytestmark = pytest.mark.django_db(transaction=True)
ADMIN_PASSWORD = "Synthetic-notice-admin-2026!"
ADMIN_PIN = "62918473"
VISITOR_PASSWORD = "Synthetic-demo-visitor-2026!"
VISITOR_PIN = "84621357"
ACCOUNTS = [
    ("demo_analyst", "Analyst"),
    ("demo_auditor", "Auditor"),
    ("demo_config_author", "Quality"),
    ("demo_quality", "Quality"),
    ("demo_reviewer", "Reviewer"),
]


def sign_in(page, server, username, password):
    page.goto(server.url + reverse("login"))
    page.get_by_label(re.compile(r"^Username\b")).fill(username)
    page.get_by_label(re.compile(r"^Password\b")).fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()


def submit(page, username, pin, reason):
    page.get_by_label(re.compile(r"^Reason\b")).fill(reason)
    page.get_by_label(re.compile(r"^Signing username\b")).fill(username)
    page.get_by_label(re.compile(r"^Signature PIN\b")).fill(pin)
    path = urlsplit(page.url).path
    with page.expect_response(
        lambda r: urlsplit(r.url).path == path and r.request.method == "POST"
    ) as response:
        page.get_by_role("button", name="Sign and save announcement", exact=True).click()
    return response.value.status


def test_administrator_publishes_and_visitor_reads_announcement(
    live_server, django_user_model, artifacts
):
    admin = django_user_model.objects.create_user(
        username="synthetic_notice_admin",
        password=ADMIN_PASSWORD,
        first_name="Synthetic",
        last_name="Notice Administrator",
    )
    admin.groups.add(Group.objects.get_or_create(name="admin")[0])
    set_pin(actor=admin, pin=ADMIN_PIN, password=ADMIN_PASSWORD)
    visitor = django_user_model.objects.create_user("demo_reviewer", password=VISITOR_PASSWORD)
    visitor.groups.add(Group.objects.get_or_create(name="reviewer")[0])
    text = _announcement_text(ACCOUNTS, VISITOR_PASSWORD, VISITOR_PIN)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(live_server.url + reverse("login"))
        expect(page.locator(".vr-announcement")).to_have_count(0)

        sign_in(page, live_server, admin.username, ADMIN_PASSWORD)
        page.get_by_role("link", name="Sign-in announcement", exact=True).click()
        expect(page.get_by_role("heading", name="Sign-in announcement", exact=True)).to_be_visible()
        expect(page.get_by_text("No announcement text has been saved.")).to_be_visible()
        expect(page.get_by_role("link", name="Sign-in announcement", exact=True)).to_have_attribute(
            "aria-current", "page"
        )
        page.get_by_label(re.compile(r"^Title\b")).fill(ANNOUNCEMENT_TITLE)
        page.get_by_label(re.compile(r"^Announcement text\b")).fill(text)
        page.get_by_label("Show on the sign-in page").check()

        # A refused signature keeps the text, clears the PIN and publishes nothing.
        assert submit(page, admin.username, "00000000", "Synthetic demo accounts") == 422
        expect(page.get_by_role("alert")).to_contain_text("Signature PIN was not accepted.")
        expect(page.get_by_label(re.compile(r"^Signature PIN\b"))).to_have_value("")
        expect(page.get_by_label(re.compile(r"^Announcement text\b"))).to_have_value(text)
        expect(page.get_by_text("No announcement text has been saved.")).to_be_visible()

        assert submit(page, admin.username, ADMIN_PIN, "Synthetic demo accounts") == 302
        expect(page.get_by_role("status")).to_contain_text("It is shown on the sign-in page.")
        current = page.locator("section", has=page.locator("#announcement-current"))
        expect(current).to_contain_text("Published")
        expect(current.get_by_role("cell", name="demo_config_author")).to_be_visible()
        expect(page.locator(".vr-timeline")).to_contain_text("Announcement published")
        expect(page.locator(".vr-timeline")).to_contain_text(
            "Signed by Synthetic Notice Administrator · announcement_authorized"
        )
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(artifacts / f"announcement-admin-{width}.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Sign out", exact=True).click()

        notice = page.get_by_role("region", name=ANNOUNCEMENT_TITLE)
        expect(notice).to_be_visible()
        expect(notice.get_by_role("row")).to_have_count(len(ACCOUNTS) + 1)
        expect(notice.get_by_text(VISITOR_PASSWORD, exact=True)).to_be_visible()
        expect(notice.get_by_text(VISITOR_PIN, exact=True)).to_be_visible()
        expect(notice).not_to_contain_text(admin.username)
        submit_button = page.get_by_role("button", name="Sign in", exact=True)
        for theme in ("Dark", "Light"):
            page.get_by_role("button", name="Theme", exact=True).click()
            page.get_by_role("button", name=theme, exact=True).click()
            for width, height in ((1440, 1000), (992, 768), (768, 844), (390, 844), (320, 568)):
                page.set_viewport_size({"width": width, "height": height})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                for part in (notice, notice.get_by_text(VISITOR_PASSWORD, exact=True)):
                    box = part.bounding_box()
                    assert 0 <= box["x"] < box["x"] + box["width"] <= width
                expect(submit_button).to_be_visible()
                if width in (1440, 390, 320):
                    page.screenshot(
                        path=str(artifacts / f"announcement-login-{theme.lower()}-{width}.png"),
                        full_page=True,
                    )

        # The announced credentials work, and the announced account cannot change the notice.
        page.set_viewport_size({"width": 1440, "height": 1000})
        sign_in(page, live_server, visitor.username, VISITOR_PASSWORD)
        expect(page.get_by_role("link", name="Account access", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Sign-in announcement", exact=True)).to_have_count(0)
        response = page.goto(live_server.url + reverse("accounts:announcement"))
        assert response.status == 403
        browser.close()
