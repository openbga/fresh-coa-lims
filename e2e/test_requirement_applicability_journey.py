"""A lot assigned under a general and a market scope is held where the two specifications state
a test differently, until a quality person who recorded none of its data signs which requirement
applies, through the pages, in Chromium."""

import re
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from helpers import expect_form, pick, wait_for_enhanced
from playwright.sync_api import expect, sync_playwright
from test_requirement_replacement_journey import WIDER_THAN_THE_PAGE

from core.models import AuditEvent, ElectronicSignature
from pagedocs.docs import doc_for
from quality.models import Lot
from sampling import services as sampling
from sampling.models import LotAssignment
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_requirement_applicability import (
    CONFLICT,
    REASON,
    TIGHT,
    WATER,
    extra_rules,
    overlay,
    sample_and_tests,
)
from tests.test_result_types_journey import build_world

ASSIGN_REASON = "Synthetic lot for the general and the EU market scope"
# The general specification's impurity line, stated alike by the market specification.
IMPURITY = {
    "code": "impurity",
    "name": "Impurity",
    "result_type": "numeric",
    "unit": "mg/g",
    "upper_limit": Decimal("5"),
    "upper_inclusive": False,
    "reporting_decimals": 2,
}
GENERAL = "98 – 102 % · rounded to 2 decimals · method synthetic-rt-method v1"
MARKET = "99 – 101 % · rounded to 2 decimals · method synthetic-rt-method v1"


@pytest.mark.django_db(transaction=True)
def test_conflicting_requirements_hold_a_lot_until_independent_quality_decides(
    live_server, django_user_model, artifacts
):
    # The receiver (rt_analyst) also holds the quality role; rt_approver recorded nothing.
    world = build_world(django_user_model, with_assay=True)
    lot, material = world["lot"], world["material"]
    bench = django_user_model.objects.create_user(
        username="rt_bench", password=PASSWORD, first_name="Synthetic", last_name="Bench"
    )
    bench.groups.add(Group.objects.get_or_create(name="analyst")[0])
    # The market states the assay more tightly, the impurity alike and water on its own; a
    # rule set applies to the market scope in addition to the lot's own.
    overlay(world, "eu-market", TIGHT, IMPURITY, WATER)
    extra_rules(world, "synthetic-eu-rules", {"scopes": ["eu-market"]}, ["water", "assay"])
    documentation = doc_for("sampling:decide")
    assert documentation is not None, "docs/pages/sampling-decide.md does not exist"
    base = live_server.url
    lot_url = base + reverse("sampling:lot", args=[lot.pk])
    decide_url = base + reverse("sampling:decide", args=[lot.pk])
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

        def statement(scope_of, code):
            """One statement of a test: a list item where it is only read, an option where
            one is chosen."""
            return scope_of.locator("fieldset li, fieldset .form-check").filter(
                has_text=f"{code} v1"
            )

        decide_links = page.get_by_role("link", name="Decide conflicting requirements")

        # An analyst assigns the lot's requirements under the general and the market scope.
        login("rt_bench")
        page.goto(lot_url)
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Sampling")
        page.get_by_role("link", name="Assign requirements", exact=True).first.click()
        expect(
            page.get_by_role("heading", name=f"Assign requirements · {lot.number}", level=1)
        ).to_be_visible()
        configured = page.locator("dl.vr-facts > div", has_text="Scopes in the configuration")
        expect(configured).to_contain_text("general, eu-market")
        expect(wait_for_enhanced(field("Material"))).to_have_value(str(material.pk))
        pick(field("Stage"), "incoming")
        expect(field("Scopes")).to_have_value("general")
        field("Scopes").fill("general, eu-market")
        field("Reason").fill(ASSIGN_REASON)
        page.get_by_role("button", name="Assign requirements", exact=True).click()
        expect(page).to_have_url(lot_url)
        expect(page.get_by_text("Applicability hold recorded:").first).to_be_visible()

        # The lot is held: both statements of the assay are shown, nothing is picked, and an
        # analyst is offered no decision.
        expect(section("Sampling readiness")).to_contain_text(f"Applicability hold: {CONFLICT}")
        current = section("Current requirements")
        hold = current.get_by_role("alert").filter(has_text="Applicability hold")
        expect(hold).to_contain_text(CONFLICT)
        expect(
            current.get_by_role("heading", name="Requirements the specifications state differently")
        ).to_be_visible()
        expect(current).to_contain_text("Nothing is merged and neither statement is picked.")
        expect(statement(current, "synthetic-rt-spec")).to_contain_text(GENERAL)
        expect(statement(current, "synthetic-rt-spec")).to_contain_text("general")
        expect(statement(current, "synthetic-rt-eu-market")).to_contain_text(MARKET)
        expect(statement(current, "synthetic-rt-eu-market")).to_contain_text("eu-market")
        expect(current.get_by_role("radio")).to_have_count(0)
        expect(current).to_contain_text("synthetic-rt-material")
        expect(decide_links).to_have_count(0)
        expect(page.get_by_role("link", name="Record sampling")).to_have_count(0)
        shots("requirement-applicability-hold")
        sign_out()

        # The person who received the lot holds the quality role too: told before any PIN.
        login("rt_analyst")
        response = page.goto(decide_url)
        assert response.status == 403
        denied = page.get_by_role("alert").filter(has_text="Not permitted")
        expect(denied).to_contain_text(
            "Someone who authored none of it decides which requirement applies."
        )
        expect(denied).to_contain_text("Independence cannot be bypassed by any role")
        expect(field("Signature PIN")).to_have_count(0)
        expect(page.get_by_role("radio")).to_have_count(0)
        expect(page.get_by_role("button", name=re.compile("^Sign decision"))).to_have_count(0)
        stated = section("Requirements stated differently")
        expect(statement(stated, "synthetic-rt-eu-market")).to_contain_text(MARKET)
        expect(page.get_by_role("link", name=f"Back to {lot.number}")).to_be_visible()
        shots("requirement-decision-denied")
        sign_out()

        # A quality person who recorded nothing of the lot is offered the decision.
        login("rt_approver")
        page.goto(lot_url)
        expect(decide_links.first).to_be_visible()
        page.locator("a.btn", has_text="Decide conflicting requirements").click()
        expect_form(page, decide_url)
        expect(
            page.get_by_role(
                "heading", name=f"Decide conflicting requirements · {lot.number}", level=1
            )
        ).to_be_visible()
        expect(page.locator('#vr-nav [aria-current="page"]')).to_have_text("Sampling")
        applies = section("What applies to this lot")
        expect(applies).to_contain_text("A lot has to meet every specification that binds it.")
        expect(applies.locator("dl.vr-facts > div", has_text="Scopes")).to_contain_text(
            "general, eu-market"
        )
        stated = section("Requirements stated differently")
        expect(stated.get_by_role("group", name="assay Assay")).to_be_visible()
        expect(statement(stated, "synthetic-rt-spec")).to_contain_text(GENERAL)
        expect(statement(stated, "synthetic-rt-eu-market")).to_contain_text(MARKET)
        expect(stated).to_contain_text("The statements differ in: limits.")
        expect(page.get_by_role("radio")).to_have_count(2)
        expect(page.get_by_role("radio", checked=True)).to_have_count(0)
        expect(
            applies.locator("dl.vr-facts > div", has_text="Specifications in force")
        ).to_contain_text("synthetic-rt-eu-market v1 (eu-market)")
        expect(
            applies.locator("dl.vr-facts > div", has_text="Additional rule sets in force")
        ).to_contain_text("synthetic-eu-rules v1")
        agreed = section("Requirements stated one way")
        expect(agreed.get_by_role("row", name=re.compile("^impurity"))).to_contain_text(
            "general, eu-market"
        )
        expect(agreed.get_by_role("row", name=re.compile("^water"))).to_contain_text("eu-market")
        signing = section("Sign decision")
        expect(signing).to_contain_text("requirements decided")
        expect(signing).to_contain_text("Signer: Synthetic Approver (rt_approver)")

        # The page's documentation opens beside it.
        toggle = page.get_by_role("button", name="Page documentation", exact=True)
        panel = page.get_by_role("complementary", name="Page documentation", exact=True)
        toggle.click()
        expect(panel.locator("[data-pagedocs-for]")).to_have_attribute(
            "data-pagedocs-for", "sampling:decide"
        )
        expect(panel.locator(".pagedocs-missing")).to_have_count(0)
        expect(panel.get_by_role("heading", name=documentation.title, exact=True)).to_be_visible()
        expect(panel.get_by_text("Who can use it", exact=True)).to_be_visible()
        expect(panel.get_by_text("Rules and hidden logic", exact=True)).to_be_visible()
        toggle.click()
        expect(panel).not_to_be_visible()
        shots("requirement-decision-review")
        # On a phone both statements are read in full, without scrolling sideways.
        page.set_viewport_size({"width": 390, "height": 844})
        for code, wording in (("synthetic-rt-spec", GENERAL), ("synthetic-rt-eu-market", MARKET)):
            option = statement(stated, code).locator("label")
            expect(option).to_contain_text(wording)
            box = option.bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= 390, (code, box)
        page.set_viewport_size({"width": 1440, "height": 1000})

        # Signed without a choice, nothing is decided and the PIN is not kept.
        sign = page.get_by_role("button", name="Sign decision and freeze requirements", exact=True)
        field("Reason for the decision").fill(REASON)
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        sign.click()
        expect_form(page, decide_url)
        expect(
            page.get_by_role("alert").filter(has_text="Choose which requirement applies")
        ).to_contain_text(
            "Choose which requirement applies for each test the specifications state differently."
        )
        expect(field("Signature PIN")).to_have_value("")
        expect(page.get_by_role("radio", checked=True)).to_have_count(0)
        expect(page.locator("#vr-form-content .vr-page-meta")).to_contain_text("Applicability hold")
        shots("requirement-decision-refused")

        # The market statement applies: a result within it also meets the general limits.
        page.get_by_role(
            "radio", name=re.compile(r"^synthetic-rt-eu-market v1 \(eu-market\)")
        ).check()
        field("Reason for the decision").fill(REASON)
        field("Signing username").fill("rt_approver")
        field("Signature PIN").fill(PIN)
        sign.click()
        expect(page).to_have_url(lot_url)
        expect(
            page.get_by_text("Decision signed. The requirements are frozen for this lot.").first
        ).to_be_visible()
        current = section("Current requirements")
        decided = current.get_by_role("status").filter(has_text="Decided")
        expect(decided).to_contain_text("quality decided which requirement applies")
        expect(decided).to_contain_text(
            "Signed by Synthetic Approver with the meaning requirements decided"
        )
        expect(decided).to_contain_text(REASON)
        expect(decided).to_contain_text("synthetic-rt-eu-market v1 (eu-market) applies, 99 – 101 %")
        expect(decided).to_contain_text("Not applied: synthetic-rt-spec v1 (general), 98 – 102 %")
        facts = current.locator("dl.vr-facts > div")
        expect(facts.filter(has_text="Stage and scopes")).to_contain_text("general, eu-market")
        specifications = facts.filter(has_text="Specifications")
        expect(specifications).to_contain_text("synthetic-rt-spec v1 (general)")
        expect(specifications).to_contain_text("synthetic-rt-eu-market v1 (eu-market)")
        expect(
            specifications.get_by_role("link", name="synthetic-rt-eu-market v1", exact=True)
        ).to_be_visible()
        expect(facts.filter(has_text="Additional rule sets")).to_contain_text(
            "synthetic-eu-rules v1 · requires water, assay"
        )
        expect(current.get_by_role("columnheader", name="Stated by", exact=True)).to_be_visible()
        assay = current.get_by_role("row", name=re.compile("^assay"))
        expect(assay).to_contain_text("≥ 99 and ≤ 101 %")
        expect(assay.get_by_role("cell").last).to_have_text("eu-market")
        for code, stated_by in (
            ("identity", "general"),
            ("impurity", "general, eu-market"),
            ("water", "eu-market"),
        ):
            row = current.get_by_role("row", name=re.compile(f"^{code}"))
            expect(row.get_by_role("cell").last).to_have_text(stated_by)
        expect(current.get_by_role("alert")).to_have_count(0)
        expect(decide_links).to_have_count(0)
        expect(section("Earlier requirement assignments")).to_contain_text("Applicability hold")
        shots("requirement-decision-signed")

        # Decided once: the page sends the reader back.
        page.goto(decide_url)
        expect(page).to_have_url(lot_url)
        expect(
            page.get_by_text("This lot is not held for a decision on conflicting requirements.")
        ).to_be_visible()
        browser.close()

    assert not errors, errors
    held, current = LotAssignment.objects.filter(lot=lot).order_by("assigned_at", "id")
    assert (held.status, held.assigned_by.username) == ("hold", "rt_bench")
    assert held.reason == ASSIGN_REASON and held.scopes == ["general", "eu-market"]
    assert held.hold_reasons == [CONFLICT]
    assert current == sampling.current_assignment(lot)
    assert (current.status, current.origin, current.supersedes_id) == ("ready", "decided", held.pk)
    assert current.assigned_by.username == "rt_approver" and current.reason == REASON
    (choice,) = current.payload["decisions"]
    assert (choice["code"], choice["scope"]) == ("assay", "eu-market")
    assert [rule["code"] for rule in current.payload["additional_rules"]] == ["synthetic-eu-rules"]
    # The refused attempt signed nothing: one signature, bound to the lot revision it produced.
    signature = ElectronicSignature.objects.get(
        object_type="quality.lot", object_id=str(lot.pk), meaning="requirements_decided"
    )
    assert signature.signer.username == "rt_approver"
    assert signature.revision == Lot.objects.get(pk=lot.pk).revision
    assert AuditEvent.objects.filter(action="lot.requirements_decided").count() == 1
    # The assay assigned afterwards is tested against the market limits.
    assay = sample_and_tests(world)["assay"]
    assert (assay.requirement["lower_limit"], assay.requirement["upper_limit"]) == ("99", "101")
    assert assay.requirement["source"].startswith("catalog:synthetic-rt-eu-market@v1#")
