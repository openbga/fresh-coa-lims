"""Planning open work, in Chromium: quality sets the turnaround target of lot testing, a
reviewer plans the tests of a new lot on the work list (due date, analyst, instrument), an
analyst takes the test nobody planned, the workload flags an instrument whose calibration runs
out before its planned work, and the reminders list that calibration."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from helpers import ACTION_TIMEOUT_MS, expect_form, field, pick
from playwright.sync_api import expect, sync_playwright

from core.services import set_pin
from laboratory.tests.helpers import PASSWORD, PIN, accept_new_calibration, make_equipment
from planning.models import Plan
from planning.tests.conftest import ROLES, lot_tests

# The section tabs scroll sideways by design (docs/ui-standards.md); tables scroll in their wrap.
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap, .vr-section-tabs')
    && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)}`)"""


def people_for(django_user_model):
    users = {}
    for name, roles in ROLES.items():
        user = django_user_model.objects.create_user(
            name, password=PASSWORD, first_name="Synthetic", last_name=name.capitalize()
        )
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        if name not in ("auditor", "admin"):
            set_pin(actor=user, pin=PIN, password=PASSWORD)
        users[name] = user
    return users


def open_session(playwright, base, width=1440, height=1000):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": height})
    page.set_default_timeout(ACTION_TIMEOUT_MS)

    def login(username):
        page.goto(base + reverse("login"))
        page.get_by_label(re.compile(r"^Username\b")).fill(username)
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(base + "/")

    return browser, page, login


@pytest.mark.django_db(transaction=True)
def test_open_work_is_planned_taken_and_checked_against_calibration(
    live_server, django_user_model, settings, artifacts
):
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = "analytical.fixtures.FixtureProvider"
    settings.ANALYTICAL_BENCH = "analytical.fixtures.SyntheticBench"
    people = people_for(django_user_model)
    meter = make_equipment(people, "SYN-PLAN-KF-01", ready=False, requires_qualification=False)
    accept_new_calibration(people, meter, days_valid=1)
    base = live_server.url
    today = timezone.localdate()
    errors = []

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("quality")
        page.goto(base + reverse("planning:targets"))
        page.get_by_role("link", name="Change targets", exact=True).click()
        expect_form(page, base + reverse("planning:targets_change"))
        field(page, "Lot testing").fill("10")
        field(page, "Reason").fill("Synthetic SOP-PLAN-01: ten days for lot testing")
        page.get_by_role("button", name="Change targets", exact=True).click()
        expect(page.get_by_text("The turnaround targets are changed.")).to_be_visible()
        expect(page.locator("table").first).to_contain_text("10 days")
        browser.close()

    tests = lot_tests(people, "SYN-PLAN-E2E")  # assigned after the target: due in ten days
    lot_tests(people, "SYN-PLAN-E2E-2", codes=("identity",))

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("reviewer")
        page.goto(base + reverse("planning:work_list") + "?q=SYN-PLAN-E2E-S1")
        rows = page.locator("table tbody tr")
        expect(rows).to_have_count(2)
        expect(rows.first).to_contain_text("Due in 10 days")
        expect(rows.first).to_contain_text("From the target")
        for code in ("identity", "water"):
            label = f"Select T-{tests[code].pk}"
            page.get_by_role("checkbox", name=label, exact=True).check()
        page.get_by_role("button", name="Plan selected tests", exact=True).click()
        expect_form(page, base + reverse("planning:plan"))  # in the form dialog over the list
        dialog = page.locator("#vr-form-dialog.show")
        expect(dialog.get_by_role("heading", name="Selected tests", exact=True)).to_be_visible()
        field(page, "Due date").fill((today + timedelta(days=2)).isoformat())
        pick(field(page, "Analyst"), label="Synthetic Analyst2 (analyst2)")
        pick(field(page, "Instrument"), label="SYN-PLAN-KF-01 · Synthetic analytical balance")
        field(page, "Reason").fill("Synthetic: needed for the Friday campaign")
        page.screenshot(path=str(artifacts / "planning-plan-desktop.png"), full_page=True)
        page.get_by_role("button", name="Save plan", exact=True).click()
        expect(page.get_by_text("Planned 2 tests.")).to_be_visible()
        page.goto(base + reverse("planning:work_list") + "?q=SYN-PLAN-E2E-S1")
        expect(rows.first).to_contain_text("Due in 2 days")
        expect(rows.first).to_contain_text("Synthetic Analyst2")
        expect(rows.first).to_contain_text("SYN-PLAN-KF-01")
        page.screenshot(path=str(artifacts / "planning-work-list-desktop.png"), full_page=True)
        assert page.evaluate(WIDER_THAN_THE_PAGE) == []
        browser.close()

    assert set(Plan.objects.values_list("analyst__username", "equipment__asset_id")) == {
        ("analyst2", "SYN-PLAN-KF-01")
    }

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("analyst")
        page.goto(base + reverse("planning:work_list"))
        pick(field(page, "Analyst"), label="Not assigned")
        page.get_by_role("button", name="Apply", exact=True).click()
        row = page.locator("table tbody tr", has_text="SYN-PLAN-E2E-2")
        row.get_by_role("button", name="Assign to me", exact=True).click()
        expect(page.get_by_text(re.compile(r"T-\d+ is assigned to you\."))).to_be_visible()
        expect(page).to_have_url(re.compile(r"analyst=none"))
        expect(page.locator("table tbody tr", has_text="SYN-PLAN-E2E-2")).to_have_count(0)

        page.goto(base + reverse("planning:workload"))
        instruments = page.locator(
            "section", has=page.get_by_role("heading", name="By instrument", exact=True)
        )
        expect(instruments).to_contain_text("Calibration runs out before planned work")
        analysts = page.locator(
            "section", has=page.get_by_role("heading", name="By analyst", exact=True)
        )
        # Open tests, Overdue, Due today, Due in the next 7 days, No due date.
        counts = analysts.locator("tr", has_text="Synthetic Analyst2").locator("td")
        expect(counts).to_have_text(["2", "0", "0", "2", "0"])
        page.screenshot(path=str(artifacts / "planning-workload-desktop.png"), full_page=True)

        page.goto(base + reverse("planning:reminders"))
        reminder = page.locator("table tbody tr", has_text="SYN-PLAN-KF-01")
        expect(reminder).to_contain_text("Due in 1 day")
        expect(reminder).to_contain_text("Calibration")
        page.screenshot(path=str(artifacts / "planning-reminders-desktop.png"), full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(base + reverse("planning:work_list"))
        assert page.evaluate(WIDER_THAN_THE_PAGE) == []
        page.screenshot(path=str(artifacts / "planning-work-list-phone.png"), full_page=True)
        browser.close()

    assert Plan.objects.filter(analyst__username="analyst").count() == 1
    assert errors == []
