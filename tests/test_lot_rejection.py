"""Signed rejection of a lot and cancellation of a lot received in error: what they freeze,
when they are refused, who may sign, and that nothing changes on the lot afterwards.

Uses the production adapters and service-created approvals only (synthetic data).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from analytical import services as analytical
from analytical.models import AnalyticalTest, Investigation
from core.models import AuditEvent, ElectronicSignature, PINCredential
from quality import rejection
from quality import services as quality
from quality.models import Lot
from reporting import services as reporting
from sampling import services as sampling
from stability import services as stability
from stability.models import Hold
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import PIN
from tests.test_requirement_replacement import complete, conclude_confirmed
from tests.test_result_types_journey import assign_sample_tests, build_world, record, submit
from tests.test_revised_versions_in_progress import assay_on, batch_method

pytestmark = pytest.mark.django_db(transaction=True)

REASON = "Synthetic: assay confirmed below the specification (NCR-SYN-001)"


@pytest.fixture
def world(django_user_model):
    """A lot under test with the five result types. The world's analyst received, sampled and
    tested it and also holds the quality role; the approver authored nothing on the lot."""
    data = build_world(django_user_model, with_assay=True)
    data["tests"] = assign_sample_tests(data)
    data["lot"].refresh_from_db()
    return data


@pytest.fixture
def received(django_user_model):
    """A lot that was only received: no requirements, samples or tests."""
    data = build_world(django_user_model)
    data["lot"].refresh_from_db()
    return data


def fresh(data):
    return Lot.objects.get(pk=data["lot"].pk)


def reject(data, who="approver", grounds="results", **changes):
    lot = fresh(data)
    kwargs = {
        "actor": data["people"][who],
        "pin": PIN,
        "lot": lot,
        "expected_revision": lot.revision,
        "grounds": grounds,
        "reason": REASON,
        "reference": "NCR-SYN-001",
        "basis": rejection.rejection_preview(lot).basis,
    }
    kwargs.update(changes)
    return rejection.reject_lot(**kwargs)


def cancel(data, who="approver", **changes):
    lot = fresh(data)
    kwargs = {
        "actor": data["people"][who],
        "pin": PIN,
        "lot": lot,
        "expected_revision": lot.revision,
        "reason": "Synthetic: the delivery was recorded twice",
        "basis": rejection.cancellation_preview(lot).basis,
    }
    kwargs.update(changes)
    return rejection.cancel_receipt(**kwargs)


def test_a_lot_under_test_is_rejected_with_its_evidence_frozen(world):
    complete(world, "identity", "salmonella")
    lot = fresh(world)
    before = lot.revision
    preview = rejection.rejection_preview(lot)
    assert preview.possible and preview.reasons == []

    rejected = reject(world, grounds="receipt")

    assert rejected.state == "rejected" and rejected.revision == before + 1
    evidence = rejected.disposition_evidence
    assert evidence["schema"] == "oq.lot-rejection/1" and evidence["decision"] == "rejected"
    assert evidence["grounds"] == "receipt" and evidence["reference"] == "NCR-SYN-001"
    assert {key: value for key, value in evidence.items() if key in preview.evidence} == (
        preview.evidence
    )
    states = {row["test_code"]: row["state"] for row in evidence["tests"]}
    assert states == {
        "identity": "reviewed",
        "salmonella": "reviewed",
        "tamc": "open",
        "impurity": "open",
        "assay": "open",
    }
    assert any("incomplete" in item for item in evidence["outstanding"])
    assert evidence["receipt"]["source"] == "on_site"
    assert evidence["requirements"]["status"] == "ready"
    signature = ElectronicSignature.objects.get(object_type="quality.lot", meaning="rejected")
    assert signature.signer == world["people"]["approver"]
    assert signature.revision == rejected.revision
    assert signature.content["disposition_evidence"] == evidence
    assert signature.audit_event.action == "signed.rejected"
    assert signature.audit_event.reason == REASON
    # The tests are kept exactly as they stood.
    assert AnalyticalTest.objects.filter(lot=lot, state="open").count() == 3


def test_a_rejected_lot_takes_no_more_records(world):
    complete(world, "identity")
    reject(world)
    people, lot = world["people"], fresh(world)
    tamc = world["tests"]["tamc"]
    with pytest.raises(ValidationError, match="no longer in quarantine"):
        record(world, tamc, "<10")
    with pytest.raises(ValidationError, match="already been dispositioned"):
        quality.dispose_lot(
            actor=people["approver"],
            pin=PIN,
            lot=lot,
            expected_revision=lot.revision,
            reason="Release after all",
        )
    with pytest.raises(ValidationError, match="was rejected"):
        reject(world, basis="0" * 64)
    with pytest.raises(ValidationError, match="was rejected"):
        cancel(world, basis="0" * 64)
    with pytest.raises(ValidationError):
        quality.correct_receipt(
            actor=people["analyst"],
            receipt=quality.current_receipt(lot),
            reason="Late correction",
            **{**on_site_receipt(), "shipment_ref": "DEL-SYN-LATE"},
        )
    with pytest.raises(ValidationError, match="Only quarantined lots"):
        sampling.assign_requirements(
            actor=people["analyst"],
            lot=lot,
            material=world["material"],
            stage="incoming",
            reason="Assign again",
        )
    with pytest.raises(ValidationError, match="signed QC disposition"):
        reporting.open_report(actor=people["approver"], lot=lot, recipient="Synthetic customer")
    with pytest.raises(ValidationError, match="Only quarantined lots"):
        sampling.record_sampling(
            actor=people["analyst"],
            lot=lot,
            reference="SYN-RT-S002",
            sampled_at=timezone.now(),
            containers_total=1,
            containers_sampled=1,
            container_ids="SYN-C002",
            quantity=Decimal("10"),
            quantity_unit="g",
            location="Synthetic sampling booth",
            reason="Late sample",
        )
    # The certificate preview shows no release evidence for a rejected lot.
    from reporting.evidence import _native

    assert _native(lot) is None
    # A protective hold can still be placed on a rejected lot: its reserve may be evidence.
    hold = stability.place_hold(
        actor=people["reviewer"], lot=lot, kind=Hold.Kind.INVESTIGATION, reason="Keep the retain"
    )
    assert hold.state == "active" and fresh(world).revision == lot.revision


def test_the_database_keeps_a_decided_lot_and_its_evidence(world):
    lot = reject(world)
    for sql, params in (
        ("UPDATE quality_lot SET revision = revision + 1 WHERE id = %s", [lot.pk]),
        ("UPDATE quality_lot SET state = 'quarantine' WHERE id = %s", [lot.pk]),
        ("UPDATE quality_lot SET disposition_evidence = '{}' WHERE id = %s", [lot.pk]),
        ("DELETE FROM quality_lot WHERE id = %s", [lot.pk]),
    ):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)
    other = quality.receive_lot(
        actor=world["people"]["analyst"],
        number="SYN-RT-002",
        material=world["material"].name,
        rules=lot.rules,
        reason="Second synthetic receipt",
        receipt=on_site_receipt(),
    )
    for sql in (
        # A decision always carries its evidence, and only a rejected or cancelled lot has one.
        "UPDATE quality_lot SET state = 'rejected' WHERE id = %s",
        "UPDATE quality_lot SET state = 'cancelled', "
        'disposition_evidence = \'{"decision": "rejected", "schema": "x"}\' WHERE id = %s',
        "UPDATE quality_lot SET state = 'released', "
        'disposition_evidence = \'{"decision": "rejected", "schema": "x"}\' WHERE id = %s',
        'UPDATE quality_lot SET disposition_evidence = \'{"decision": "rejected"}\' WHERE id = %s',
        "UPDATE quality_lot SET state = 'destroyed' WHERE id = %s",
    ):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, [other.pk])
    assert Lot.objects.get(pk=other.pk).state == "quarantine"


def test_an_open_investigation_is_concluded_before_the_lot_is_rejected(world):
    complete(world, "identity", "salmonella", "tamc", "impurity")
    assay = world["tests"]["assay"]
    record(world, assay, "97.00")
    _, investigation = submit(world, assay)
    assert investigation is not None
    preview = rejection.rejection_preview(fresh(world))
    assert not preview.possible
    assert preview.reasons == [
        f"{investigation.label} is open. Conclude it before the lot is rejected: the "
        "investigation is completed whatever is decided about the lot."
    ]
    with pytest.raises(ValidationError, match="Conclude it before the lot is rejected"):
        reject(world)
    assert fresh(world).state == "quarantine"

    conclude_confirmed(world, Investigation.objects.get(pk=investigation.pk))
    lot = reject(world)
    evidence = lot.disposition_evidence
    assert evidence["investigations"] == [
        {
            "investigation": investigation.pk,
            "label": investigation.label,
            "test": assay.pk,
            "phase": "closed",
            "outcome": "confirmed",
        }
    ]
    assert (
        f"{investigation.label} confirmed an out-of-specification result."
        in (evidence["outstanding"])
    )


def test_results_not_yet_submitted_are_submitted_before_the_lot_is_rejected(world):
    assay = world["tests"]["assay"]
    record(world, assay, "96.00")
    preview = rejection.rejection_preview(fresh(world))
    assert preview.reasons == [
        f"{assay.label} assay holds results that were not submitted. Submit them first, so "
        "that a failing result is evaluated and investigated."
    ]
    with pytest.raises(ValidationError, match="holds results that were not submitted"):
        reject(world)
    # Submitting evaluates the result: the failure opens an investigation, which is
    # concluded before the rejection.
    _, investigation = submit(world, assay)
    assert investigation is not None
    assert "is open" in rejection.rejection_preview(fresh(world)).reasons[0]


def test_rejection_is_signed_by_an_independent_quality_person(world):
    people = world["people"]
    lot = fresh(world)
    # The analyst holds the quality role and received, sampled and tested the lot.
    assert rejection.rejection_denial(people["analyst"], lot) == rejection.SELF_REJECTION
    with pytest.raises(ValidationError, match="Another quality person must sign"):
        reject(world, who="analyst")
    with pytest.raises(PermissionDenied):
        reject(world, who="reviewer")
    assert rejection.rejection_denial(people["approver"], lot) == ""
    assert fresh(world).state == "quarantine"
    assert not ElectronicSignature.objects.filter(object_type="quality.lot").exists()


def test_a_wrong_pin_is_counted_and_signs_nothing(world):
    with pytest.raises(ValidationError):
        reject(world, pin="00000000")
    credential = PINCredential.objects.get(user=world["people"]["approver"])
    assert credential.failures == 1
    assert fresh(world).state == "quarantine"


def test_a_stale_page_or_missing_grounds_signs_nothing(world):
    lot = fresh(world)
    page = rejection.rejection_preview(lot)
    complete(world, "identity")  # changes the lot after the page was read
    with pytest.raises(ValidationError, match="Record changed"):
        reject(world, expected_revision=lot.revision, basis=page.basis)
    with pytest.raises(ValidationError, match="changed after this page was opened"):
        reject(world, basis=page.basis)
    with pytest.raises(ValidationError, match="Choose the grounds"):
        reject(world, grounds="")
    with pytest.raises(ValidationError, match="at most 200"):
        reject(world, reference="x" * 201)
    with pytest.raises(ValidationError, match="required"):
        reject(world, reason="  ")
    assert fresh(world).state == "quarantine"
    assert PINCredential.objects.get(user=world["people"]["approver"]).failures == 0


def test_a_lot_that_meets_its_requirements_can_still_be_rejected(world):
    complete(world, "identity", "salmonella", "tamc", "impurity", "assay")
    preview = rejection.rejection_preview(fresh(world))
    assert preview.possible and preview.evidence["outstanding"] == []
    lot = reject(world, grounds="other")
    assert lot.state == "rejected" and lot.disposition_evidence["grounds"] == "other"


def test_a_failed_qc_batch_is_rejected_although_it_holds_a_test_of_a_rejected_lot(
    django_user_model, client
):
    data = build_world(django_user_model, with_assay=True)
    people = data["people"]
    method = batch_method(data)
    assay_on(data, method)
    tests = assign_sample_tests(data)
    assay = tests["assay"]
    batch = analytical.create_batch(
        actor=people["analyst"], number="SYN-QC-REJ", method_code=method.code, reason="Run"
    )
    analytical.assign_to_batch(actor=people["analyst"], test=assay, batch=batch, reason="Run")
    analytical.record_qc(
        actor=people["analyst"],
        batch=batch,
        check_code="control",
        value=Decimal("90"),
        raw_reference="NB-SYN-QC p1",
    )
    lot = reject(data)
    # The batch's rejection page counts no test of the rejected lot as invalidated.
    client.force_login(people["reviewer"])
    page = client.get(reverse("analytical:batch_reject", args=[batch.pk])).content.decode()
    assert "<dt>Tests invalidated</dt><dd>0</dd>" in page
    batch.refresh_from_db()
    analytical.reject_batch(
        actor=people["reviewer"],
        pin=PIN,
        batch=batch,
        expected_revision=batch.revision,
        reason="Control out of limits",
    )
    batch.refresh_from_db()
    assay.refresh_from_db()
    assert batch.state == "rejected"
    # The rejected lot's test stays as the rejection froze it; no rerun is added to the lot.
    assert assay.state == "open" and not AnalyticalTest.objects.filter(parent=assay).exists()
    assert fresh(data).revision == lot.revision


def test_a_lot_received_in_error_is_cancelled(received):
    people = received["people"]
    lot = fresh(received)
    preview = rejection.cancellation_preview(lot)
    assert preview.possible
    # The analyst received the lot; whoever recorded it does not cancel it.
    assert rejection.cancellation_denial(people["analyst"], lot) == rejection.SELF_CANCELLATION
    with pytest.raises(ValidationError, match="Another quality person must sign"):
        cancel(received, who="analyst")

    cancelled = cancel(received, reference="DEV-SYN-002")

    assert cancelled.state == "cancelled" and cancelled.revision == lot.revision + 1
    evidence = cancelled.disposition_evidence
    assert evidence["schema"] == "oq.lot-cancellation/1" and evidence["decision"] == "cancelled"
    assert evidence["reference"] == "DEV-SYN-002" and evidence["requirements"] is None
    assert evidence["receipt"]["shipment_ref"] == on_site_receipt()["shipment_ref"]
    assert "grounds" not in evidence and "tests" not in evidence
    event = AuditEvent.objects.get(action="signed.cancelled")
    assert event.reason == "Synthetic: the delivery was recorded twice"
    with pytest.raises(ValidationError, match="cancelled as received in error"):
        reject(received, basis="0" * 64)
    with pytest.raises(ValidationError, match="Only quarantined lots"):
        sampling.assign_requirements(
            actor=people["analyst"],
            lot=cancelled,
            material=received["material"],
            stage="incoming",
            reason="Assign",
        )


def test_a_cancelled_lot_has_no_material_to_keep_or_hold(received):
    people = received["people"]
    lot = cancel(received)
    with pytest.raises(ValidationError, match="it has no material"):
        stability.place_hold(
            actor=people["reviewer"], lot=lot, kind=Hold.Kind.INVESTIGATION, reason="Hold"
        )
    with pytest.raises(ValidationError, match="it has no material"):
        stability.record_reserve(
            actor=people["analyst"],
            lot=lot,
            reason="Retain",
            identifier="RSV-SYN-1",
            retained_on=timezone.localdate(),
            **RESERVE,
        )


RESERVE = {
    "container_description": "Synthetic jar",
    "storage_location": "Synthetic shelf",
    "quantity": Decimal("10"),
    "test_quantity": Decimal("1"),
    "quantity_unit": "g",
    "minimum_multiple": Decimal("2"),
}


def test_a_lot_whose_material_was_sampled_is_rejected_not_cancelled(world):
    preview = rejection.cancellation_preview(fresh(world))
    assert not preview.possible
    assert preview.reasons[0] == "Samples were taken from this lot: SYN-RT-S001."
    assert "reject it" in preview.reasons[-1]
    with pytest.raises(ValidationError, match="Samples were taken from this lot"):
        cancel(world)
    assert fresh(world).state == "quarantine"


def test_a_lot_with_a_reserve_sample_is_not_cancelled(received):
    stability.record_reserve(
        actor=received["people"]["analyst"],
        lot=fresh(received),
        reason="Retain",
        identifier="RSV-SYN-2",
        retained_on=timezone.localdate() - timedelta(days=1),
        **RESERVE,
    )
    preview = rejection.cancellation_preview(fresh(received))
    assert preview.reasons[0] == "Reserve samples were recorded for this lot: RSV-SYN-2."
    with pytest.raises(ValidationError, match="Reserve samples were recorded"):
        cancel(received)
    assert fresh(received).state == "quarantine"


def test_whoever_created_a_lot_does_not_cancel_it(received):
    people = received["people"]
    # A lot received before receipt details were kept names only its creator.
    legacy = Lot.objects.create(
        number="SYN-RT-LEGACY",
        material=received["material"].name,
        rules=fresh(received).rules,
        created_by=people["approver"],
    )
    assert rejection.cancellation_denial(people["approver"], legacy) == rejection.SELF_CANCELLATION
    assert rejection.cancellation_denial(people["author"], legacy) == ""
    assert rejection.cancellation_preview(legacy).evidence["receipt"] is None
    cancelled = cancel({"lot": legacy, "people": people}, who="author")
    assert cancelled.state == "cancelled"
