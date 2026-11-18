"""A quality person withdraws an issued certificate of analysis through its pages and records
that its recipient was told; the issued version stays downloadable as issued, in Chromium."""

import re

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import expect_form, field, fill_signature, pick, submit_signed
from playwright.sync_api import expect, sync_playwright

from reporting.models import RecipientNotification, Report
from tests.test_certificate_withdrawal import REASON, RECIPIENT
from tests.test_certificate_withdrawal import world as world  # noqa: F401
from tests.test_integrated_journey import PASSWORD
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

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
def test_quality_withdraws_a_certificate_and_records_the_notification(
    live_server, world, artifacts
):
    report = world["report"]
    base = live_server.url
    detail_url = base + reverse("reporting:detail", args=[report.pk])
    version_url = base + reverse("reporting:version", args=[report.pk, 1])
    errors = []

    # The ORM is not called while Playwright's event loop runs: each session closes first.
    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("synthetic_approver")
        page.goto(detail_url)
        page.get_by_role("button", name="More", exact=True).click()
        page.get_by_role("link", name="Withdraw certificate", exact=True).click()
        expect_form(page, base + reverse("reporting:withdraw", args=[report.pk]))
        expect(page.get_by_text("stops being valid when you sign").first).to_be_visible()
        page.screenshot(path=str(artifacts / "certificate-withdraw-desktop.png"), full_page=True)
        field(page, "Reference").fill("IA-3")
        fill_signature(page, "synthetic_approver", reason=REASON)
        assert submit_signed(page, "Sign and withdraw") in (200, 302)
        expect(page).to_have_url(detail_url)
        expect(page.get_by_text("This certificate was withdrawn on").first).to_be_visible()
        expect(page.get_by_text("Recipient notification not recorded.").first).to_be_visible()
        expect(page.locator(".vr-page-meta").get_by_text("Withdrawn", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Amend certificate", exact=True)).to_have_count(0)
        page.screenshot(path=str(artifacts / "certificate-withdrawn-desktop.png"), full_page=True)

        page.get_by_role("link", name="Record notification", exact=True).click()
        expect_form(page, base + reverse("reporting:notify", args=[report.pk]))
        expect(field(page, "Recipient notified")).to_have_value(RECIPIENT)
        field(page, "Date notified").fill(timezone.localdate().isoformat())
        pick(field(page, "Means"), label="Letter")
        field(page, "Evidence reference").fill("SYN-LETTER-0001 in complaint file SYN-CF-7")
        assert submit_signed(page, "Record notification") in (200, 302)
        expect(page).to_have_url(detail_url)
        panel = page.locator(
            "section", has=page.get_by_role("heading", name="Recipient notifications")
        )
        expect(panel).to_contain_text("SYN-LETTER-0001 in complaint file SYN-CF-7")
        expect(panel).to_contain_text("Letter")
        expect(page.get_by_text("Recipient notification not recorded.")).to_have_count(0)
        page.screenshot(path=str(artifacts / "certificate-notified-desktop.png"), full_page=True)

        page.goto(version_url)
        expect(page.get_by_text("this version is no longer valid").first).to_be_visible()
        expect(page.get_by_role("link", name="Download PDF", exact=True)).to_be_visible()
        browser.close()

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base, width=390, height=844)
        login("synthetic_approver")
        page.goto(detail_url)
        page.screenshot(path=str(artifacts / "certificate-withdrawn-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.evaluate(
            WIDER_THAN_THE_PAGE
        )
        browser.close()

    assert not errors, errors
    report = Report.objects.get(pk=report.pk)
    assert (report.state, report.withdrawal_reference) == ("withdrawn", "IA-3")
    assert RecipientNotification.objects.get(report=report).means == "letter"
