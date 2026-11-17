"""A supplier certificate recorded, corrected and withdrawn through the pages, in Chromium."""

import re

import pytest
from django.urls import reverse
from helpers import pick
from playwright.sync_api import expect, sync_playwright

from core.models import AuditEvent
from quality import certificates
from quality.models import SupplierCertificate
from tests.test_integrated_journey import PASSWORD
from tests.test_supplier_certificates import build_supplied_world


@pytest.mark.django_db(transaction=True)
def test_certificate_recorded_corrected_read_and_withdrawn(
    live_server, django_user_model, artifacts
):
    world = build_supplied_world(django_user_model)
    lot = world["lot"]
    lot_url = live_server.url + reverse("quality:lot_detail", args=[lot.pk])
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def login(username):
            page.goto(live_server.url + reverse("login"))
            page.get_by_label(re.compile(r"^Username\b")).fill(username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(live_server.url + "/")

        def sign_out():
            page.get_by_role("button", name="Sign out", exact=True).click()

        def field(label):
            return page.get_by_label(re.compile(r"^" + re.escape(label)))

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        def section(heading):
            return page.locator("section", has=page.get_by_role("heading", name=heading))

        # The analyst opens the lot and records what the supplier's certificate states.
        login("sc_analyst2")
        page.goto(lot_url)
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Lots")
        listed = section("Supplier certificates")
        expect(listed).to_contain_text("No supplier certificate is recorded.")
        listed.get_by_role("link", name="Record supplier certificate").click()
        expect(
            page.get_by_role("heading", name="Record supplier certificate", exact=True, level=1)
        ).to_be_visible()
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Lots")
        expect(page.get_by_text("SUP-LOT-SYN-001")).to_be_visible()  # The receipt, to compare.
        field("Certificate number").fill("COA-SYN-0001")
        field("Issued by").fill("Synthetic Ingredients Supply")
        field("Date of the certificate").fill("2026-11-02")
        field("Lot number on the certificate").fill("SUP-LOT-SYN-001")
        field("Where the certificate is kept").fill("DMS-SYN-COA-0001")
        field("Reason").fill("Synthetic certificate transcribed")
        page.get_by_role("button", name="Record supplier certificate", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text(certificates.NO_RESULTS)
        expect(field("Certificate number")).to_have_value("COA-SYN-0001")

        field("Assay result (%)").fill("97.50")
        field("Assay method on the certificate").fill("Supplier HPLC-07")
        field("Assay limits on the certificate").fill("98.0 - 102.0 %")
        field("Total aerobic count result (CFU/g)").fill("10")
        field("Total aerobic count stated as less than this value").check()
        pick(page.get_by_label("Identity result", exact=True), label="Conforms")
        page.get_by_role("button", name="Record supplier certificate", exact=True).click()
        expect(
            page.get_by_text("Enter the wording of the result on the certificate.")
        ).to_be_visible()
        field("Identity wording on the certificate").fill("Complies")
        shots("supplier-certificate-form")
        page.get_by_role("button", name="Record supplier certificate", exact=True).click()

        # The record: the supplier's results beside the specification, apart from own tests.
        expect(page.get_by_text("Supplier certificate recorded.")).to_be_visible()
        expect(
            page.get_by_role("heading", name="Supplier certificate COA-SYN-0001", level=1)
        ).to_be_visible()
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Lots")
        expect(page.get_by_text("They are not the laboratory's own tests")).to_be_visible()
        expect(page.get_by_text("As on the receipt")).to_be_visible()
        results = section("Results stated by the supplier")
        assay = results.get_by_role("row", name=re.compile("^Assay"))
        expect(assay).to_contain_text("97.50")
        expect(assay).to_contain_text("98 to 102 %")
        expect(assay).to_contain_text("Does not meet the specification")
        expect(results.get_by_role("row", name=re.compile("^Total aerobic count"))).to_contain_text(
            "<10"
        )
        identity = results.get_by_role("row", name=re.compile("^Identity"))
        expect(identity).to_contain_text("Stated as: Complies")
        expect(identity).to_contain_text("Meets the specification")
        expect(results).to_contain_text("does not hold the lot by itself")
        toggle = page.get_by_role("button", name="Page documentation", exact=True)
        panel = page.get_by_role("complementary", name="Page documentation", exact=True)
        toggle.click()
        expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
            "data-pagedocs-for", "quality:certificate_detail"
        )
        expect(panel.get_by_text("Rules and hidden logic", exact=True)).to_be_visible()
        toggle.click()
        shots("supplier-certificate-record")

        # A correction opens with the record and keeps the one it replaces.
        page.get_by_role("link", name="Correct supplier certificate").click()
        expect(field("Assay result (%)")).to_have_value("97.50")
        expect(field("Total aerobic count stated as less than this value")).to_be_checked()
        field("Reason for correction").fill("Nothing changed")
        page.get_by_role("button", name="Correct supplier certificate", exact=True).click()
        expect(page.get_by_text("The correction changes nothing.")).to_be_visible()
        field("Assay result (%)").fill("99.60")
        field("Reason for correction").fill("Assay misread from the second page")
        page.get_by_role("button", name="Correct supplier certificate", exact=True).click()
        expect(
            page.get_by_text("Supplier certificate corrected; the original is kept.")
        ).to_be_visible()
        history = section("History")
        expect(history.locator(".vr-history-item")).to_have_count(2)
        corrected = history.locator(".vr-history-item").nth(1)
        expect(corrected.locator("del").first).to_have_text("97.50 %")
        expect(corrected).to_contain_text("99.60 %")
        expect(corrected).to_contain_text("Assay misread from the second page")
        expect(section("Results stated by the supplier")).not_to_contain_text("Does not meet")
        certificate_url = page.url
        page.goto(lot_url)
        listed = section("Supplier certificates")
        expect(listed.get_by_role("link", name="COA-SYN-0001")).to_be_visible()
        expect(listed).to_contain_text("All meet the specification")
        shots("supplier-certificate-lot-record")
        sign_out()

        # An auditor reads the record and cannot change it.
        login("sc_auditor")
        page.goto(lot_url)
        expect(page.get_by_role("link", name="Record supplier certificate")).to_have_count(0)
        section("Supplier certificates").get_by_role("link", name="COA-SYN-0001").click()
        expect(page).to_have_url(certificate_url)
        expect(page.get_by_role("link", name="Correct supplier certificate")).to_have_count(0)
        assert page.goto(certificate_url + "correct/").status == 403
        assert page.goto(certificate_url + "withdraw/").status == 403
        page.goto(live_server.url + "/")
        sign_out()

        # The analyst withdraws the record; it is kept and marked.
        login("sc_analyst2")
        page.goto(certificate_url)
        page.get_by_role("link", name="Withdraw supplier certificate").click()
        field("Reason for withdrawal").fill("Recorded on the wrong lot")
        page.get_by_role("button", name="Withdraw supplier certificate", exact=True).click()
        expect(
            page.get_by_text("Supplier certificate withdrawn; the record is kept.")
        ).to_be_visible()
        expect(page.get_by_role("link", name="Correct supplier certificate")).to_have_count(0)
        expect(section("History").locator(".vr-history-item")).to_have_count(3)
        shots("supplier-certificate-withdrawn")
        browser.close()

    assert not errors, errors
    lot.refresh_from_db()
    current = certificates.lot_chains(lot)[0][-1]
    assert SupplierCertificate.objects.filter(lot=lot).count() == 2
    assert certificates.is_withdrawn(current)
    assert current.results.get(test_code="assay").value_text == "99.60"
    assert current.corrects.results.get(test_code="assay").value_text == "97.50"
    assert list(
        AuditEvent.objects.filter(action__startswith="supplier_certificate.")
        .order_by("occurred_at")
        .values_list("action", "actor__username")
    ) == [
        ("supplier_certificate.recorded", "sc_analyst2"),
        ("supplier_certificate.corrected", "sc_analyst2"),
        ("supplier_certificate.withdrawn", "sc_analyst2"),
    ]
