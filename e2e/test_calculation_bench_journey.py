"""Calculated result, bench checks and a raw-data file through the forms, in Chromium."""

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from analytical.models import RawDataFile
from tests.test_calculation_bench_journey import (
    FORMULA,
    REPLICATES,
    assign_water,
    calibrate,
)
from tests.test_calculation_bench_journey import world as world  # noqa: F401
from tests.test_integrated_journey import PASSWORD, PIN


def run_in_thread(function, *args):
    """Run database setup outside the sync Playwright event loop, closing its connection."""
    from django.db import connection

    try:
        return function(*args)
    finally:
        connection.close()


PAYLOAD = b"replicate,titrant_volume_mL\n1,1.25\n2,1.31\n"
INPUT_LABELS = {
    "titrant_volume": "Titrant volume",
    "titer": "Titrant water equivalent",
    "sample_mass": "Sample mass",
}


@pytest.mark.django_db(transaction=True)
def test_calculated_result_with_bench_checks_and_raw_data_through_the_forms(
    live_server, world, artifacts
):
    people = world["people"]
    test = assign_water(world)
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page.on("pageerror", lambda error: errors.append(str(error)))

        def goto(name, *args):
            page.goto(live_server.url + reverse(name, args=args))

        def login(person):
            goto("login")
            page.get_by_label(re.compile(r"^Username\b")).fill(person.username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(live_server.url + "/")

        def fill_inputs(inputs):
            for code, label in INPUT_LABELS.items():
                page.get_by_label(re.compile(rf"^{label}\b")).fill(inputs[code])

        def fill_original_record(text):
            page.get_by_label(re.compile(r"^Original record\b")).fill(text)

        def record_button():
            return page.get_by_role("button", name="Record observation", exact=True)

        try:
            login(people["analyst"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Record observation", exact=True).click()
            expect(page).to_have_url(
                live_server.url + reverse("analytical:observation_new", args=[test.pk])
            )

            # The form asks for the approved inputs and offers no directly entered value.
            for label in INPUT_LABELS.values():
                expect(page.get_by_label(re.compile(rf"^{label}\b"))).to_be_visible()
            expect(page.get_by_label(re.compile(r"^Observed value\b"))).to_have_count(0)
            fill_inputs(REPLICATES[0])
            page.get_by_label(re.compile(r"SYN-TITRATOR-01")).check()
            page.get_by_label(re.compile(r"SYN-KF-TITRANT-01")).check()
            fill_original_record("RAW-SYN-CB-BROWSER-1")
            record_button().click()
            expect(page).to_have_url(
                live_server.url + reverse("analytical:test_detail", args=[test.pk])
            )
            expect(page.get_by_text("0.25", exact=True).first).to_be_visible()
            expect(page.get_by_text(FORMULA).first).to_be_visible()
            expect(page.get_by_text("2500.4").first).to_be_visible()
            expect(page.get_by_text("SYN-TITRATOR-01").first).to_be_visible()
            expect(page.get_by_text("SYN-KF-TITRANT-01").first).to_be_visible()
            page.screenshot(path=str(artifacts / "calculation-bench-recorded.png"), full_page=True)

            # No instrument ticked: refused on the form, nothing stored.
            goto("analytical:observation_new", test.pk)
            fill_inputs(REPLICATES[1])
            page.get_by_label(re.compile(r"SYN-KF-TITRANT-01")).check()
            fill_original_record("RAW-SYN-CB-BROWSER-REFUSED")
            record_button().click()
            expect(
                page.get_by_text(re.compile(r"requires one|requires at least one")).first
            ).to_be_visible()
            expect(page).to_have_url(
                live_server.url + reverse("analytical:observation_new", args=[test.pk])
            )
            expect(record_button()).to_be_visible()

            # Second replicate.
            goto("analytical:observation_new", test.pk)
            fill_inputs(REPLICATES[1])
            page.get_by_label(re.compile(r"SYN-TITRATOR-01")).check()
            page.get_by_label(re.compile(r"SYN-KF-TITRANT-01")).check()
            fill_original_record("RAW-SYN-CB-BROWSER-2")
            record_button().click()
            expect(page.get_by_text("0.26", exact=True).first).to_be_visible()

            # Raw-data file.
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Attach raw data", exact=True).click()
            page.get_by_label(re.compile(r"^File\b")).set_input_files(
                {"name": "titration-run-1.csv", "mimeType": "text/csv", "buffer": PAYLOAD}
            )
            page.get_by_label(re.compile(r"^What the file is\b")).fill("Synthetic titration export")
            page.get_by_role("button", name="Attach file", exact=True).click()
            expect(page.get_by_role("cell", name="titration-run-1.csv")).to_be_visible()

            # Submit, then review as the independent reviewer.
            page.get_by_label(re.compile(r"^Reason\b")).fill("Synthetic original records complete")
            page.get_by_role("button", name="Submit for review", exact=True).click()
            expect(page.get_by_text("Awaiting review", exact=True)).to_be_visible()
            page.get_by_role("button", name="Sign out", exact=True).click()

            login(people["reviewer"])
            goto("analytical:test_detail", test.pk)
            with page.expect_download() as download_info:
                page.get_by_role(
                    "link", name=re.compile(r"^Download\b.*titration-run-1\.csv")
                ).click()
            downloaded = download_info.value
            assert downloaded.suggested_filename == "titration-run-1.csv"
            with open(downloaded.path(), "rb") as handle:
                assert handle.read() == PAYLOAD
            page.get_by_role("link", name="Sign review", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            page.get_by_label(re.compile(r"^Signing username\b")).fill(people["reviewer"].username)
            page.get_by_label(re.compile(r"^Signature PIN\b")).fill(PIN)
            page.get_by_label(re.compile(r"^Reason\b")).fill("Independent synthetic review")
            page.get_by_role("button", name="Sign and review", exact=True).click()
            expect(page.get_by_text("Reviewed · conforms", exact=True)).to_be_visible()

            # A failed calibration afterwards lists the test on the equipment page.
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(run_in_thread, calibrate, people, world["equipment"], "fail").result()
            goto("laboratory:equipment_detail", world["equipment"].pk)
            link = page.get_by_role("link", name=re.compile(rf"^{re.escape(test.label)}\b"))
            expect(link.first).to_be_visible()
            link.first.click()
            expect(page).to_have_url(
                live_server.url + reverse("analytical:test_detail", args=[test.pk])
            )
        except Exception:
            page.screenshot(path=str(artifacts / "calculation-bench-failure.png"), full_page=True)
            (artifacts / "calculation-bench-failure.html").write_text(page.content())
            raise
        finally:
            browser.close()

    test.refresh_from_db()
    assert test.state == "reviewed" and test.conforms
    observations = list(test.current_observations().order_by("replicate"))
    assert [o.value for o in observations] == [Decimal("0.25"), Decimal("0.26")]
    for observation, replicate in zip(observations, REPLICATES, strict=True):
        assert {i["code"]: i["value"] for i in observation.inputs} == replicate
        assert [e["asset_id"] for e in observation.eligibility["equipment"]] == ["SYN-TITRATOR-01"]
        assert [r["identifier"] for r in observation.eligibility["reagents"]] == [
            "SYN-KF-TITRANT-01"
        ]
    stored = RawDataFile.objects.get(test=test)
    assert stored.filename == "titration-run-1.csv"
    assert stored.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert bytes(stored.content) == PAYLOAD
    assert not errors, errors
