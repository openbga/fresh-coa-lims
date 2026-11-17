"""A stability pull tested in the system through the pages, as real roles, in Chromium: the
acceptance criteria of the protocol, an out-of-specification result held on the pull and not on
the lot, an authorized retest, independent acceptance and the comparison by time point."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from helpers import pick
from playwright.sync_api import expect, sync_playwright
from test_requirement_replacement_journey import WIDER_THAN_THE_PAGE

from analytical.models import AnalyticalTest, Investigation
from core.services import set_pin
from laboratory.tests.helpers import PASSWORD, PIN, ROLES
from quality.models import Lot, Sample
from stability.models import Protocol, Pull, Study
from stability.tests.helpers import draft_protocol, lot_of, shelf_life

CRITERION = "95 to 105 %"


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
def test_stability_pull_is_tested_in_the_system_and_the_lot_record_is_left_alone(
    live_server, people, artifacts
):
    config = shelf_life(people)
    protocol = draft_protocol(
        people,
        code="SYN-STAB-E2E",
        intervals=(30, 100),
        specification=config["specification"],
        test_codes=("assay",),
    )
    lot = lot_of(people, config["material"])
    before = (lot.revision, lot.state, lot.disposition_evidence)
    start = timezone.localdate() - timedelta(days=100)
    base = live_server.url
    protocol_url = base + reverse("stability:protocol_detail", args=[protocol.pk])
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

        def shots(name, visible=None):
            """Desktop and phone screenshots; on the phone the page must not scroll sideways
            and, when given, the text must lie inside the viewport."""
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                name,
                page.evaluate(WIDER_THAN_THE_PAGE),
            )
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            for text in visible or ():
                box = page.get_by_text(text).first.bounding_box()
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, (name, text, box)
            page.set_viewport_size({"width": 1440, "height": 1000})

        def sign(person, reason, button, label="Reason"):
            # Type only once the signing page has loaded, as the other journeys do: its
            # deferred script moves the form into a dialog and moves the focus.
            expect(field("Signing username")).to_be_visible()
            page.wait_for_load_state()
            field("Signing username").fill(person)
            field("Signature PIN").fill(PIN)
            field(label).fill(reason)
            page.get_by_role("button", name=button, exact=True).click()

        def section(heading):
            return page.locator("section", has=page.get_by_role("heading", name=heading))

        # Quality sees the acceptance criteria that its signature approves.
        login("quality")
        page.goto(protocol_url)
        facts = page.locator("dl.vr-facts > div", has_text="Acceptance criteria")
        expect(facts.first).to_contain_text("syn-shelf-life")
        criteria = section("Acceptance criteria in force")
        expect(criteria).to_contain_text(CRITERION)
        expect(criteria).to_contain_text("assay")
        shots("stability-testing-protocol")
        page.get_by_role("link", name="Approve", exact=True).click()
        expect(page.get_by_text("Acceptance criteria", exact=True).first).to_be_visible()
        sign("quality", "Independent review of the protocol and its criteria", "Sign and approve")
        expect(page.get_by_text("Protocol approved.").first).to_be_visible()
        sign_out()

        # An analyst starts the study, records the 100-day pull and assigns its tests.
        login("analyst")
        page.goto(base + reverse("stability:study_new"))
        field("Identifier").fill("STB-E2E-1")
        pick(field("Approved protocol"), str(protocol.pk))
        pick(field("Lot"), label=lot.number)  # a remote select: chosen by its text
        field("Container and closure").fill("Synthetic marketed container")
        field("Time zero").fill(start.isoformat())
        field("Reason").fill("Synthetic study start")
        page.get_by_role("button", name="Start study", exact=True).click()
        expect(
            page.get_by_text("Study started; pulls are scheduled from time zero.")
        ).to_be_visible()
        study_url = page.url

        def record_pull(days):
            page.goto(study_url)
            page.get_by_role("link", name=re.compile(rf"\b{days} days\b")).first.click()
            url = page.url
            page.get_by_role("link", name="Record pull", exact=True).first.click()
            page.locator("#id_quantity").fill("5")
            page.locator("#id_quantity_unit").fill("g")
            field("Where the pull is held").fill("Synthetic shelf")
            if days < 100:
                # The form proposes today, which is long past the window of the early pull.
                field("Deviation reason").fill("Synthetic late pull")
            field("Reason").fill("Synthetic pull")
            page.get_by_role("button", name="Record pull", exact=True).click()
            return url

        second_url = record_pull(30)
        pull_url = record_pull(100)
        expect(
            page.get_by_text("Pull recorded; assign its tests or link its evidence.")
        ).to_be_visible()
        expect(page.get_by_text("No tests assigned yet")).to_be_visible()
        expect(page.get_by_role("link", name="Assign tests", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Link evidence", exact=True)).to_be_visible()
        page.get_by_role("link", name="Assign tests", exact=True).click()
        assign_table = page.locator("table").first
        expect(assign_table).to_contain_text(CRITERION)
        expect(assign_table).to_contain_text("syn-shelf-assay revision 1")
        expect(page.get_by_text("syn-shelf-life", exact=False).first).to_be_visible()
        shots("stability-testing-assign", visible=[CRITERION])
        field("Reason").fill("Tests of the 100 day time point")
        page.get_by_role("button", name="Assign tests", exact=True).click()
        expect(page.get_by_text("Assigned 1 test(s) to the pull.")).to_be_visible()
        sign_out()

        # A qualified second analyst records an out-of-specification result.
        login("analyst2")
        page.goto(pull_url)
        shots("stability-testing-pull-open")
        page.get_by_role("link", name=re.compile(r"assay")).first.click()
        test_url = page.url
        notice = page.get_by_role("status").filter(has_text="Stability test")
        expect(notice).to_contain_text("100 days")
        expect(notice).to_contain_text("is not part of the record of lot")
        shots("stability-testing-test")
        page.get_by_role("link", name="Record observation", exact=True).click()
        field("Observed value").fill("91.0")
        field("Original record").fill("NB-STB-E2E p1")
        page.get_by_role("button", name="Record observation", exact=True).click()
        expect(page.get_by_text("Observation recorded.").first).to_be_visible()
        field("Reason").fill("Original records complete")
        page.get_by_role("button", name="Submit for review", exact=True).click()
        expect(page).to_have_url(re.compile(r"/investigations/\d+/$"))
        investigation_url = page.url
        expect(page.get_by_text("Pull held").first).to_be_visible()
        expect(page.get_by_role("status").filter(has_text="Pull held")).to_contain_text(
            "record of lot SYN-STB-LOT-1 is not changed"
        )
        shots("stability-testing-investigation")
        sign_out()

        # An independent reviewer signs the failing test; the pull cannot be accepted yet.
        login("reviewer2")
        page.goto(test_url)
        page.get_by_role("link", name="Sign review", exact=True).click()
        sign("reviewer2", "Raw data checked", "Sign and review")
        expect(page.get_by_text("Out of specification · reviewed").first).to_be_visible()
        sign_out()
        login("reviewer")
        accept_url = pull_url + "accept/"
        response = page.goto(accept_url)
        assert response.status == 403
        expect(page.get_by_text("Testing is not complete").first).to_be_visible()
        expect(page.get_by_label(re.compile(r"^Signature PIN\b"))).to_have_count(0)
        sign_out()

        # The laboratory assessment, then quality authorizes a retest of the material pulled.
        login("analyst2")
        page.goto(investigation_url)
        page.get_by_role("link", name="Record entry", exact=True).click()
        page.get_by_role("textbox", name=re.compile(r"^Entry\b")).fill(
            "No laboratory error found; the original is confirmed to be genuine"
        )
        page.get_by_role("button", name="Record entry", exact=True).click()
        expect(page.get_by_text("Investigation entry recorded.")).to_be_visible()
        sign_out()
        login("quality")
        page.goto(investigation_url)
        page.get_by_role("link", name="Authorize retest", exact=True).click()
        expect(page.get_by_text("Retest of the material that was pulled")).to_be_visible()
        expect(page.get_by_role("radio")).to_have_count(1)
        expect(page.get_by_text("Resample:")).to_have_count(0)
        expect(page.get_by_label(re.compile(r"^New sample"))).to_have_count(0)
        sign("quality", "Retest the pulled material once", "Sign and authorize", "Scientific")
        expect(
            page.get_by_text("Retest authorized; the linked test is ready to record.")
        ).to_be_visible()
        sign_out()

        login("analyst2")
        page.goto(investigation_url)
        retest_link = page.locator("table a.vr-id").nth(1)
        retest_link.click()
        retest_url = page.url
        page.get_by_role("link", name="Record observation", exact=True).click()
        field("Observed value").fill("99.4")
        field("Original record").fill("NB-STB-E2E p2")
        page.get_by_role("button", name="Record observation", exact=True).click()
        field("Reason").fill("Retest records complete")
        page.get_by_role("button", name="Submit for review", exact=True).click()
        expect(page.get_by_text("Awaiting review").first).to_be_visible()
        sign_out()
        login("reviewer2")
        page.goto(retest_url)
        page.get_by_role("link", name="Sign review", exact=True).click()
        sign("reviewer2", "Retest raw data checked", "Sign and review")
        expect(page.get_by_text("Reviewed · conforms").first).to_be_visible()
        sign_out()

        # A different quality person concludes: the original result is invalidated.
        login("quality2")
        page.goto(investigation_url)
        page.get_by_role("link", name="Conclude", exact=True).click()
        page.get_by_label("Invalidated", exact=False).first.check()
        field("Assignable laboratory cause").fill("Synthetic: sample preparation dilution error")
        sign(
            "quality2",
            "Original invalidated for the documented cause",
            "Sign conclusion",
            "Conclusion",
        )
        expect(page.get_by_text("concluded.").first).to_be_visible()
        sign_out()

        # An independent reviewer accepts the pull against the criterion.
        login("reviewer")
        page.goto(accept_url)
        results = page.locator("dl.vr-facts")
        expect(results).to_contain_text(f"99.4 % against {CRITERION}")
        outcome = results.locator("div", has_text="Outcome recorded with your signature").last
        expect(outcome).to_contain_text("Meets the acceptance criteria")
        shots("stability-testing-accept")
        sign("reviewer", "Pull and results reviewed", "Sign and review")
        expect(page.get_by_text("Pull accepted.").first).to_be_visible()
        expect(page).to_have_url(pull_url)
        expect(page.locator("dl.vr-facts")).to_contain_text("Meets the acceptance criteria")
        tests = section("Tests")
        expect(tests).to_contain_text("99.4")
        expect(tests).to_contain_text(CRITERION)
        expect(tests).to_contain_text("Accepted: meets the acceptance criteria")
        expect(page.get_by_text("Signatures").first).to_be_visible()
        shots("stability-testing-pull-accepted", visible=["99.4"])

        # The study compares results by condition and time point.
        page.goto(study_url)
        results = section("Results · Long-term")
        expect(results).to_be_visible()
        # Time points are rows and tests are columns, the criterion in the column heading.
        expect(results.locator("thead")).to_contain_text(CRITERION)
        row = results.locator("tbody tr", has_text="100 days")
        expect(row).to_contain_text("99.4")
        # On a phone the result is in view without scrolling the table sideways.
        shots("stability-testing-study", visible=["99.4", CRITERION])
        sign_out()

        # Role boundaries: an auditor reads the pull and is offered no action.
        login("auditor")
        page.goto(pull_url)
        expect(page.get_by_role("heading", name="Tests", exact=True)).to_be_visible()
        for name in ("Assign tests", "Accept pull", "Link evidence", "Record pull"):
            expect(page.get_by_role("link", name=name, exact=True)).to_have_count(0)
        response = page.goto(second_url + "tests/")
        assert response.status == 403
        sign_out()

        browser.close()

    assert errors == []
    lot = Lot.objects.get(pk=lot.pk)
    assert (lot.revision, lot.state, lot.disposition_evidence) == before
    assert not AnalyticalTest.objects.filter(lot=lot).exists()
    assert not Investigation.objects.filter(lot=lot).exists()
    assert not Sample.objects.filter(lot=lot).exists()
    study = Study.objects.get(identifier="STB-E2E-1")
    pull = study.pulls.get(timepoint__interval_days=100)
    assert pull.state == Pull.State.ACCEPTED and pull.outcome == Pull.Outcome.CONFORMS
    assert pull.tests.count() == 2
    assert Protocol.objects.get(pk=protocol.pk).state == Protocol.State.APPROVED
