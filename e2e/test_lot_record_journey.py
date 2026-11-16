"""An auditor exports a released lot's complete record through the pages, in Chromium."""

import hashlib
import io
import json
import re
import zipfile

import pytest
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from core.models import AuditEvent
from reporting.lot_record import EXPORT_ACTION
from tests.test_integrated_journey import PASSWORD, integrated  # noqa: F401
from tests.test_lot_record_export import released  # noqa: F401

PURPOSE = "Synthetic inspection request INS-SYN-002"
# What makes a page scroll sideways on a phone: elements that reach past the right edge,
# outside the tables that scroll inside their own frame.
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap, .table-responsive')
    && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""


@pytest.mark.django_db(transaction=True)
def test_auditor_exports_the_record_and_an_analyst_cannot(live_server, released, artifacts):  # noqa: F811
    lot = released["lot"]
    base = live_server.url
    lot_url = base + reverse("quality:lot_detail", args=[lot.pk])
    export_url = base + reverse("quality:lot_record", args=[lot.pk])
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, accept_downloads=True
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def login(username):
            page.goto(base + reverse("login"))
            page.get_by_label(re.compile(r"^Username\b")).fill(username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(base + "/")

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                name,
                page.evaluate(WIDER_THAN_THE_PAGE),
            )
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        # An auditor opens the export from the lot and sees what the record holds.
        login("synthetic_auditor")
        page.goto(lot_url)
        page.get_by_role("link", name="Export record", exact=True).click()
        expect(page).to_have_url(export_url)
        expect(
            page.get_by_role("heading", name=f"Export record · {lot.number}", level=1)
        ).to_be_visible()
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Lots")
        holds = page.locator(
            "section", has=page.get_by_role("heading", name="What the record holds now")
        )
        expect(holds.get_by_role("row", name=re.compile(r"^Tests\b"))).to_contain_text("1")
        expect(holds.get_by_role("row", name=re.compile(r"^Raw-data files\b"))).to_contain_text("1")
        expect(
            holds.get_by_role("row", name=re.compile(r"^Electronic signatures\b"))
        ).to_be_visible()
        shots("lot-record-export")

        # The purpose is required; nothing is exported or recorded without it.
        button = page.get_by_role("button", name="Download the record")
        button.click()
        expect(page.get_by_text("This field is required.").first).to_be_visible()
        purpose = page.get_by_label(re.compile(r"^Purpose of the export"))
        shots("lot-record-export-error")

        # With a purpose the package downloads, and the page stays usable.
        purpose.fill(PURPOSE)
        with page.expect_download() as info:
            button.click()
        download = info.value
        assert re.fullmatch(
            r"SYN-INTEGRATED-001-record-\d{8}T\d{6}Z\.zip", download.suggested_filename
        )
        target = artifacts / download.suggested_filename
        download.save_as(target)
        expect(button).to_be_enabled()
        expect(page).to_have_url(export_url)

        # Analysts read the lot but do not see the export, and are refused if they open it.
        page.get_by_role("button", name="Sign out", exact=True).click()
        login("synthetic_receiver")
        page.goto(lot_url)
        expect(page.get_by_role("heading", name=lot.number, level=1)).to_be_visible()
        expect(page.get_by_role("link", name="Export record")).to_have_count(0)
        refused = page.goto(export_url)
        assert refused.status == 403
        browser.close()

    assert errors == []
    data = target.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = {name.split("/", 1)[1]: archive.read(name) for name in archive.namelist()}
    assert members["record.pdf"].startswith(b"%PDF-")
    record = json.loads(members["record.json"])
    assert record["export"]["purpose"] == PURPOSE
    assert record["export"]["exported_by"]["username"] == "synthetic_auditor"
    event = AuditEvent.objects.get(action=EXPORT_ACTION)
    assert event.after["package_sha256"] == hashlib.sha256(data).hexdigest()
    assert event.reason == PURPOSE
