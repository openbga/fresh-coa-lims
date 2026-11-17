"""A contract laboratory approved, its report recorded, reviewed and printed, in Chromium."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import pick, submit_for_review
from playwright.sync_api import expect, sync_playwright

from analytical import services as analytical
from analytical.models import Observation
from core.models import AuditEvent, ElectronicSignature
from laboratory.models import ContractApproval, ContractLaboratory, ContractUse
from tests.test_integrated_journey import PASSWORD, PIN, assign_and_sample
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

REPORT = "CLR-SYN-2026-0042"


@pytest.mark.django_db(transaction=True)
def test_contract_laboratory_from_approval_to_certificate(live_server, integrated, artifacts):  # noqa: F811
    data, people = integrated, integrated["people"]
    sample = assign_and_sample(data)
    tests, holds = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign approved tests"
    )
    assert not holds and len(tests) == 1
    test, lot = tests[0], data["lot"]
    method = data["method"].method.code
    today = timezone.localdate()
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

        def sign_out():
            page.get_by_role("button", name="Sign out", exact=True).click()

        def field(label):
            return page.get_by_label(re.compile(r"^" + re.escape(label)))

        def sign(person, reason, button):
            expect(page.get_by_role("dialog")).to_be_visible()
            field("Signing username").fill(person.username)
            field("Signature PIN").fill(PIN)
            field("Reason").fill(reason)
            page.get_by_role("button", name=button, exact=True).click()

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        def fill_report(date):
            pick(field("Contract laboratory"), index=1)
            field("Report number").fill(REPORT)
            field("Date of the report").fill(date.isoformat())
            field("Where the report is kept").fill("DMS-SYN-CLR-0042")
            field("Reported value (%)").fill("100.25")

        try:
            # Quality adds the laboratory and records the evidence for one method.
            login(people["author"])
            goto("laboratory:overview")
            page.get_by_role("link", name="Contract laboratories", exact=True).click()
            expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Laboratory")
            expect(page.get_by_text("No records yet")).to_be_visible()
            page.get_by_role("link", name="New contract laboratory").first.click()
            field("Code").fill("cl-syn-001")
            field("Name").fill("Synthetic Contract Analytics")
            field("Location").fill("Synthetic City, Nowhere")
            field("Reason").fill("Synthetic contract laboratory")
            page.get_by_role("button", name="Add contract laboratory", exact=True).click()
            expect(page.get_by_text("Contract laboratory cl-syn-001 added.")).to_be_visible()
            expect(page.get_by_text("No approval is recorded.")).to_be_visible()
            page.get_by_role("link", name="Record approval", exact=True).click()
            field("Method code").fill(method)
            field("Evidence reference").fill("QAG-SYN-001 rev 1")
            field("Valid from").fill((today - timedelta(days=10)).isoformat())
            field("Valid until").fill((today + timedelta(days=300)).isoformat())
            field("Reason").fill("Synthetic quality agreement and audit")
            page.get_by_role("button", name="Record approval", exact=True).click()
            expect(page.get_by_text("Approval evidence recorded")).to_be_visible()
            expect(page.get_by_text("Awaiting approval").first).to_be_visible()
            # The person who recorded the evidence is offered no signature.
            expect(page.get_by_role("link", name="Approve", exact=True)).to_have_count(0)
            approval_url = page.url
            shots("contract-approval-recorded")
            sign_out()

            # Until a second quality person signs, no report is accepted.
            login(people["receiver"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Record contract laboratory result", exact=True).click()
            expect(
                page.get_by_text(f"No contract laboratory is approved for method {method}.")
            ).to_be_visible()
            sign_out()

            login(people["approver"])
            page.goto(approval_url)
            page.get_by_role("link", name="Approve", exact=True).click()
            sign(people["approver"], "Agreement and audit report checked", "Sign and approve")
            expect(page.get_by_text("Contract laboratory approval signed.")).to_be_visible()
            expect(page.get_by_text("Approved", exact=True).first).to_be_visible()
            sign_out()

            # The analyst records what the laboratory's report states.
            login(people["receiver"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Record contract laboratory result", exact=True).click()
            expect(
                page.get_by_role(
                    "heading", name=re.compile("^Record contract laboratory result"), level=1
                )
            ).to_be_visible()
            expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Testing")
            toggle = page.get_by_role("button", name="Page documentation", exact=True)
            panel = page.get_by_role("complementary", name="Page documentation", exact=True)
            toggle.click()
            expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
                "data-pagedocs-for", "analytical:contract_result"
            )
            expect(panel.get_by_text("Rules and hidden logic", exact=True)).to_be_visible()
            toggle.click()
            # A report dated before the approval began is refused beside the laboratory.
            fill_report(today - timedelta(days=11))
            page.get_by_role("button", name="Record contract laboratory result").click()
            expect(page.get_by_text(re.compile("Refused: cl-syn-001: No approval"))).to_be_visible()
            expect(field("Report number")).to_have_value(REPORT)
            shots("contract-result-refused")
            fill_report(today - timedelta(days=2))
            page.get_by_role("button", name="Record contract laboratory result").click()
            expect(page.get_by_text("Contract laboratory result recorded.").first).to_be_visible()
            expect(page.get_by_text("It was not tested in this laboratory.")).to_be_visible()
            expect(page.get_by_text("Approval relied on:")).to_be_visible()
            expect(page.get_by_text("QAG-SYN-001 rev 1")).to_be_visible()
            # A correction is corrective, so it sits under More in the header.
            page.locator(".vr-page-actions").get_by_role("button", name="More").click()
            expect(
                page.get_by_role("link", name="Correct contract laboratory result", exact=True)
            ).to_be_visible()
            page.keyboard.press("Escape")
            shots("contract-result-recorded")
            submit_for_review(page, "Report transcribed")
            expect(page.get_by_text("Awaiting review", exact=True)).to_be_visible()
            sign_out()

            # A different person reviews it against the report, then quality dispositions.
            login(people["reviewer"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Sign review", exact=True).click()
            expect(page.get_by_text("Reported by contract laboratory")).to_be_visible()
            sign(people["reviewer"], "Checked against the laboratory's report", "Sign and review")
            expect(page.get_by_text("Reviewed · conforms", exact=True)).to_be_visible()
            sign_out()

            login(people["approver"])
            goto("quality:lot_detail", lot.pk)
            page.get_by_role("link", name="Review disposition", exact=True).click()
            sign(people["approver"], "Independent synthetic QC disposition", "Sign approved")
            meta = page.locator(".vr-page-meta")
            expect(meta.get_by_text("Released", exact=True)).to_be_visible()
            page.get_by_role("link", name="Issue certificate of analysis", exact=True).click()
            printed = (
                "Tested by contract laboratory Synthetic Contract Analytics, Synthetic City, "
                f"Nowhere. Report {REPORT} dated {(today - timedelta(days=2)).isoformat()}."
            )
            expect(page.get_by_text(printed)).to_be_visible()
            page.get_by_role("link", name="Continue to signing", exact=True).click()
            field("Issued to").fill("Synthetic browser recipient")
            sign(people["approver"], "Issue reviewed evidence", "Sign and issue certificate")
            page.get_by_role("link", name="Version 1", exact=True).click()
            expect(page.get_by_text(printed)).to_be_visible()
            shots("contract-result-certificate")

            # The laboratory's record lists the result that relied on its approval.
            page.goto(approval_url)
            relied = page.locator(
                "section", has=page.get_by_role("heading", name="Results that relied on")
            )
            expect(relied.get_by_role("link", name=re.compile(test.label))).to_be_visible()
            expect(relied).to_contain_text(REPORT)
            expect(relied).to_contain_text("Reviewed")
            shots("contract-approval-relied-on")
        except Exception:
            page.screenshot(path=str(artifacts / "contract-failure.png"), full_page=True)
            (artifacts / "contract-failure.html").write_text(page.content())
            raise
        finally:
            browser.close()

    assert not errors, errors
    laboratory = ContractLaboratory.objects.get()
    approval = ContractApproval.objects.get()
    assert (laboratory.code, approval.state) == ("cl-syn-001", "approved")
    observation = Observation.objects.get(test=test)
    assert observation.contract["approval"]["id"] == approval.pk
    assert observation.recorded_by == people["receiver"]
    assert ContractUse.objects.get().report_number == REPORT
    assert AuditEvent.objects.filter(action="contract.report_refused").count() == 1
    assert ElectronicSignature.objects.filter(
        object_type="laboratory.contractapproval", meaning="approved"
    ).exists()
    lot.refresh_from_db()
    assert lot.state == "released"
