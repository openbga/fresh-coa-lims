"""Results imported from an instrument export through the pages, in Chromium."""

import re

import pytest
from django.urls import reverse
from helpers import expect_form, submit_for_review
from playwright.sync_api import expect, sync_playwright

from analytical.models import Observation, RawDataFile
from tests.test_calculation_bench_journey import assign_water, build_world
from tests.test_instrument_import_journey import FILE_IMPORT, export
from tests.test_integrated_journey import PASSWORD, PIN


@pytest.fixture
def world(django_user_model):
    return build_world(django_user_model, file_import=FILE_IMPORT)


@pytest.mark.django_db(transaction=True)
def test_export_is_attached_checked_recorded_and_reviewed_through_the_pages(
    live_server, world, artifacts
):
    people = world["people"]
    test = assign_water(world)
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

        try:
            login(people["analyst"])
            goto("analytical:test_detail", test.pk)
            expect(page.get_by_text("Synthetic titrator determination export")).to_be_visible()
            page.get_by_role("link", name="Import results", exact=True).click()
            expect_form(page, reverse("analytical:import_new", args=[test.pk]))
            page.get_by_label(re.compile(r"^Instrument export\b")).set_input_files(
                {
                    "name": "kf-run-4.txt",
                    "mimeType": "text/plain",
                    "buffer": export(test.label, "1,25", "1,31"),
                }
            )
            page.get_by_role("button", name="Attach and read", exact=True).click()
            # The page that shows the values read opens in the dialog in its place.
            reading = re.escape(reverse("analytical:import_new", args=[test.pk])) + r"\d+/"
            expect(page.locator("#vr-form-dialog.show [data-vr-form-page]")).to_have_attribute(
                "data-vr-form-url", re.compile(rf"^{reading}$")
            )
            rows = page.locator("table[aria-labelledby='rows-heading'] tbody tr")
            expect(rows).to_have_count(2)
            expect(rows.nth(0)).to_contain_text("1,25")
            expect(rows.nth(1)).to_contain_text("1,31")
            page.screenshot(path=str(artifacts / "instrument-import-check.png"), full_page=True)

            # A missing entered input is refused on the form; nothing is recorded.
            page.get_by_label(re.compile(r"SYN-TITRATOR-01")).check()
            page.get_by_label(re.compile(r"SYN-KF-TITRANT-01")).check()
            page.get_by_label(re.compile(r"^Row 2: Titrant water equivalent\b")).fill("4.98")
            page.get_by_label(re.compile(r"^Row 2: Sample mass\b")).fill("2500.4")
            page.get_by_label(re.compile(r"^Row 3: Titrant water equivalent\b")).fill("4.98")
            page.get_by_label(re.compile(r"^Original record\b")).fill("Titrator memory, run 4")
            record = page.get_by_role("button", name="Record imported results", exact=True)
            record.click()
            expect(page.get_by_text("This field is required.").first).to_be_visible()

            page.get_by_label(re.compile(r"^Row 3: Sample mass\b")).fill("2498.7")
            record.click()
            expect(page).to_have_url(
                live_server.url + reverse("analytical:test_detail", args=[test.pk])
            )
            expect(page.get_by_text("2 replicates imported.")).to_be_visible()
            expect(page.get_by_text("0.25", exact=True).first).to_be_visible()
            expect(page.get_by_text("0.26", exact=True).first).to_be_visible()
            expect(page.get_by_text("Volume (mL) 1,25").first).to_be_visible()
            expect(page.get_by_text("Results imported")).to_be_visible()
            page.screenshot(path=str(artifacts / "instrument-import-recorded.png"), full_page=True)

            submit_for_review(page, "Imported results complete")
            expect(page.get_by_text("Awaiting review", exact=True)).to_be_visible()
            page.get_by_role("button", name="Sign out", exact=True).click()

            login(people["reviewer"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Sign review", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            expect(
                page.get_by_text(re.compile(r"replicate 1 from kf-run-4\.txt row 2"))
            ).to_be_visible()
            expect(
                page.get_by_text(re.compile(r"read again from the stored file: agrees"))
            ).to_be_visible()
            page.get_by_label(re.compile(r"^Signing username\b")).fill(people["reviewer"].username)
            page.get_by_label(re.compile(r"^Signature PIN\b")).fill(PIN)
            page.get_by_label(re.compile(r"^Reason\b")).fill("Rows checked against the titrator")
            page.get_by_role("button", name="Sign and review", exact=True).click()
            expect(page.get_by_text("Reviewed · conforms", exact=True)).to_be_visible()
        except Exception:
            page.screenshot(path=str(artifacts / "instrument-import-failure.png"), full_page=True)
            raise
        finally:
            browser.close()
    assert errors == []
    stored = RawDataFile.objects.get(test=test)
    imported = Observation.objects.filter(test=test, source_file=stored)
    assert sorted(o.source["row"] for o in imported) == [2, 3]
