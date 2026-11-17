"""Forms open in the shared form dialog over the record they were opened from, and leaving one
without signing returns focus to the control that opened it.

A link in the page header, its More menu included, opens the form in the dialog
(static/js/form-dialog.js) while the address stays the record's. Escape or Cancel closes it
and focuses the opener. Nothing is signed or changed on the way.
"""

import pytest
from django.urls import reverse
from helpers import browser_page, expect_form, login, ready_test
from playwright.sync_api import expect

from core.models import ElectronicSignature
from tests.test_integrated_journey import assign_and_sample
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("leave", ["Escape", "Cancel"])
def test_leaving_signing_returns_focus_to_its_opener(live_server, integrated, leave):
    data = integrated
    ready_test(data, assign_and_sample(data))
    lot = data["lot"]
    signatures = ElectronicSignature.objects.count()
    record = live_server.url + reverse("quality:lot_detail", args=[lot.pk])
    signing = reverse("quality:disposition", args=[lot.pk])
    with browser_page({"width": 1440, "height": 900}) as page:
        login(page, live_server, data["people"]["approver"])
        page.goto(record)
        opener = page.locator(f".vr-page-actions a[href='{signing}']")
        opener.click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        if leave == "Escape":
            page.keyboard.press("Escape")
        else:
            dialog.locator("[data-signature-cancel]").click()
        expect(page).to_have_url(record)
        expect(page.locator(f".vr-page-actions a[href='{signing}']")).to_be_focused()
    assert ElectronicSignature.objects.count() == signatures


def test_more_menu_forms_open_over_the_record(live_server, integrated):
    data = integrated  # a received lot, not yet sampled: it can still be cancelled
    lot = data["lot"]
    record = live_server.url + reverse("quality:lot_detail", args=[lot.pk])
    with browser_page({"width": 1440, "height": 900}) as page:
        login(page, live_server, data["people"]["approver"])
        page.goto(record)
        page.locator(".vr-page-actions").get_by_role("button", name="More").click()
        page.get_by_role("link", name="Cancel lot received in error").click()
        expect_form(page, reverse("quality:lot_cancel", args=[lot.pk]))
        expect(page).to_have_url(record)
