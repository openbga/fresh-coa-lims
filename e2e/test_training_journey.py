"""Training to a qualification, in Chromium: a reviewer records an analyst's assessment of
competence, the analyst acknowledges it with their signature, the reviewer records from it a
qualification to review the method, quality approves it, and the reminders list it as it nears
its last valid day."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from helpers import ACTION_TIMEOUT_MS, pick
from helpers import field as labelled
from playwright.sync_api import expect, sync_playwright

from core.models import ElectronicSignature
from core.services import set_pin
from laboratory.models import Qualification, TrainingRecord
from laboratory.tests.helpers import PASSWORD, PIN

ROLES = {"analyst": ["analyst"], "reviewer": ["reviewer"], "quality": ["quality"]}


@pytest.mark.django_db(transaction=True)
def test_training_is_acknowledged_and_a_qualification_to_review_relies_on_it(
    live_server, django_user_model, artifacts
):
    people = {}
    for name, roles in ROLES.items():
        user = django_user_model.objects.create_user(
            f"trn_{name}", password=PASSWORD, first_name="Synthetic", last_name=name.title()
        )
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        set_pin(actor=user, pin=PIN, password=PASSWORD)
        people[name] = user
    today = timezone.localdate()
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
            # Not the controls of the list behind the form dialog (their ids are renamed).
            return labelled(page, label)

        def sign(person, reason, button):
            expect(page.get_by_role("dialog")).to_be_visible()
            field("Signing username").fill(person.username)
            field("Signature PIN").fill(PIN)
            field("Reason for signing").fill(reason)
            page.get_by_role("button", name=button, exact=True).click()

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        try:
            # A reviewer records the analyst's assessment from the Training tab.
            login(people["reviewer"])
            goto("laboratory:overview")
            page.locator(".vr-section-tabs").get_by_role("link", name="Training").click()
            expect(page.get_by_text("No records yet")).to_be_visible()
            page.get_by_role("link", name="New training record").first.click()
            pick(field("Trainee"), label="trn_analyst")
            field("Activity").fill("SYN-HPLC-ASSAY")
            field("Procedure or course").fill("SOP-SYN-HPLC-01 rev 3")
            pick(field("Kind of training"), label="Assessment of competence")
            pick(field("Outcome"), label="Competent")
            field("Trainer or assessor").fill("Synthetic Senior Analyst")
            field("Completed on").fill((today - timedelta(days=2)).isoformat())
            field("Reason").fill("Synthetic assessment of competence")
            page.get_by_role("button", name="Record training", exact=True).click()
            expect(page.get_by_text("Training recorded; the trainee acknowledges")).to_be_visible()
            expect(page.get_by_text("Awaiting acknowledgement").first).to_be_visible()
            # Nobody but the trainee is offered the acknowledgement, nor a qualification yet.
            expect(page.get_by_role("link", name="Acknowledge", exact=True)).to_have_count(0)
            expect(page.get_by_role("link", name="Record qualification")).to_have_count(0)
            training_url = page.url
            sign_out()

            # The analyst acknowledges it with their signature.
            login(people["analyst"])
            page.goto(training_url)
            page.get_by_role("link", name="Acknowledge", exact=True).click()
            sign(people["analyst"], "I took this assessment", "Sign and acknowledge")
            expect(page.get_by_text("Training acknowledged.")).to_be_visible()
            expect(page.get_by_text("Acknowledged", exact=True).first).to_be_visible()
            expect(page.get_by_role("link", name="Record qualification")).to_have_count(0)
            shots("training-acknowledged")
            sign_out()

            # The reviewer records a qualification to review the method, relying on it.
            login(people["reviewer"])
            page.goto(training_url)
            page.get_by_role("link", name="Record qualification").click()
            expect(field("Activity")).to_have_value("SYN-HPLC-ASSAY")
            pick(field("Qualified for"), label="Reviewing results")
            field("Evidence reference").fill("AUTH-SYN-HPLC-07")
            field("Valid from").fill(today.isoformat())
            field("Valid until (inclusive)").fill((today + timedelta(days=20)).isoformat())
            field("Reason").fill("Authorized to review the method after the assessment")
            page.get_by_role("button", name="Record qualification", exact=True).click()
            expect(page.get_by_text("Qualification recorded; independent approval")).to_be_visible()
            expect(page.get_by_text("Reviewing results").first).to_be_visible()
            expect(page.get_by_role("heading", name="Training relied on")).to_be_visible()
            qualification_url = page.url
            sign_out()

            # Quality approves it, signing the training it relies on.
            login(people["quality"])
            page.goto(qualification_url)
            page.get_by_role("link", name="Approve", exact=True).click()
            sign(people["quality"], "Assessment and authorization checked", "Sign and approve")
            expect(page.get_by_text("Qualification approved.")).to_be_visible()
            shots("qualification-to-review")

            # Twenty days before its last valid day, it is on the reminders.
            goto("planning:reminders")
            reminder = page.locator("table tbody tr", has_text="SYN-HPLC-ASSAY")
            expect(reminder).to_contain_text("Expires in 20 days")
            expect(reminder).to_contain_text("Qualification")
            shots("qualification-reminder")
        finally:
            browser.close()

    training = TrainingRecord.objects.get()
    qualification = Qualification.objects.get()
    assert training.state == "acknowledged" and training.outcome == "competent"
    assert (qualification.state, qualification.work) == ("approved", "review")
    assert qualification.training == [training.pk]
    approval = ElectronicSignature.objects.get(
        object_type="laboratory.qualification", meaning="approved"
    )
    assert approval.content["training"] == [training.pk]
    assert errors == []
