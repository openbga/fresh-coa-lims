"""Turnaround and right-first-time figures, in Chromium: a reviewer opens the figures of the
last 30 days, breaks them down by analyst, follows a count to the reviewed tests behind it,
narrows the list to the tests that were not right first time and exports it; an analyst sees
no figures."""

import csv
import io
import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import ACTION_TIMEOUT_MS, field, pick
from playwright.sync_api import expect, sync_playwright
from test_planning_journey import WIDER_THAN_THE_PAGE, open_session, people_for

from analytical import services as analytical
from laboratory.tests.helpers import PIN
from planning import services
from planning.models import Work
from planning.tests.conftest import fresh, lot_tests


def finish(people, test, value, analyst="analyst", returned=False):
    analytical.record_observation(
        actor=people[analyst], test=fresh(test), value=Decimal(value), raw_reference="NB-FIG-E2E"
    )
    for _ in range(2 if returned else 1):
        test = fresh(test)
        analytical.submit_test(
            actor=people[analyst], test=test, expected_revision=test.revision, reason="Complete"
        )
        if returned and _ == 0:
            test = fresh(test)
            analytical.return_test(
                actor=people["reviewer"],
                test=test,
                expected_revision=test.revision,
                reason="Synthetic: the unit was not stated",
            )
    test = fresh(test)
    analytical.review_test(
        actor=people["reviewer2"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Raw data checked",
    )


@pytest.mark.django_db(transaction=True)
def test_figures_open_the_reviewed_tests_behind_them(
    live_server, django_user_model, settings, artifacts
):
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = "analytical.fixtures.FixtureProvider"
    settings.ANALYTICAL_BENCH = "analytical.fixtures.SyntheticBench"
    people = people_for(django_user_model)
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() - timedelta(days=40)):
        services.set_targets(
            actor=people["quality"],
            days={"lot": 3},
            expected={work: None for work in Work.values},
            reason="Synthetic SOP-FIG-01",
        )
    late = lot_tests(people, "SYN-FIG-E2E-1", assigned_at=timezone.now() - timedelta(days=6))
    finish(people, late["identity"], "1.00")
    finish(people, late["water"], "0.20", returned=True)
    soon = lot_tests(people, "SYN-FIG-E2E-2", codes=("identity",), material="Synthetic granules")
    finish(people, soon["identity"], "1.01", analyst="analyst2")
    base = live_server.url
    errors = []

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("reviewer")
        page.goto(base + reverse("planning:work_list"))
        page.get_by_role("link", name="Figures", exact=True).click()
        expect(page).to_have_url(base + reverse("planning:figures"))
        summary = page.locator(
            "section", has=page.get_by_role("heading", name="In the period", exact=True)
        )
        expect(summary.locator("dl")).to_contain_text("Reviewed tests3")
        expect(summary.locator("tr", has_text="Reviewed late")).to_contain_text("67% of 3")
        expect(summary.locator("tr", has_text="Returned for correction")).to_contain_text("1")
        page.screenshot(path=str(artifacts / "planning-figures-desktop.png"), full_page=True)

        pick(field(page, "Figures by"), label="Analyst")
        page.get_by_role("button", name="Show figures", exact=True).click()
        expect(page).to_have_url(re.compile(r"by=analyst"))
        by_analyst = page.locator(
            "section", has=page.get_by_role("heading", name="By analyst", exact=True)
        )
        row = by_analyst.locator("tr", has_text="Synthetic Analyst2")
        # Reviewed, Median, 9 in 10 within, On time, Late, Right first time, Returned,
        # Corrected, Repeat.
        expect(row.locator("td").first).to_have_text("1")
        first = by_analyst.locator(
            "tr", has=page.get_by_role("rowheader", name="Synthetic Analyst", exact=True)
        )
        first.locator("td").nth(4).get_by_role("link").click()
        expect(page).to_have_url(re.compile(r"/planning/figures/tests/\?.*timeliness=late"))
        rows = page.locator("table tbody tr")
        expect(rows).to_have_count(2)
        expect(rows.first).to_contain_text("Late by 3 days")

        pick(field(page, "First time"), label="Not right first time")
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(rows).to_have_count(1)
        expect(rows.first).to_contain_text("Not right first time")
        expect(rows.first).to_contain_text("Returned")
        page.screenshot(path=str(artifacts / "planning-reviewed-desktop.png"), full_page=True)
        with page.expect_download() as download:
            page.get_by_role("button", name="Export filtered CSV", exact=True).click()
        lines = list(csv.reader(io.StringIO(open(download.value.path()).read())))
        assert len(lines) == 2 and lines[1][0] == f"T-{late['water'].pk}"
        assert lines[1][lines[0].index("Returns")] == "1"

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(base + reverse("planning:figures") + "?by=material")
        expect(page.get_by_role("heading", name="By material", exact=True)).to_be_visible()
        assert page.evaluate(WIDER_THAN_THE_PAGE) == []
        page.screenshot(path=str(artifacts / "planning-figures-phone.png"), full_page=True)
        page.emulate_media(color_scheme="dark")
        page.goto(base + reverse("planning:reviewed"))
        assert page.evaluate(WIDER_THAN_THE_PAGE) == []
        page.screenshot(path=str(artifacts / "planning-reviewed-phone-dark.png"), full_page=True)
        browser.close()

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.set_default_timeout(ACTION_TIMEOUT_MS)
        login("analyst")
        page.goto(base + reverse("planning:work_list"))
        expect(page.get_by_role("link", name="Workload", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Figures", exact=True)).to_have_count(0)
        assert page.goto(base + reverse("planning:figures")).status == 403
        browser.close()

    assert errors == []
