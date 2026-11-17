"""Where a lot is (quality/route.py): stages derived from recorded data only, and the lot list
gets them from its one annotated query (no query per row)."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from core.models import RuleSet
from quality.models import Lot
from quality.route import stages, summary

pytestmark = pytest.mark.django_db


def states(route):
    return [stage["state"] for stage in route]


def counts(**changes):
    values = {
        "state": "quarantine",
        "assignment": "ready",
        "samples": 2,
        "tests": 6,
        "entered": 3,
        "reviewed": 0,
        "issued": False,
        "investigation_open": False,
    }
    values.update(changes)
    return stages(**values)


def test_results_in_progress_shows_its_share():
    route = counts()
    assert states(route) == ["done", "done", "current", "pending", "pending", "pending"]
    assert route[2]["progress"] == 50 and summary(route) == "3 of 6 entered"


def test_unassigned_lot_starts_at_the_requirements():
    route = counts(assignment="", samples=0, tests=0, entered=0)
    assert states(route)[0] == "current" and summary(route) == "Not assigned"
    assert set(states(route)[1:]) == {"pending"}


def test_applicability_hold_and_open_investigation_are_held():
    assert counts(assignment="hold")[0]["state"] == "held"
    route = counts(entered=6, reviewed=5, investigation_open=True)
    assert states(route)[3] == "held" and route[3]["progress"] == 80


def test_decisions_and_certificate():
    released = counts(state="released", entered=6, reviewed=6)
    assert states(released) == ["done"] * 5 + ["current"]
    assert summary(released) == "Not issued"
    issued = counts(state="released", entered=6, reviewed=6, issued=True)
    assert states(issued) == ["done"] * 6 and summary(issued) == "Certificate issued"
    rejected = counts(state="rejected")
    assert rejected[4]["state"] == "rejected" and summary(rejected) == "Rejection signed"
    cancelled = counts(state="cancelled")
    assert set(states(cancelled)) == {"pending"} and summary(cancelled) == "Received in error"


def test_lot_list_route_costs_no_query_per_row(client, django_user_model):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    user = django_user_model.objects.create_user("route-reader")
    user.groups.add(Group.objects.get_or_create(name="auditor")[0])
    rules = RuleSet.objects.create(
        code="route-rules",
        segment="synthetic",
        status="approved",
        effective_from=timezone.now(),
        author=user,
    )
    client.force_login(user)

    def listing(lots):
        for n in range(Lot.objects.count(), lots):
            Lot.objects.create(
                number=f"SYN-ROUTE-{n:03}", material="Synthetic", rules=rules, created_by=user
            )
        with CaptureQueriesContext(connection) as queries:
            response = client.get(reverse("quality:lot_list"))
        assert response.status_code == 200
        return len(queries), response.content.decode()

    listing(2)  # the first request also loads the account's preferences into the session
    few, _ = listing(2)
    many, body = listing(12)
    assert many == few  # the route counts come from the list's own query
    assert body.count('class="vr-microroute"') == 12 and "Not assigned" in body


def test_lot_record_lists_what_signing_enforces_and_shows_holds(client, django_user_model):
    """The QC disposition aside lists exactly quality.services.disposition_blockers, the list
    dispose_lot checks (stability holds, then sampling and analytical evidence); active holds are
    header pills."""
    import html
    import re

    from quality.services import disposition_blockers
    from stability.gates import lot_blockers as hold_blockers
    from stability.services import place_hold

    quality = django_user_model.objects.create_user("route-quality")
    quality.groups.add(Group.objects.get_or_create(name="quality")[0])
    rules = RuleSet.objects.create(
        code="route-hold-rules",
        segment="synthetic",
        status="approved",
        effective_from=timezone.now(),
        author=quality,
    )
    lot = Lot.objects.create(
        number="SYN-ROUTE-HOLD", material="Synthetic", rules=rules, created_by=quality
    )
    hold = place_hold(actor=quality, lot=lot, kind="quality", reason="Synthetic hold reason")
    client.force_login(quality)
    body = client.get(reverse("quality:lot_detail", args=[lot.pk])).content.decode()
    aside = body[body.index('id="disposition-heading"') : body.index('id="receipt-heading"')]
    checklist = aside[aside.index('class="vr-checklist"') : aside.index("</ul>")]
    listed = [
        html.unescape(re.sub(r"<[^>]+>", "", item)).strip()
        for item in re.findall(r"<li>(.*?)</li>", checklist, re.S)
    ]
    assert listed == disposition_blockers(lot)
    assert listed[: len(hold_blockers(lot))] == hold_blockers(lot)  # holds first
    assert any("no specification or sampling requirements are assigned." in m for m in listed)
    meta = body[
        body.index('class="vr-page-meta"') : body.index("</ul>", body.index("vr-page-meta"))
    ]
    assert hold.identifier in meta and ">Active<" in meta
    # A quality reviewer's next step is the disposition, whatever other roles they hold.
    disposition = reverse("quality:disposition", args=[lot.pk])
    assert f'class="btn btn-primary" href="{disposition}"' in body
