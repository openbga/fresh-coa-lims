"""A stability pull tested in the system: its tests belong to the pull, run through the
testing services and never touch the record of the study's lot (synthetic data only)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from analytical import gates
from analytical import services as analytical
from analytical.contracts import canonical_hash
from analytical.models import AnalyticalTest, Investigation, Observation
from catalog import services as catalog
from core.models import AuditEvent, ElectronicSignature
from quality.models import Lot, Sample
from stability import evidence, services, testing
from stability.models import ProtocolCondition, Pull, Study

from .helpers import (
    PIN,
    accept,
    add_line,
    approve_revision,
    approved_protocol,
    assign,
    draft_protocol,
    lot_of,
    make_lot,
    observe,
    pulled,
    review,
    reviewed,
    shelf_life,
    shown_criteria,
    specified_study,
    started_study,
    submit,
)

pytestmark = pytest.mark.django_db(transaction=True)


def lot_record(lot):
    """Everything a stability test could leak into, as one comparable value."""
    lot = Lot.objects.get(pk=lot.pk)
    return {
        "lot": (lot.state, lot.revision, lot.disposition_evidence),
        "samples": sorted(Sample.objects.filter(lot=lot).values_list("pk", flat=True)),
        "tests": sorted(AnalyticalTest.objects.filter(lot=lot).values_list("pk", flat=True)),
        "investigations": sorted(
            Investigation.objects.filter(lot=lot).values_list("pk", flat=True)
        ),
        "status": gates.lot_status(lot)[0],
        "evidence": gates.lot_evidence(lot),
        "authors": sorted(gates.lot_author_ids(lot)),
        "history": AuditEvent.objects.filter(
            object_type="quality.lot", object_id=str(lot.pk)
        ).count(),
    }


def test_tests_of_a_pull_freeze_the_protocol_criteria_and_name_no_lot(people):
    study, config = specified_study(people)
    pull = pulled(people, study)
    before, revision = lot_record(study.lot), pull.revision
    (test,) = assign(people, pull)
    assert (test.lot_id, test.sample_id, test.pull_id) == (None, None, pull.pk)
    assert test.kind == "original" and test.state == "open"
    spec = config["revision"]
    assert test.requirement["source"] == (
        f"catalog:syn-shelf-life@v{spec.version}#rev{spec.pk}/stability:SYN-STAB-TESTED@v1"
    )
    assert test.requirement_hash == canonical_hash(test.requirement)
    assert test.spec.acceptance and test.spec.method.code == "syn-shelf-assay"
    pull.refresh_from_db()
    assert pull.revision == revision + 1  # an acceptance opened before is stale
    assert lot_record(study.lot) == before
    event = AuditEvent.objects.get(action="test.assigned", object_id=str(test.pk))
    assert event.after["pull"] == pull.pk and event.actor == people["analyst2"]
    # Assigning again creates nothing and changes nothing.
    assert assign(people, pull) == []
    pull.refresh_from_db()
    assert pull.revision == revision + 1


def test_assigning_is_refused_without_role_reason_or_an_open_pull(people):
    study, _ = specified_study(people)
    scheduled = study.pulls.get(timepoint__interval_days=30)
    with pytest.raises(ValidationError, match="Record the pull before testing it"):
        assign(people, scheduled)
    pull = pulled(people, study)
    with pytest.raises(PermissionDenied):
        analytical.assign_pull_tests(
            actor=people["reviewer"], pull=pull, reason="No role", criteria_hash=""
        )
    with pytest.raises(ValidationError, match="reason"):
        analytical.assign_pull_tests(
            actor=people["analyst2"], pull=pull, reason=" ", criteria_hash=""
        )
    assert not AnalyticalTest.objects.exists()


def test_a_protocol_without_a_specification_is_not_tested_here(people):
    study = started_study(people)
    pull = pulled(people, study)
    with pytest.raises(ValidationError, match="names no specification"):
        assign(people, pull)
    assert testing.assignment_refusal(pull) == testing.NO_SPECIFICATION
    assert not AnalyticalTest.objects.exists()


def test_without_the_configured_source_no_pull_is_tested(people, settings):
    study, _ = specified_study(people)
    pull = pulled(people, study)
    settings.ANALYTICAL_STABILITY_PULLS = ""
    with pytest.raises(ValidationError, match="not configured"):
        assign(people, pull)
    assert not AnalyticalTest.objects.exists()


def test_a_pull_keeps_one_kind_of_evidence(people):
    study, _ = specified_study(people)
    linked = pulled(people, study, 30)
    services.attach_pull_evidence(
        actor=people["analyst"],
        pull=linked,
        external_sample_ref="EXT-1",
        evidence_ref="EXT-REPORT-1",
        reason="External record",
    )
    with pytest.raises(ValidationError, match="external system"):
        assign(people, linked)
    tested = pulled(people, study, 100)
    assign(people, tested)
    with pytest.raises(ValidationError, match="tested in the system"):
        services.attach_pull_evidence(
            actor=people["analyst"],
            pull=tested,
            external_sample_ref="EXT-2",
            evidence_ref="EXT-REPORT-2",
            reason="External record",
        )
    tested.refresh_from_db()
    assert tested.external_sample_ref == "" and tested.evidence_ref == ""


def test_assignment_holds_when_the_specification_cannot_answer_a_test(people):
    config = shelf_life(people)
    protocol = approved_protocol(
        people, code="SYN-HELD", specification=config["specification"], test_codes=("assay",)
    )
    study = started_study(people, protocol=protocol, lot=lot_of(people, config["material"]))
    pull = pulled(people, study)
    # A later version that no longer states the test takes over.
    later = catalog.new_specification_revision(
        actor=people["quality"],
        specification=config["specification"],
        basis="Synthetic revision without the assay",
        effective_from=timezone.now(),
        effective_until=timezone.now() + timedelta(days=200),
        reason="Synthetic revision",
    )
    # A new version starts with the lines of the one before it.
    catalog.remove_test_line(
        actor=people["quality"], line=later.tests.get(code="assay"), reason="No longer tested"
    )
    add_line(people, later, "water", method=config["method"])
    approve_revision(people, later)
    with pytest.raises(ValidationError, match="v2 does not state assay"):
        assign(people, pull)
    assert not AnalyticalTest.objects.exists()
    pull.refresh_from_db()
    assert pull.revision == 2  # recorded once, nothing since


def test_protocol_approval_needs_the_specification_to_state_every_test(people):
    config = shelf_life(people)
    draft = draft_protocol(
        people,
        code="SYN-MISSING",
        specification=config["specification"],
        test_codes=("assay", "water"),
    )
    with pytest.raises(ValidationError, match="does not state water"):
        services.approve_protocol(
            actor=people["quality"],
            pin=PIN,
            protocol=draft,
            expected_revision=draft.revision,
            reason="Independent approval",
        )
    draft.refresh_from_db()
    assert draft.state == "draft"
    assert testing.protocol_problems(draft) and not ElectronicSignature.objects.filter(
        object_type="stability.protocol", object_id=str(draft.pk)
    )


def test_the_specification_of_a_protocol_is_fixed_from_creation(people):
    config = shelf_life(people)
    draft = draft_protocol(people, code="SYN-FIXED", specification=config["specification"])
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        type(draft).objects.filter(pk=draft.pk).update(specification=None)


def test_a_study_needs_a_lot_of_the_specification_material(people):
    config = shelf_life(people)
    protocol = approved_protocol(
        people, code="SYN-MAT", specification=config["specification"], test_codes=("assay",)
    )
    with pytest.raises(ValidationError, match="has no requirements assigned"):
        started_study(people, protocol=protocol, lot=make_lot(people, "SYN-UNASSIGNED"))
    other = catalog.create_material(
        actor=people["quality"],
        code="syn-other",
        name="Other synthetic material",
        kind="finished_product",
        reason="Synthetic master data",
    )
    with pytest.raises(ValidationError, match="is syn-other"):
        started_study(people, protocol=protocol, lot=lot_of(people, other, "SYN-OTHER"))
    assert not Study.objects.exists()


def test_a_pull_is_tested_reviewed_and_accepted_with_its_outcome(people):
    study, _ = specified_study(people)
    pull = pulled(people, study)
    before = lot_record(study.lot)
    (test,) = assign(people, pull)
    with pytest.raises(ValidationError, match="Testing is not complete.*incomplete"):
        accept(people, pull)
    observe(people, test, "100.2")
    _, investigation = submit(people, test)
    assert investigation is None
    with pytest.raises(ValidationError, match="awaits independent review"):
        accept(people, pull)
    with pytest.raises(PermissionDenied):
        review(people, test, reviewer="analyst2")  # analyst2 holds no reviewer role
    people["analyst2"].groups.add(people["reviewer"].groups.get())
    with pytest.raises(ValidationError, match="own test"):
        review(people, test, reviewer="analyst2")
    signed = review(people, test)
    assert signed.state == "reviewed" and signed.conforms
    assert ElectronicSignature.objects.filter(
        object_type="analytical.analyticaltest", object_id=str(test.pk), meaning="reviewed"
    ).exists()
    blockers, rows, outcome = evidence.pull_results(pull)
    assert (blockers, outcome) == ([], "conforms") and rows[0]["tests"] == [signed]
    # Whoever produced the data does not accept the pull, whatever roles they hold.
    with pytest.raises(PermissionDenied):
        accept(people, pull, reviewer="analyst2")
    accepted = accept(people, pull)
    assert (accepted.state, accepted.outcome) == ("accepted", "conforms")
    frozen = accepted.result_evidence
    assert frozen["schema"] == "stability.pull-results/1" and frozen["outcome"] == "conforms"
    (result,) = frozen["results"]
    assert result["test_code"] == "assay" and result["outcome"] == "conforms"
    assert result["tests"][0]["reportable"] == "100.2"
    assert result["tests"][0]["review"]["signer"]
    assert result["tests"][0]["requirement_hash"] == test.requirement_hash
    assert people["analyst2"].pk in frozen["author_ids"]
    signature = ElectronicSignature.objects.get(
        object_type="stability.pull", object_id=str(pull.pk), meaning="reviewed"
    )
    assert signature.content["result_evidence"] == frozen  # the signature binds the results
    assert lot_record(study.lot) == before


def test_evidence_changes_make_an_open_acceptance_stale(people):
    study, _ = specified_study(people, codes=("assay", "water"))
    pull = pulled(people, study)
    assay, water = sorted(assign(people, pull), key=lambda t: t.test_code)
    reviewed(people, assay)
    pull.refresh_from_db()
    shown = pull.revision
    observe(people, water, "99.0")  # recorded after the acceptance page was opened
    with pytest.raises(ValidationError, match="Record changed"):
        services.accept_pull(
            actor=people["reviewer"],
            pin=PIN,
            pull=pull,
            expected_revision=shown,
            reason="Stale acceptance",
        )
    pull.refresh_from_db()
    assert pull.state == "pulled" and pull.revision == shown + 1


def test_a_failing_result_holds_the_pull_and_never_the_lot(people):
    study, _ = specified_study(people)
    pull = pulled(people, study)
    before = lot_record(study.lot)
    (test,) = assign(people, pull)
    observe(people, test, "91.0")
    submitted, investigation = submit(people, test)
    assert submitted.conforms is False
    assert investigation.lot_id is None and investigation.is_stability
    assert investigation.test_id == test.pk
    review(people, test)
    with pytest.raises(ValidationError, match=f"{investigation.label} is open"):
        accept(people, pull)
    assert lot_record(study.lot) == before
    assert gates.lot_blockers(study.lot) == before["status"]


def invalidate_with_retest(people, pull, test, investigation):
    analytical.add_entry(
        actor=people["analyst2"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic assessment: dilution error found in the notebook",
    )
    investigation.refresh_from_db()
    with pytest.raises(ValidationError, match="no other sample"):
        analytical.authorize_retest(
            actor=people["quality"],
            pin=PIN,
            investigation=investigation,
            expected_revision=investigation.revision,
            kind="resample",
            reason="A resample is not possible for a pull",
        )
    analytical.authorize_retest(
        actor=people["quality"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        kind="retest",
        reason="Retest of the pulled material",
    )
    retest = AnalyticalTest.objects.get(parent=test)
    assert (retest.pull_id, retest.lot_id, retest.sample_id) == (pull.pk, None, None)
    assert retest.kind == "retest" and retest.investigation_id == investigation.pk
    return retest


def test_an_invalidated_failure_is_answered_by_the_retest(people):
    study, _ = specified_study(people)
    pull = pulled(people, study)
    before = lot_record(study.lot)
    (test,) = assign(people, pull)
    _, investigation = reviewed(people, test, "91.0")
    retest = invalidate_with_retest(people, pull, test, investigation)
    reviewed(people, retest, "99.4")
    investigation.refresh_from_db()
    analytical.conclude(
        actor=people["quality2"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="invalidated",
        assignable_cause="Synthetic dilution error",
        reason="Original invalid; the retest stands",
    )
    blockers, rows, outcome = evidence.pull_results(pull)
    assert (blockers, outcome) == ([], "conforms")
    assert [t.pk for t in rows[0]["tests"]] == [retest.pk]
    accepted = accept(people, pull)
    assert accepted.outcome == "conforms"
    result = accepted.result_evidence["results"][0]
    assert [t["test"] for t in result["tests"]] == [retest.pk]
    assert result["excluded_tests"] == [
        {"test": test.pk, "kind": "original", "state": "invalidated"}
    ]
    assert accepted.result_evidence["investigations"][0]["outcome"] == "invalidated"
    assert lot_record(study.lot) == before


def test_a_confirmed_failure_closes_the_pull_with_the_outcome_fails(people):
    study, _ = specified_study(people, intervals=(30, 100))
    pull = pulled(people, study)
    before = lot_record(study.lot)
    (test,) = assign(people, pull)
    _, investigation = reviewed(people, test, "91.0")
    analytical.add_entry(
        actor=people["analyst2"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic assessment: no laboratory error found",
    )
    investigation.refresh_from_db()
    analytical.conclude(
        actor=people["quality2"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="confirmed",
        assignable_cause="",
        reason="Out-of-specification result confirmed",
    )
    blockers, rows, outcome = evidence.pull_results(pull)
    assert (blockers, outcome) == ([], "fails")
    accepted = accept(people, pull)
    assert (accepted.state, accepted.outcome) == ("accepted", "fails")
    assert accepted.result_evidence["results"][0]["tests"][0]["conforms"] is False
    # The lot of the study is as it was: no hold, no investigation, no revision.
    assert lot_record(study.lot) == before
    # The study can still be completed: a failing result is an outcome, not a missing pull.
    for other in study.pulls.exclude(pk=pull.pk):
        other = pulled(people, study, other.timepoint.interval_days)
        (extra,) = assign(people, other)
        reviewed(people, extra)
        accept(people, other)
    study.refresh_from_db()
    closed = services.close_study(
        actor=people["quality"],
        pin=PIN,
        study=study,
        expected_revision=study.revision,
        outcome="completed",
        reason="Every pull accepted",
    )
    assert closed.state == "completed"


def close(people, study, outcome="terminated"):
    study.refresh_from_db()
    return services.close_study(
        actor=people["quality"],
        pin=PIN,
        study=study,
        expected_revision=study.revision,
        outcome=outcome,
        reason="Synthetic early termination",
    )


def test_a_study_is_not_closed_while_testing_of_its_pulls_is_in_progress(people):
    study, _ = specified_study(people, codes=("assay", "water"))
    pull = pulled(people, study)
    assay, water = sorted(assign(people, pull), key=lambda t: t.test_code)
    observe(people, water, "91.0")  # out of specification once submitted
    with pytest.raises(ValidationError, match=f"{water.label} water holds results"):
        close(people, study)
    submit(people, water)
    with pytest.raises(ValidationError, match="awaits independent review"):
        close(people, study)
    review(people, water)
    investigation = Investigation.objects.get(test=water)
    with pytest.raises(ValidationError, match=f"{investigation.label} is open"):
        close(people, study)
    study.refresh_from_db()
    assert study.state == "active"
    assert not ElectronicSignature.objects.filter(object_type="stability.study").exists()
    # The way forward: conclude the investigation. The untouched assay test does not stop it.
    analytical.add_entry(
        actor=people["analyst2"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic assessment: no laboratory error found",
    )
    investigation.refresh_from_db()
    analytical.conclude(
        actor=people["quality2"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="confirmed",
        assignable_cause="",
        reason="Out-of-specification result confirmed",
    )
    assert close(people, study).state == "terminated"
    # The closed study's pulls take no more testing.
    assay = AnalyticalTest.objects.get(pk=assay.pk)
    assert analytical.subject_refusal(assay).startswith(f"Study {study.identifier} is closed")
    for attempt in (
        lambda: observe(people, assay),
        lambda: assign(people, pull),
        lambda: analytical.correct_observation(
            actor=people["analyst2"],
            observation=Observation.objects.get(test=water),
            value=Decimal("91.1"),
            raw_reference="NB-STB-1 p2",
            reason="Late correction",
        ),
    ):
        with pytest.raises(ValidationError, match="is closed|Only open tests"):
            attempt()
    with pytest.raises(ValidationError, match="is closed; its pulls take no more testing"):
        observe(people, assay)
    assert Observation.objects.count() == 1


def test_accepted_pull_refuses_further_work_and_is_immutable(people):
    study, _ = specified_study(people)
    pull = pulled(people, study)
    (test,) = assign(people, pull)
    reviewed(people, test)
    accepted = accept(people, pull)
    assert analytical.subject_refusal(AnalyticalTest.objects.get(pk=test.pk)) == (
        "This pull is accepted; its tests take no more work."
    )
    with pytest.raises(ValidationError, match="accepted"):
        assign(people, accepted)
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        Pull.objects.filter(pk=pull.pk).update(outcome="fails")


def test_database_keeps_a_test_with_exactly_one_subject(people):
    study, _ = specified_study(people)
    pull = pulled(people, study)
    (test,) = assign(people, pull)
    lot = study.lot
    sample = Sample.objects.create(
        lot=lot, reference="SYN-GUARD-S", collected_at=timezone.now(), created_by=people["analyst"]
    )
    base = {
        "test_code": "guard",
        "requirement": test.requirement,
        "requirement_hash": test.requirement_hash,
        "created_by": people["analyst"],
    }
    for subject in (
        {"lot": lot, "sample": sample, "pull": pull},  # both
        {},  # neither
        {"lot": lot},  # a lot without its sample
    ):
        with pytest.raises(IntegrityError, match="analytical_test_subject"), transaction.atomic():
            AnalyticalTest.objects.create(**base, **subject)
    # One original test for a code of a pull.
    with pytest.raises(IntegrityError, match="one_original_pull_test"), transaction.atomic():
        AnalyticalTest.objects.create(**{**base, "test_code": "assay"}, pull=pull)
    # A pull is never resampled and its requirements are never replaced.
    with pytest.raises(IntegrityError, match="analytical_pull_test_kind"), transaction.atomic():
        AnalyticalTest.objects.create(**base, pull=pull, kind="revised", parent=test)
    # A linked test stays with the subject of the test it follows.
    with pytest.raises(DatabaseError, match="belongs to the lot or stability pull"):
        with transaction.atomic():
            AnalyticalTest.objects.create(**base, lot=lot, sample=sample, kind="rerun", parent=test)
    # An investigation of a stability test is never an investigation of the lot.
    with pytest.raises(DatabaseError, match="belongs to the lot of its test"):
        with transaction.atomic():
            Investigation.objects.create(
                lot=lot, test=test, trigger="Guard", opened_by=people["analyst"]
            )
    # The pull of a test is part of its identity.
    with pytest.raises(DatabaseError, match="identity"), transaction.atomic():
        AnalyticalTest.objects.filter(pk=test.pk).update(pull=None, lot=lot, sample=sample)


def test_criteria_approved_after_the_page_opened_are_not_frozen_unseen(people):
    study, config = specified_study(people)
    pull = pulled(people, study)
    shown = shown_criteria(pull)
    later = catalog.new_specification_revision(
        actor=people["quality"],
        specification=config["specification"],
        basis="Synthetic tighter limit",
        effective_from=timezone.now(),
        effective_until=timezone.now() + timedelta(days=200),
        reason="Synthetic revision",
    )
    catalog.remove_test_line(
        actor=people["quality"], line=later.tests.get(code="assay"), reason="Replaced"
    )
    add_line(people, later, "assay", method=config["method"], lower_limit=Decimal("99"))
    approve_revision(people, later)
    with pytest.raises(ValidationError, match="acceptance criteria in force changed"):
        assign(people, pull, criteria_hash=shown)
    assert not AnalyticalTest.objects.exists()
    pull.refresh_from_db()
    assert pull.revision == 2
    (test,) = assign(people, pull)  # with the criteria shown now
    assert "@v2#" in test.requirement["source"] and test.requirement["lower_limit"] == "99"


def test_two_analysts_assigning_one_pull_at_once_create_each_test_once(people, monkeypatch):
    from laboratory.tests.helpers import run_interleaved

    study, _ = specified_study(people)
    pull = pulled(people, study)
    token = shown_criteria(pull)

    def by(name):
        return lambda: analytical.assign_pull_tests(
            actor=people[name], pull=pull, reason="Tests of the time point", criteria_hash=token
        )

    outcome = run_interleaved(monkeypatch, testing, "lock", by("analyst2"), by("analyst"))
    assert outcome["first"] == [], outcome  # the other analyst's tests are seen, not repeated
    assert len(outcome["second"]) == 1, outcome
    assert AnalyticalTest.objects.filter(pull=pull).count() == 1


def test_a_draft_protocol_is_withdrawn_and_the_code_drafted_again(people):
    config = shelf_life(people)
    draft = draft_protocol(
        people, code="SYN-WD", specification=config["specification"], test_codes=("assy",)
    )
    with pytest.raises(ValidationError, match="does not state assy"):
        services.approve_protocol(
            actor=people["quality"],
            pin=PIN,
            protocol=draft,
            expected_revision=draft.revision,
            reason="Independent approval",
        )
    with pytest.raises(ValidationError, match="still a draft"):
        draft_protocol(people, code="SYN-WD", specification=config["specification"])
    with pytest.raises(PermissionDenied, match="author or a quality person"):
        services.withdraw_protocol(
            actor=people["analyst2"],
            protocol=draft,
            expected_revision=draft.revision,
            reason="Not mine",
        )
    with pytest.raises(ValidationError, match="Record changed"):
        services.withdraw_protocol(
            actor=people["analyst"],
            protocol=draft,
            expected_revision=draft.revision - 1,
            reason="Stale",
        )
    with pytest.raises(ValidationError, match="reason"):
        services.withdraw_protocol(
            actor=people["analyst"], protocol=draft, expected_revision=draft.revision, reason=""
        )
    withdrawn = services.withdraw_protocol(
        actor=people["quality"],
        protocol=draft,
        expected_revision=draft.revision,
        reason="Test code mistyped",
    )
    assert withdrawn.state == "withdrawn" and withdrawn.revision == draft.revision + 1
    event = AuditEvent.objects.get(action="protocol.withdrawn", object_id=str(draft.pk))
    assert event.reason == "Test code mistyped" and event.actor == people["quality"]
    with pytest.raises(ValidationError, match="Only a draft"):
        services.withdraw_protocol(
            actor=people["analyst"],
            protocol=withdrawn,
            expected_revision=withdrawn.revision,
            reason="Again",
        )
    with pytest.raises(ValidationError, match="Only a draft protocol can be approved"):
        services.approve_protocol(
            actor=people["quality"],
            pin=PIN,
            protocol=withdrawn,
            expected_revision=withdrawn.revision,
            reason="Approve a withdrawn draft",
        )
    # The database keeps a withdrawn draft as it was and takes no more content.
    model = type(withdrawn)
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        model.objects.filter(pk=withdrawn.pk).update(state="draft")
    with pytest.raises(ValidationError, match="is withdrawn and frozen"):
        services.add_condition(
            actor=people["analyst"],
            protocol=withdrawn,
            label="Late",
            setpoint="S",
            temperature_c=None,
            humidity_pct=None,
            reason="Late",
        )
    with pytest.raises(DatabaseError, match="Only a draft protocol accepts"):
        with transaction.atomic():
            ProtocolCondition.objects.create(protocol=withdrawn, label="Late", setpoint="S")
    corrected = approved_protocol(
        people, code="SYN-WD", specification=config["specification"], test_codes=("assay",)
    )
    assert (corrected.version, corrected.state) == (2, "approved")
    withdrawn.refresh_from_db()
    assert withdrawn.state == "withdrawn"


def test_a_pulled_pull_that_cannot_be_tested_is_missed_and_the_study_completed(people):
    study, _ = specified_study(people, codes=("assay", "water"), intervals=(30, 100))
    lost = pulled(people, study, 100)
    assay, water = sorted(assign(people, lost), key=lambda t: t.test_code)
    reviewed(people, assay)
    observe(people, water, "99.0")
    with pytest.raises(ValidationError, match="holds results"):
        services.mark_pull_missed(actor=people["analyst"], pull=lost, reason="Material lost")
    # Water was spilled before submission: a correction cannot bring it back, so the lab
    # submits what it has and reviews it, then records the pull as missed.
    submit(people, water)
    review(people, water)
    missed = services.mark_pull_missed(
        actor=people["analyst"], pull=lost, reason="Retained material lost; see DEV-SYN-1"
    )
    assert (missed.state, missed.missed_reason) == (
        "missed",
        "Retained material lost; see DEV-SYN-1",
    )
    assert AnalyticalTest.objects.filter(pull=lost, state="reviewed").count() == 2
    first = pulled(people, study, 30)
    with pytest.raises(ValidationError, match="Only a scheduled or pulled pull"):
        services.mark_pull_missed(actor=people["analyst"], pull=missed, reason="Again")
    for test in assign(people, first):
        reviewed(people, test)
    accept(people, first)
    study.refresh_from_db()
    closed = services.close_study(
        actor=people["quality"],
        pin=PIN,
        study=study,
        expected_revision=study.revision,
        outcome="completed",
        reason="Every pull accepted or missed",
    )
    assert closed.state == "completed"


def test_untouched_tests_of_a_missed_pull_take_no_more_work(people):
    study, _ = specified_study(people)
    pull = pulled(people, study)
    (test,) = assign(people, pull)
    services.mark_pull_missed(actor=people["analyst"], pull=pull, reason="Insufficient material")
    test = AnalyticalTest.objects.get(pk=test.pk)
    assert analytical.subject_refusal(test) == "This pull is missed; its tests take no more work."
    with pytest.raises(ValidationError, match="missed; its tests take no more work"):
        observe(people, test)


def test_the_assign_page_refuses_changed_criteria_and_shows_the_ones_in_force(client, people):
    import re as regex

    from django.urls import reverse

    study, config = specified_study(people)
    pull = pulled(people, study)
    url = reverse("stability:pull_tests", args=[pull.pk])
    client.force_login(people["analyst2"])
    page = client.get(url).content.decode()
    shown = regex.search(r'name="criteria" value="([0-9a-f]{64})"', page).group(1)
    assert "95 to 105 %" in page
    later = catalog.new_specification_revision(
        actor=people["quality"],
        specification=config["specification"],
        basis="Synthetic tighter limit",
        effective_from=timezone.now(),
        effective_until=timezone.now() + timedelta(days=200),
        reason="Synthetic revision",
    )
    catalog.remove_test_line(
        actor=people["quality"], line=later.tests.get(code="assay"), reason="Replaced"
    )
    add_line(people, later, "assay", method=config["method"], lower_limit=Decimal("99"))
    approve_revision(people, later)
    refused = client.post(url, {"reason": "Tests of the time point", "criteria": shown})
    html = refused.content.decode()
    assert refused.status_code == 422
    assert "acceptance criteria in force changed" in html and "99 to 105 %" in html
    assert not AnalyticalTest.objects.exists()
    current = regex.search(r'name="criteria" value="([0-9a-f]{64})"', html).group(1)
    assert current != shown
    done = client.post(url, {"reason": "Tests of the time point", "criteria": current})
    assert done.status_code == 302
    assert AnalyticalTest.objects.get(pull=pull).requirement["lower_limit"] == "99"
