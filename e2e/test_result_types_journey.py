"""Qualitative result and a count reported as less than a value, in Chromium."""

import re

import pytest
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_result_types_journey import (
    OBSERVED_ID,
    assign_sample_tests,
)
from tests.test_result_types_journey import world as world  # noqa: F401


@pytest.mark.django_db(transaction=True)
def test_qualitative_and_less_than_count_through_the_forms(live_server, world, artifacts):
    people = world["people"]
    tests = assign_sample_tests(world)
    identity, tamc = tests["identity"], tests["tamc"]
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

        def submit(test):
            page.get_by_label(re.compile(r"^Reason\b")).fill("Synthetic original records complete")
            page.get_by_role("button", name="Submit for review", exact=True).click()
            expect(page.get_by_text("Awaiting review", exact=True)).to_be_visible()

        try:
            login(people["analyst"])
            goto("analytical:observation_new", identity.pk)
            page.get_by_label("Conforms", exact=True).check()
            page.get_by_label(re.compile(r"^What was observed\b")).fill(OBSERVED_ID)
            page.get_by_label(re.compile(r"^Original record\b")).fill("RAW-SYN-RT-BROWSER-1")
            page.get_by_role("button", name="Record observation", exact=True).click()
            expect(page.get_by_text(OBSERVED_ID, exact=True)).to_be_visible()
            submit(identity)

            goto("analytical:observation_new", tamc.pk)
            page.get_by_label(re.compile(r"^Observed count\b")).fill("10")
            page.get_by_label(re.compile(r"^Reported as less than this value")).check()
            page.get_by_label(re.compile(r"^Original record\b")).fill("RAW-SYN-RT-BROWSER-2")
            page.get_by_role("button", name="Record observation", exact=True).click()
            expect(page.get_by_text("<10", exact=True).first).to_be_visible()
            submit(tamc)
            page.get_by_role("button", name="Sign out", exact=True).click()

            login(people["reviewer"])
            for test in (identity, tamc):
                goto("analytical:test_detail", test.pk)
                page.get_by_role("link", name="Sign review", exact=True).click()
                expect(page.get_by_role("dialog")).to_be_visible()
                page.get_by_label(re.compile(r"^Signing username\b")).fill(
                    people["reviewer"].username
                )
                page.get_by_label(re.compile(r"^Signature PIN\b")).fill(PIN)
                page.get_by_label(re.compile(r"^Reason\b")).fill("Independent synthetic review")
                page.get_by_role("button", name="Sign and review", exact=True).click()
                expect(page.get_by_text("Reviewed · conforms", exact=True)).to_be_visible()
            goto("analytical:test_detail", identity.pk)
            expect(page.get_by_text(OBSERVED_ID, exact=True)).to_be_visible()
            expect(page.locator("dd strong", has_text="Conforms").first).to_be_visible()
            goto("analytical:test_detail", tamc.pk)
            expect(page.locator("dd strong", has_text="<10 CFU/g").first).to_be_visible()
            expect(page.locator("td", has_text="<10").first).to_be_visible()
        except Exception:
            page.screenshot(path=str(artifacts / "result-types-failure.png"), full_page=True)
            (artifacts / "result-types-failure.html").write_text(page.content())
            raise
        finally:
            browser.close()

    for test in (identity, tamc):
        test.refresh_from_db()
        assert test.state == "reviewed" and test.conforms
    observation = tamc.current_observations().get()
    assert (observation.qualifier, observation.value_text) == ("<", "<10")
    assert identity.current_observations().get().observed_text == OBSERVED_ID
    assert not errors, errors
