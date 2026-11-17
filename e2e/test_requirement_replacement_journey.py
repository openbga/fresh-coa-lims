"""A revised specification retires the earlier version and replaces a lot's requirements during
testing, through the pages, in Chromium."""

import re

import pytest
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from analytical.models import AnalyticalTest
from core.models import AuditEvent, ElectronicSignature
from sampling import services as sampling
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_requirement_replacement import READINGS, complete, new_specification_version
from tests.test_result_types_journey import assign_sample_tests, build_world

REASON = "Change record CC-SYN-014: assay limits tightened"
# What makes a page scroll sideways on a phone: elements that reach past the right edge,
# outside the tables that scroll inside their own frame.
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""


@pytest.mark.django_db(transaction=True)
def test_revised_specification_replaces_requirements_and_the_test_is_repeated(
    live_server, django_user_model, artifacts
):
    world = build_world(django_user_model, with_assay=True)
    world["tests"] = assign_sample_tests(world)
    complete(world, "identity", "assay")
    lot, assay = world["lot"], world["tests"]["assay"]
    first = world["spec"]
    draft = new_specification_version(world, approved=False)
    base = live_server.url
    approve_url = base + reverse("catalog:specification_approve", args=[draft.pk])
    spec_url = base + reverse("catalog:specification", args=[first.specification_id])
    lot_url = base + reverse("sampling:lot", args=[lot.pk])
    replace_url = base + reverse("sampling:replace", args=[lot.pk])
    testing_url = base + reverse("analytical:lot_testing", args=[lot.pk])
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def login(username):
            page.goto(base + reverse("login"))
            page.get_by_label(re.compile(r"^Username\b")).fill(username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(base + "/")

        def sign_out():
            page.get_by_role("button", name="Sign out", exact=True).click()

        def field(label):
            return page.get_by_label(re.compile(r"^" + re.escape(label)))

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                name,
                page.evaluate(WIDER_THAN_THE_PAGE),
            )
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        def section(heading):
            return page.locator("section", has=page.get_by_role("heading", name=heading))

        # Quality approves the revised specification; the page says what the signature retires.
        login("rt_approver")
        page.goto(approve_url)
        retires = page.get_by_role("status").filter(has_text="Retires earlier")
        expect(retires).to_contain_text("Your signature also retires it")
        expect(retires).to_contain_text("synthetic-rt-spec v1 stops applying at the moment of your")
        expect(retires).to_contain_text("Lots keep the versions frozen")
        shots("specification-approval-retires")
        field("Approval comment").fill("Independent review of the tightened assay limits")
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign and approve", exact=True).click()
        expect(page.get_by_text("synthetic-rt-spec v2 approved and signed.")).to_be_visible()
        page.goto(spec_url)
        retired = page.get_by_role("row", name=re.compile(r"\b1\b.*Superseded"))
        expect(retired).to_contain_text("by version 2 from")
        shots("specification-versions-superseded")

        # The lot is in testing: its requirements are replaced with a signature, not assigned.
        page.goto(lot_url)
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Sampling")
        expect(page.get_by_role("link", name="Change requirements")).to_have_count(0)
        page.get_by_role("link", name="Replace requirements", exact=True).click()
        expect(
            page.get_by_role("heading", name=f"Replace requirements · {lot.number}", level=1)
        ).to_be_visible()
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Sampling")
        requirements = section("Requirements")
        changed = requirements.get_by_role("row", name=re.compile("^assay"))
        expect(changed).to_contain_text("Changed")
        expect(changed).to_contain_text("98 – 102 %")
        expect(changed).to_contain_text("98.5 – 101.5 %")
        expect(requirements.get_by_role("row", name=re.compile("^identity"))).to_contain_text(
            "Unchanged"
        )
        effects = section("Effect on the lot's tests")
        expect(effects.get_by_role("row", name=re.compile(assay.label))).to_contain_text(
            "Superseded"
        )
        expect(effects.get_by_text("Carries over", exact=True)).to_have_count(4)
        toggle = page.get_by_role("button", name="Page documentation", exact=True)
        panel = page.get_by_role("complementary", name="Page documentation", exact=True)
        toggle.click()
        expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
            "data-pagedocs-for", "sampling:replace"
        )
        expect(panel.get_by_text("Rules and hidden logic", exact=True)).to_be_visible()
        toggle.click()
        shots("requirement-replacement-review")

        # A refused signature changes nothing and keeps the page.
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign and replace requirements", exact=True).click()
        expect(page.get_by_text("This field is required.")).to_be_visible()
        expect(field("Signature PIN")).to_have_value("")
        field("Reason for the replacement").fill(REASON)
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        page.get_by_role("button", name="Sign and replace requirements", exact=True).click()
        expect(page).to_have_url(lot_url)
        expect(page.get_by_text("Requirements replaced and signed.")).to_be_visible()
        current = section("Current requirements")
        expect(current).to_contain_text("replaced the earlier ones during testing")
        expect(current).to_contain_text("with the meaning requirements replaced")
        expect(current).to_contain_text(REASON)
        expect(current).to_contain_text("synthetic-rt-spec v2")
        expect(current.get_by_role("row", name=re.compile("^assay"))).to_contain_text("98.5")
        shots("requirement-replacement-signed")
        page.goto(replace_url)
        expect(page).to_have_url(lot_url)
        expect(page.get_by_text("There is nothing to replace.")).to_be_visible()
        sign_out()

        # The analyst, who tested the lot and also holds the quality role, repeats the
        # superseded test; the earlier one stays in the record.
        login("rt_analyst")
        page.goto(testing_url)
        gate = section("Analytical evidence for QC disposition")
        expect(gate).to_contain_text("no assay test under the lot's current requirements")
        old = page.get_by_role("row", name=re.compile(assay.label))
        expect(old).to_contain_text("Superseded · requirements replaced")
        page.get_by_role("button", name=re.compile("^Assign required tests")).click()
        expect(page.get_by_text("Assigned 1 test(s)")).to_be_visible()
        repeat = page.get_by_role("row", name=re.compile("Repeat under replaced requirements"))
        expect(repeat).to_contain_text("Open")
        expect(repeat).to_contain_text("98.5")
        repeat.get_by_role("link").first.click()
        expect(page.get_by_role("link", name=assay.label, exact=True)).to_be_visible()
        page.get_by_role("link", name=assay.label, exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Superseded")).to_contain_text(
            "It takes no more work and does not count toward the lot's disposition."
        )
        expect(page.get_by_role("link", name="Record result")).to_have_count(0)
        shots("superseded-test")
        browser.close()

    assert not errors, errors
    current = sampling.current_assignment(lot)
    assert current.origin == "replaced" and current.reason == REASON
    signature = ElectronicSignature.objects.get(
        object_type="quality.lot", object_id=str(lot.pk), meaning="requirements_replaced"
    )
    assert signature.signer.username == "rt_approver"
    assert signature.revision == current.replacement["lot_revision"]
    assay.refresh_from_db()
    assert assay.state == "superseded" and assay.reportable_display == READINGS["assay"]
    repeated = AnalyticalTest.objects.get(lot=lot, kind="revised")
    assert repeated.parent == assay and repeated.state == "open"
    assert AuditEvent.objects.filter(action="revision.superseded").count() == 1
    assert AuditEvent.objects.filter(action="test.superseded").count() == 1


@pytest.mark.django_db(transaction=True)
def test_a_quality_person_who_tested_the_lot_is_told_before_any_pin(
    live_server, django_user_model, artifacts
):
    world = build_world(django_user_model, with_assay=True)
    world["tests"] = assign_sample_tests(world)
    complete(world, "assay")
    new_specification_version(world)
    lot = world["lot"]
    base = live_server.url

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base + reverse("login"))
        page.get_by_label(re.compile(r"^Username\b")).fill("rt_analyst")
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(base + "/")
        response = page.goto(base + reverse("sampling:replace", args=[lot.pk]))
        assert response.status == 403
        expect(page.get_by_role("alert")).to_contain_text("Someone who authored none of it")
        expect(page.get_by_label(re.compile("^Signature PIN"))).to_have_count(0)
        expect(page.get_by_role("link", name=f"Back to {lot.number}")).to_be_visible()
        page.screenshot(path=str(artifacts / "requirement-replacement-denied.png"), full_page=True)
        browser.close()

    assert sampling.current_assignment(lot).origin == "assigned"
