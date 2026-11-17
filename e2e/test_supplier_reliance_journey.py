"""A supplier qualified, a certificate result accepted in place of a test, the lot dispositioned
and the supplier's result named on the certificate of analysis, in Chromium."""

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import pick
from playwright.sync_api import expect, sync_playwright

from analytical import services as analytical
from analytical.models import AnalyticalTest
from core.models import AuditEvent, ElectronicSignature
from quality.models import SupplierResultAcceptance
from sampling import services as sampling
from suppliers.models import SupplierQualification
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_result_types_journey import record, review, submit
from tests.test_supplier_certificates import certify
from tests.test_supplier_reliance import accept, build_reliance_world, fully_stated, propose


class Journey:
    """One browser session with the helpers every step uses."""

    def __init__(self, playwright, base, artifacts, errors):
        self.base, self.artifacts = base, artifacts
        self.browser = playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.page.on("pageerror", lambda error: errors.append(str(error)))

    def goto(self, name, *args):
        self.page.goto(self.base + reverse(name, args=args))

    def login(self, person):
        self.goto("login")
        self.page.get_by_label(re.compile(r"^Username\b")).fill(person.username)
        self.page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        self.page.get_by_role("button", name="Sign in", exact=True).click()
        expect(self.page).to_have_url(self.base + "/")

    def sign_out(self):
        self.page.get_by_role("button", name="Sign out", exact=True).click()

    def field(self, label):
        return self.page.get_by_label(re.compile(r"^" + re.escape(label)))

    def sign(self, person, reason, button):
        expect(self.page.get_by_role("dialog")).to_be_visible()
        self.field("Signing username").fill(person.username)
        self.field("Signature PIN").fill(PIN)
        self.field("Reason").fill(reason)
        self.page.get_by_role("button", name=button, exact=True).click()

    def section(self, heading):
        return self.page.locator(
            "section", has=self.page.get_by_role("heading", name=heading, exact=True)
        )

    def shots(self, name):
        page = self.page
        page.screenshot(path=str(self.artifacts / f"{name}-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
        page.screenshot(path=str(self.artifacts / f"{name}-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})

    def failed(self, name):
        self.page.screenshot(path=str(self.artifacts / f"{name}-failure.png"), full_page=True)
        (self.artifacts / f"{name}-failure.html").write_text(self.page.content())


@pytest.mark.django_db(transaction=True)
def test_supplier_result_from_qualification_to_certificate(
    live_server, django_user_model, artifacts
):
    world = build_reliance_world(django_user_model)
    people, lot, supplier = world["people"], world["lot"], world["supplier"]
    certificate = certify(world, fully_stated(), lot=lot)
    certificate_url = live_server.url + reverse("quality:certificate_detail", args=[certificate.pk])
    today = timezone.localdate()
    errors = []

    # Quality qualifies the supplier for the material; a second quality person signs.
    with sync_playwright() as playwright:
        journey = Journey(playwright, live_server.url, artifacts, errors)
        page, field = journey.page, journey.field
        try:
            journey.login(people["author"])
            journey.goto("suppliers:detail", supplier.pk)
            expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Suppliers")
            expect(page.get_by_text("No qualification is recorded.")).to_be_visible()
            page.get_by_role("link", name="Record qualification", exact=True).click()
            pick(page.get_by_label(re.compile("^Material")), label=str(world["material"]))
            page.get_by_role("button", name="Continue", exact=True).click()
            expect(
                page.get_by_role("heading", name=re.compile("^Record qualification"), level=1)
            ).to_be_visible()
            for name in ("Assay", "Impurity", "Salmonella", "Total aerobic count"):
                page.get_by_label(re.compile(rf"^{name} \(")).check()
            field("How the supplier was qualified").fill(
                "Three synthetic lots tested in full and compared with the certificates"
            )
            field("Evidence reference").fill("SQR-SYN-001 rev 1")
            field("Valid from").fill((today - timedelta(days=10)).isoformat())
            field("Valid until").fill((today + timedelta(days=300)).isoformat())
            field("Reason").fill("Synthetic supplier qualification")
            journey.shots("supplier-qualification-form")
            page.get_by_role("button", name="Record qualification", exact=True).click()
            expect(page.get_by_text("Qualification evidence recorded")).to_be_visible()
            expect(page.get_by_text("Awaiting approval").first).to_be_visible()
            # The person who recorded the evidence is offered no signature.
            expect(page.get_by_role("link", name="Approve", exact=True)).to_have_count(0)
            qualification_url = page.url
            journey.sign_out()

            # Until it is signed, the certificate's results cannot be proposed.
            journey.login(people["analyst"])
            page.goto(certificate_url)
            stated = journey.section("Results stated by the supplier")
            expect(stated).to_contain_text("still awaiting its signature")
            expect(page.get_by_role("link", name=re.compile("^Propose"))).to_have_count(0)
            journey.sign_out()

            journey.login(people["approver"])
            page.goto(qualification_url)
            page.get_by_role("link", name="Approve", exact=True).click()
            journey.sign(people["approver"], "Qualification report checked", "Sign and approve")
            expect(page.get_by_text("Supplier qualification signed.")).to_be_visible()
            expect(page.get_by_text("Approved", exact=True).first).to_be_visible()
            journey.shots("supplier-qualification-approved")
            journey.sign_out()
        except Exception:
            journey.failed("supplier-qualification")
            raise
        finally:
            journey.browser.close()

    # Between the sessions: the laboratory samples the lot, assigns its tests and performs the
    # identity test the rule set keeps with it; three of the other results are accepted.
    sample = sampling.record_sampling(
        actor=people["analyst"],
        lot=lot,
        reference="SYN-REL-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    analytical.assign_tests(actor=people["analyst"], sample=sample, reason="Assign tests")
    identity = AnalyticalTest.objects.get(lot=lot, test_code="identity")
    record(world, identity, "conforms")
    submit(world, identity)
    review(world, identity)
    for code in ("impurity", "salmonella", "tamc"):
        accept(world, propose(world, certificate, code))
    assay_test = AnalyticalTest.objects.get(lot=lot, test_code="assay")

    with sync_playwright() as playwright:
        journey = Journey(playwright, live_server.url, artifacts, errors)
        page, field = journey.page, journey.field
        try:
            # The analyst proposes the assay stated on the certificate in place of the test.
            journey.login(people["analyst"])
            page.goto(certificate_url)
            expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Lots")
            stated = journey.section("Results stated by the supplier")
            # Identity stays with the laboratory: the rule set says so.
            expect(stated).to_contain_text("requires the laboratory to perform identity itself")
            journey.shots("supplier-reliance-certificate")
            stated.get_by_role("link", name=re.compile("^Propose in place of a test")).click()
            expect(
                page.get_by_role(
                    "heading", name="Propose supplier result in place of a test", level=1
                )
            ).to_be_visible()
            expect(page.get_by_text("SQR-SYN-001 rev 1")).to_be_visible()
            expect(page.get_by_text("the laboratory always performs: identity")).to_be_visible()
            toggle = page.get_by_role("button", name="Page documentation", exact=True)
            panel = page.get_by_role("complementary", name="Page documentation", exact=True)
            toggle.click()
            expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
                "data-pagedocs-for", "quality:acceptance_new"
            )
            expect(panel.get_by_role("heading", name="Rules and hidden logic")).to_be_visible()
            toggle.click()
            page.get_by_role("button", name="Propose supplier result", exact=True).click()
            expect(page.get_by_role("alert")).to_be_visible()  # A reason is required.
            field("Reason").fill("Supplier qualified for this test")
            page.get_by_role("button", name="Propose supplier result", exact=True).click()
            expect(page.get_by_text("Supplier result proposed in place of a test")).to_be_visible()
            expect(page.get_by_text("Awaiting acceptance").first).to_be_visible()
            # The proposer also holds the reviewer role and is offered no signature.
            expect(page.get_by_role("link", name="Accept", exact=True)).to_have_count(0)
            acceptance_url = page.url
            journey.shots("supplier-result-proposed")
            # The test assigned for the requirement takes no laboratory work meanwhile.
            journey.goto("analytical:test_detail", assay_test.pk)
            expect(
                page.get_by_text("is proposed or accepted in place of this test")
            ).to_be_visible()
            expect(page.get_by_role("link", name="Record observation")).to_have_count(0)
            journey.sign_out()

            # An auditor reads the record and can neither accept nor withdraw it.
            journey.login(people["auditor"])
            page.goto(acceptance_url)
            expect(page.get_by_role("link", name="Withdraw", exact=True)).to_have_count(0)
            assert page.goto(acceptance_url + "accept/").status == 403
            assert page.goto(acceptance_url + "withdraw/").status == 403
            page.goto(live_server.url + "/")
            journey.sign_out()

            # A reviewer who authored none of it signs the acceptance.
            journey.login(people["reviewer"])
            page.goto(acceptance_url)
            page.get_by_role("link", name="Accept", exact=True).click()
            journey.sign(
                people["reviewer"], "Checked against the supplier's certificate", "Sign and accept"
            )
            expect(page.get_by_text("Supplier result accepted in place of a test.")).to_be_visible()
            expect(page.get_by_text("Accepted", exact=True).first).to_be_visible()
            journey.shots("supplier-result-accepted")
            journey.goto("analytical:lot_testing", lot.pk)
            accepted = journey.section("Supplier results accepted in place of tests")
            expect(accepted.get_by_role("row")).to_have_count(5)  # Header and four results.
            expect(page.get_by_text("Not tested · supplier result").first).to_be_visible()
            expect(page.get_by_text("or an accepted supplier result")).to_be_visible()
            journey.shots("supplier-reliance-testing")
            journey.sign_out()

            # Quality sees which results are the supplier's, dispositions and issues.
            journey.login(people["approver"])
            journey.goto("quality:lot_detail", lot.pk)
            listed = journey.section("Supplier results in place of tests")
            expect(listed.get_by_role("row")).to_have_count(5)
            journey.shots("supplier-reliance-lot-record")
            page.get_by_role("link", name="Review disposition", exact=True).click()
            expect(
                page.get_by_text(re.compile("Assay: the supplier's stated result 99.60 %"))
            ).to_be_visible()
            journey.sign(
                people["approver"], "Independent synthetic QC disposition", "Sign approved"
            )
            meta = page.locator(".vr-page-meta")
            expect(meta.get_by_text("Released", exact=True)).to_be_visible()
            page.get_by_role("link", name="Issue certificate of analysis", exact=True).click()
            expect(
                page.get_by_text("Results accepted from the supplier's certificate of analysis.")
            ).to_be_visible()
            expect(page.get_by_text("This laboratory did not perform these tests.")).to_be_visible()
            page.get_by_role("link", name="Continue to signing", exact=True).click()
            field("Issued to").fill("Synthetic browser recipient")
            journey.sign(
                people["approver"], "Issue reviewed evidence", "Sign and issue certificate"
            )
            page.get_by_role("link", name="Version 1", exact=True).click()
            printed = page.get_by_role(
                "region", name="Results accepted from the supplier's certificate"
            )
            expect(printed.get_by_role("row", name=re.compile("^assay"))).to_contain_text(
                "COA-SYN-0001 dated 2026-11-02, issued by Synthetic Ingredients Supply"
            )
            expect(
                page.get_by_text("Supplier result assay accepted in place of a test")
            ).to_be_visible()
            journey.shots("supplier-reliance-certificate-of-analysis")

            # The qualification lists the results that relied on it.
            page.goto(qualification_url)
            relied = journey.section("Supplier results that relied on this qualification")
            expect(relied.get_by_role("row")).to_have_count(5)
            expect(relied).to_contain_text("Released")
            journey.shots("supplier-qualification-relied-on")
        except Exception:
            journey.failed("supplier-reliance")
            raise
        finally:
            journey.browser.close()

    assert not errors, errors
    qualification = SupplierQualification.objects.get()
    assert (qualification.state, qualification.recorded_by) == ("approved", people["author"])
    assert qualification.test_codes == ["assay", "impurity", "salmonella", "tamc"]
    assay = SupplierResultAcceptance.objects.get(test_code="assay")
    assert (assay.state, assay.proposed_by) == ("accepted", people["analyst"])
    assert ElectronicSignature.objects.filter(
        object_type="quality.supplierresultacceptance",
        object_id=str(assay.pk),
        meaning="accepted",
        signer=people["reviewer"],
    ).exists()
    assert not AuditEvent.objects.filter(action="supplier_result.refused").exists()
    lot.refresh_from_db()
    assert lot.state == "released"
    frozen = lot.disposition_evidence["analytical"]
    assert [r["test_code"] for r in frozen["results"]] == ["identity"]
    assert len(frozen["supplier_results"]) == 4
    assay_test.refresh_from_db()
    assert assay_test.state == "open" and not assay_test.observations.exists()
