"""An analyst records a lot's expiry and retest dates and corrects them, quality releases the
lot with the dates frozen, and the lot list finds it by its dates, in Chromium."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import PASSWORD, expect_form, sign
from playwright.sync_api import expect, sync_playwright

from quality.models import Lot, LotDates
from tests.test_result_types_journey import build_world, review, run

WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)}`)"""

BASIS = "Supplier certificate SYN-COA-501: expiry date; retest period 12 months (SOP-SYN-QC-012)"


def open_session(playwright, base, width=1440, height=1000):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": height})

    def login(username):
        page.goto(base + reverse("login"))
        page.get_by_label(re.compile(r"^Username\b")).fill(username)
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(base + "/")

    def field(label):
        return page.get_by_label(re.compile(r"^" + re.escape(label) + r"\s*\*?$")).first

    return browser, page, login, field


@pytest.mark.django_db(transaction=True)
def test_dates_are_recorded_corrected_frozen_with_the_release_and_listed(
    live_server, django_user_model, artifacts
):
    world = build_world(django_user_model)
    for test, _ in run(world).values():
        review(world, test)
    lot = world["lot"]
    base = live_server.url
    lot_url = base + reverse("quality:lot_detail", args=[lot.pk])
    dates_url = base + reverse("quality:lot_dates", args=[lot.pk])
    today = timezone.localdate()
    expiry, retest = today + timedelta(days=365), today + timedelta(days=20)
    errors = []

    with sync_playwright() as playwright:
        browser, page, login, field = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))

        login("rt_analyst")
        page.goto(lot_url)
        panel = page.locator(
            "section", has=page.get_by_role("heading", name="Expiry and retest dates")
        )
        expect(panel).to_contain_text("No expiry or retest date is recorded.")
        panel.get_by_role("link", name="Record dates", exact=True).click()
        expect_form(page, dates_url)  # in the form dialog, over the lot record
        expect(
            page.get_by_role("heading", name="Record expiry and retest dates", level=1)
        ).to_be_visible()
        field("Expiry date").fill(expiry.isoformat())
        field("Retest date").fill((expiry + timedelta(days=1)).isoformat())
        field("Basis").fill(BASIS)
        field("Reason").fill("Synthetic dates from the supplier certificate")
        page.get_by_role("button", name="Record dates", exact=True).click()
        expect(
            page.get_by_text("The retest date cannot be after the expiry date.").first
        ).to_be_visible()
        field("Retest date").fill((today + timedelta(days=40)).isoformat())
        page.get_by_role("button", name="Record dates", exact=True).click()
        expect(page).to_have_url(lot_url)
        expect(page.get_by_text("Dates recorded.").first).to_be_visible()
        expect(panel).to_contain_text((today + timedelta(days=40)).isoformat())
        expect(panel).to_contain_text(BASIS)
        page.screenshot(path=str(artifacts / "lot-dates-recorded-desktop.png"), full_page=True)

        # A correction keeps the record it replaces, and the history shows what changed.
        panel.get_by_role("link", name="Correct dates", exact=True).click()
        expect(
            page.get_by_role("heading", name="Correct expiry and retest dates", level=1)
        ).to_be_visible()
        expect(field("Expiry date")).to_have_value(expiry.isoformat())
        field("Retest date").fill(retest.isoformat())
        field("Reason for correction").fill("Synthetic: retest period is 6 months")
        page.get_by_role("button", name="Correct dates", exact=True).click()
        expect(
            page.get_by_text("Dates corrected; the record replaced is kept.").first
        ).to_be_visible()
        history = page.locator(
            "details#dates-history, details[aria-labelledby='dates-history-heading']"
        )
        history.locator("summary").click()  # a record's secondary history opens on its heading
        expect(history).to_contain_text("Dates corrected")
        page.get_by_role("button", name="Sign out", exact=True).click()

        # Quality releases the lot; the signing page names the dates the release freezes.
        login("rt_approver")
        page.goto(lot_url)
        page.get_by_role("link", name="Review disposition", exact=True).click()
        expect(
            page.get_by_text(re.compile("The release freezes the lot's expiry date")).first
        ).to_be_visible()
        assert sign(
            page, "rt_approver", "Sign approved", "Synthetic independent QC disposition"
        ) in (
            200,
            302,
        )
        expect(page).to_have_url(lot_url)
        meta = page.locator(".vr-page-meta")
        expect(meta.get_by_text("Released", exact=True)).to_be_visible()
        expect(panel).to_contain_text("The release froze these dates.")
        expect(panel.get_by_role("link", name="Correct dates")).to_have_count(0)
        page.screenshot(path=str(artifacts / "lot-dates-released-desktop.png"), full_page=True)

        # The lot list shows the dates and finds the lot by them.
        page.goto(base + reverse("quality:lot_list") + "?dates=soon")
        expect(page.get_by_role("link", name=lot.number, exact=True)).to_be_visible()
        expect(page.get_by_text(retest.isoformat()).first).to_be_visible()
        page.goto(base + reverse("quality:lot_list") + "?dates=retest_due")
        expect(page.get_by_role("link", name=lot.number, exact=True)).to_have_count(0)
        page.screenshot(path=str(artifacts / "lot-dates-list-desktop.png"), full_page=True)
        browser.close()

    assert not errors, errors
    released = Lot.objects.get(pk=lot.pk)
    assert released.state == "released"
    frozen = released.disposition_evidence["dates"]
    assert frozen["retest_on"] == retest.isoformat() and frozen["expiry_on"] == expiry.isoformat()
    assert LotDates.objects.filter(lot=lot).count() == 2


@pytest.mark.django_db(transaction=True)
def test_the_dates_page_fits_a_phone(live_server, django_user_model, artifacts):
    world = build_world(django_user_model)
    base = live_server.url
    with sync_playwright() as playwright:
        browser, page, login, field = open_session(playwright, base, width=390, height=844)
        login("rt_analyst")
        page.goto(base + reverse("quality:lot_dates", args=[world["lot"].pk]))
        expect(field("Expiry date")).to_be_visible()
        page.screenshot(path=str(artifacts / "lot-dates-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.evaluate(
            WIDER_THAN_THE_PAGE
        )
        page.goto(base + reverse("quality:lot_detail", args=[world["lot"].pk]))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.evaluate(
            WIDER_THAN_THE_PAGE
        )
        browser.close()
