"""Protocol, study, pull, reserve, retention and hold contracts against PostgreSQL."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature
from laboratory.tests.helpers import make_equipment
from stability import gates, services
from stability.evidence import sample_evidence
from stability.models import (
    Hold,
    Protocol,
    ProtocolCondition,
    ProtocolTimepoint,
    Pull,
    ReserveSample,
    RetentionObligation,
    Study,
    add_months,
)
from stability.services import protocol_digest

from .helpers import (
    PIN,
    approved_protocol,
    make_lot,
    make_sample,
    review_sample,
    sample_with_result,
    started_study,
)

pytestmark = pytest.mark.django_db(transaction=True)


def record(people, pull, **overrides):
    values = {
        "actor": people["analyst"],
        "pull": pull,
        "pulled_on": timezone.localdate(),
        "quantity": "10",
        "quantity_unit": "g",
        "storage_location": "Synthetic cabinet",
        "reason": "Synthetic pull",
    }
    values.update(overrides)
    return services.record_pull(**values)


def pull_for(study, days):
    return study.pulls.get(timepoint__interval_days=days)


def accept(people, pull, actor="reviewer"):
    pull.refresh_from_db()
    return services.accept_pull(
        actor=people[actor],
        pin=PIN,
        pull=pull,
        expected_revision=pull.revision,
        reason="Evidence reviewed",
    )


# --- Protocols -------------------------------------------------------------------------------


def test_protocol_signature_binds_the_complete_content(people):
    protocol = approved_protocol(people)
    signature = ElectronicSignature.objects.get(object_type="stability.protocol")
    assert signature.meaning == "approved" and signature.signer == people["quality"]
    assert signature.content["content_digest"] == protocol_digest(protocol)
    assert signature.revision == protocol.revision
    assert protocol.state == "approved" and protocol.approved_at


def test_author_cannot_approve_and_incomplete_protocols_are_refused(people):
    author = people["analyst"]
    protocol = services.create_protocol(
        actor=author,
        code="P",
        title="T",
        product="X",
        document_ref="D",
        document_url="",
        test_profile_ref="",
        basis="B",
        reason="Draft",
    )
    people["analyst"].groups.add(people["quality"].groups.get())
    with pytest.raises(PermissionDenied, match="author"):
        services.approve_protocol(
            actor=author, pin=PIN, protocol=protocol, expected_revision=1, reason="Self"
        )
    with pytest.raises(ValidationError, match="no storage conditions"):
        services.approve_protocol(
            actor=people["quality"], pin=PIN, protocol=protocol, expected_revision=1, reason="Empty"
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
    protocol.refresh_from_db()
    with pytest.raises(ValidationError, match="at least one timepoint"):
        services.approve_protocol(
            actor=people["quality"],
            pin=PIN,
            protocol=protocol,
            expected_revision=protocol.revision,
            reason="No timepoint",
        )
    assert condition.pk and not ElectronicSignature.objects.exists()


def test_content_added_after_review_makes_the_signature_stale(people):
    author = people["analyst"]
    protocol = services.create_protocol(
        actor=author,
        code="P",
        title="T",
        product="X",
        document_ref="D",
        document_url="",
        test_profile_ref="",
        basis="B",
        reason="Draft",
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
    reviewed_revision = protocol.revision
    services.add_timepoint(
        actor=author,
        protocol=protocol,
        condition=condition,
        label="2m",
        interval_days=60,
        window_days=2,
        test_codes=["identity"],
        reason="Added while the approver was reviewing",
    )
    with pytest.raises(ValidationError, match="Record changed"):
        services.approve_protocol(
            actor=people["quality"],
            pin=PIN,
            protocol=protocol,
            expected_revision=reviewed_revision,
            reason="Stale",
        )
    with pytest.raises(PermissionDenied):
        services.add_condition(
            actor=people["quality"],
            protocol=protocol,
            label="D",
            setpoint="S",
            temperature_c=None,
            humidity_pct=None,
            reason="Not the author",
        )


def test_approved_protocol_is_frozen_and_new_version_supersedes(people):
    v1 = approved_protocol(people)
    with pytest.raises(ValidationError, match="frozen"):
        services.add_condition(
            actor=people["analyst"],
            protocol=v1,
            label="Late",
            setpoint="S",
            temperature_c=None,
            humidity_pct=None,
            reason="Late",
        )
    condition = v1.conditions.get()
    with pytest.raises(DatabaseError), transaction.atomic():
        ProtocolCondition.objects.create(protocol=v1, label="Sneaky", setpoint="S")
    with pytest.raises(DatabaseError), transaction.atomic():
        ProtocolTimepoint.objects.filter(condition=condition).update(window_days=99)
    with pytest.raises(DatabaseError), transaction.atomic():
        Protocol.objects.filter(pk=v1.pk).update(title="Changed")
    v2 = approved_protocol(people)
    v1.refresh_from_db()
    assert (v2.version, v1.state, v2.state) == (2, "superseded", "approved")
    assert AuditEvent.objects.filter(action="protocol.superseded").count() == 1
    with pytest.raises(ValidationError, match="current approved"):
        started_study(people, protocol=v1)


# --- Studies and pulls -----------------------------------------------------------------------


def test_study_schedules_one_pull_per_timepoint(people):
    study = started_study(people)
    assert study.rule_basis.startswith("rules-SYN-LOT-1 v1")
    due = {p.timepoint.interval_days: p.due_date for p in study.pulls.all()}
    assert due == {d: study.start_date + timedelta(days=d) for d in (30, 100, 180)}
    with pytest.raises(ValidationError):
        started_study(people, protocol=study.protocol, lot=study.lot)


def test_pull_window_deviation_future_date_and_state(people):
    study = started_study(people)
    on_time = pull_for(study, 100)
    with pytest.raises(ValidationError, match="future"):
        record(people, on_time, pulled_on=timezone.localdate() + timedelta(days=1))
    late = pull_for(study, 30)
    with pytest.raises(ValidationError, match="outside its window"):
        record(people, late)
    recorded = record(people, late, deviation_reason="Chamber door fault")
    assert recorded.state == "pulled" and recorded.deviation_reason
    with pytest.raises(ValidationError, match="not awaiting"):
        record(people, late, deviation_reason="Again")
    with pytest.raises(PermissionDenied):
        record(people, on_time, actor=people["reviewer"])
    assert record(people, on_time).pulled_by == people["analyst"]


def test_chamber_must_be_fit_and_use_is_recorded(people):
    study = started_study(people)
    pull = pull_for(study, 100)
    broken = make_equipment(people, "CH-BAD", ready=False)
    with pytest.raises(ValidationError, match="CH-BAD"):
        record(people, pull, chamber=broken)
    pull.refresh_from_db()
    assert pull.state == "scheduled"
    chamber = make_equipment(people, "CH-OK")
    record(people, pull, chamber=chamber)
    from laboratory.models import ResourceUse

    use = ResourceUse.objects.get()
    assert use.context_type == "stability.pull" and use.equipment == chamber


def test_evidence_link_rules(people):
    study = started_study(people)
    pull = record(people, pull_for(study, 100))
    with pytest.raises(ValidationError, match="Link a sample"):
        services.attach_pull_evidence(actor=people["analyst2"], pull=pull, reason="None")
    other = sample_with_result(
        people,
        started_study(
            people, lot=make_lot(people, "OTHER"), protocol=study.protocol, identifier="STB-2"
        ),
        reference="OTHER-S",
    )
    with pytest.raises(ValidationError, match="different lot"):
        services.attach_pull_evidence(
            actor=people["analyst2"], pull=pull, sample_reference=other.reference, reason="Wrong"
        )
    with pytest.raises(ValidationError, match="No sample"):
        services.attach_pull_evidence(
            actor=people["analyst2"], pull=pull, sample_reference="NOPE", reason="Missing"
        )
    linked = services.attach_pull_evidence(
        actor=people["analyst2"],
        pull=pull,
        external_sample_ref="EXT-1",
        evidence_ref="EXT-EVID-1",
        reason="External system record",
    )
    assert linked.evidence_recorded_by == people["analyst2"]
    event = AuditEvent.objects.filter(action="pull.evidence_linked").latest("occurred_at")
    assert (
        event.before["external_sample_ref"] == "" and event.after["external_sample_ref"] == "EXT-1"
    )


def test_accept_requires_independent_reviewer_and_complete_reviewed_testing(people):
    study = started_study(people)
    pull = record(people, pull_for(study, 100))
    people["analyst2"].groups.add(people["reviewer"].groups.get())
    with pytest.raises(ValidationError, match="Link a sample"):
        accept(people, pull)
    sample = sample_with_result(people, study, state="submitted")
    services.attach_pull_evidence(
        actor=people["analyst2"], pull=pull, sample_reference=sample.reference, reason="Linked"
    )
    with pytest.raises(ValidationError, match="not yet reviewed"):
        accept(people, pull)
    # The documenting analyst and the puller cannot accept, even holding the reviewer role.
    people["analyst"].groups.add(people["reviewer"].groups.get())
    for actor in ("analyst", "analyst2"):
        with pytest.raises(PermissionDenied, match="pulled or documented"):
            accept(people, pull, actor)
    review_sample(people, sample)
    accepted = accept(people, pull)
    assert accepted.state == "accepted" and accepted.accepted_at
    signature = ElectronicSignature.objects.get(object_type="stability.pull")
    assert signature.meaning == "reviewed" and signature.content["state"] == "accepted"
    with pytest.raises(DatabaseError), transaction.atomic():
        Pull.objects.filter(pk=pull.pk).update(storage_location="elsewhere")


def test_out_of_specification_testing_blocks_acceptance(people):
    study = started_study(people)
    pull = record(people, pull_for(study, 100))
    sample = sample_with_result(people, study, value="2.0")
    services.attach_pull_evidence(
        actor=people["analyst2"], pull=pull, sample_reference=sample.reference, reason="Linked"
    )
    with pytest.raises(ValidationError, match="is open"):
        accept(people, pull)
    pull.refresh_from_db()
    assert pull.state == "pulled"
    assert not ElectronicSignature.objects.filter(object_type="stability.pull").exists()


def test_external_evidence_path_and_stale_signature(people):
    study = started_study(people)
    pull = record(people, pull_for(study, 100))
    services.attach_pull_evidence(
        actor=people["analyst2"],
        pull=pull,
        external_sample_ref="EXT-1",
        evidence_ref="EXT-EVID-1",
        reason="External record",
    )
    pull.refresh_from_db()
    with pytest.raises(ValidationError, match="Record changed"):
        services.accept_pull(
            actor=people["reviewer"],
            pin=PIN,
            pull=pull,
            expected_revision=pull.revision - 1,
            reason="Stale",
        )
    assert accept(people, pull).state == "accepted"


def test_missed_pull_needs_closed_window_and_is_permanent(people):
    study = started_study(people)
    with pytest.raises(ValidationError, match="not closed"):
        services.mark_pull_missed(actor=people["analyst"], pull=pull_for(study, 100), reason="x")
    missed = services.mark_pull_missed(
        actor=people["analyst"], pull=pull_for(study, 30), reason="Chamber outage"
    )
    assert missed.state == "missed"
    with pytest.raises(DatabaseError), transaction.atomic():
        Pull.objects.filter(pk=missed.pk).update(state="scheduled")
    with pytest.raises(ValidationError):
        record(people, missed, deviation_reason="Retroactive")


def test_close_study_rules(people):
    study = started_study(people)
    kwargs = {
        "pin": PIN,
        "study": study,
        "expected_revision": study.revision,
        "reason": "Close",
        "outcome": "completed",
    }
    people["analyst"].groups.add(people["quality"].groups.get())
    with pytest.raises(PermissionDenied, match="started"):
        services.close_study(actor=people["analyst"], **kwargs)
    with pytest.raises(ValidationError, match="not accepted or missed"):
        services.close_study(actor=people["quality"], **kwargs)
    closed = services.close_study(actor=people["quality"], **{**kwargs, "outcome": "terminated"})
    assert closed.state == "terminated"
    with pytest.raises(ValidationError, match="already closed"):
        services.close_study(
            actor=people["quality2"], **{**kwargs, "expected_revision": closed.revision}
        )
    with pytest.raises(ValidationError, match="no longer active"):
        record(people, pull_for(study, 100))
    with pytest.raises(DatabaseError), transaction.atomic():
        Study.objects.filter(pk=study.pk).update(container_closure="changed")


# --- Reserve and retention -------------------------------------------------------------------


def make_reserve(people, lot, identifier="RES-1", quantity="25", test_quantity="10"):
    return services.record_reserve(
        actor=people["analyst"],
        lot=lot,
        identifier=identifier,
        container_description="Full synthetic package",
        storage_location="Cabinet A",
        quantity=quantity,
        test_quantity=test_quantity,
        quantity_unit="g",
        minimum_multiple="2",
        retained_on=timezone.localdate(),
        reason="Synthetic reserve",
    )


def test_add_months_clamps_and_crosses_years():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 10), 14) == date(2028, 1, 10)
    assert add_months(date(2026, 12, 31), 12) == date(2027, 12, 31)


def test_reserve_quantity_check_and_immutability(people):
    lot = make_lot(people)
    enough = make_reserve(people, lot)
    short = make_reserve(people, lot, "RES-2", quantity="15")
    assert enough.meets_minimum and not short.meets_minimum
    with pytest.raises(ValidationError):
        make_reserve(people, lot, "RES-3", test_quantity="0")
    with pytest.raises(DatabaseError), transaction.atomic():
        ReserveSample.objects.filter(pk=enough.pk).update(quantity=1)
    with pytest.raises(DatabaseError), transaction.atomic():
        ReserveSample.objects.filter(pk=enough.pk).delete()


def test_every_obligation_and_hold_must_clear_before_disposal(people):
    lot = make_lot(people)
    reserve = make_reserve(people, lot)
    today = timezone.localdate()
    assert "No retention obligation" in gates.disposal_blockers(lot, reserve, today)[0]
    expiry = services.add_obligation(
        actor=people["analyst"],
        lot=lot,
        reserve=reserve,
        anchor_kind="expiry",
        anchor_date=today - timedelta(days=400),
        offset_months=12,
        basis="Synthetic basis A",
        reason="Basis A",
    )
    distribution = services.add_obligation(
        actor=people["analyst"],
        lot=lot,
        reserve=reserve,
        anchor_kind="last_distribution",
        anchor_date=None,
        offset_months=24,
        basis="Synthetic basis B",
        reason="Basis B",
    )
    assert expiry.retain_until < today
    blockers = gates.disposal_blockers(lot, reserve, today)
    assert len(blockers) == 1 and "not yet known" in blockers[0]
    set_ = services.set_anchor(
        actor=people["analyst"],
        obligation=distribution,
        anchor_date=today - timedelta(days=10),
        reason="Distribution record found",
    )
    assert "runs through" in gates.disposal_blockers(lot, reserve, today)[0]
    boundary = set_.retain_until
    assert gates.disposal_blockers(lot, reserve, boundary)  # inclusive on the last day
    assert not gates.disposal_blockers(lot, reserve, boundary + timedelta(days=1))
    services.place_hold(
        actor=people["reviewer"], lot=lot, kind="legal", reason="Matter 1", reserve=reserve
    )
    assert "HOLD-" in gates.disposal_blockers(lot, reserve, boundary + timedelta(days=1))[0]
    with pytest.raises(ValidationError, match="already set"):
        services.set_anchor(
            actor=people["analyst"], obligation=distribution, anchor_date=today, reason="Move"
        )
    for attempt in (
        lambda: RetentionObligation.objects.filter(pk=distribution.pk).update(anchor_date=today),
        lambda: RetentionObligation.objects.filter(pk=expiry.pk).update(offset_months=0),
        lambda: RetentionObligation.objects.filter(pk=expiry.pk).delete(),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            attempt()


def test_obligation_must_match_the_reserve_lot(people):
    reserve = make_reserve(people, make_lot(people))
    with pytest.raises(ValidationError, match="different lot"):
        services.add_obligation(
            actor=people["analyst"],
            lot=make_lot(people, "OTHER"),
            reserve=reserve,
            anchor_kind="expiry",
            anchor_date=None,
            offset_months=12,
            basis="B",
            reason="x",
        )


# --- Holds -----------------------------------------------------------------------------------


def test_hold_blocks_disposition_and_stales_in_flight_signatures(people):
    lot = make_lot(people)
    revision = lot.revision
    hold = services.place_hold(
        actor=people["analyst"],
        lot=lot,
        kind="investigation",
        reason="Complaint 12",
        reference="INV-9",
    )
    lot.refresh_from_db()
    assert lot.revision == revision + 1  # an open disposition signature now fails as stale
    assert "HOLD-" in gates.lot_blockers(lot)[0] and "Complaint 12" in gates.lot_blockers(lot)[0]
    assert gates.lot_hold_evidence(lot)["holds"][0]["state"] == "active"
    with pytest.raises(PermissionDenied):
        services.place_hold(actor=people["auditor"], lot=lot, kind="quality", reason="No")
    people["analyst"].groups.add(people["quality"].groups.get())
    with pytest.raises(PermissionDenied, match="placed"):
        services.release_hold(
            actor=people["analyst"], pin=PIN, hold=hold, expected_revision=1, reason="Self release"
        )
    with pytest.raises(ValidationError, match="Record changed"):
        services.release_hold(
            actor=people["quality"], pin=PIN, hold=hold, expected_revision=5, reason="Stale"
        )
    released = services.release_hold(
        actor=people["quality"],
        pin=PIN,
        hold=hold,
        expected_revision=1,
        reason="Investigation closed",
    )
    assert released.state == "released" and not gates.lot_blockers(lot)
    signature = ElectronicSignature.objects.get(object_type="stability.hold")
    assert signature.meaning == "approved" and signature.content["state"] == "released"
    with pytest.raises(ValidationError, match="already released"):
        services.release_hold(
            actor=people["quality2"],
            pin=PIN,
            hold=released,
            expected_revision=released.revision,
            reason="Again",
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        Hold.objects.filter(pk=hold.pk).update(state="active", released_at=None)


def test_hold_on_released_lot_does_not_need_the_immutable_lot_row(people):
    from quality.models import Lot

    lot = make_lot(people)
    Lot.objects.filter(pk=lot.pk).update(state="released")
    lot.refresh_from_db()
    hold = services.place_hold(
        actor=people["quality"], lot=lot, kind="regulatory", reason="Recall review"
    )
    assert hold.state == "active" and gates.lot_blockers(lot)
    released = services.release_hold(
        actor=people["quality2"], pin=PIN, hold=hold, expected_revision=1, reason="Cleared"
    )
    assert released.state == "released"


# --- Review regressions ----------------------------------------------------------------------


def test_one_sample_cannot_be_evidence_for_two_pulls(people):
    study = started_study(people)
    first = record(people, pull_for(study, 100))
    second = record(people, pull_for(study, 30), deviation_reason="Late")
    sample = sample_with_result(people, study)
    services.attach_pull_evidence(
        actor=people["analyst2"], pull=first, sample_reference=sample.reference, reason="First"
    )
    with pytest.raises(ValidationError, match="already evidence"):
        services.attach_pull_evidence(
            actor=people["analyst2"],
            pull=second,
            sample_reference=sample.reference,
            reason="Reuse across timepoints",
        )
    second.refresh_from_db()
    assert second.sample_id is None
    with pytest.raises(DatabaseError), transaction.atomic():
        Pull.objects.filter(pk=second.pk).update(sample=sample)  # the database refuses too


def test_sample_must_be_collected_on_the_pull_date(people):
    study = started_study(people)
    pull = record(people, pull_for(study, 100))
    old = make_sample(people, study.lot, "OLD-S", collected_at=timezone.now() - timedelta(days=3))
    with pytest.raises(ValidationError, match="not on the pull date"):
        services.attach_pull_evidence(
            actor=people["analyst2"],
            pull=pull,
            sample_reference=old.reference,
            reason="Pre-storage sample",
        )
    # A pull dated early cannot borrow a later sample either (no false Jan 1 sampling).
    early = record(
        people,
        pull_for(study, 30),
        pulled_on=timezone.localdate() - timedelta(days=60),
        deviation_reason="Early pull",
    )
    with pytest.raises(ValidationError, match="not on the pull date"):
        services.attach_pull_evidence(
            actor=people["analyst2"],
            pull=early,
            sample_reference=sample_with_result(people, study, reference="LATE-S").reference,
            reason="Later sample for an earlier pull",
        )
    pull.refresh_from_db()
    assert pull.sample_id is None


def test_tests_created_before_the_pull_do_not_count(people):
    study = started_study(people)
    sample = sample_with_result(people, study)
    blockers, evidence = sample_evidence(
        sample, ["identity"], not_before=timezone.now() + timedelta(hours=1)
    )
    assert evidence == [] and any("before the pull" in b for b in blockers)
    assert sample_evidence(sample, ["identity"], not_before=timezone.now() - timedelta(days=1))[1]
