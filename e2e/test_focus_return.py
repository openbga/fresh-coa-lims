"""Leaving a signing page without signing returns focus to the control that opened it.

The signature dialog (static/js/signature-dialog.js) closes on Escape or Cancel by going back to
the record; static/js/app.js then focuses the link that opened the signing page. Nothing is
signed or changed on the way.
"""

import pytest
from django.urls import reverse
from helpers import browser_page, login, ready_test
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
