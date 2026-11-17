"""A quality person signs that an open test cannot be completed, through the pages in
Chromium: the repeat on another sample, the exit through an investigation, and the phone layout."""

import re

import pytest
from django.urls import reverse
from helpers import expect_form, pick
from playwright.sync_api import expect, sync_playwright

from analytical.models import AnalyticalTest, Investigation
from core.models import ElectronicSignature
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_test_not_completed import REASON, new_sample, observe
from tests.test_test_not_completed import world as nc_world  # noqa: F401  (shared fixture)

# Elements that reach past the right edge, outside the tables that scroll in their own frame.
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""

SHOTS = "/tmp/nc-journey"


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
        return page.get_by_label(re.compile(r"^" + re.escape(label) + r"(?!\s+link)"))

    return browser, page, login, field


def fits_the_phone(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.evaluate(
        WIDER_THAN_THE_PAGE
    )
    assert not page.evaluate(WIDER_THAN_THE_PAGE)


@pytest.mark.django_db(transaction=True)
def test_quality_signs_that_a_test_cannot_be_completed_and_repeats_it(
    live_server,
    nc_world,  # noqa: F811
    artifacts,
):
    assay, lot = nc_world["assay"], nc_world["lot"]
    observe(nc_world, assay, "99.90")  # one in-limit replicate of the two the test needs
    other = new_sample(nc_world, "SYN-NC-S002")
    base = live_server.url
    test_url = base + reverse("analytical:test_detail", args=[assay.pk])
    not_completed_url = base + reverse("analytical:test_not_completed", args=[assay.pk])
    errors = []

    with sync_playwright() as playwright:
        browser, page, login, field = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))

        # The analyst recorded the data and is not offered the action as signer.
        login("nc_analyst")
        page.goto(test_url)
        # Not offered: the header says why, and the page refuses before any PIN when opened.
        expect(page.get_by_role("link", name="Record not completed", exact=True)).to_have_count(0)
        expect(page.locator('[data-refused="not-completed"]')).to_be_visible()
        page.goto(not_completed_url)
        expect(page.get_by_role("alert").first).to_be_visible()
        expect(page.get_by_label(re.compile("^Signature PIN"))).to_have_count(0)
        page.get_by_role("button", name="Sign out", exact=True).click()

        login("nc_approver")
        page.goto(test_url)
        page.get_by_role("link", name="Record not completed", exact=True).click()
        expect_form(page, not_completed_url)
        expect(page.get_by_text("What follows").first).to_be_visible()
        expect(page.get_by_text("99.90").first).to_be_visible()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.screenshot(path=f"{SHOTS}/not-completed-desktop.png", full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        fits_the_phone(page)
        page.screenshot(path=f"{SHOTS}/not-completed-phone.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})

        # Missing grounds keep the page; the PIN field is emptied.
        field("Signing username").fill("nc_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign: not completed", exact=True).click()
        expect(page.get_by_text("This field is required.").first).to_be_visible()
        expect(field("Signature PIN")).to_have_value("")

        pick(field("Cause"), label="The sample was lost, damaged or used up")
        page.get_by_label("On another sample of the lot").check()
        choice = page.locator('select[name="sample"] option', has_text="SYN-NC-S002")
        pick(field("Sample for the repeat"), value=choice.get_attribute("value"))
        field("Why the test cannot be completed").fill(REASON)
        field("Signing username").fill("nc_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign: not completed", exact=True).click()

        expect(page).to_have_url(test_url)
        expect(page.get_by_text("recorded as not completed.").first).to_be_visible()
        notice = page.get_by_role("status").filter(has_text="cannot be completed")
        expect(notice).to_contain_text("Not completed")
        expect(notice).to_contain_text("Cause: the sample was lost, damaged or used up")
        expect(notice).to_contain_text(REASON)
        expect(notice).to_contain_text("SYN-NC-S002")
        expect(page.get_by_role("link", name="Record not completed")).to_have_count(0)
        page.screenshot(path=f"{SHOTS}/test-notice-desktop.png", full_page=True)

        # Phone width: the notice page and the page that signs.
        page.set_viewport_size({"width": 390, "height": 844})
        fits_the_phone(page)
        page.screenshot(path=f"{SHOTS}/test-notice-phone.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})

        notice.locator("a.vr-id").click()
        expect(page).not_to_have_url(test_url)
        expect(page).to_have_url(re.compile(r"/testing/tests/\d+/$"))
        repeat_url = page.url
        expect(page.get_by_text("SYN-NC-S002").first).to_be_visible()
        expect(page.get_by_role("link", name="Record not completed", exact=True)).to_be_visible()

        # The lot's testing page and the test list show the state and filter by it.
        page.goto(base + reverse("analytical:lot_testing", args=[lot.pk]))
        expect(page.get_by_text("Not completed").first).to_be_visible()
        page.goto(base + reverse("analytical:test_list"))
        pick(page.get_by_label("Status", exact=True), label="Not completed")
        page.get_by_role("button", name="Apply").first.click()
        expect(page.get_by_role("link", name=assay.label, exact=True).first).to_be_visible()
        expect(page.get_by_role("row", name=re.compile("Not completed")).first).to_be_visible()
        expect(page.locator(f'a[href="{repeat_url[len(base) :]}"]')).to_have_count(0)
        browser.close()

    assert not errors, errors
    assay = AnalyticalTest.objects.get(pk=assay.pk)
    assert assay.state == AnalyticalTest.State.NOT_COMPLETED
    repeat = AnalyticalTest.objects.get(parent=assay)
    assert repeat_url.endswith(f"/{repeat.pk}/")
    assert repeat.sample.reference == "SYN-NC-S002" and repeat.kind == "repeat"
    signature = ElectronicSignature.objects.get(
        object_type="analytical.analyticaltest", object_id=str(assay.pk), meaning="not_completed"
    )
    assert signature.signer.username == "nc_approver"
    assert other.pk == repeat.sample_id


@pytest.mark.django_db(transaction=True)
def test_a_reading_outside_the_limits_gives_no_repeat_and_opens_an_investigation(
    live_server,
    nc_world,  # noqa: F811
    artifacts,
):
    assay = nc_world["assay"]
    observe(nc_world, assay, "97.10")
    base = live_server.url
    test_url = base + reverse("analytical:test_detail", args=[assay.pk])
    errors = []

    with sync_playwright() as playwright:
        browser, page, login, field = open_session(playwright, base, width=390, height=844)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("nc_approver")
        page.goto(test_url)
        page.get_by_role("link", name="Record not completed", exact=True).click()
        expect(page.get_by_text("What follows").first).to_be_visible()
        expect(page.get_by_text("97.10").first).to_be_visible()
        expect(page.get_by_text("open an investigation").first).to_be_visible()
        expect(page.get_by_label("On another sample of the lot")).to_have_count(0)
        expect(page.get_by_label(re.compile("^Sample for the repeat"))).to_have_count(0)
        fits_the_phone(page)
        page.screenshot(path=f"{SHOTS}/not-completed-outside-phone.png", full_page=True)

        pick(field("Cause"), index=1)
        field("Why the test cannot be completed").fill(REASON)
        field("Signing username").fill("nc_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign: not completed", exact=True).click()

        expect(page).to_have_url(test_url)
        notice = page.get_by_role("status").filter(has_text="cannot be completed")
        expect(notice).to_contain_text("97.10")
        fits_the_phone(page)
        page.screenshot(path=f"{SHOTS}/test-notice-investigation-phone.png", full_page=True)
        notice.locator("a[href*='/investigations/']").click()
        expect(page).to_have_url(re.compile(r"/testing/investigations/\d+/$"))
        browser.close()

    assert not errors, errors
    assert Investigation.objects.filter(test=assay).exists()
    assert not AnalyticalTest.objects.filter(parent=assay).exists()
