import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from core.models import ElectronicSignature, RuleSet
from core.services import set_pin
from quality.models import Lot


@pytest.mark.django_db(transaction=True)
def test_lot_to_signed_disposition(live_server, settings):
    # Synthetic regression for the retained development-only manual result path.
    settings.DEBUG = True
    password = "Synthetic-browser-login-2026!"
    pin = "12345678"
    users = {}
    for name, role in [("analyst", "analyst"), ("reviewer", "reviewer"), ("qa", "quality")]:
        user = get_user_model().objects.create_user(username=name, password=password)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        set_pin(actor=user, pin=pin, password=password)
        users[name] = user
    RuleSet.objects.create(
        code="browser-synthetic",
        segment="chemical",
        author=users["qa"],
        status="approved",
        effective_from=timezone.now() - timedelta(days=1),
        effective_until=timezone.now() + timedelta(days=365),
        policy={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        def login(username):
            page.goto(f"{live_server.url}/accounts/login/")
            page.get_by_label("Username").fill(username)
            page.get_by_label(re.compile(r"^Password\b")).fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_role("heading", name="Material lots", exact=True)).to_be_visible()

        login("analyst")
        page.locator(".vr-page-actions").get_by_role("link", name="New material lot").click()
        page.get_by_label(re.compile(r"^Number\b")).fill("SYNTHETIC-BROWSER-001")
        page.get_by_label(re.compile(r"^Material\b")).fill("Synthetic calibration material")
        page.get_by_label(re.compile(r"^Rules\b")).select_option(label="browser-synthetic v1")
        page.get_by_label(re.compile(r"^Reason\b")).fill("Synthetic receipt")
        page.get_by_role("button", name="Receive lot", exact=True).click()
        page.get_by_role("link", name="Add sample").click()
        page.get_by_label(re.compile(r"^Reference\b")).fill("SYNTHETIC-SAMPLE-001")
        page.get_by_label(re.compile(r"^Collected at\b")).fill("2026-11-10T10:00")
        page.get_by_label(re.compile(r"^Reason\b")).fill("Synthetic sampling")
        page.get_by_role("button", name="Add sample", exact=True).click()
        page.get_by_role("link", name="Record result").click()
        for label, value in [
            ("Test code", "identity"),
            ("Value", "1"),
            ("Unit", "ratio"),
            ("Lower limit", "0.9"),
            ("Upper limit", "1.1"),
            ("Reason", "Synthetic observation"),
        ]:
            page.get_by_label(re.compile(r"^" + label + r"\b")).fill(value)
        page.get_by_role("button", name="Record result", exact=True).click()
        lot_url = page.url
        page.get_by_role("button", name="Sign out", exact=True).click()
        login("reviewer")
        page.goto(lot_url)
        page.get_by_role("link", name="Review result").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.get_by_label("Signing username").fill("reviewer")
        page.get_by_label(re.compile(r"^Signature PIN\b")).fill(pin)
        page.get_by_label(re.compile(r"^Reason\b")).fill("Independent synthetic review")
        page.get_by_role("button", name="Sign reviewed", exact=True).click()
        page.get_by_role("button", name="Sign out", exact=True).click()
        login("qa")
        page.goto(lot_url)
        page.get_by_role("link", name="Review disposition").click()
        page.get_by_label("Signing username").fill("qa")
        page.get_by_label(re.compile(r"^Signature PIN\b")).fill(pin)
        page.get_by_label(re.compile(r"^Reason\b")).fill("Synthetic disposition")
        page.get_by_role("button", name="Sign approved", exact=True).click()
        expect(page.get_by_text("Released", exact=True)).to_be_visible()
        screenshots = Path(".local/qa")
        screenshots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshots / "journey-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(screenshots / "journey-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()
    assert Lot.objects.get(number="SYNTHETIC-BROWSER-001").state == "released"
    assert ElectronicSignature.objects.count() == 2
