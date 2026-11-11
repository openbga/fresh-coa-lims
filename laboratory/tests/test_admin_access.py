"""Admin role boundary for laboratory pages: read everything, mutate nothing without a role."""

import pytest
from django.urls import reverse

from core.models import AuditEvent
from laboratory import services, urls
from laboratory.models import Calibration, Equipment, Qualification, ReagentLot, ResourceUse

from .access import check_boundary, make_user, route_names
from .helpers import (
    accept_new_calibration,
    make_equipment,
    make_reagent,
    qualify_analyst,
)

pytestmark = pytest.mark.django_db(transaction=True)

READ_ROUTES = {
    "laboratory:overview",
    "laboratory:equipment_list",
    "laboratory:equipment_detail",
    "laboratory:calibration_list",
    "laboratory:qualification_list",
    "laboratory:qualification_detail",
    "laboratory:reagent_list",
    "laboratory:reagent_detail",
    "laboratory:use_list",
}
MUTATION_ROUTES = {
    "laboratory:equipment_new",
    "laboratory:calibration_new",
    "laboratory:equipment_out_of_service",
    "laboratory:equipment_return",
    "laboratory:equipment_qualification_new",
    "laboratory:calibration_accept",
    "laboratory:qualification_new",
    "laboratory:qualification_approve",
    "laboratory:qualification_revoke",
    "laboratory:reagent_new",
    "laboratory:reagent_release",
    "laboratory:reagent_reject",
    "laboratory:use_new",
}
TRACKED = [Equipment, Calibration, Qualification, ReagentLot, ResourceUse]


def test_every_laboratory_route_is_classified_exactly_once():
    names = route_names(urls)
    assert READ_ROUTES | MUTATION_ROUTES == names
    assert not READ_ROUTES & MUTATION_ROUTES


@pytest.fixture
def world(people, django_user_model):
    """Real records so every parameterised route resolves for an authorized user."""
    ready = make_equipment(people, "E-READY")
    stopped = make_equipment(people, "E-OOS")
    services.take_out_of_service(actor=people["analyst"], equipment=stopped, reason="Drift")
    awaiting = make_equipment(people, "E-CAL", ready=False)
    calibration = accept_new_calibration(people, awaiting, accept=False)
    today_user = people["analyst2"]
    pending = services.record_qualification(
        actor=people["reviewer"],
        user=today_user,
        activity="ASSAY-A",
        scope_note="",
        evidence_ref="T-1",
        evidence_url="",
        valid_from="2026-01-01",
        valid_until="2099-01-01",
        reason="Training record",
    )
    approved = qualify_analyst(people, people["analyst2"], "ASSAY-B")
    reagent = make_reagent(people, "R-NEW", release=False)
    users = dict(people)
    for name, roles in {
        "admin_analyst": ["admin", "analyst"],
        "admin_reviewer": ["admin", "reviewer"],
        "admin_quality": ["admin", "quality"],
    }.items():
        users[name] = make_user(django_user_model, name, roles)
    return {
        "users": users,
        "ready": ready,
        "stopped": stopped,
        "awaiting": awaiting,
        "calibration": calibration,
        "pending": pending,
        "approved": approved,
        "reagent": reagent,
    }


def routes(world):
    ready, stopped = world["ready"], world["stopped"]
    reads = [
        ("laboratory:overview", [], None),
        ("laboratory:equipment_list", [], None),
        ("laboratory:equipment_detail", [world["awaiting"].pk], None),
        ("laboratory:equipment_detail", [stopped.pk], None),
        ("laboratory:calibration_list", [], None),
        ("laboratory:qualification_list", [], None),
        ("laboratory:qualification_detail", [world["pending"].pk], None),
        ("laboratory:reagent_list", [], None),
        ("laboratory:reagent_detail", [world["reagent"].pk], None),
        ("laboratory:use_list", [], None),
    ]
    mutations = [
        ("laboratory:equipment_new", [], "analyst"),
        ("laboratory:calibration_new", [ready.pk], "analyst"),
        ("laboratory:equipment_out_of_service", [ready.pk], "reviewer"),
        ("laboratory:equipment_return", [stopped.pk], "quality"),
        ("laboratory:equipment_qualification_new", [ready.pk], "analyst"),
        ("laboratory:calibration_accept", [world["calibration"].pk], "reviewer"),
        ("laboratory:qualification_new", [], "reviewer"),
        ("laboratory:qualification_approve", [world["pending"].pk], "quality"),
        ("laboratory:qualification_revoke", [world["approved"].pk], "quality"),
        ("laboratory:reagent_new", [], "analyst"),
        ("laboratory:reagent_release", [world["reagent"].pk], "reviewer"),
        ("laboratory:reagent_reject", [world["reagent"].pk], "analyst"),
        ("laboratory:use_new", [], "analyst"),
    ]
    assert {n for n, _, _ in reads} == READ_ROUTES
    assert {n for n, _, _ in mutations} == MUTATION_ROUTES
    return reads, mutations


def test_admin_reads_every_page_and_cannot_reach_any_mutation(client, world):
    reads, mutations = routes(world)
    # Read routes with identifiers also resolve for Admin through a real record, not a 404.
    check_boundary(
        client,
        reads=reads,
        mutations=mutations,
        users=world["users"],
        admin_only=world["users"]["admin"],
        tracked=TRACKED,
    )


def test_admin_with_a_role_keeps_exactly_that_roles_actions(client, world):
    users = world["users"]
    awaiting = reverse("laboratory:equipment_detail", args=[world["awaiting"].pk])
    accept = reverse("laboratory:calibration_accept", args=[world["calibration"].pk])
    record = reverse("laboratory:calibration_new", args=[world["awaiting"].pk])
    new_equipment = reverse("laboratory:equipment_new")
    listing = reverse("laboratory:equipment_list")

    client.force_login(users["admin"])
    page = client.get(awaiting).content.decode()
    assert f'href="{accept}' not in page and f'href="{record}' not in page
    assert f'href="{new_equipment}' not in client.get(listing).content.decode()

    client.force_login(users["admin_analyst"])
    assert f'href="{record}' in client.get(awaiting).content.decode()
    assert f'href="{new_equipment}' in client.get(listing).content.decode()
    assert client.get(new_equipment).status_code == 200
    assert client.get(accept).status_code == 403  # analyst role cannot accept calibrations

    client.force_login(users["admin_reviewer"])
    assert f'href="{accept}' in client.get(awaiting).content.decode()
    assert client.get(accept).status_code == 200
    assert client.get(new_equipment).status_code == 403  # reviewer role cannot register equipment


def test_multi_role_admin_is_not_a_self_review_bypass(client, world, people, django_user_model):
    # Admin who holds analyst + reviewer: records a calibration, then cannot accept it.
    recorder = make_user(django_user_model, "admin_recorder", ["admin", "analyst", "reviewer"])
    own = accept_new_calibration(people, world["ready"], accept=False)
    mine = services.record_calibration(
        actor=recorder,
        equipment=world["ready"],
        performed_at=own.performed_at,
        due_date=own.due_date,
        outcome="pass",
        standard_ref="CERT",
        certificate_ref="",
        certificate_url="",
        tolerance_note="",
        reason="Own calibration",
    )
    client.force_login(recorder)
    url = reverse("laboratory:calibration_accept", args=[mine.pk])
    denied = client.get(url)
    assert denied.status_code == 403 and "cannot accept" in denied.content.decode()
    posted = client.post(
        url,
        {
            "signature_username": recorder.username,
            "expected_revision": mine.revision,
            "pin": "82519374",
            "reason": "Self review",
        },
    )
    assert posted.status_code == 403
    mine.refresh_from_db()
    assert mine.state == "recorded"
    # The same admin may accept someone else's calibration.
    other = reverse("laboratory:calibration_accept", args=[world["calibration"].pk])
    assert client.get(other).status_code == 200
    assert AuditEvent.objects.filter(action="signed.reviewed", actor=recorder).count() == 0
