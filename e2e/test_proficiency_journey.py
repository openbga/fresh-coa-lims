"""A proficiency testing round, in Chromium: quality plans it for a method, an analyst records
an unsatisfactory result and the report, a quality person who recorded none of it reviews the
outcome with corrective follow-up, records the follow-up, and another quality person closes it;
the method shows the outcome."""

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
from catalog.models import ProficiencyParticipation
from core.models import ElectronicSignature
from core.services import set_pin
from laboratory.tests.helpers import PASSWORD, PIN

ROLES = {"analyst": ["analyst"], "planner": ["quality"], "reviewer": ["quality"]}


@pytest.mark.django_db(transaction=True)
def test_a_round_is_planned_reviewed_and_its_follow_up_closed(
    live_server, django_user_model, artifacts
):
    people = {}
    for name, roles in ROLES.items():
        user = django_user_model.objects.create_user(
            f"pt_{name}", password=PASSWORD, first_name="Synthetic", last_name=name.title()
        )
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        set_pin(actor=user, pin=PIN, password=PASSWORD)
        people[name] = user
    now = timezone.now()
    today = timezone.localdate()
    method, _ = catalog.create_method(
        actor=people["planner"],
        code="syn-kf-water",
        title="Synthetic water by Karl Fischer",
        technique="Karl Fischer titration",
        document_ref="SOP-SYN-KF-01 rev 2",
        suitability_kind="validation",
        suitability_ref="VR-SYN-KF-01",
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

        def sign(person, button):
            expect(page.get_by_role("dialog")).to_be_visible()
            field("Signing username").fill(person.username)
            field("Signature PIN").fill(PIN)
            field("Reason for signing").fill("Synthetic signature")
            page.get_by_role("button", name=button, exact=True).click()

        try:
            # Quality plans the round from the Proficiency testing tab.
            login(people["planner"])
            goto("catalog:methods")
            tabs = page.locator(".vr-section-tabs")
            tabs.get_by_role("link", name="Proficiency testing").click()
            page.get_by_role("link", name="New participation").first.click()
            pick(field("Method"), label="syn-kf-water · Synthetic water by Karl Fischer")
            pick(field("Kind"), label="Proficiency testing scheme")
            field("Provider or organizer").fill("Synthetic PT Provider")
            field("Round").fill("Round 2026-4")
            field("Test item").fill("Synthetic lactose, water content")
            field("Results due").fill((today + timedelta(days=14)).isoformat())
            field("Reason").fill("Annual plan")
            page.get_by_role("button", name="Plan participation", exact=True).click()
            expect(page.get_by_text(re.compile(r"PT-\d+ planned\."))).to_be_visible()
            record_url = page.url
            sign_out()

            # The analyst records the result and the report; the score decides the outcome.
            login(people["analyst"])
            page.goto(record_url)
            page.get_by_role("link", name="Record result", exact=True).click()
            field("Measurand").fill("Water")
            field("Unit").fill("%")
            field("Laboratory's result").fill("5.62")
            field("Assigned value").fill("5.10")
            pick(field("Analyst"), label="Synthetic Analyst (pt_analyst)")
            pick(field("Score"), label="z score")
            field("Score value").fill("3.4")
            field("Reason").fill("From the provider's report")
            page.get_by_role("button", name="Record result", exact=True).click()
            expect(page.get_by_text("Water added to")).to_be_visible()
            page.get_by_role("link", name="Record report", exact=True).click()
            field("Item received").fill((today - timedelta(days=12)).isoformat())
            field("Results reported").fill((today - timedelta(days=5)).isoformat())
            field("Laboratory records").fill("WS-SYN-KF-0412")
            field("Provider's report").fill("SYN-PT 2026-4 final report")
            field("Report dated").fill((today - timedelta(days=1)).isoformat())
            field("Reason for change").fill("Report received")
            page.get_by_role("button", name="Save report", exact=True).click()
            expect(page.get_by_text("Report of")).to_be_visible()
            # Nobody is offered the review of results they recorded.
            expect(page.get_by_role("link", name="Review outcome")).to_have_count(0)
            shots("proficiency-awaiting-review")
            sign_out()

            # A quality person who recorded none of it reviews the outcome with follow-up.
            login(people["reviewer"])
            page.goto(record_url)
            page.get_by_role("link", name="Review outcome", exact=True).click()
            expect(page.get_by_role("dialog").get_by_text("Unsatisfactory").first).to_be_visible()
            field("Review of the outcome").fill("Positive bias above the action signal.")
            expect(page.get_by_label("Corrective follow-up")).to_be_checked()
            sign(people["reviewer"], "Sign review")
            expect(page.get_by_text(re.compile(r"PT-\d+ reviewed\."))).to_be_visible()
            expect(page.get_by_text("Corrective follow-up open").first).to_be_visible()
            page.get_by_role("link", name="Record follow-up", exact=True).click()
            field("Cause").fill("Drift of the titrant factor between standardizations.")
            field("Corrective actions").fill("Daily standardization; analysts briefed.")
            field("Results already reported").fill("Results since the last round re-checked.")
            field("Effectiveness check").fill("Remaining item re-analysed: z = 0.4.")
            field("Quality-system reference").fill("CAPA-SYN-021")
            field("Reason for change").fill("Investigation complete")
            page.get_by_role("button", name="Save follow-up", exact=True).click()
            expect(page.get_by_text("Follow-up of")).to_be_visible()
            # Whoever recorded the follow-up does not close it.
            expect(page.get_by_role("link", name="Close follow-up")).to_have_count(0)
            sign_out()

            # The planner, who recorded none of it, closes the follow-up.
            login(people["planner"])
            page.goto(record_url)
            page.get_by_role("link", name="Close follow-up", exact=True).click()
            sign(people["planner"], "Sign and close")
            expect(page.get_by_text(re.compile(r"Follow-up of PT-\d+ closed\."))).to_be_visible()
            shots("proficiency-closed")
            goto("catalog:methods")
            expect(page.get_by_text("Unsatisfactory").first).to_be_visible()
            shots("proficiency-methods-list")
        finally:
            browser.close()

    item = ProficiencyParticipation.objects.get()
    assert item.state == "closed" and item.outcome == "unsatisfactory"
    assert item.follow_up_required and item.close_content["quality_reference"] == "CAPA-SYN-021"
    assert ElectronicSignature.objects.filter(
        meaning="reviewed", signer=people["reviewer"]
    ).exists()
    assert ElectronicSignature.objects.filter(meaning="closed", signer=people["planner"]).exists()
    assert errors == []
