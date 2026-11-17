"""An analyst starts the reassessment of a released lot whose retest date is near and assigns
its tests; once they are reviewed, an independent quality person concludes that the material is
suitable until a later retest date, which the lot record then shows, in Chromium."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import PASSWORD, expect_form, field, fill_signature, submit_signed
from playwright.sync_api import expect, sync_playwright

from analytical.models import AnalyticalTest
from quality.models import Lot, Reassessment
from tests.test_reassessment import READINGS, released_world
from tests.test_result_types_journey import record, review, submit

WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)}`)"""


def open_session(playwright, base, width=1440, height=1000):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": height})

    def login(username):
        page.goto(base + reverse("login"))
        page.get_by_label(re.compile(r"^Username\b")).fill(username)
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(base + "/")

    return browser, page, login


@pytest.mark.django_db(transaction=True)
def test_a_released_lot_is_reassessed_and_given_a_later_retest_date(
    live_server, django_user_model, artifacts
):
    world = released_world(django_user_model, retest_in=10, expiry_in=400)
    lot = world["lot"]
    base = live_server.url
    lot_url = base + reverse("quality:lot_detail", args=[lot.pk])
    today = timezone.localdate()
    new_retest = today + timedelta(days=180)
    errors = []

    # The ORM is not called while Playwright's event loop runs: each session closes first.
    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))

        login("rt_analyst")
        page.goto(lot_url)
        panel = page.locator("section", has=page.get_by_role("heading", name="Reassessments"))
        panel.get_by_role("link", name="Start reassessment", exact=True).click()
        expect_form(page, base + reverse("quality:reassessment_new", args=[lot.pk]))
        field(page, "Sample reference").fill("SYN-RA-E2E-1")
        field(page, "Quantity taken").fill("25")
        field(page, "Containers sampled").fill("SYN-C001; warehouse bay B2")
        field(page, "Why the material is examined again").fill("Retest date in ten days")
        page.get_by_role("button", name="Start reassessment", exact=True).click()
        expect(page).to_have_url(re.compile(r"/reassessments/\d+/$"))
        detail_url = page.url
        pk = int(detail_url.rstrip("/").rsplit("/", 1)[1])
        expect(page.get_by_text(f"RA-{pk} started; assign its tests.").first).to_be_visible()

        page.get_by_role("link", name="Assign tests", exact=True).click()
        expect_form(page, base + reverse("quality:reassessment_tests", args=[pk]))
        expect(page.get_by_text("Acceptance criteria in force").first).to_be_visible()
        field(page, "Reason").fill("Assign the reassessment's tests")
        page.get_by_role("button", name="Assign tests", exact=True).click()
        expect(page).to_have_url(detail_url)
        expect(page.get_by_text("Assigned 4 test(s)").first).to_be_visible()
        page.screenshot(path=str(artifacts / "reassessment-tests-desktop.png"), full_page=True)
        browser.close()

    # The tests are recorded, submitted and reviewed like any other (services, synthetic).
    item = Reassessment.objects.get(pk=pk)
    for test in AnalyticalTest.objects.filter(reassessment=item):
        record(world, test, READINGS[test.test_code])
        submit(world, test)
        review(world, test)

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("rt_approver")
        page.goto(detail_url)
        page.get_by_role("link", name="Conclude", exact=True).click()
        expect_form(page, base + reverse("quality:reassessment_conclude", args=[pk]))
        page.get_by_label("Suitable for use until a new retest date").check()
        field(page, "New retest date").fill(new_retest.isoformat())
        fill_signature(page, "rt_approver", reason="Every result conforms")
        assert submit_signed(page, "Sign and conclude") in (200, 302)
        expect(page).to_have_url(detail_url)
        expect(page.locator(".vr-page-meta").get_by_text("Suitable", exact=True)).to_be_visible()
        page.screenshot(path=str(artifacts / "reassessment-concluded-desktop.png"), full_page=True)

        page.goto(lot_url)
        dates_panel = page.locator(
            "section", has=page.get_by_role("heading", name="Expiry and retest dates")
        )
        expect(dates_panel).to_contain_text(new_retest.isoformat())
        expect(dates_panel).to_contain_text(f"set by RA-{pk}")
        panel = page.locator("section", has=page.get_by_role("heading", name="Reassessments"))
        expect(panel).to_contain_text("Suitable")
        page.screenshot(path=str(artifacts / "reassessment-lot-desktop.png"), full_page=True)
        browser.close()

    assert not errors, errors
    item.refresh_from_db()
    assert (item.state, item.outcome, item.retest_on) == ("concluded", "suitable", new_retest)
    assert Lot.objects.get(pk=lot.pk).state == "released"


@pytest.mark.django_db(transaction=True)
def test_the_reassessment_pages_fit_a_phone(live_server, django_user_model, artifacts):
    world = released_world(django_user_model)
    base = live_server.url
    from tests.test_reassessment import begin

    item = begin(world)
    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base, width=390, height=844)
        login("rt_analyst")
        for url in (
            reverse("quality:reassessment_detail", args=[item.pk]),
            reverse("quality:reassessment_tests", args=[item.pk]),
        ):
            page.goto(base + url)
            page.screenshot(
                path=str(artifacts / f"reassessment-{url.strip('/').split('/')[-1]}-mobile.png"),
                full_page=True,
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                page.evaluate(WIDER_THAN_THE_PAGE)
            )
        browser.close()
