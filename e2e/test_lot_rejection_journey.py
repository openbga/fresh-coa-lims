"""A quality person signs the rejection of a lot in quarantine, or the cancellation of a lot
received in error, through the pages in Chromium; refusals show no PIN field."""

import re

import pytest
from django.urls import reverse
from helpers import pick
from playwright.sync_api import expect, sync_playwright

from core.models import ElectronicSignature
from quality.models import Lot
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_result_types_journey import assign_sample_tests, build_world

# Elements that reach past the right edge, outside the tables that scroll in their own frame.
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""

REASON = "Synthetic: assay not met, see NCR-SYN-020"


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


@pytest.mark.django_db(transaction=True)
def test_quality_rejects_a_lot_and_cancels_one_received_in_error(
    live_server, django_user_model, artifacts
):
    world = build_world(django_user_model, with_assay=True)
    world["tests"] = assign_sample_tests(world)
    lot = world["lot"]
    base = live_server.url
    lot_url = base + reverse("quality:lot_detail", args=[lot.pk])
    reject_url = base + reverse("quality:lot_reject", args=[lot.pk])
    cancel_url = base + reverse("quality:lot_cancel", args=[lot.pk])
    list_url = base + reverse("quality:lot_list")
    errors = []

    with sync_playwright() as playwright:
        browser, page, login, field = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))

        # Refusal: the analyst received, sampled and tested the lot; the page names no PIN field.
        login("rt_analyst")
        response = page.goto(reject_url)
        assert response.status == 403
        expect(page.get_by_role("alert").first).to_contain_text("Another quality person must sign")
        expect(page.get_by_label(re.compile("^Signature PIN"))).to_have_count(0)
        # A sampled lot is not cancelled either.
        page.goto(cancel_url)
        expect(page.get_by_text("Samples were taken from this lot").first).to_be_visible()
        expect(page.get_by_label(re.compile("^Signature PIN"))).to_have_count(0)
        page.get_by_role("button", name="Sign out", exact=True).click()

        # Independent quality person rejects the lot.
        login("rt_approver")
        page.goto(lot_url)
        page.get_by_role("link", name="Reject lot", exact=True).click()
        expect(page).to_have_url(reject_url)
        expect(page.get_by_role("heading", name=re.compile("^Reject lot"), level=1)).to_be_visible()
        expect(
            page.get_by_role("heading", name="What stands in the way of release")
        ).to_be_visible()
        expect(page.get_by_role("heading", name="Tests", exact=True)).to_be_visible()
        expect(page.get_by_role("table").first.get_by_role("row")).not_to_have_count(1)
        page.screenshot(path=str(artifacts / "lot-rejection-desktop.png"), full_page=True)

        # Missing grounds and a wrong PIN refuse the signature and keep the page.
        field("Reason for the rejection").fill(REASON)
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign and reject the lot", exact=True).click()
        expect(page.get_by_text("This field is required.").first).to_be_visible()
        expect(field("Signature PIN")).to_have_value("")
        pick(field("Grounds for the rejection"), index=1)
        field("Record in the quality system").fill("NCR-SYN-020")
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill("00000000")
        page.get_by_role("button", name="Sign and reject the lot", exact=True).click()
        expect(page.get_by_text("Signature PIN was not accepted.").first).to_be_visible()
        expect(field("Reason for the rejection")).to_have_value(REASON)
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign and reject the lot", exact=True).click()

        expect(page).to_have_url(lot_url)
        expect(page.get_by_text("Lot rejected.").first).to_be_visible()
        expect(page.get_by_text(re.compile("^rejected$", re.I)).first).to_be_visible()
        decision = page.locator("section", has=page.get_by_role("heading", name="Rejection"))
        expect(decision).to_contain_text(REASON)
        expect(decision).to_contain_text("NCR-SYN-020")
        expect(decision).to_contain_text("Synthetic Approver")
        expect(decision).to_contain_text("What stood in the way of release")
        expect(page.get_by_role("link", name="Reject lot", exact=True)).to_have_count(0)
        expect(page.get_by_role("link", name="Cancel lot received in error")).to_have_count(0)
        page.screenshot(path=str(artifacts / "lot-rejected-desktop.png"), full_page=True)

        # The list filtered by status shows the lot.
        page.goto(list_url)
        pick(page.get_by_label("Status", exact=True), label="Rejected")
        page.get_by_role("button", name=re.compile("^(Filter|Apply|Search)")).first.click()
        expect(page.get_by_role("link", name=lot.number, exact=True)).to_be_visible()
        pick(page.get_by_label("Status", exact=True), label="Quarantine")
        page.get_by_role("button", name=re.compile("^(Filter|Apply|Search)")).first.click()
        expect(page.get_by_role("link", name=lot.number, exact=True)).to_have_count(0)
        browser.close()

    assert not errors, errors
    assert Lot.objects.get(pk=lot.pk).state == "rejected"
    signature = ElectronicSignature.objects.get(object_type="quality.lot", object_id=str(lot.pk))
    assert signature.meaning == "rejected" and signature.signer.username == "rt_approver"


@pytest.mark.django_db(transaction=True)
def test_quality_cancels_a_lot_received_in_error(live_server, django_user_model, artifacts):
    world = build_world(django_user_model)
    lot = world["lot"]
    base = live_server.url
    lot_url = base + reverse("quality:lot_detail", args=[lot.pk])
    cancel_url = base + reverse("quality:lot_cancel", args=[lot.pk])

    with sync_playwright() as playwright:
        browser, page, login, field = open_session(playwright, base)
        login("rt_analyst")  # received the lot
        assert page.goto(cancel_url).status == 403
        expect(page.get_by_label(re.compile("^Signature PIN"))).to_have_count(0)
        page.get_by_role("button", name="Sign out", exact=True).click()

        login("rt_approver")
        page.goto(lot_url)
        page.get_by_role("button", name="More", exact=True).click()  # a corrective action
        page.get_by_role("link", name="Cancel lot received in error").click()
        expect(page).to_have_url(cancel_url)
        field("What was recorded in error").fill("Synthetic: delivery recorded twice")
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign and cancel the lot", exact=True).click()
        expect(page).to_have_url(lot_url)
        expect(page.get_by_text("Lot cancelled as received in error.").first).to_be_visible()
        expect(page.get_by_text(re.compile("^cancelled$", re.I)).first).to_be_visible()
        expect(page.get_by_text("delivery recorded twice").first).to_be_visible()
        expect(page.get_by_role("link", name="Cancel lot received in error")).to_have_count(0)
        page.screenshot(path=str(artifacts / "lot-cancelled-desktop.png"), full_page=True)
        browser.close()

    assert Lot.objects.get(pk=lot.pk).state == "cancelled"


@pytest.mark.django_db(transaction=True)
def test_the_rejection_page_fits_a_phone(live_server, django_user_model, artifacts):
    world = build_world(django_user_model, with_assay=True)
    world["tests"] = assign_sample_tests(world)
    base = live_server.url

    with sync_playwright() as playwright:
        browser, page, login, field = open_session(playwright, base, width=390, height=844)
        login("rt_approver")
        page.goto(base + reverse("quality:lot_reject", args=[world["lot"].pk]))
        expect(page.get_by_role("heading", name="Tests", exact=True)).to_be_visible()
        page.screenshot(path="/tmp/lot-rejection-phone.png", full_page=True)
        page.screenshot(path=str(artifacts / "lot-rejection-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.evaluate(
            WIDER_THAN_THE_PAGE
        )
        assert not page.evaluate(WIDER_THAN_THE_PAGE)
        browser.close()
