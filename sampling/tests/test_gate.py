"""Sampling disposition gate, deviation assessment and resample provenance."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.urls import reverse
from django.utils import timezone

from catalog.tests.factories import PIN, approve
from core.models import ElectronicSignature
from quality.models import Lot
from quality.services import add_sample
from sampling import services
from sampling.models import DeviationReview, SamplingRecord
from sampling.services import lot_blockers

from .test_services import assign, ready, sample  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def short(people, ready, reference="SYN-S-DEV", **extra):  # noqa: F811
    return sample(
        people,
        ready,
        reference=reference,
        containers_sampled=2,
        deviation="Two containers inaccessible (synthetic).",
        **extra,
    )


def assess(people, record, actor="approver", accept=True, **overrides):
    review = DeviationReview.objects.get(record=record)
    kwargs = {
        "actor": people[actor],
        "pin": PIN,
        "review": review,
        "expected_revision": review.revision,
        "accept": accept,
        "reason": "Remaining containers representative (synthetic).",
    }
    kwargs.update(overrides)
    return services.assess_deviation(**kwargs)


def test_unassigned_and_held_lots_block(people, ready):  # noqa: F811
    assert lot_blockers(ready["lot"]) == [
        "Applicability hold: no specification or sampling requirements are assigned."
    ]
    assign(people, ready, scope="eu-market")
    [reason] = lot_blockers(ready["lot"])
    assert reason.startswith("Applicability hold:") and "eu-market" in reason


def test_assigned_plan_alone_is_not_sampling(people, ready):  # noqa: F811
    assign(people, ready)
    assert lot_blockers(ready["lot"]) == [
        "No sampling has been recorded against the approved sampling plan."
    ]


def test_bare_foundation_sample_blocks(people, ready):  # noqa: F811
    assign(people, ready)
    sample(people, ready)
    add_sample(
        actor=people["analyst"],
        lot=ready["lot"],
        reference="SYN-BARE",
        collected_at=timezone.now(),
        reason="Bypass attempt",
    )
    assert lot_blockers(ready["lot"]) == [
        "Sample SYN-BARE has no sampling record against the approved plan."
    ]


def test_clean_sampling_has_no_blockers(people, ready):  # noqa: F811
    assign(people, ready)
    sample(people, ready)
    assert lot_blockers(ready["lot"]) == []


def test_deviation_pending_rejected_and_accepted(people, ready):  # noqa: F811
    assign(people, ready)
    record = short(people, ready)
    assert DeviationReview.objects.get(record=record).status == "pending"
    assert lot_blockers(ready["lot"]) == [
        "Sampling deviation for sample SYN-S-DEV awaits quality assessment."
    ]
    before = Lot.objects.get(pk=ready["lot"].pk).revision
    assess(people, record, accept=False)
    assert "was rejected" in lot_blockers(ready["lot"])[0]
    assert Lot.objects.get(pk=ready["lot"].pk).revision == before + 1
    correction = services.correct_sampling(
        actor=people["analyst"],
        record=record,
        reason="Recounted containers",
        sampled_at=record.sampled_at,
        containers_total=9,
        containers_sampled=2,
        container_ids="C1, C2",
        quantity=Decimal("60"),
        quantity_unit="g",
        location="Booth 1",
        deviation="Two containers damaged; QA informed (synthetic).",
    )
    assert "awaits quality assessment" in lot_blockers(ready["lot"])[0]
    signed = assess(people, correction)
    assert signed.status == "accepted" and signed.decided_by == people["approver"]
    assert lot_blockers(ready["lot"]) == []
    signature = ElectronicSignature.objects.get(
        object_type="sampling.deviationreview", object_id=str(signed.pk)
    )
    assert signature.meaning == "accepted"


def test_deviation_assessment_independence_roles_and_staleness(people, ready):  # noqa: F811
    assign(people, ready)
    record = short(people, ready, actor=people["dual"])
    with pytest.raises(PermissionDenied):
        assess(people, record, actor="dual")
    for role in ("analyst", "reviewer", "admin"):
        with pytest.raises(PermissionDenied):
            assess(people, record, actor=role)
    with pytest.raises(ValidationError, match="Record changed"):
        assess(people, record, expected_revision=99)
    with pytest.raises(ValidationError, match="PIN"):
        assess(people, record, pin="00000000")
    assert DeviationReview.objects.get(record=record).status == "pending"
    decided = assess(people, record)
    with pytest.raises(ValidationError):
        assess(people, record)
    with pytest.raises(DatabaseError), transaction.atomic():
        DeviationReview.objects.filter(pk=decided.pk).update(status="pending")


def test_reassigned_plan_blocks_old_sampling(people, ready, monkeypatch):  # noqa: F811
    assign(people, ready)
    sample(people, ready)
    # A new plan version for a later period cannot overlap; simulate a different current plan
    # by reassigning after a new approved plan version takes effect.
    old_plan = ready["plan"]
    new = services.new_plan_revision(
        actor=people["author"],
        plan=old_plan.plan,
        basis="all",
        minimum_quantity=Decimal("10"),
        quantity_unit="g",
        instructions="Every container (synthetic).",
        rationale="Synthetic change.",
        effective_from=old_plan.effective_until,
        effective_until=old_plan.effective_until + timedelta(days=30),
        reason="Next plan",
    )
    approve(new, people["approver"])
    current = services.current_assignment(ready["lot"])
    current.plan_revision_id = new.pk  # in-memory only: emulate assignment after the boundary
    monkeypatch.setattr(services, "current_assignment", lambda lot: current)
    [reason] = lot_blockers(ready["lot"])
    assert "was sampled under" in reason and str(new) in reason


def test_resample_requires_sampled_original_of_same_lot(people, ready):  # noqa: F811
    assign(people, ready)
    original = sample(people, ready)
    with pytest.raises(ValidationError) as caught:
        sample(people, ready, reference="SYN-RS-0", purpose="resample")
    assert "resample_of" in caught.value.message_dict
    with pytest.raises(ValidationError):
        sample(people, ready, reference="SYN-RS-X", resample_of=original.sample)
    resample = sample(
        people, ready, reference="SYN-RS-1", purpose="resample", resample_of=original.sample
    )
    assert resample.resample_of == original.sample
    assert lot_blockers(ready["lot"]) == []


def test_lot_page_shows_blockers_and_assess_action(client, people, ready):  # noqa: F811
    assign(people, ready)
    record = short(people, ready)
    client.force_login(people["approver"])
    body = client.get(reverse("sampling:lot", args=[ready["lot"].pk])).content.decode()
    assert "awaits quality assessment" in body
    url = reverse("sampling:deviation_assess", args=[record.pk])
    assert url in body
    response = client.post(
        url,
        {
            "decision": "accept",
            "reason": "Representative",
            "signature_username": people["approver"].username,
            "pin": PIN,
            "expected_revision": 1,
        },
    )
    assert response.status_code == 302
    assert DeviationReview.objects.get(record=record).status == "accepted"
    client.force_login(people["analyst"])
    assert client.get(url).status_code == 403
    assert SamplingRecord.objects.count() == 1


def test_sampler_sees_blocked_assessment_page(client, people, ready):  # noqa: F811
    assign(people, ready)
    record = short(people, ready, actor=people["dual"])
    client.force_login(people["dual"])
    response = client.get(reverse("sampling:deviation_assess", args=[record.pk]))
    assert response.status_code == 403
    assert "another person must assess" in response.content.decode()


def test_reassignment_refused_once_native_testing_started(client, people, ready):  # noqa: F811
    """Regression: reassigning after tests exist would strand the lot (one original per code)."""
    from analytical.models import AnalyticalTest

    first = assign(people, ready)
    record = sample(people, ready)
    AnalyticalTest.objects.create(
        lot=ready["lot"],
        sample=record.sample,
        test_code="assay",
        requirement=services.test_requirements(ready["lot"])["assay"],
        requirement_hash="0" * 64,
        created_by=people["analyst"],
    )
    revision = Lot.objects.get(pk=ready["lot"].pk).revision
    with pytest.raises(ValidationError, match="Testing has started"):
        assign(people, ready)
    assert services.current_assignment(ready["lot"]) == first
    assert Lot.objects.get(pk=ready["lot"].pk).revision == revision
    client.force_login(people["analyst"])
    url = reverse("sampling:assign", args=[ready["lot"].pk])
    assert client.get(url).status_code == 302
    body = client.get(reverse("sampling:lot", args=[ready["lot"].pk])).content.decode()
    assert url not in body and "cannot be reassigned" in body
    response = client.post(
        url, {"material": first.material_id, "stage": "incoming", "scope": "general", "reason": "x"}
    )
    assert response.status_code == 302
    assert services.current_assignment(ready["lot"]) == first
