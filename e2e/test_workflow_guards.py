"""Browser regressions for native disposition, production entry and session boundaries."""

import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from django.db import connections
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from analytical import gates
from analytical import services as analytical
from core.models import AuditEvent, ElectronicSignature
from quality import services as quality
from quality.models import Result
from sampling import services as sampling
from stability import services as stability
from tests.test_integrated_journey import PASSWORD, PIN, assign_and_sample, observed_test
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
ARTIFACTS = Path(".local/qa")


@contextmanager
def browser_page():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        yield page
        browser.close()


def login(page, live_server, person):
    page.goto(live_server.url + reverse("login"))
    page.get_by_label(re.compile(r"^Username\b")).fill(person.username)
    page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page).to_have_url(live_server.url + "/")


def ready_test(data, sample):
    test, investigation = observed_test(data, sample, "100.25")
    assert investigation is None
    test = analytical.review_test(
        actor=data["people"]["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent browser-guard fixture review",
    )
    assert test.state == "reviewed" and test.conforms
    assert gates.lot_blockers(data["lot"]) == []
    return test


def record_state(lot):
    lot.refresh_from_db()
    return {
        "state": lot.state,
        "revision": lot.revision,
        "signatures": ElectronicSignature.objects.count(),
        "lot_events": AuditEvent.objects.filter(
            object_type="quality.lot", object_id=str(lot.pk)
        ).count(),
        "results": Result.objects.filter(sample__lot=lot).count(),
    }


def open_disposition(page, live_server, data):
    actor = data["people"]["approver"]
    login(page, live_server, actor)
    page.goto(live_server.url + reverse("quality:disposition", args=[data["lot"].pk]))
    expect(page.get_by_role("dialog")).to_be_visible()
    page.get_by_label(re.compile(r"^Signing username\b")).fill(actor.username)
    page.get_by_label(re.compile(r"^Signature PIN\b")).fill(PIN)
    page.get_by_label(re.compile(r"^Reason\b")).fill("Independent synthetic disposition attempt")


def submit_disposition(page, lot):
    path = reverse("quality:disposition", args=[lot.pk])
    with page.expect_response(
        lambda response: urlsplit(response.url).path == path and response.request.method == "POST"
    ) as response:
        page.get_by_role("button", name="Sign approved", exact=True).click()
    return response.value.status


def test_disposition_rejects_missing_sampling_provenance(live_server, integrated):
    data = integrated
    sampling.assign_requirements(
        actor=data["people"]["analyst"],
        lot=data["lot"],
        material=data["material"],
        stage="incoming",
        reason="Approved requirements without sampling evidence",
    )
    sample = quality.add_sample(
        actor=data["people"]["analyst"],
        lot=data["lot"],
        reference="SYN-NO-PROVENANCE",
        collected_at=timezone.now(),
        reason="Basic sample receipt is not sampling-plan evidence",
    )
    ready_test(data, sample)
    before = record_state(data["lot"])
    with browser_page() as page:
        open_disposition(page, live_server, data)
        status = submit_disposition(page, data["lot"])
        expect(page.get_by_role("dialog")).to_contain_text("no sampling record")
        page.screenshot(path=str(ARTIFACTS / "guard-missing-sampling.png"), full_page=True)
        assert status == 422
    assert record_state(data["lot"]) == before
    assert before["state"] == "quarantine"


def test_disposition_rejects_active_hold(live_server, integrated):
    data = integrated
    ready_test(data, assign_and_sample(data))
    hold = stability.place_hold(
        actor=data["people"]["analyst"],
        lot=data["lot"],
        kind="quality",
        reason="Synthetic unresolved supplier discrepancy",
    )
    before = record_state(data["lot"])
    with browser_page() as page:
        open_disposition(page, live_server, data)
        status = submit_disposition(page, data["lot"])
        expect(page.get_by_role("dialog")).to_contain_text("hold) is active")
        expect(page.get_by_role("dialog")).to_contain_text(hold.identifier)
        page.screenshot(path=str(ARTIFACTS / "guard-active-hold.png"), full_page=True)
        assert status == 422
    assert record_state(data["lot"]) == before
    hold.refresh_from_db()
    assert hold.state == "active"


def test_manual_result_rejected_outside_debug(live_server, integrated, settings):
    data = integrated
    sample = quality.add_sample(
        actor=data["people"]["analyst"],
        lot=data["lot"],
        reference="SYN-MANUAL-PRODUCTION",
        collected_at=timezone.now(),
        reason="Unassigned synthetic sample",
    )
    assert not data["lot"].qc_assignments.exists(), "Prove DEBUG gate independently of assignments"
    settings.DEBUG = False
    # Local HTTP transport settings were initialized from DEBUG=true at process startup.
    assert settings.SECURE_SSL_REDIRECT is False
    before = record_state(data["lot"])
    with browser_page() as page:
        login(page, live_server, data["people"]["analyst"])
        path = reverse("quality:result_new", args=[sample.pk])
        page.goto(live_server.url + path)
        for label, value in [
            ("Test code", "assay"),
            ("Value", "100"),
            ("Unit", "%"),
            ("Lower limit", "98"),
            ("Upper limit", "102"),
            ("Reason", "Synthetic production manual-entry attempt"),
        ]:
            page.get_by_label(re.compile(r"^" + label + r"\b")).fill(value)
        with page.expect_response(
            lambda response: (
                urlsplit(response.url).path == path and response.request.method == "POST"
            )
        ) as response:
            page.get_by_role("button", name="Record result", exact=True).click()
        expect(
            page.get_by_text(
                "Record observations through approved native testing requirements.", exact=True
            )
        ).to_be_visible()
        page.screenshot(path=str(ARTIFACTS / "guard-manual-production.png"), full_page=True)
        assert response.value.status == 422
    assert record_state(data["lot"]) == before
    assert not Result.objects.filter(sample=sample).exists()


@pytest.mark.parametrize(
    "expired_clock", ["last_activity_at", "authenticated_at"], ids=["idle", "absolute"]
)
def test_expired_session_cannot_sign(live_server, integrated, settings, expired_clock):
    data = integrated
    settings.SESSION_IDLE_SECONDS = 60
    settings.SESSION_ABSOLUTE_SECONDS = 120
    ready_test(data, assign_and_sample(data))
    before = record_state(data["lot"])
    with browser_page() as page:
        open_disposition(page, live_server, data)
        cookies = {cookie["name"]: cookie["value"] for cookie in page.context.cookies()}
        session_key = cookies[settings.SESSION_COOKIE_NAME]

        def expire_session():
            try:
                session = import_module(settings.SESSION_ENGINE).SessionStore(
                    session_key=session_key
                )
                now = timezone.now().timestamp()
                # Expire one clock only; keep the other recent to isolate idle vs absolute expiry.
                session["authenticated_at"] = now
                session["last_activity_at"] = now
                session[expired_clock] = now - 121
                session.save()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(expire_session).result()
        status = submit_disposition(page, data["lot"])
        expect(page).to_have_url(re.compile(r"/accounts/login/\?next="))
        expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
        expect(
            page.get_by_text("Your session expired. Sign in again to continue.", exact=True)
        ).to_be_visible()
        page.screenshot(path=str(ARTIFACTS / f"guard-session-{expired_clock}.png"), full_page=True)
        assert status == 302
    assert record_state(data["lot"]) == before
    assert (
        AuditEvent.objects.filter(
            actor=data["people"]["approver"], action="session.expired"
        ).count()
        == 1
    )
    assert (
        not import_module(settings.SESSION_ENGINE)
        .SessionStore(session_key=session_key)
        .get("_auth_user_id")
    )
