"""Admin = see everything, change nothing scientific; admin plus a lab role is no bypass.

Every analytical route is listed below as either a read page or a mutation, and the lists
must cover the whole URL module. Each mutation URL points at a real record that a lab user
can reach (200 or a reasoned 302), so admin denials cannot pass on a missing ID.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from analytical import services, urls
from analytical.models import (
    AnalyticalTest,
    Investigation,
    InvestigationEntry,
    Observation,
    QCBatch,
    QCResult,
)
from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import set_pin
from quality.models import Lot
from quality.services import add_sample

from .conftest import PASSWORD, PIN, fresh, login, pass_qc, record, submit

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("plain_static")]

READ = {
    "test_list",
    "batch_list",
    "investigation_list",
    "lot_testing",
    "test_detail",
    "batch_detail",
    "investigation_detail",
}
MUTATION_PAGES = {
    "observation_new",
    "observation_correct",
    "test_batch",
    "test_return",
    "test_review",
    "batch_new",
    "qc_record",
    "qc_correct",
    "batch_reject",
    "entry_new",
    "escalate",
    "authorize",
    "conclude",
}
# Read pages that also accept a scientific POST (assign tests, submit results).
POST_ON_READ = {"lot_testing", "test_detail"}


def _user(django_user_model, name, *roles, superuser=False):
    make = (
        django_user_model.objects.create_superuser
        if superuser
        else (django_user_model.objects.create_user)
    )
    user = make(name, password=PASSWORD, first_name="Test", last_name=name.capitalize())
    for role in roles:
        user.groups.add(Group.objects.get_or_create(name=role)[0])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


@pytest.fixture
def world(people, assigned, batch, make_lot, django_user_model):
    """Real records in states where every action is offered to some lab role."""
    lot, sample, tests = assigned
    assay, identity = tests["assay"], tests["identity"]
    pass_qc(people, batch)
    services.assign_to_batch(actor=people["analyst"], test=assay, batch=batch, reason="Run")
    assay = record(people, assay, "100.0", "100.2")  # complete, not submitted: correct/submit
    identity = record(people, identity, "0.50")
    _, investigation = submit(people, identity)  # OOS: review offered, investigation open
    services.add_entry(
        actor=people["analyst"], investigation=investigation, kind="assessment", text="Checked"
    )
    failed = services.create_batch(
        actor=people["analyst2"], number="SYN-B2", method_code="SYN-HPLC", reason="Run"
    )
    services.record_qc(
        actor=people["analyst2"],
        batch=failed,
        check_code="blank",
        value=Decimal("0.30"),
        raw_reference="RUN-2 blank",
    )
    lot2, sample2 = make_lot("SYN-LOT-2")
    created, _ = services.assign_tests(actor=people["analyst"], sample=sample2, reason="Assign")
    tests2 = {t.test_code: t for t in created}
    spare = add_sample(
        actor=people["analyst"],
        lot=lot,
        reference="SYN-LOT-1-S2",
        collected_at=timezone.now(),
        reason="Synthetic sample",
    )
    obs = Observation.objects.filter(test=assay).first()
    blank = QCResult.objects.get(batch=batch, check_code="blank")
    inv = investigation.pk
    w = {
        "lot": lot,
        "spare": spare,
        "assay": fresh(assay),
        "identity": fresh(identity),
        "unbatched": tests2["assay"],
        "unrecorded": tests2["identity"],
        "batch": batch,
        "failed": failed,
        "investigation": fresh(investigation),
        "admin": _user(django_user_model, "admin.only", "admin"),
        "lab": _user(django_user_model, "admin.lab", "admin", "analyst", "reviewer", "quality"),
    }
    w["read"] = {
        "test_list": reverse("analytical:test_list") + "?state=oos&q=SYN",
        "batch_list": reverse("analytical:batch_list"),
        "investigation_list": reverse("analytical:investigation_list") + "?state=all",
        "lot_testing": reverse("analytical:lot_testing", args=[lot.pk]),
        "test_detail": reverse("analytical:test_detail", args=[assay.pk]),
        "batch_detail": reverse("analytical:batch_detail", args=[batch.pk]),
        "investigation_detail": reverse("analytical:investigation_detail", args=[inv]),
    }
    review_post = {"signature_username": "admin.only", "pin": PIN, "reason": "Checked"}
    w["mutations"] = {
        "observation_new": (
            reverse("analytical:observation_new", args=[tests2["identity"].pk]),
            {"value": "1.00", "raw_reference": "NB-9"},
        ),
        "observation_correct": (
            reverse("analytical:observation_correct", args=[obs.pk]),
            {"value": "100.1", "raw_reference": "NB-9", "reason": "Typo"},
        ),
        "test_batch": (
            reverse("analytical:test_batch", args=[tests2["assay"].pk]),
            {"batch": batch.pk, "reason": "Run"},
        ),
        "test_return": (
            reverse("analytical:test_return", args=[identity.pk]),
            {"expected_revision": fresh(identity).revision, "reason": "Fix"},
        ),
        "test_review": (
            reverse("analytical:test_review", args=[identity.pk]),
            {**review_post, "expected_revision": fresh(identity).revision},
        ),
        "batch_new": (
            reverse("analytical:batch_new"),
            {"number": "SYN-B9", "method_code": "SYN-HPLC", "reason": "Run"},
        ),
        "qc_record": (
            reverse("analytical:qc_record", args=[failed.pk, "control"]),
            {"value": "100.0", "raw_reference": "RUN-2 control"},
        ),
        "qc_correct": (
            reverse("analytical:qc_correct", args=[blank.pk]),
            {"value": "0.02", "raw_reference": "RUN-1 blank", "reason": "Typo"},
        ),
        "batch_reject": (
            reverse("analytical:batch_reject", args=[failed.pk]),
            {**review_post, "expected_revision": fresh(failed).revision},
        ),
        "entry_new": (
            reverse("analytical:entry_new", args=[inv]),
            {"kind": "evidence", "text": "Admin note", "external_reference": ""},
        ),
        "escalate": (
            reverse("analytical:escalate", args=[inv]),
            {"expected_revision": fresh(investigation).revision, "reason": "Escalate"},
        ),
        "authorize": (
            reverse("analytical:authorize", args=[inv]),
            {
                **review_post,
                "kind": "retest",
                "expected_revision": fresh(investigation).revision,
            },
        ),
        "conclude": (
            reverse("analytical:conclude", args=[inv]),
            {
                **review_post,
                "outcome": "confirmed",
                "assignable_cause": "",
                "expected_revision": fresh(investigation).revision,
            },
        ),
    }
    w["read_posts"] = {
        "lot_testing": (w["read"]["lot_testing"], {"sample": spare.pk, "reason": "Assign"}),
        "test_detail": (
            w["read"]["test_detail"],
            {"expected_revision": fresh(assay).revision, "reason": "Results complete"},
        ),
    }
    return w


def _state():
    """Everything a scientific mutation or a failed signature attempt would change."""
    return {
        "events": AuditEvent.objects.count(),
        "signatures": ElectronicSignature.objects.count(),
        "observations": Observation.objects.count(),
        "qc": QCResult.objects.count(),
        "entries": InvestigationEntry.objects.count(),
        "tests": sorted(AnalyticalTest.objects.values_list("pk", "state", "revision", "batch_id")),
        "batches": sorted(QCBatch.objects.values_list("pk", "state", "revision")),
        "investigations": sorted(Investigation.objects.values_list("pk", "phase", "revision")),
        "lots": sorted(Lot.objects.values_list("pk", "state", "revision")),
        "pin_failures": sorted(PINCredential.objects.values_list("user_id", "failures")),
    }


def test_route_lists_cover_every_analytical_url():
    names = {p.name for p in urls.urlpatterns}
    assert names == READ | MUTATION_PAGES
    assert not READ & MUTATION_PAGES and POST_ON_READ <= READ


def test_admin_reads_every_page_and_sees_no_scientific_actions(client, world):
    assert set(world["read"]) == READ and set(world["mutations"]) == MUTATION_PAGES
    login(client, world["admin"])
    pages = {}
    for name, url in world["read"].items():
        response = client.get(url)
        assert response.status_code == 200, name
        pages[name] = response.content.decode()
    extra = {
        "identity": reverse("analytical:test_detail", args=[world["identity"].pk]),
        "unbatched": reverse("analytical:test_detail", args=[world["unbatched"].pk]),
        "unrecorded": reverse("analytical:test_detail", args=[world["unrecorded"].pk]),
        "failed": reverse("analytical:batch_detail", args=[world["failed"].pk]),
    }
    for name, url in extra.items():
        response = client.get(url)
        assert response.status_code == 200, name
        pages[name] = response.content.decode()
    hidden = _action_markers(world)
    for page, markers in hidden.items():
        for marker in markers:
            assert marker not in pages[page], (page, marker)
    assert 'name="pin"' not in "".join(pages.values())

    # The same pages offer every action once a lab role is held alongside admin.
    login(client, world["lab"])
    for page, markers in hidden.items():
        url = world["read"].get(page) or extra[page]
        body = client.get(url).content.decode()
        for marker in markers:
            assert marker in body, (page, marker)


def _action_markers(w):
    inv = w["investigation"].pk
    return {
        "lot_testing": ['name="sample"', "Assign required tests"],
        "batch_list": [reverse("analytical:batch_new")],
        "test_detail": [
            "Submit for review",
            reverse("analytical:observation_correct", args=[w["assay"].observations.first().pk]),
        ],
        "identity": [reverse("analytical:test_review", args=[w["identity"].pk])],
        "unbatched": [reverse("analytical:test_batch", args=[w["unbatched"].pk])],
        "unrecorded": [reverse("analytical:observation_new", args=[w["unrecorded"].pk])],
        "batch_detail": [
            reverse(
                "analytical:qc_correct",
                args=[QCResult.objects.get(batch=w["batch"], check_code="blank").pk],
            )
        ],
        "failed": [
            reverse("analytical:batch_reject", args=[w["failed"].pk]),
            reverse("analytical:qc_record", args=[w["failed"].pk, "control"]),
        ],
        "investigation_detail": [
            reverse("analytical:entry_new", args=[inv]),
            reverse("analytical:escalate", args=[inv]),
            reverse("analytical:authorize", args=[inv]),
            reverse("analytical:conclude", args=[inv]),
        ],
    }


def test_admin_cannot_open_or_post_any_scientific_mutation(client, world, django_user_model):
    # Each target is a real, reachable record: a lab user is not refused or sent to a 404.
    login(client, world["lab"])
    for name, (url, _) in world["mutations"].items():
        assert client.get(url).status_code in (200, 302), name

    root = _user(django_user_model, "root.only", superuser=True)  # no implicit lab role
    for actor in (world["admin"], root):
        login(client, actor)
        before = _state()
        for name, (url, data) in world["mutations"].items():
            assert client.get(url).status_code == 403, (actor, name)
            assert client.post(url, data).status_code == 403, (actor, name)
        for name, (url, data) in world["read_posts"].items():
            assert client.post(url, data).status_code == 403, (actor, name)
        assert _state() == before, actor
    assert not AnalyticalTest.objects.filter(sample=world["spare"]).exists()


def test_admin_with_lab_roles_keeps_independence(client, people, world):
    """Multi-role admin can act, but never review or decide on their own work."""
    lab = world["lab"]
    test = world["unrecorded"]
    login(client, lab)
    response = client.post(
        reverse("analytical:observation_new", args=[test.pk]),
        {"value": "1.00", "raw_reference": "NB-7"},
    )
    assert response.status_code == 302 and fresh(test).current_observations().count() == 1
    response = client.post(
        reverse("analytical:test_detail", args=[test.pk]),
        {"expected_revision": fresh(test).revision, "reason": "Results complete"},
    )
    assert response.status_code == 302 and fresh(test).state == "submitted"
    before = _state()
    response = client.get(reverse("analytical:test_review", args=[test.pk]))
    assert response.status_code == 302
    page = client.get(response.url).content.decode()
    assert "You cannot review your own test." in page and 'name="pin"' not in page
    response = client.post(
        reverse("analytical:test_review", args=[test.pk]),
        {
            "signature_username": "admin.lab",
            "pin": PIN,
            "reason": "Self",
            "expected_revision": fresh(test).revision,
        },
    )
    assert response.status_code == 302 and fresh(test).state == "submitted"
    assert _state() == before
    with pytest.raises(ValidationError, match="your own test"):
        services.review_test(
            actor=lab,
            pin=PIN,
            test=fresh(test),
            expected_revision=fresh(test).revision,
            reason="Self",
        )
