"""Real approved catalog → native testing → signed disposition → issued CoA in Chromium."""

import hashlib
import re
from pathlib import Path

import pytest
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from analytical import services as analytical
from core.models import ElectronicSignature
from quality.models import Result
from reporting.models import ReportVersion
from tests.test_integrated_journey import PASSWORD, PIN, assign_and_sample
from tests.test_integrated_journey import integrated as integrated  # noqa: F401


@pytest.mark.django_db(transaction=True)
def test_native_observation_to_signed_certificate(live_server, integrated):
    data = integrated
    sample = assign_and_sample(data)
    tests, holds = analytical.assign_tests(
        actor=data["people"]["analyst"],
        sample=sample,
        reason="Assign approved tests for synthetic browser journey",
    )
    assert not holds and len(tests) == 1
    test = tests[0]
    lot = data["lot"]
    screenshots = Path(".local/qa")
    screenshots.mkdir(parents=True, exist_ok=True)
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def goto(name, *args):
            page.goto(live_server.url + reverse(name, args=args))

        def login(person):
            goto("login")
            page.get_by_label(re.compile(r"^Username\b")).fill(person.username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(live_server.url + "/")

        def sign(person, reason, button):
            expect(page.get_by_role("dialog")).to_be_visible()
            page.get_by_label(re.compile(r"^Signing username\b")).fill(person.username)
            page.get_by_label(re.compile(r"^Signature PIN\b")).fill(PIN)
            page.get_by_label(re.compile(r"^Reason\b")).fill(reason)
            page.get_by_role("button", name=button, exact=True).click()

        try:
            login(data["people"]["analyst"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Record observation", exact=True).click()
            page.get_by_label(re.compile(r"^Observed value\b")).fill("100.25")
            page.get_by_label(re.compile(r"^Original record\b")).fill("RAW-SYN-BROWSER-001 rev 1")
            page.get_by_role("button", name="Record observation", exact=True).click()
            expect(page.get_by_text("RAW-SYN-BROWSER-001 rev 1", exact=True)).to_be_visible()
            page.get_by_label(re.compile(r"^Reason\b")).fill("Synthetic original records complete")
            page.get_by_role("button", name="Submit for review", exact=True).click()
            expect(page.get_by_text("Awaiting review", exact=True)).to_be_visible()
            page.get_by_role("button", name="Sign out", exact=True).click()

            login(data["people"]["reviewer"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Sign review", exact=True).click()
            sign(
                data["people"]["reviewer"],
                "Independent synthetic raw-data review",
                "Sign and review",
            )
            expect(page.get_by_text("Reviewed · conforms", exact=True)).to_be_visible()
            page.get_by_role("button", name="Sign out", exact=True).click()

            login(data["people"]["approver"])
            goto("quality:lot_detail", lot.pk)
            page.get_by_role("link", name="Review disposition", exact=True).click()
            sign(
                data["people"]["approver"], "Independent synthetic QC disposition", "Sign approved"
            )
            expect(page.get_by_text("Released", exact=True)).to_be_visible()
            page.get_by_role("link", name="Issue certificate of analysis", exact=True).click()
            expect(page.get_by_text("Preview, not issued", exact=True)).to_be_visible()
            page.get_by_role("link", name="Continue to signing", exact=True).click()
            page.get_by_label(re.compile(r"^Issued to\b")).fill("Synthetic browser recipient")
            sign(
                data["people"]["approver"],
                "Issue reviewed synthetic evidence",
                "Sign and issue certificate",
            )
            page.get_by_role("link", name="Version 1", exact=True).click()
            expect(page.get_by_text("Current version", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="Issued record", exact=True)).to_be_visible()

            with page.expect_download() as pending_download:
                page.get_by_role("link", name="Download PDF", exact=True).click()
            download = pending_download.value
            assert download.failure() is None
            pdf = Path(download.path()).read_bytes()
            (screenshots / "native-certificate.pdf").write_bytes(pdf)
            assert pdf.startswith(b"%PDF-")
            page.screenshot(
                path=str(screenshots / "native-certificate-desktop.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(screenshots / "native-certificate-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        except Exception:
            page.screenshot(path=str(screenshots / "native-failure.png"), full_page=True)
            (screenshots / "native-failure.html").write_text(page.content())
            raise
        finally:
            browser.close()

    lot.refresh_from_db()
    test.refresh_from_db()
    assert lot.state == "released" and test.state == "reviewed"
    assert not Result.objects.filter(sample__lot=lot).exists(), (
        "Legacy results must not supply evidence"
    )
    version = ReportVersion.objects.get(report__lot=lot)
    assert hashlib.sha256(pdf).hexdigest() == version.pdf_sha256
    assert version.pdf_size == len(pdf)
    assert ElectronicSignature.objects.filter(
        object_type="analytical.analyticaltest", object_id=str(test.pk), meaning="reviewed"
    ).exists()
    assert ElectronicSignature.objects.filter(
        object_type="quality.lot", object_id=str(lot.pk), meaning="approved"
    ).exists()
    assert not errors, errors
