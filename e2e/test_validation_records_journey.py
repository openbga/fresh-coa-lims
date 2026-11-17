"""Validation records through the pages, in Chromium: one quality person records an intended
use, another accepts it with a signature, a read-only role sees it, and an administrator
records a rehearsal whose evidence a quality person who did not record it accepts."""

import re

import pytest
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from catalog.tests.factories import PASSWORD, PIN, approved_rules, approved_specification
from catalog.tests.factories import material, person
from core.models import ElectronicSignature
from validation.models import Rehearsal, RehearsalFile

# Elements reaching past the right edge of a phone, outside tables that scroll in their frame.
WIDER_THAN_THE_PAGE = """() => [...document.querySelectorAll('body *')]
  .filter(e => !e.closest('.vr-table-wrap') && e.getBoundingClientRect().right > innerWidth + 0.5)
  .slice(0, 12)
  .map(e => `${e.tagName}.${String(e.className).slice(0, 40)} right=`
    + `${Math.round(e.getBoundingClientRect().right)} `
    + `${e.children.length ? '' : (e.textContent || '').trim().slice(0, 60)}`)"""
EVIDENCE = b"Synthetic restore check report\nAll synthetic checks passed.\n"


@pytest.mark.django_db(transaction=True)
def test_intended_use_and_rehearsal_are_recorded_and_accepted(
    live_server, django_user_model, artifacts
):
    qa_a, qa_b = person("val_qa_a", "quality"), person("val_qa_b", "quality")
    admin, analyst = person("val_admin", "admin"), person("val_analyst", "analyst")
    approved_rules(qa_a)
    approved_specification(qa_a, qa_b, material(qa_a))
    base = live_server.url
    errors, signer = [], None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def login(user):
            page.goto(base + reverse("login"))
            page.get_by_label(re.compile(r"^Username\b")).fill(user.username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(base + "/")

        def sign_out():
            page.get_by_role("button", name="Sign out", exact=True).click()

        def field(label):
            return page.get_by_label(re.compile(r"^" + re.escape(label) + r"(?!\s+link)"))

        def shots(name, known=""):
            page.screenshot(path=str(artifacts / f"{name}-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(artifacts / f"{name}-mobile.png"), full_page=True)
            # `known` names a defect reported separately: its elements are not counted.
            wide = [w for w in page.evaluate(WIDER_THAN_THE_PAGE) if not known or known not in w]
            assert not wide, (name, wide)
            page.set_viewport_size({"width": 1440, "height": 1000})

        def sign(button, reason):
            expect(page.get_by_role("dialog")).to_be_visible()
            field("Signing username").fill(signer)
            field("Signature PIN").fill(PIN)
            field("Reason").fill(reason)
            page.get_by_role("dialog").get_by_role("button", name=button, exact=True).click()

        # 1. Quality user A records an intended use.
        login(qa_a)
        page.get_by_role("link", name="Validation", exact=True).click()
        expect(page.get_by_role("heading", name="Intended use", level=1)).to_be_visible()
        expect(page.get_by_text("No accepted intended use").first).to_be_visible()
        shots("validation-use-list-empty")
        page.get_by_role("link", name=re.compile("New intended use")).first.click()
        field("Title").fill("Synthetic QC release testing")
        field("Intended use").fill("Release testing of synthetic incoming materials.")
        for box in page.get_by_role("checkbox").all():
            box.check()
        owner = f"{qa_a.get_full_name()} ({qa_a.username})"
        field("Process owner").select_option(label=owner)
        field("System owner").select_option(label=owner)
        field("Validation report").fill("VAL-SYN-001 rev 1")
        field("Reason").fill("Synthetic validation completed")
        page.get_by_role("button", name="Record intended use", exact=True).click()
        expect(page).to_have_url(re.compile(r"/validation/intended-use/\d+/$"))
        expect(page.get_by_text(re.compile(r"UA-\d+")).first).to_be_visible()
        expect(page.get_by_text("Awaiting acceptance").first).to_be_visible()
        expect(
            page.get_by_role("heading", name="Approved configuration in force now")
        ).to_be_visible()
        expect(page.get_by_role("link", name="Accept", exact=True)).to_have_count(0)
        use_url = page.url
        shots("validation-use-awaiting")

        # 2. Quality user B accepts with a signature.
        sign_out()
        login(qa_b)
        page.goto(use_url)
        page.get_by_role("link", name="Accept", exact=True).click()
        shots("validation-use-accept")
        signer = qa_b.username
        sign("Sign and accept", "Validation report reviewed")
        expect(page.get_by_text("Accepted", exact=True).first).to_be_visible()
        expect(page.get_by_role("heading", name="Changes since acceptance")).to_be_visible()
        expect(
            page.get_by_role("heading", name="Approved configuration frozen at acceptance")
        ).to_be_visible()
        shots("validation-use-accepted")

        # 3. The analyst only reads.
        sign_out()
        login(analyst)
        page.goto(base + reverse("validation:use_list"))
        expect(page.get_by_text("Current acceptance").first).to_be_visible()
        expect(page.get_by_role("link", name=re.compile("New intended use"))).to_have_count(0)
        shots("validation-use-list-current")

        # 4. The administrator records an upgrade rehearsal and attaches evidence.
        sign_out()
        login(admin)
        page.goto(base + reverse("validation:rehearsal_new"))
        field("Rehearsal of").select_option(label="Upgrade")
        field("Title").fill("Synthetic upgrade rehearsal")
        field("Performed on").fill("2026-11-01")
        field("Environment").fill("Isolated synthetic copy")
        field("Procedure").fill("SOP-SYN-IT-009 rev 1")
        field("Acceptance criteria").fill("Migrations apply and the checks pass.")
        page.get_by_label("Criteria met").check()
        field("Observations").fill("Every synthetic check passed.")
        field("Reason").fill("Synthetic rehearsal")
        page.get_by_role("button", name="Record rehearsal", exact=True).click()
        expect(page.get_by_text("An upgrade names the release before it.")).to_be_visible()
        shots("validation-rehearsal-form-error")
        field("Release before").fill("abc0001")
        page.locator("#id_release").fill("abc0002")
        page.get_by_role("button", name="Record rehearsal", exact=True).click()
        expect(page.get_by_text("Evidence needed").first).to_be_visible()
        rehearsal_url = page.url
        page.get_by_role("link", name="Attach evidence", exact=True).click()
        page.set_input_files(
            "input[type=file]",
            {"name": "restore-check.txt", "mimeType": "text/plain", "buffer": EVIDENCE},
        )
        field("What the file is").fill("Synthetic restore check report")
        page.get_by_role("button", name="Attach file", exact=True).click()
        files = page.locator("section", has=page.get_by_role("heading", name="Evidence files"))
        expect(files).to_contain_text("restore-check.txt")
        with page.expect_download() as download:
            files.get_by_role("link", name="restore-check.txt").click()
        with open(download.value.path(), "rb") as saved:
            assert saved.read() == EVIDENCE
        # Defect: the long info label of the "What a rehearsal record does" notice (nowrap, flex:
        # none, static/css/app.css:757 and :802) squeezes the text into a sliver on a phone.
        shots("validation-rehearsal-recorded")

        # 5. Quality user A, who did not record it, accepts the rehearsal.
        sign_out()
        login(qa_a)
        page.goto(rehearsal_url)
        page.get_by_role("link", name="Accept", exact=True).click()
        shots("validation-rehearsal-accept")
        signer = qa_a.username
        sign("Sign and accept", "Evidence reviewed")
        expect(page.get_by_text("Accepted: criteria met").first).to_be_visible()
        browser.close()

    assert errors == []
    assert ElectronicSignature.objects.filter(object_type="validation.useacceptance").count() == 1
    assert ElectronicSignature.objects.filter(object_type="validation.rehearsal").count() == 1
    assert Rehearsal.objects.get().state == Rehearsal.State.ACCEPTED
    assert RehearsalFile.objects.count() == 1
