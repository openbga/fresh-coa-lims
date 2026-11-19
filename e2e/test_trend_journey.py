"""A trend chart, in Chromium: quality creates the chart of an assay from its specification line
and drafts limits computed from ten reviewed lots, another quality person approves them with a
signature, a later result outside the limits raises an out-of-trend alert, and quality evaluates
it: one person records the findings, another concludes the evaluation with a signature."""

import re

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import ACTION_TIMEOUT_MS, db_call, pick
from helpers import field as labelled
from playwright.sync_api import expect, sync_playwright

from core.models import ElectronicSignature
from trending.models import Evaluation, Limits
from trending.tests.conftest import BASELINE, PASSWORD, PIN, make_trend, reviewed_lot


@pytest.mark.django_db(transaction=True)
def test_a_chart_is_drawn_its_limits_approved_and_an_alert_evaluated(
    live_server, django_user_model, artifacts
):
    data = make_trend(django_user_model)
    people = data["people"]
    for value in BASELINE:
        reviewed_lot(data, value)
    today = timezone.localdate().isoformat()
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
            # Quality creates the chart from the Trends item and drafts computed limits.
            login(people["author"])
            page.get_by_role("navigation").get_by_role("link", name="Trends").click()
            page.get_by_role("link", name="New trend chart").first.click()
            line = "syn-trend-api · Incoming material · assay (%) · syn-trend-spec v1"
            pick(field("Test"), label=line)
            field("Reason").fill("Follow the assay")
            page.get_by_role("button", name="Create chart", exact=True).click()
            expect(page.get_by_text(re.compile(r"TC-\d+ created\."))).to_be_visible()
            expect(page.locator("svg.vr-trend-plot")).to_be_visible()
            chart_url = page.url
            page.get_by_role("link", name="Draft limits", exact=True).click()
            page.get_by_label("Computed from a baseline of results").check()
            field("Baseline from").fill(today)
            field("Baseline to").fill(today)
            page.get_by_label("Results in a row on the same side of the center line").check()
            field("Basis of the limits").fill("The first ten synthetic lots")
            field("Reason for change").fill("First limits")
            page.get_by_role("button", name="Save draft", exact=True).click()
            expect(page.get_by_text("Limits v1 drafted.")).to_be_visible()
            # Whoever drafted the limits is told why they cannot approve them.
            expect(page.get_by_text("You drafted or changed these limits")).to_be_visible()
            limits_url = page.url
            sign_out()

            # Another quality person approves them with a signature.
            login(people["approver"])
            page.goto(limits_url)
            page.get_by_role("link", name="Approve limits", exact=True).click()
            sign(people["approver"], "Sign and approve")
            expect(page.get_by_text(re.compile(r"TC-\d+ v1 approved\."))).to_be_visible()
            sign_out()

            # A later result outside the limits raises an alert, which quality evaluates.
            alert = db_call(lambda: reviewed_lot(data, "103.0"))
            login(people["author"])
            page.goto(chart_url)
            expect(page.get_by_text("1 open alert").first).to_be_visible()
            shots("trend-chart-alert")
            page.get_by_role("link", name="Evaluate alerts", exact=True).click()
            expect(page.get_by_label(re.compile(rf"^{alert.label} ·"))).to_be_checked()
            field("Reason").fill("Look into the high assay")
            page.get_by_role("button", name="Open evaluation", exact=True).click()
            expect(page.get_by_text(re.compile(r"OOT-\d+ opened\."))).to_be_visible()
            page.get_by_role("link", name="Record findings", exact=True).click()
            field("Laboratory check").fill("Titrant factor and calculation checked: no error.")
            field("Cause").fill("None found; the lot's starting material came from a new batch.")
            field("Lots and results affected").fill("The lot conforms; nothing reported changes.")
            field("Quality-system reference").fill("DEV-SYN-031")
            field("Reason for change").fill("Findings")
            page.get_by_role("button", name="Save findings", exact=True).click()
            expect(page.get_by_text(re.compile(r"Findings of OOT-\d+ recorded\."))).to_be_visible()
            expect(page.get_by_role("link", name="Conclude evaluation")).to_have_count(0)
            sign_out()

            login(people["approver"])
            page.goto(chart_url)
            page.get_by_role("link", name=re.compile(r"^OOT-\d+$")).first.click()
            page.get_by_role("link", name="Conclude evaluation", exact=True).click()
            page.get_by_label("Not confirmed").check()
            field("Conclusion").fill("Chance variation within the process; no action.")
            sign(people["approver"], "Sign and conclude")
            expect(page.get_by_text(re.compile(r"OOT-\d+ concluded\."))).to_be_visible()
            shots("trend-evaluation-concluded")
            page.goto(chart_url)
            expect(page.get_by_text("No open alert").first).to_be_visible()
        finally:
            browser.close()

    limits = Limits.objects.get()
    assert limits.state == "approved" and limits.rules == ["beyond", "run"]
    evaluation = Evaluation.objects.get()
    assert evaluation.state == "concluded" and evaluation.outcome == "not_confirmed"
    assert [a["test"] for a in evaluation.content["alerts"]] == [alert.pk]
    assert ElectronicSignature.objects.filter(meaning="approved", signer=people["approver"])
    assert ElectronicSignature.objects.filter(meaning="concluded", signer=people["approver"])
    assert errors == []
