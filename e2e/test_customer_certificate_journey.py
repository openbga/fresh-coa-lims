"""A quality person issues a certificate for the market scope of a lot under two specifications:
the review page offers the scopes, shows the certificate for the one chosen with its limits and
the conformity of each result, and the signed certificate names the scope; its version page
offers the certificate data beside the PDF, in Chromium."""

import json
import re

import pytest
from django.urls import reverse
from helpers import expect_form, fill_signature, submit_signed
from playwright.sync_api import expect, sync_playwright

from reporting import services as reporting
from reporting.models import Report
from tests.test_customer_certificates import MARKET, released
from tests.test_customer_certificates import world as world  # noqa: F401
from tests.test_integrated_journey import PASSWORD
from tests.test_requirement_applicability import TIGHT, WATER

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
def test_quality_issues_a_certificate_for_a_customer_scope(live_server, world, artifacts):
    lot = released(world, TIGHT, WATER)
    base = live_server.url
    preview_url = base + reverse("reporting:issue_preview", args=[lot.pk])
    errors = []

    # The ORM is not called while Playwright's event loop runs: each session closes first.
    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("rt_author")
        page.goto(preview_url)
        chooser = page.locator("section", has=page.get_by_role("heading", name="Certificate for"))
        expect(chooser.get_by_label("All of the lot's requirements")).to_be_checked()
        expect(
            page.get_by_role("heading", name="Conformity with each specification")
        ).to_be_visible()
        page.screenshot(path=str(artifacts / "customer-certificate-general.png"), full_page=True)

        chooser.get_by_label(re.compile(r"^eu-market: synthetic-rt-eu-market version 1")).check()
        chooser.get_by_role("button", name="Show this certificate", exact=True).click()
        expect(page).to_have_url(re.compile(r"\?scope=eu-market$"))
        expect(page.get_by_text("This certificate is issued for scope eu-market.")).to_be_visible()
        expect(
            page.get_by_role("heading", name="Conformity with each specification")
        ).to_have_count(0)
        results = page.get_by_role(
            "region", name="Reportable results against the specification of scope eu-market"
        )
        expect(results.get_by_role("rowheader")).to_have_text(
            [re.compile("^assay"), re.compile("^water")]
        )
        expect(results).to_contain_text("99 – 101 % · rounded to 2 decimals")
        expect(results.get_by_text("Conforms")).to_have_count(2)
        page.screenshot(path=str(artifacts / "customer-certificate-market.png"), full_page=True)

        page.get_by_role("link", name="Continue to signing", exact=True).click()
        expect_form(page, base + reverse("reporting:issue_sign", args=[lot.pk]))
        expect(page.get_by_text("version 1, for scope eu-market").first).to_be_visible()
        page.get_by_label(re.compile(r"^Issued to\b")).fill("Synthetic customer EU")
        fill_signature(page, "rt_author", reason="Customer certificate, synthetic order 7")
        assert submit_signed(page, "Sign and issue certificate") in (200, 302)
        expect(
            page.get_by_text("Scope eu-market: the tests its specification states")
        ).to_be_visible()
        page.screenshot(path=str(artifacts / "customer-certificate-issued.png"), full_page=True)

        # The version page offers the certificate data beside the PDF.
        page.get_by_role("link", name="Version 1", exact=True).click()
        expect(page.get_by_text("PDF/A-3a, PDF/UA-1")).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role("link", name="Download data", exact=True).click()
        saved = artifacts / "customer-certificate-market-data.json"
        download.value.save_as(saved)
        assert download.value.suggested_filename.endswith("-v1.json")
        page.screenshot(path=str(artifacts / "customer-certificate-version.png"), full_page=True)
        browser.close()

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base, width=390, height=844)
        login("rt_author")
        page.goto(preview_url + "?scope=eu-market")
        expect(page.get_by_text("This certificate is issued for scope eu-market.")).to_be_visible()
        page.screenshot(path=str(artifacts / "customer-certificate-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.evaluate(
            WIDER_THAN_THE_PAGE
        )
        browser.close()

    assert not errors, errors
    report = Report.objects.get()
    assert (report.scope, report.recipient, report.state) == (
        MARKET,
        "Synthetic customer EU",
        "issued",
    )
    version = report.versions.get()
    data = reporting.read_pdf(actor=world["people"]["author"], version=version)
    assert data.startswith(b"%PDF-")
    (artifacts / "customer-certificate-market.pdf").write_bytes(data)
    downloaded = saved.read_bytes()
    assert downloaded == bytes(version.data)
    certificate = json.loads(downloaded)
    assert certificate["schema"] == "oq.certificate-data/1"
    assert certificate["certificate"]["scope"] == MARKET
    assert [r["test"] for r in certificate["results"]] == ["assay", "water"]
