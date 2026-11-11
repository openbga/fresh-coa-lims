"""Admin role boundary for stability pages: read everything, mutate nothing without a role."""

import pytest
from django.urls import reverse

from laboratory.tests.access import check_boundary, make_user, route_names
from stability import services, urls
from stability.models import (
    Hold,
    Protocol,
    ProtocolCondition,
    ProtocolTimepoint,
    Pull,
    ReserveSample,
    RetentionObligation,
    Study,
)

from .helpers import PIN, approved_protocol, make_lot, started_study

pytestmark = pytest.mark.django_db(transaction=True)

READ_ROUTES = {
    "stability:overview",
    "stability:protocol_list",
    "stability:protocol_detail",
    "stability:study_list",
    "stability:study_detail",
    "stability:pull_list",
    "stability:pull_detail",
    "stability:reserve_list",
    "stability:reserve_detail",
    "stability:hold_list",
    "stability:hold_detail",
}
MUTATION_ROUTES = {
    "stability:protocol_new",
    "stability:condition_new",
    "stability:timepoint_new",
    "stability:protocol_approve",
    "stability:study_new",
    "stability:study_close",
    "stability:pull_record",
    "stability:pull_evidence",
    "stability:pull_missed",
    "stability:pull_accept",
    "stability:reserve_new",
    "stability:obligation_new",
    "stability:anchor_set",
    "stability:hold_new",
    "stability:hold_release",
}
TRACKED = [
    Protocol,
    ProtocolCondition,
    ProtocolTimepoint,
    Study,
    Pull,
    ReserveSample,
    RetentionObligation,
    Hold,
]


def test_every_stability_route_is_classified_exactly_once():
    names = route_names(urls)
    assert READ_ROUTES | MUTATION_ROUTES == names
    assert not READ_ROUTES & MUTATION_ROUTES


@pytest.fixture
def world(people, django_user_model):
    """Real records so every parameterised route resolves for an authorized user."""
    author = people["analyst"]
    draft = services.create_protocol(
        actor=author,
        code="DRAFT-P",
        title="Draft",
        product="X",
        document_ref="D",
        document_url="",
        test_profile_ref="",
        basis="B",
        reason="Draft",
    )
    condition = services.add_condition(
        actor=author,
        protocol=draft,
        label="Long-term",
        setpoint="S",
        temperature_c=None,
        humidity_pct=None,
        reason="Add",
    )
    services.add_timepoint(
        actor=author,
        protocol=draft,
        condition=condition,
        label="1m",
        interval_days=30,
        window_days=2,
        test_codes=["identity"],
        reason="Add",
    )
    draft.refresh_from_db()
    study = started_study(people, protocol=approved_protocol(people, code="LIVE-P"))
    pulls = {p.timepoint.interval_days: p for p in study.pulls.select_related("timepoint")}
    pulled = services.record_pull(
        actor=author,
        pull=pulls[100],
        pulled_on=pulls[100].due_date,
        quantity="5",
        quantity_unit="g",
        storage_location="Shelf",
        reason="Pull",
    )
    reserve = services.record_reserve(
        actor=author,
        lot=study.lot,
        identifier="RES-1",
        container_description="Package",
        storage_location="Cabinet",
        quantity="25",
        test_quantity="10",
        quantity_unit="g",
        minimum_multiple="2",
        retained_on=pulled.pulled_on,
        reason="Reserve",
    )
    obligation = services.add_obligation(
        actor=author,
        lot=study.lot,
        reserve=reserve,
        anchor_kind="last_distribution",
        anchor_date=None,
        offset_months=24,
        basis="Basis",
        reason="Unknown anchor",
    )
    hold = services.place_hold(
        actor=author, lot=make_lot(people, "HOLD-LOT"), kind="quality", reason="Review"
    )
    users = dict(people)
    for name, roles in {
        "admin_analyst": ["admin", "analyst"],
        "admin_quality": ["admin", "quality"],
        "admin_author": ["admin", "analyst", "quality"],
    }.items():
        users[name] = make_user(django_user_model, name, roles)
    return {
        "users": users,
        "draft": draft,
        "study": study,
        "pulls": pulls,
        "pulled": pulled,
        "reserve": reserve,
        "obligation": obligation,
        "hold": hold,
    }


def routes(world):
    draft, study, pulls = world["draft"], world["study"], world["pulls"]
    reads = [
        ("stability:overview", [], None),
        ("stability:protocol_list", [], None),
        ("stability:protocol_detail", [draft.pk], None),
        ("stability:study_list", [], None),
        ("stability:study_detail", [study.pk], None),
        ("stability:pull_list", [], None),
        ("stability:pull_detail", [pulls[30].pk], None),
        ("stability:pull_detail", [world["pulled"].pk], None),
        ("stability:reserve_list", [], None),
        ("stability:reserve_detail", [world["reserve"].pk], None),
        ("stability:hold_list", [], None),
        ("stability:hold_detail", [world["hold"].pk], None),
    ]
    mutations = [
        ("stability:protocol_new", [], "analyst"),
        ("stability:condition_new", [draft.pk], "analyst"),
        ("stability:timepoint_new", [draft.pk], "analyst"),
        ("stability:protocol_approve", [draft.pk], "quality"),
        ("stability:study_new", [], "analyst"),
        ("stability:study_close", [study.pk], "quality"),
        ("stability:pull_record", [pulls[180].pk], "analyst"),
        ("stability:pull_evidence", [world["pulled"].pk], "analyst"),
        ("stability:pull_missed", [pulls[30].pk], "analyst"),
        ("stability:pull_accept", [world["pulled"].pk], "reviewer"),
        ("stability:reserve_new", [], "analyst"),
        ("stability:obligation_new", [], "analyst"),
        ("stability:anchor_set", [world["obligation"].pk], "analyst"),
        ("stability:hold_new", [], "reviewer"),
        ("stability:hold_release", [world["hold"].pk], "quality"),
    ]
    assert {n for n, _, _ in reads} == READ_ROUTES
    assert {n for n, _, _ in mutations} == MUTATION_ROUTES
    return reads, mutations


def test_admin_reads_every_page_and_cannot_reach_any_mutation(client, world):
    reads, mutations = routes(world)
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
    draft = world["draft"]
    detail = reverse("stability:protocol_detail", args=[draft.pk])
    approve = reverse("stability:protocol_approve", args=[draft.pk])
    release = reverse("stability:hold_release", args=[world["hold"].pk])
    hold_detail = reverse("stability:hold_detail", args=[world["hold"].pk])
    new_hold = reverse("stability:hold_new")

    client.force_login(users["admin"])
    assert f'href="{approve}' not in client.get(detail).content.decode()
    assert f'href="{release}' not in client.get(hold_detail).content.decode()
    assert f'href="{new_hold}' not in client.get(reverse("stability:hold_list")).content.decode()

    client.force_login(users["admin_quality"])
    assert f'href="{approve}' in client.get(detail).content.decode()
    assert client.get(approve).status_code == 200
    assert f'href="{release}' in client.get(hold_detail).content.decode()
    assert client.get(release).status_code == 200
    assert client.get(reverse("stability:protocol_new")).status_code == 200  # quality may author
    pull = reverse("stability:pull_record", args=[world["pulls"][180].pk])
    assert client.get(pull).status_code == 403  # recording a pull is analyst-only

    client.force_login(users["admin_analyst"])
    assert client.get(reverse("stability:protocol_new")).status_code == 200
    assert client.get(approve).status_code == 403  # analyst role cannot approve


def test_multi_role_admin_is_not_an_independence_bypass(client, world):
    author = world["users"]["admin_author"]  # admin + analyst + quality
    protocol = services.create_protocol(
        actor=author,
        code="OWN-P",
        title="Own",
        product="X",
        document_ref="D",
        document_url="",
        test_profile_ref="",
        basis="B",
        reason="Own draft",
    )
    condition = services.add_condition(
        actor=author,
        protocol=protocol,
        label="C",
        setpoint="S",
        temperature_c=None,
        humidity_pct=None,
        reason="Add",
    )
    services.add_timepoint(
        actor=author,
        protocol=protocol,
        condition=condition,
        label="1m",
        interval_days=30,
        window_days=2,
        test_codes=["identity"],
        reason="Add",
    )
    protocol.refresh_from_db()
    client.force_login(author)
    url = reverse("stability:protocol_approve", args=[protocol.pk])
    denied = client.get(url)
    assert denied.status_code == 403 and "authored" in denied.content.decode()
    posted = client.post(
        url,
        {
            "signature_username": author.username,
            "expected_revision": protocol.revision,
            "pin": PIN,
            "reason": "Self approval",
        },
    )
    assert posted.status_code == 403
    protocol.refresh_from_db()
    assert protocol.state == Protocol.State.DRAFT
    # Someone else's draft remains approvable by the same multi-role account.
    other = reverse("stability:protocol_approve", args=[world["draft"].pk])
    assert client.get(other).status_code == 200
