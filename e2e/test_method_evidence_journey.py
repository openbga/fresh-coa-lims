"""Method evidence to an approved method version, in Chromium: an analyst records the validation
of a method with its characteristics, a quality person who did not record it approves it with
a signature, another quality person has the draft method version rely on it, and the first
approves that version, whose page then links the record."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from helpers import ACTION_TIMEOUT_MS, pick
from helpers import field as labelled
from playwright.sync_api import expect, sync_playwright

from catalog import services as catalog
from catalog.models import MethodEvidence, MethodRevision
from core.models import ElectronicSignature
from core.services import set_pin
from laboratory.tests.helpers import PASSWORD, PIN

ROLES = {"analyst": ["analyst"], "quality": ["quality"], "author": ["quality"]}


@pytest.mark.django_db(transaction=True)
def test_validation_evidence_is_approved_and_a_method_version_relies_on_it(
    live_server, django_user_model, artifacts
):
    people = {}
    for name, roles in ROLES.items():
        user = django_user_model.objects.create_user(
            f"mev_{name}", password=PASSWORD, first_name="Synthetic", last_name=name.title()
        )
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        set_pin(actor=user, pin=PIN, password=PASSWORD)
        people[name] = user
    now = timezone.now()
    method, draft = catalog.create_method(
        actor=people["author"],
        code="syn-hplc-assay",
        title="Synthetic HPLC assay",
        technique="HPLC-UV",
        document_ref="SOP-SYN-HPLC-01 rev 3",
        suitability_kind="validation",
        suitability_ref="To be linked",
        effective_from=now - timedelta(days=1),
        effective_until=now + timedelta(days=365),
        reason="Synthetic method for the journey",
    )
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(ACTION_TIMEOUT_MS)
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
            return labelled(page, label)

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        try:
            # The analyst records the validation from the Method evidence tab.
            login(people["analyst"])
            goto("catalog:methods")
            page.locator(".vr-section-tabs").get_by_role("link", name="Method evidence").click()
            page.get_by_role("link", name="New evidence record").first.click()
            pick(field("Method"), label="syn-hplc-assay · Synthetic HPLC assay")
            pick(field("Kind of evidence"), label="Method validation")
            field("Title").fill("Validation of the synthetic assay in tablets")
            field("Procedure studied").fill("SOP-SYN-HPLC-01 rev 3")
            field("Intended use").fill("Assay of the synthetic API in tablets, 80 to 120 %.")
            field("Report").fill("VR-SYN-HPLC-01 rev 1")
            field("Report completed on").fill(
                (timezone.localdate() - timedelta(days=2)).isoformat()
            )
            pick(field("Conclusion"), label="Suitable for the intended use")
            field("Statement of suitability").fill("Suitable for the assay in tablets.")
            field("Reason").fill("Validation report issued")
            page.get_by_role("button", name="Record draft", exact=True).click()
            expect(page.get_by_text("recorded as a draft")).to_be_visible()
            expect(page.get_by_text("Add the characteristics that were evaluated")).to_be_visible()
            page.get_by_role("link", name="Add characteristic", exact=True).click()
            pick(field("Characteristic"), label="Accuracy")
            field("Detail").fill("Recovery at 80, 100 and 120 %")
            field("Acceptance criterion").fill("Mean recovery 98.0 to 102.0 %")
            field("Result obtained").fill("99.4 %")
            pick(field("Criterion"), label="Met")
            field("Reason").fill("Report table 3")
            page.get_by_role("button", name="Add characteristic", exact=True).click()
            expect(page.get_by_text("Mean recovery 98.0 to 102.0 %")).to_be_visible()
            # Nobody is offered approval of their own record.
            expect(page.get_by_role("link", name="Review and approve")).to_have_count(0)
            evidence_url = page.url
            shots("method-evidence-draft")
            sign_out()

            # A quality person who did not record it approves it with a signature.
            login(people["quality"])
            page.goto(evidence_url)
            page.get_by_role("link", name="Review and approve", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            field("Signing username").fill(people["quality"].username)
            field("Signature PIN").fill(PIN)
            field("Reason for signing").fill("Report and criteria checked")
            page.get_by_role("button", name="Sign and approve", exact=True).click()
            expect(page.get_by_text(re.compile(r"MEV-\d+ approved\."))).to_be_visible()
            shots("method-evidence-approved")
            sign_out()

            # The author of the draft version has it rely on the approved record.
            login(people["author"])
            page.goto(evidence_url)
            page.get_by_role("link", name="Rely on it in version 1").click()
            # The record it was opened from is chosen.
            expect(page.locator("select[name=evidence] option:checked").last).to_contain_text(
                "Validation of the synthetic assay"
            )
            field("Reason for change").fill("Validation report approved")
            page.get_by_role("button", name="Save suitability evidence", exact=True).click()
            expect(page.get_by_text("Suitability evidence of draft")).to_be_visible()
            sign_out()

            # The quality person approves the version; its page links the record.
            login(people["quality"])
            goto("catalog:method", method.pk)
            page.get_by_role("link", name=re.compile("^Review and approve")).click()
            expect(
                page.get_by_text("Validation of the synthetic assay in tablets").last
            ).to_be_visible()
            field("Approval comment").fill("Procedure and evidence checked")
            field("Signing username").fill(people["quality"].username)
            field("Signature PIN").fill(PIN)
            page.get_by_role("button", name="Sign and approve", exact=True).click()
            expect(page.get_by_text("approved and signed")).to_be_visible()
            expect(page.get_by_role("link", name=re.compile(r"^MEV-\d+$")).first).to_be_visible()
            shots("method-version-relies-on-evidence")
        finally:
            browser.close()

    item = MethodEvidence.objects.get()
    version = MethodRevision.objects.get(pk=draft.pk)
    assert item.state == "approved" and item.characteristics.count() == 1
    assert version.status == "approved" and version.evidence == item
    assert version.approved_content["evidence"]["content_hash"] == item.content_hash
    assert version.suitability_ref == "VR-SYN-HPLC-01 rev 1"
    assert ElectronicSignature.objects.filter(
        object_type="catalog.methodevidence", meaning="approved", signer=people["quality"]
    ).exists()
    assert errors == []
