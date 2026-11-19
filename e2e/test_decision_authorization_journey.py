"""A lot whose rule set reserves its release for people qualified for "Synthetic-QC-Release", in
Chromium: the quality person holding no such qualification is told so on the lot record and is
not offered the disposition; another quality person records a qualification for release
decisions, a third approves it, and the first then signs the release, which names the
qualification on the lot record and on the qualification's own page."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import ACTION_TIMEOUT_MS, db_call, pick
from helpers import field as labelled
from playwright.sync_api import expect, sync_playwright

from laboratory.models import Qualification
from quality.models import Lot
from tests.test_decision_authorization import RELEASE_ACTIVITY, RESERVED, ready
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_result_types_journey import build_world


@pytest.mark.django_db(transaction=True)
def test_a_release_reserved_for_qualified_people(live_server, django_user_model, artifacts):
    world = ready(build_world(django_user_model, extra_policy=RESERVED))
    people, lot = world["people"], world["lot"]
    lot_url = live_server.url + reverse("quality:lot_detail", args=[lot.pk])
    today = timezone.localdate()
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(ACTION_TIMEOUT_MS)
        page.on("pageerror", lambda error: errors.append(str(error)))

        def login(person):
            page.goto(live_server.url + reverse("login"))
            page.get_by_label(re.compile(r"^Username\b")).fill(person.username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(live_server.url + "/")

        def sign_out():
            page.get_by_role("button", name="Sign out", exact=True).click()

        def field(label):
            return labelled(page, label)

        def sign(person, reason, button, reason_label="Reason for signing"):
            expect(page.get_by_role("dialog")).to_be_visible()
            field("Signing username").fill(person.username)
            field("Signature PIN").fill(PIN)
            field(reason_label).fill(reason)
            page.get_by_role("button", name=button, exact=True).click()

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        try:
            # The approver holds the quality role but no qualification for release decisions.
            login(people["approver"])
            page.goto(lot_url)
            disposition = page.locator("section", has=page.locator("#disposition-heading"))
            expect(disposition).to_contain_text("Who may release")
            expect(disposition).to_contain_text(f"qualified for “{RELEASE_ACTIVITY}”")
            expect(page.get_by_role("link", name="Review disposition")).to_have_count(0)
            expect(page.locator('[data-refused="disposition"]')).to_contain_text(
                "You hold no approved, current qualification for it."
            )
            shots("release-reserved")
            sign_out()

            # Another quality person records the qualification; a third approves it.
            login(people["author"])
            page.goto(live_server.url + reverse("laboratory:qualification_new"))
            pick(field("Qualified person"), label=people["approver"].username)
            field("Activity").fill(RELEASE_ACTIVITY)
            pick(field("Qualified for"), label="Release decisions")
            field("Evidence reference").fill("AUTH-SYN-RELEASE-01")
            field("Valid from").fill(today.isoformat())
            field("Valid until (inclusive)").fill((today + timedelta(days=365)).isoformat())
            field("Reason").fill("Authorized for release decisions in the synthetic segment")
            page.get_by_role("button", name="Record qualification", exact=True).click()
            expect(page.get_by_text("Qualification recorded; independent approval")).to_be_visible()
            expect(page.get_by_text("Release decisions").first).to_be_visible()
            qualification_url = page.url
            sign_out()

            login(people["analyst"])
            page.goto(qualification_url)
            page.get_by_role("link", name="Approve", exact=True).click()
            sign(people["analyst"], "Authorization record checked", "Sign and approve")
            expect(page.get_by_text("Qualification approved.")).to_be_visible()
            sign_out()

            # The approver now signs the release, which names the qualification it relies on.
            held = db_call(lambda: Qualification.objects.get(work="release"))
            login(people["approver"])
            page.goto(lot_url)
            page.get_by_role("link", name="Review disposition", exact=True).click()
            expect(page.get_by_role("dialog")).to_contain_text(
                f"This signature relies on your qualification QUAL-{held.pk}"
            )
            shots("release-signature")
            sign(
                people["approver"],
                "Independent synthetic QC disposition",
                "Sign approved",
                reason_label="Reason",
            )
            expect(page.get_by_text("Lot released.")).to_be_visible()
            released = page.locator("section", has=page.locator("#reports-heading"))
            expect(released).to_contain_text("Released under")
            expect(released.get_by_role("link", name=f"QUAL-{held.pk}")).to_be_visible()
            shots("release-authorized")

            released.get_by_role("link", name=f"QUAL-{held.pk}").click()
            decisions = page.locator("section", has_text="Decisions relying on it")
            expect(decisions).to_contain_text(lot.number)
            shots("qualification-decisions")
        finally:
            browser.close()

    lot = Lot.objects.get(pk=lot.pk)
    assert lot.state == "released"
    assert lot.disposition_evidence["authorization"][0]["qualification"] == held.pk
    assert errors == []
