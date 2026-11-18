"""A balance fails after a lot was released and its certificate issued: a quality person starts
an impact assessment from the balance's page, the system finds the test, the lot and the
certificate, quality decides on each and holds the lot, the certificate is withdrawn with a
signature and its recipient's notification recorded, and another quality person concludes the
assessment, in Chromium."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import PASSWORD, expect_form, field, fill_signature, pick, submit_signed
from playwright.sync_api import expect, sync_playwright

from impact.models import Assessment, Item
from reporting.models import Report
from tests.test_impact_assessment import released, reviewed_world, used

WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)}`)"""


def open_session(playwright, base, width=1440, height=1000):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": height})

    def login(username):
        page.goto(base + reverse("login"))
        page.get_by_label(re.compile(r"^Username\b")).fill(username)
        page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(base + "/")

    return browser, page, login


def decide(page, base, item, decision, rationale, follow_up=""):
    page.goto(base + reverse("impact:decide", args=[item.pk]))
    page.get_by_label(decision, exact=True).check()
    field(page, "Reason for the decision").fill(rationale)
    if follow_up:
        field(page, "Follow-up").fill(follow_up)
    page.get_by_role("button", name="Record decision", exact=True).click()
    expect(page.get_by_text("Decision recorded for").first).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_a_failure_after_release_is_assessed_and_its_certificate_withdrawn(
    live_server, django_user_model, artifacts
):
    world = released(reviewed_world(django_user_model))
    used(world, world["tests"]["impurity"], world["balance"])
    base = live_server.url
    balance, lot, report = world["balance"], world["lot"], world["report"]
    today = timezone.localdate()
    errors = []

    # The ORM is not called while Playwright's event loop runs: each session closes first.
    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("rt_author")
        page.goto(base + reverse("laboratory:equipment_detail", args=[balance.pk]))
        page.get_by_role("button", name="More").click()
        page.get_by_role("link", name="Assess impact", exact=True).click()
        expect_form(page, base + reverse("impact:new"))
        field(page, "Problem").fill("Balance out of tolerance at the weekly check")
        field(page, "What happened").fill("Synthetic: the 100 g check weight read 100.6 g.")
        field(page, "Period of concern from").fill((today - timedelta(days=7)).isoformat())
        field(page, "Quality-system reference").fill("DEV-SYN-0042")
        page.get_by_role("button", name="Start assessment", exact=True).click()
        expect(page).to_have_url(re.compile(r"/impact/\d+/$"))
        detail_url = page.url
        expect(page.get_by_text("record(s) found from the cause").first).to_be_visible()
        for heading in ("Tests", "Lots", "Certificates"):
            expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
        page.screenshot(path=str(artifacts / "impact-started-desktop.png"), full_page=True)
        browser.close()

    assessment = Assessment.objects.get()
    items = {item.kind: item for item in assessment.items.all()}
    assert set(items) == {Item.Kind.TEST, Item.Kind.LOT, Item.Kind.CERTIFICATE}

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("rt_author")
        decide(
            page,
            base,
            items[Item.Kind.TEST],
            "Affected",
            "Weighed on the balance during the period",
            "Withdraw the certificate; retest under an investigation",
        )
        decide(page, base, items[Item.Kind.LOT], "Affected", "Its impurity result", "Held")
        decide(
            page,
            base,
            items[Item.Kind.CERTIFICATE],
            "Affected",
            "States the affected result",
            "Withdrawn",
        )
        page.goto(detail_url)
        lots = page.locator("section", has=page.get_by_role("heading", name="Lots", exact=True))
        lots.get_by_role("link", name="Place hold", exact=True).click()
        expect_form(page, base + reverse("impact:hold", args=[items[Item.Kind.LOT].pk]))
        field(page, "Why the lot is held").fill("Hold until the impurity is retested")
        page.get_by_role("button", name="Place hold", exact=True).click()
        expect(page).to_have_url(detail_url)
        expect(lots).to_contain_text("HOLD-")
        # The starter and decider cannot conclude it.
        expect(page.get_by_text("another quality person concludes it")).to_be_visible()

        # Withdraw the certificate from its own page and record that its recipient was told.
        page.goto(base + reverse("reporting:withdraw", args=[report.pk]))
        fill_signature(page, "rt_author", reason="Its impurity result is not reliable")
        assert submit_signed(page, "Sign and withdraw") in (200, 302)
        page.goto(base + reverse("reporting:detail", args=[report.pk]))
        expect(page.locator(".vr-page-meta").get_by_text("Withdrawn", exact=True)).to_be_visible()
        page.goto(base + reverse("reporting:notify", args=[report.pk]))
        field(page, "Date notified").fill(today.isoformat())
        pick(field(page, "Means"), "email")
        field(page, "Evidence reference").fill("Email to the customer, DMS-SYN-0042")
        page.get_by_role("button", name="Record notification", exact=True).click()
        expect(page).to_have_url(base + reverse("reporting:detail", args=[report.pk]))
        page.screenshot(path=str(artifacts / "impact-certificate-withdrawn.png"), full_page=True)
        browser.close()

    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base)
        page.on("pageerror", lambda error: errors.append(str(error)))
        login("rt_approver")
        page.goto(detail_url)
        page.get_by_role("link", name="Conclude", exact=True).click()
        expect_form(page, base + reverse("impact:conclude", args=[assessment.pk]))
        fill_signature(page, "rt_approver", reason="Impact assessed; follow-up recorded")
        assert submit_signed(page, "Sign and conclude") in (200, 302)
        expect(page).to_have_url(detail_url)
        expect(page.locator(".vr-page-meta").get_by_text("Concluded", exact=True)).to_be_visible()
        page.screenshot(path=str(artifacts / "impact-concluded-desktop.png"), full_page=True)
        page.goto(base + reverse("quality:lot_detail", args=[lot.pk]))
        panel = page.locator("section", has=page.get_by_role("heading", name="Impact assessments"))
        expect(panel).to_contain_text(assessment.label)
        expect(panel).to_contain_text("Affected")
        browser.close()

    assert not errors, errors
    assessment.refresh_from_db()
    assert assessment.state == "concluded" and assessment.evidence["affected"] == 3
    assert Report.objects.get(pk=report.pk).state == "withdrawn"


@pytest.mark.django_db(transaction=True)
def test_the_impact_pages_fit_a_phone(live_server, django_user_model, artifacts):
    world = reviewed_world(django_user_model)
    used(world, world["tests"]["impurity"], world["balance"])
    from tests.test_impact_assessment import begin

    assessment = begin(world)
    item = assessment.items.get(kind=Item.Kind.LOT)
    base = live_server.url
    with sync_playwright() as playwright:
        browser, page, login = open_session(playwright, base, width=390, height=844)
        login("rt_author")
        for name, url in (
            ("list", reverse("impact:list")),
            ("detail", reverse("impact:detail", args=[assessment.pk])),
            ("decide", reverse("impact:decide", args=[item.pk])),
            ("new", reverse("impact:new")),
        ):
            page.goto(base + url)
            page.screenshot(path=str(artifacts / f"impact-{name}-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                page.evaluate(WIDER_THAN_THE_PAGE)
            )
        browser.close()
