"""A reviewer checks a certificate a customer sent back, in the form dialog over the certificate
list: the file as issued is genuine and current, a copy saved again is not found. A recipient
then checks the same file without an account, where the laboratory offers it, at a desktop and a
phone width. The certificate page lists the staff check and the recipient's, kept once a day,
in Chromium."""

import re

import pytest
from django.urls import reverse
from helpers import expect_form
from playwright.sync_api import expect, sync_playwright

from reporting.models import CertificateCheck
from tests.test_customer_certificates import TIGHT, issue, released
from tests.test_customer_certificates import world as world  # noqa: F401
from tests.test_integrated_journey import PASSWORD

WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)}`)"""


def pdf_file(content, name="certificate.pdf"):
    return {"name": name, "mimeType": "application/pdf", "buffer": content}


@pytest.mark.django_db(transaction=True)
def test_staff_and_a_recipient_check_a_certificate(live_server, world, artifacts, settings):
    settings.CERTIFICATE_CHECK = True
    report = issue(world, released(world, TIGHT), recipient="Synthetic returning customer")
    version = report.versions.get()
    issued = bytes(version.pdf)
    base = live_server.url
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + reverse("login"))
        page.get_by_label(re.compile(r"^Username\b")).fill("rt_reviewer")
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(base + "/")

        page.goto(base + reverse("reporting:list"))
        page.get_by_role("link", name="Check a certificate").click()
        expect_form(page, reverse("reporting:check"))
        dialog = page.locator("#vr-form-dialog.show")
        expect(dialog.get_by_text("without an account at")).to_be_visible()
        dialog.get_by_label(re.compile(r"^Certificate file\b")).set_input_files(pdf_file(issued))
        dialog.get_by_role("button", name="Check certificate").click()
        expect(dialog.get_by_text("Genuine and current")).to_be_visible()
        expect(
            dialog.get_by_text(f"This file is certificate {report.number}, version 1")
        ).to_be_visible()
        expect(dialog.get_by_role("link", name=f"Open certificate {report.number}")).to_be_visible()
        page.screenshot(path=str(artifacts / "certificate-check-staff.png"))

        # The same certificate saved again by another program has other bytes.
        dialog.get_by_label(re.compile(r"^Certificate file\b")).set_input_files(
            pdf_file(issued + b"%%EOF\n", "resaved.pdf")
        )
        dialog.get_by_role("button", name="Check certificate").click()
        expect(
            dialog.get_by_text("No certificate issued by this laboratory matches this file.")
        ).to_be_visible()
        expect(dialog.get_by_text("Genuine and current")).to_have_count(0)
        browser.close()

        # A recipient, without an account.
        for width, height, name in ((1440, 1000, "desktop"), (390, 844, "phone")):
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + reverse("login"))
            page.get_by_role("link", name="Check a certificate").click()
            expect(page).to_have_url(base + reverse("certificate_check"))
            expect(page.get_by_role("heading", name="Check a certificate", level=1)).to_be_visible()
            page.get_by_label(re.compile(r"^Certificate file\b")).set_input_files(pdf_file(issued))
            page.get_by_role("button", name="Check certificate").click()
            expect(page.get_by_text("Genuine and current")).to_be_visible()
            expect(page.get_by_text("Synthetic returning customer")).to_have_count(0)
            assert page.evaluate(WIDER_THAN_THE_PAGE) == [], name
            page.screenshot(
                path=str(artifacts / f"certificate-check-public-{name}.png"), full_page=True
            )
            assert not [c for c in page.context.cookies() if c["name"] == "sessionid"]
            browser.close()

    assert errors == []
    # The recipient's two checks of the same version today are kept once.
    checks = CertificateCheck.objects.order_by("id")
    assert [(c.checked_by_id is None, c.answer) for c in checks] == [
        (False, "current"),
        (True, "current"),
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base + reverse("login"))
        page.get_by_label(re.compile(r"^Username\b")).fill("rt_reviewer")
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.goto(base + reverse("reporting:detail", args=[report.pk]))
        panel = page.locator("section, .card", has=page.get_by_role("heading", name="Checks"))
        expect(panel.get_by_text("A recipient, without an account")).to_have_count(1)
        expect(panel.get_by_text("Synthetic Reviewer")).to_have_count(1)
        page.screenshot(path=str(artifacts / "certificate-check-record.png"), full_page=True)
        browser.close()
