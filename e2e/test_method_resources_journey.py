"""Suitable instruments and lots of a method version, in Chromium: quality lists the titrator and
the titrant on a draft version, sees each beside the register, another quality person approves
the version, and the analyst recording a result under it is offered only what it lists."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import expect_form, pick
from helpers import field as labelled
from playwright.sync_api import expect, sync_playwright

from analytical.models import Observation
from catalog import services as catalog
from catalog.models import MethodRevision
from laboratory import services as laboratory
from tests.test_calculation_bench_journey import (
    REPLICATES,
    assign_water,
    calibrate,
)
from tests.test_calculation_bench_journey import world as world  # noqa: F401
from tests.test_integrated_journey import PASSWORD, PIN

INPUT_LABELS = {
    "titrant_volume": "Titrant volume",
    "titer": "Titrant water equivalent",
    "sample_mass": "Sample mass",
}


def run_in_thread(function, *args):
    """Run database setup outside the sync Playwright event loop, closing its connection."""
    from django.db import connection

    try:
        return function(*args)
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_suitable_resources_listed_approved_and_offered_at_the_bench(live_server, world, artifacts):
    people = world["people"]
    balance = laboratory.register_equipment(
        actor=people["analyst"],
        asset_id="SYN-BAL-09",
        description="Synthetic balance",
        category="Balance",
        location="Synthetic laboratory",
        requires_qualification=False,
        reason="Synthetic equipment",
    )
    calibrate(people, balance)
    draft = catalog.new_method_revision(
        actor=people["author"],
        method=world["method"],
        technique="Titration",
        document_ref="SOP-SYN-KF rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-KF rev 1",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=365),
        reason="List the suitable instrument and titrant",
    )
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
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

        def add_line(name, *, required=True):
            page.get_by_role("link", name="Add suitable resource to version 2").click()
            expect_form(page, reverse("catalog:method_resource_new", args=[draft.pk]))
            pick(field("Name in the register"), label=name)
            if not required:
                field("Recorded with every result").uncheck()
            field("Reason for change").fill("Validated with it")
            page.get_by_role("button", name="Add suitable resource", exact=True).click()
            expect(page.get_by_text(re.compile(rf"{name} listed as suitable"))).to_be_visible()

        def shots(name):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        try:
            # The author lists the titrator by its category and the titrant by its name.
            login(people["author"])
            goto("catalog:method", world["method"].pk)
            add_line("titrator")
            add_line("Synthetic titrant")
            table = page.get_by_role("table", name=re.compile("Suitable instruments.*v2"))
            expect(table.get_by_role("link", name="SYN-TITRATOR-01")).to_be_visible()
            expect(table.get_by_role("link", name="SYN-KF-TITRANT-01")).to_be_visible()
            expect(table.get_by_text("SYN-BAL-09")).to_have_count(0)
            expect(table.get_by_text("Recorded with every result")).to_have_count(2)
            shots("method-resources-draft")
            sign_out()

            # Another quality person approves the version; the lines are part of what is signed.
            login(people["approver"])
            goto("catalog:method", world["method"].pk)
            page.get_by_role("link", name=re.compile("^Review and approve")).click()
            approving = page.get_by_role("dialog")
            expect(
                approving.get_by_role("table", name=re.compile("Suitable instruments.*v2"))
            ).to_contain_text("Synthetic titrant")
            field("Approval comment").fill("Procedure and suitable resources checked")
            field("Signing username").fill(people["approver"].username)
            field("Signature PIN").fill(PIN)
            page.get_by_role("button", name="Sign and approve", exact=True).click()
            expect(page.get_by_text("approved and signed")).to_be_visible()
            sign_out()

            with ThreadPoolExecutor(max_workers=1) as pool:
                test = pool.submit(run_in_thread, assign_water, world).result()

            # The analyst is offered only the listed instrument and lot.
            login(people["analyst"])
            goto("analytical:observation_new", test.pk)
            expect(page.get_by_label(re.compile(r"SYN-TITRATOR-01"))).to_be_visible()
            expect(page.get_by_label(re.compile(r"SYN-BAL-09"))).to_have_count(0)
            for code, label in INPUT_LABELS.items():
                page.get_by_label(re.compile(rf"^{label}\b")).fill(REPLICATES[0][code])
            page.get_by_label(re.compile(r"SYN-TITRATOR-01")).check()
            page.get_by_label(re.compile(r"SYN-KF-TITRANT-01")).check()
            page.get_by_label(re.compile(r"^Original record\b")).fill("RAW-SYN-SR-1")
            shots("method-resources-bench")
            page.get_by_role("button", name="Record observation", exact=True).click()
            expect(page).to_have_url(
                live_server.url + reverse("analytical:test_detail", args=[test.pk])
            )
            expect(page.get_by_text("0.25", exact=True).first).to_be_visible()
        finally:
            browser.close()

    version = MethodRevision.objects.get(pk=draft.pk)
    assert version.status == "approved"
    assert [line["name"] for line in version.approved_content["resources"]] == [
        "titrator",
        "Synthetic titrant",
    ]
    (observation,) = Observation.objects.filter(test=test)
    assert observation.eligibility["equipment"][0]["suitable_as"] == "titrator"
    assert errors == []
