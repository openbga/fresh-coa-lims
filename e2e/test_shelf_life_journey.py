"""A shelf-life evaluation, in Chromium: quality drafts the evaluation of an assay at the long-term
condition from a study of three tested batches, sees the regression drawn with the confidence
limit and the estimate, and another quality person concludes it with a signature that records a
shelf life no longer than the estimate."""

import re

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from helpers import ACTION_TIMEOUT_MS, pick
from helpers import field as labelled
from playwright.sync_api import expect, sync_playwright

from core.models import ElectronicSignature
from core.services import set_pin
from laboratory.tests.helpers import PASSWORD, PIN, ROLES
from stability import shelf_life
from stability.forms import shelf_life_study_label
from stability.models import ShelfLifeEvaluation
from stability.tests.helpers import FALLING, studies_with_results


@pytest.fixture
def people(django_user_model):
    users = {}
    for name, roles in ROLES.items():
        user = django_user_model.objects.create_user(name, password=PASSWORD)
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        if name not in ("auditor", "admin"):
            set_pin(actor=user, pin=PIN, password=PASSWORD)
        users[name] = user
    return users


@pytest.mark.django_db(transaction=True)
def test_a_shelf_life_is_evaluated_and_independently_concluded(live_server, people, artifacts):
    studies, _ = studies_with_results(people, FALLING)
    study_label = shelf_life_study_label(studies[0])
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
            # Quality starts from the Shelf life tab: a study first, then the test.
            login(people["quality"])
            page.get_by_role("navigation").get_by_role("link", name="Stability").click()
            page.get_by_role("link", name="Shelf life", exact=True).click()
            page.get_by_role("link", name="New evaluation").first.click()
            pick(field("Study"), label=study_label)
            page.get_by_role("button", name="Continue", exact=True).click()
            pick(field("Storage condition"), label="Long-term")
            pick(field("Test"), label="Assay (assay) · 95 to 105 %")
            page.get_by_label("Expected to decrease").check()
            field("Purpose").fill("Synthetic data for a proposed shelf life")
            field("Reason").fill("Evaluate the three primary batches")
            page.get_by_role("button", name="Draft evaluation", exact=True).click()
            expect(page.get_by_text(re.compile(r"SLE-\d+ drafted"))).to_be_visible()
            expect(page.locator("svg.vr-trend-plot")).to_be_visible()
            expect(page.get_by_text("Pooled: one line for all studies").first).to_be_visible()
            # Whoever drafted it is told why they cannot conclude it.
            expect(page.get_by_text(re.compile("another quality person concludes"))).to_be_visible()
            shots("shelf-life-draft")
            detail = page.url
            sign_out()

            # Another quality person concludes it with a signature.
            login(people["quality2"])
            page.goto(detail)
            page.get_by_role("link", name="Conclude", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            page.get_by_label("Shelf life supported", exact=True).check()
            field("Shelf life (months)").fill("18")
            field("Conclusion").fill(
                "The pooled data of three batches support 18 months, within the estimate."
            )
            field("Signing username").fill(people["quality2"].username)
            field("Signature PIN").fill(PIN)
            field("Reason for signing").fill("Independent statistical review")
            page.get_by_role("button", name="Sign and conclude", exact=True).click()
            expect(page.get_by_text(re.compile(r"SLE-\d+ concluded\."))).to_be_visible()
            expect(page.get_by_text("Concluded · 18 months").first).to_be_visible()
            shots("shelf-life-concluded")
        finally:
            browser.close()

    evaluation = ShelfLifeEvaluation.objects.get()
    assert evaluation.state == "concluded" and evaluation.shelf_life_months == 18
    assert evaluation.drafted_by == people["quality"]
    assert evaluation.content["figures"]["model"] == "pooled"
    assert shelf_life.replay(evaluation.content).longest_supported >= 18
    signature = ElectronicSignature.objects.get(meaning="concluded")
    assert signature.signer == people["quality2"]
    assert errors == []
