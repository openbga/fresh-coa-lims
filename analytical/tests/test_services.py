from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from analytical import gates, services
from analytical.fixtures import requirement_payload
from analytical.models import (
    AnalyticalTest,
    Investigation,
    InvestigationEntry,
    Observation,
    QCBatch,
    QCResult,
)
from core.models import AuditEvent, ElectronicSignature, PINCredential
from quality.models import Lot
from quality.services import add_sample

from .conftest import PIN, complete, fresh, pass_qc, record, review, submit

pytestmark = pytest.mark.django_db(transaction=True)


def blockers(lot):
    return gates.lot_blockers(fresh(lot))


def test_accepted_journey_publishes_evidence(people, assigned, batch):
    lot, _, tests = assigned
    start = fresh(lot).revision
    pass_qc(people, batch)
    complete(people, tests["assay"], "99.50", "100.10", batch=batch)
    complete(people, tests["identity"], "1.004")
    assert blockers(lot) == []
    assay = fresh(tests["assay"])
    assert (assay.state, assay.mean_value, assay.reportable_value, assay.conforms) == (
        "reviewed",
        Decimal("99.80000000"),
        Decimal("99.8"),
        True,
    )
    identity = fresh(tests["identity"])
    assert identity.reportable_value == Decimal("1.00")
    assert fresh(lot).revision > start
    evidence = gates.lot_evidence(fresh(lot))
    assert evidence["complete"] and evidence["schema"] == "analytical.lot-evidence/1"
    row = next(r for r in evidence["results"] if r["test_code"] == "assay")
    assert row["reportable"] == "99.8"
    assert [r["value"] for r in row["replicates"]] == ["99.50", "100.10"]
    assert row["review"]["meaning"] == "reviewed" and row["batch"] == "SYN-B1"
    assert row["requirement_hash"] == assay.requirement_hash
    signature = ElectronicSignature.objects.get(
        object_type="analytical.analyticaltest", object_id=str(assay.pk)
    )
    assert signature.signer == people["reviewer"] and signature.content["state"] == "reviewed"


def test_incomplete_and_unreviewed_tests_block(people, assigned):
    lot, _, tests = assigned
    assert f"T-{tests['assay'].pk} assay is incomplete." in blockers(lot)
    record(people, tests["identity"], "1.0")
    submit(people, tests["identity"])
    assert any("awaits independent review" in b for b in blockers(lot))
    assert "Sample SYN-LOT-1-S1 has no reviewed conforming identity result." in blockers(lot)


def test_missing_unsupported_and_unconfigured_requirements_hold(people, make_lot, settings):
    lot, sample = make_lot("SYN-LOT-H", tests=("identity", "sterility"))
    created, holds = services.assign_tests(actor=people["analyst"], sample=sample, reason="Go")
    assert [t.test_code for t in created] == ["identity"]
    assert holds == ["No approved specification is available for sterility."]
    assert "No approved specification is available for sterility." in blockers(lot)

    class Exclusive:
        def requirements(self, lot):
            return {"identity": {**requirement_payload("identity"), "bounds": "exclusive"}}

        def methods(self):
            return []

    import analytical.tests.test_services as module

    module.Exclusive = Exclusive
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = "analytical.tests.test_services.Exclusive"
    assert any("Only inclusive" in b for b in blockers(lot))
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = ""
    assert "No approved test-requirement provider is configured." in blockers(lot)
    _, holds = services.assign_tests(actor=people["analyst"], sample=sample, reason="Go")
    assert holds == ["No approved test-requirement provider is configured."]


def test_correction_preserves_original_and_requires_reason(people, assigned):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.5")
    original = Observation.objects.get(test=test)
    with pytest.raises(ValidationError, match="reason"):
        services.correct_observation(
            actor=people["analyst2"],
            observation=original,
            value=Decimal("1.05"),
            raw_reference="NB-1 p1",
            reason=" ",
        )
    correction = services.correct_observation(
        actor=people["analyst2"],
        observation=original,
        value=Decimal("1.05"),
        raw_reference="NB-1 p1",
        reason="Transcription error: notebook reads 1.05",
    )
    assert correction.supersedes == original
    assert list(fresh(test).current_observations()) == [correction]
    assert Observation.objects.filter(test=test).count() == 2
    with pytest.raises(ValidationError, match="already been corrected"):
        services.correct_observation(
            actor=people["analyst"],
            observation=original,
            value=Decimal("1"),
            raw_reference="x",
            reason="again",
        )
    submitted, investigation = submit(people, test)
    assert submitted.conforms and investigation is None
    # Both analysts generated data, so neither may review; the original row stays immutable.
    for action in [
        lambda: Observation.objects.filter(pk=original.pk).update(value=Decimal("1.0")),
        lambda: Observation.objects.filter(pk=original.pk).delete(),
    ]:
        with pytest.raises(DatabaseError), transaction.atomic():
            action()
    event = AuditEvent.objects.get(action="observation.corrected")
    assert event.before["value"] == "1.5" and event.after["value"] == "1.05"


def test_no_self_review_including_multi_role_and_qc_authors(people, assigned, batch):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.0", who="multi")
    submit(people, test, who="multi")
    with pytest.raises(ValidationError, match="own test"):
        review(people, test, who="multi")
    with pytest.raises(ValidationError, match="own test"):
        services.return_test(
            actor=people["multi"],
            test=fresh(test),
            expected_revision=fresh(test).revision,
            reason="Check",
        )
    # Recording batch QC is authorship of the run.
    services.record_qc(
        actor=people["multi"],
        batch=batch,
        check_code="blank",
        value=Decimal("0"),
        raw_reference="RUN blank",
    )
    services.record_qc(
        actor=people["analyst2"],
        batch=batch,
        check_code="control",
        value=Decimal("100"),
        raw_reference="RUN control",
    )
    services.assign_to_batch(
        actor=people["analyst"], test=tests["assay"], batch=batch, reason="Run"
    )
    record(people, tests["assay"], "100", "100")
    submit(people, tests["assay"])
    with pytest.raises(ValidationError, match="own test"):
        review(people, tests["assay"], who="multi")
    assert not ElectronicSignature.objects.exists()
    review(people, tests["assay"])


def test_author_of_a_superseded_correction_cannot_review(people, assigned):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.0")
    services.correct_observation(
        actor=people["multi"],
        observation=test.observations.get(),
        value=Decimal("1.1"),
        raw_reference="NB-1 p3",
        reason="Transcription",
    )
    services.correct_observation(
        actor=people["analyst"],
        observation=fresh(test).current_observations().get(),
        value=Decimal("1.0"),
        raw_reference="NB-1 p4",
        reason="Reverted after second check",
    )
    submit(people, test)
    with pytest.raises(ValidationError, match="own test"):
        review(people, test, who="multi")
    assert review(people, test).state == "reviewed"


def test_roles_are_enforced(people, assigned):
    _, _, tests = assigned
    with pytest.raises(PermissionDenied):
        record(people, tests["identity"], "1.0", who="auditor")
    with pytest.raises(PermissionDenied):
        record(people, tests["identity"], "1.0", who="reviewer")
    record(people, tests["identity"], "1.0")
    submit(people, tests["identity"])
    with pytest.raises(PermissionDenied):
        review(people, tests["identity"], who="analyst2")
    with pytest.raises(PermissionDenied):
        review(people, tests["identity"], who="quality")


def test_stale_review_and_failed_pin_leave_no_signature(people, assigned):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.0")
    submit(people, test)
    test = fresh(test)
    with pytest.raises(ValidationError, match="Record changed"):
        services.review_test(
            actor=people["reviewer"],
            pin=PIN,
            test=test,
            expected_revision=test.revision - 1,
            reason="Checked",
        )
    with pytest.raises(ValidationError, match="not accepted"):
        services.review_test(
            actor=people["reviewer"],
            pin="00000000",
            test=test,
            expected_revision=test.revision,
            reason="Checked",
        )
    assert PINCredential.objects.get(user=people["reviewer"]).failures == 1
    assert AuditEvent.objects.filter(action="signature.denied").count() == 1
    assert fresh(test).state == "submitted" and not ElectronicSignature.objects.exists()


def test_return_reopens_conforming_submission_for_correction(people, assigned):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.0")
    submit(people, test)
    services.return_test(
        actor=people["reviewer"],
        test=fresh(test),
        expected_revision=fresh(test).revision,
        reason="Wrong notebook page",
    )
    test = fresh(test)
    assert test.state == "open" and test.reportable_value is None
    services.correct_observation(
        actor=people["analyst"],
        observation=test.observations.get(),
        value=Decimal("1.01"),
        raw_reference="NB-1 p2",
        reason="Notebook page corrected",
    )
    submit(people, test)
    assert review(people, test).reportable_value == Decimal("1.01")


def test_qc_gates_submission_and_freezes_after_submission(people, assigned, batch):
    _, _, tests = assigned
    test = tests["assay"]
    with pytest.raises(ValidationError, match="QC batch"):
        record(people, test, "100")
    services.assign_to_batch(actor=people["analyst"], test=test, batch=batch, reason="Run")
    record(people, test, "100", "100.2")
    with pytest.raises(ValidationError, match="incomplete"):
        submit(people, test)
    pass_qc(people, batch, control="97.0")
    with pytest.raises(ValidationError, match="failed"):
        submit(people, test)
    services.correct_qc(
        actor=people["analyst2"],
        qc_result=batch.qc_results.get(check_code="control"),
        value=Decimal("99.0"),
        raw_reference="RUN-1 control reread",
        reason="Integration window error",
    )
    assert fresh(batch).qc_status()[0] == "passed"
    assert QCResult.objects.filter(batch=batch).count() == 3
    submit(people, test)
    with pytest.raises(ValidationError, match="QC cannot change"):
        services.record_qc(
            actor=people["analyst2"],
            batch=batch,
            check_code="blank",
            value=Decimal("0"),
            raw_reference="x",
        )
    with pytest.raises(ValidationError, match="QC cannot change"):
        services.correct_qc(
            actor=people["analyst2"],
            qc_result=batch.current_qc().get(check_code="blank"),
            value=Decimal("0.2"),
            raw_reference="x",
            reason="change",
        )
    with pytest.raises(ValidationError, match="already has submitted"):
        services.assign_to_batch(
            actor=people["analyst"], test=tests["identity"], batch=batch, reason="late"
        )


def test_duplicate_batch_number_is_refused_even_when_submitted_concurrently(
    people, batch, monkeypatch
):
    def create():
        return services.create_batch(
            actor=people["analyst"], number=batch.number, method_code="SYN-HPLC", reason="Again"
        )

    with pytest.raises(ValidationError, match="already exists"):
        create()
    # A double submission: the second request checked before the first committed its insert.
    real_filter = QCBatch.objects.filter

    def unseen(*args, **kwargs):
        found = real_filter(*args, **kwargs)
        return found.none() if "number" in kwargs else found

    monkeypatch.setattr(QCBatch.objects, "filter", unseen)
    with pytest.raises(ValidationError, match="already exists"):
        create()
    monkeypatch.undo()
    assert QCBatch.objects.count() == 1
    assert AuditEvent.objects.filter(action="batch.created").count() == 1


def test_batch_creation_reraises_integrity_errors_other_than_a_duplicate_number(
    people, monkeypatch
):
    """A foreign-key/not-null or audit integrity fault is not reported as a duplicate number."""

    def broken_audit(**kwargs):
        raise IntegrityError("synthetic not-null failure in audit recording")

    monkeypatch.setattr(services, "record_event", broken_audit)
    with pytest.raises(IntegrityError, match="synthetic not-null"):
        services.create_batch(
            actor=people["analyst"], number="SYN-B-FAULT", method_code="SYN-HPLC", reason="Run"
        )
    # A real non-unique constraint violation (foreign key) is not translated either.
    monkeypatch.undo()

    def orphan(**fields):
        fields.pop("created_by")
        batch = QCBatch(created_by_id=0, **fields)  # deferred FK fails at commit
        batch.save()
        return batch

    monkeypatch.setattr(services.QCBatch.objects, "create", orphan)
    with pytest.raises(IntegrityError, match="foreign key"):
        services.create_batch(
            actor=people["analyst"], number="SYN-B-FK", method_code="SYN-HPLC", reason="Run"
        )
    monkeypatch.undo()
    assert not QCBatch.objects.exists()


def test_rejecting_failed_batch_creates_reruns_and_investigates_oos(people, assigned, batch):
    lot, _, tests = assigned
    test = tests["assay"]
    services.assign_to_batch(actor=people["analyst"], test=test, batch=batch, reason="Run")
    record(people, test, "92.0", "100.0")
    with pytest.raises(ValidationError, match="Only a batch with failed QC"):
        services.reject_batch(
            actor=people["reviewer"],
            pin=PIN,
            batch=fresh(batch),
            expected_revision=fresh(batch).revision,
            reason="No",
        )
    pass_qc(people, batch, control="90.0")
    with pytest.raises(PermissionDenied):
        services.reject_batch(
            actor=people["analyst"],
            pin=PIN,
            batch=fresh(batch),
            expected_revision=fresh(batch).revision,
            reason="QC failed",
        )
    services.reject_batch(
        actor=people["reviewer"],
        pin=PIN,
        batch=fresh(batch),
        expected_revision=fresh(batch).revision,
        reason="Control failed",
    )
    assert fresh(batch).state == "rejected"
    original = fresh(test)
    assert original.state == "invalidated"
    rerun = AnalyticalTest.objects.get(parent=original)
    assert (rerun.kind, rerun.state, rerun.batch_id) == ("rerun", "open", None)
    investigation = Investigation.objects.get(test=original)
    assert "92.0" in investigation.trigger
    assert any(investigation.label in b for b in blockers(lot))
    with pytest.raises(DatabaseError), transaction.atomic():
        QCBatch.objects.filter(pk=batch.pk).update(state="open")
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalyticalTest.objects.filter(pk=original.pk).update(state="open")


def _oos(people, assigned):
    lot, sample, tests = assigned
    test = record(people, tests["identity"], "1.30")
    submitted, investigation = submit(people, test)
    assert not submitted.conforms and investigation.phase == "laboratory"
    return lot, sample, fresh(test), investigation


def _authorize(people, investigation, kind="retest", who="quality", sample=None):
    investigation = fresh(investigation)
    return services.authorize_retest(
        actor=people[who],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        kind=kind,
        sample=sample,
        reason="Phase I found possible dilution error; one retest of the same sample",
    )


def _conclude(people, investigation, outcome, cause="", who="quality2"):
    investigation = fresh(investigation)
    return services.conclude(
        actor=people[who],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome=outcome,
        assignable_cause=cause,
        reason="Independent quality conclusion",
    )


def test_oos_holds_and_cannot_be_corrected_or_returned(people, assigned):
    lot, _, test, investigation = _oos(people, assigned)
    assert any(investigation.label in b for b in blockers(lot))
    with pytest.raises(ValidationError, match="Only open tests"):
        services.correct_observation(
            actor=people["analyst"],
            observation=test.observations.get(),
            value=Decimal("1.0"),
            raw_reference="x",
            reason="typo",
        )
    with pytest.raises(ValidationError, match="cannot be returned"):
        services.return_test(
            actor=people["reviewer"], test=test, expected_revision=test.revision, reason="Fix"
        )
    with pytest.raises(ValidationError, match="laboratory assessment"):
        _authorize(people, investigation)


def test_oos_invalidated_with_conforming_retest_releases_gate(people, assigned):
    lot, _, test, investigation = _oos(people, assigned)
    review(people, test)  # data verified; OOS stands until concluded
    services.add_entry(
        actor=people["analyst"],
        investigation=investigation,
        kind="assessment",
        text="Dilution flask 3 used wrong volume",
        external_reference="DEV-001",
    )
    _authorize(people, investigation)
    with pytest.raises(ValidationError, match="no further retests"):
        _authorize(people, investigation)
    child = AnalyticalTest.objects.get(investigation=investigation)
    assert (child.kind, child.parent_id, child.sample_id) == ("retest", test.pk, test.sample_id)
    with pytest.raises(ValidationError, match="still incomplete"):
        _conclude(people, investigation, "invalidated", "Dilution error")
    record(people, child, "1.01", who="analyst2")
    submit(people, child, who="analyst2")
    review(people, child)
    with pytest.raises(ValidationError, match="assignable cause"):
        _conclude(people, investigation, "invalidated", " ")
    closed = _conclude(people, investigation, "invalidated", "Dilution error documented")
    assert closed.phase == "closed" and fresh(test).state == "invalidated"
    assert Observation.objects.filter(test=test).exists()  # original evidence preserved
    blockers_now = blockers(lot)
    assert not any("identity" in b for b in blockers_now), blockers_now
    evidence = gates.lot_evidence(fresh(lot))
    identity = next(r for r in evidence["results"] if r["test_code"] == "identity")
    assert identity["kind"] == "retest" and identity["reportable"] == "1.01"
    assert {
        "test": test.pk,
        "test_code": "identity",
        "kind": "original",
        "state": "invalidated",
    } in evidence["excluded_tests"]
    assert evidence["investigations"][0]["conclusion"]["meaning"] == "concluded"
    with pytest.raises(DatabaseError), transaction.atomic():
        Investigation.objects.filter(pk=investigation.pk).update(conclusion="edited")
    with pytest.raises(DatabaseError), transaction.atomic():
        InvestigationEntry.objects.filter(investigation=investigation).delete()


def test_failing_retest_cannot_invalidate_and_confirmed_oos_blocks(people, assigned):
    lot, _, test, investigation = _oos(people, assigned)
    review(people, test)
    services.add_entry(
        actor=people["reviewer"],
        investigation=investigation,
        kind="assessment",
        text="No obvious laboratory error",
    )
    _authorize(people, investigation)
    child = AnalyticalTest.objects.get(investigation=investigation)
    record(people, child, "1.25", who="analyst2")
    submitted, extra = submit(people, child, who="analyst2")
    assert not submitted.conforms and extra is None  # stays inside the open investigation
    review(people, child)
    with pytest.raises(ValidationError, match="also out of specification"):
        _conclude(people, investigation, "invalidated", "Suspected pipette")
    _conclude(people, investigation, "confirmed")
    assert any("confirmed an out-of-specification" in b for b in blockers(lot))
    assert fresh(test).state == "reviewed"


def test_independence_for_authorization_and_conclusion(people, assigned):
    lot, _, test, investigation = _oos(people, assigned)
    review(people, test)
    services.add_entry(
        actor=people["analyst"], investigation=investigation, kind="assessment", text="Checked"
    )
    people["analyst"].groups.add(people["quality"].groups.get())
    with pytest.raises(ValidationError, match="own result"):
        _authorize(people, investigation, who="analyst")
    with pytest.raises(ValidationError, match="own work"):
        _conclude(people, investigation, "confirmed", who="analyst")
    with pytest.raises(PermissionDenied):
        _conclude(people, investigation, "confirmed", who="reviewer")
    assert not ElectronicSignature.objects.filter(object_type="analytical.investigation").exists()


def test_resample_requires_new_sample_of_same_lot(people, assigned, make_lot):
    lot, sample, test, investigation = _oos(people, assigned)
    review(people, test)
    services.add_entry(
        actor=people["analyst"],
        investigation=investigation,
        kind="assessment",
        text="Sample container damaged",
    )
    services.escalate(
        actor=people["reviewer"],
        investigation=investigation,
        expected_revision=fresh(investigation).revision,
        reason="Sampling suspected; full investigation",
    )
    assert fresh(investigation).phase == "full"
    _, other_sample = make_lot("SYN-LOT-2")
    for wrong in (None, sample, other_sample):
        with pytest.raises(ValidationError):
            _authorize(people, investigation, kind="resample", sample=wrong)
    new = add_sample(
        actor=people["analyst"],
        lot=fresh(lot),
        reference="SYN-LOT-1-S2",
        collected_at=timezone.now(),
        reason="Authorized resample",
    )
    _authorize(people, investigation, kind="resample", sample=new)
    child = AnalyticalTest.objects.get(investigation=investigation)
    assert (child.kind, child.sample_id) == ("resample", new.pk)


def test_released_lot_rejects_analytical_changes(people, assigned):
    lot, _, tests = assigned
    Lot.objects.filter(pk=lot.pk).update(state="rejected")
    with pytest.raises(ValidationError, match="no longer in quarantine"):
        record(people, tests["identity"], "1.0")


def test_test_identity_and_requirement_snapshot_are_immutable(people, assigned):
    _, _, tests = assigned
    test = tests["identity"]
    for change in [{"test_code": "other"}, {"requirement": {}}, {"created_by": people["quality"]}]:
        with pytest.raises(DatabaseError), transaction.atomic():
            AnalyticalTest.objects.filter(pk=test.pk).update(**change)
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalyticalTest.objects.filter(pk=test.pk).delete()


def test_each_sample_needs_its_own_reportable_results(people, assigned, batch):
    lot, _, tests = assigned
    pass_qc(people, batch)
    complete(people, tests["assay"], "100.0", "100.2", batch=batch)
    complete(people, tests["identity"], "1.00")
    assert blockers(lot) == []
    second = add_sample(
        actor=people["analyst"],
        lot=fresh(lot),
        reference="SYN-LOT-1-S2",
        collected_at=timezone.now(),
        reason="Second container",
    )
    assert "Sample SYN-LOT-1-S2 has no identity test assigned." in blockers(lot)
    created, _ = services.assign_tests(actor=people["analyst"], sample=second, reason="Go")
    identity = next(t for t in created if t.test_code == "identity")
    complete(people, identity, "1.02")
    assert blockers(lot) == [
        f"T-{next(t for t in created if t.test_code == 'assay').pk} assay is incomplete.",
        "Sample SYN-LOT-1-S2 has no reviewed conforming assay result.",
    ]


def test_resample_answers_for_original_sample_and_authors_are_published(people, assigned):
    lot, sample, test, investigation = _oos(people, assigned)
    review(people, test)
    services.add_entry(
        actor=people["reviewer2"],
        investigation=investigation,
        kind="assessment",
        text="Container seal broken",
    )
    new = add_sample(
        actor=people["analyst"],
        lot=fresh(lot),
        reference="SYN-LOT-1-S9",
        collected_at=timezone.now(),
        reason="Authorized resample",
    )
    _authorize(people, investigation, kind="resample", sample=new)
    child = AnalyticalTest.objects.get(investigation=investigation)
    record(people, child, "1.03", who="analyst2")
    submit(people, child, who="analyst2")
    review(people, child)
    _conclude(people, investigation, "invalidated", "Sampling container damaged")
    remaining = blockers(lot)
    assert not any("identity" in b for b in remaining), remaining
    assert not any("SYN-LOT-1-S9" in b for b in remaining)
    evidence = gates.lot_evidence(fresh(lot))
    row = next(r for r in evidence["results"] if r["test_code"] == "identity")
    assert (row["for_sample"], row["sample"], row["kind"]) == (
        "SYN-LOT-1-S1",
        "SYN-LOT-1-S9",
        "resample",
    )
    authors = gates.lot_author_ids(fresh(lot))
    assert authors == {people["analyst"].pk, people["analyst2"].pk, people["reviewer2"].pk}
    assert evidence["author_ids"] == sorted(authors)


def test_concurrent_reviews_of_one_revision_sign_once(people, assigned):
    import threading

    from django.db import connection

    _, _, tests = assigned
    test = record(people, tests["identity"], "1.0")
    submit(people, test)
    revision = fresh(test).revision
    barrier, outcomes = threading.Barrier(2), []

    def sign(who):
        try:
            barrier.wait()
            services.review_test(
                actor=people[who],
                pin=PIN,
                test=fresh(test),
                expected_revision=revision,
                reason="Checked",
            )
            outcomes.append("signed")
        except ValidationError as exc:
            outcomes.append(" ".join(exc.messages))
        finally:
            connection.close()

    threads = [threading.Thread(target=sign, args=(w,)) for w in ("reviewer", "reviewer2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["Record changed. Reload and review before signing.", "signed"]
    assert ElectronicSignature.objects.filter(object_id=str(test.pk)).count() == 1


def test_investigative_entry_author_cannot_conclude(people, assigned):
    _, _, test, investigation = _oos(people, assigned)
    review(people, test)
    services.add_entry(
        actor=people["quality2"],
        investigation=investigation,
        kind="evidence",
        text="Balance calibration record checked",
    )
    services.add_entry(
        actor=people["analyst"],
        investigation=investigation,
        kind="assessment",
        text="No error found",
    )
    with pytest.raises(ValidationError, match="own work"):
        _conclude(people, investigation, "confirmed", who="quality2")
    _conclude(people, investigation, "confirmed", who="quality")


def _unqualified(*, actor, test):
    raise ValidationError(f"{actor.username} has no current qualification for {test.test_code}.")


def test_observations_require_configured_analyst_eligibility(people, assigned, settings, make_lot):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.0")
    observation = test.observations.get()
    assert observation.eligibility == {
        "policy": "synthetic-test-fixture",
        "user": people["analyst"].pk,
        "activity": "SYN-IR",
    }
    event = AuditEvent.objects.get(action="observation.recorded")
    assert event.after["eligibility"]["activity"] == "SYN-IR"
    settings.ANALYTICAL_ELIGIBILITY_CHECK = "analytical.tests.test_services._unqualified"
    with pytest.raises(ValidationError, match="no current qualification"):
        services.correct_observation(
            actor=people["analyst2"],
            observation=observation,
            value=Decimal("1.01"),
            raw_reference="x",
            reason="typo",
        )
    _, other = make_lot("SYN-LOT-E", tests=("identity",))
    (fresh_test,), _ = services.assign_tests(actor=people["analyst"], sample=other, reason="Go")
    with pytest.raises(ValidationError, match="no current qualification"):
        record(people, fresh_test, "1.0")
    assert not Observation.objects.filter(test=fresh_test).exists()
    settings.ANALYTICAL_ELIGIBILITY_CHECK = ""
    with pytest.raises(ValidationError, match="eligibility check is configured"):
        services.correct_observation(
            actor=people["analyst2"],
            observation=observation,
            value=Decimal("1.01"),
            raw_reference="x",
            reason="typo",
        )
    assert Observation.objects.filter(test=test).count() == 1
    assert fresh(test).revision == test.revision


def test_results_against_superseded_requirement_do_not_count(people, assigned, settings):
    lot, _, tests = assigned
    complete(people, tests["identity"], "1.00")
    assert not any("identity" in b for b in blockers(lot))

    class Tightened:
        def requirements(self, lot):
            payload = requirement_payload("identity")
            payload.update(source="fixture:SYN-SPEC-IDENTITY@2", lower_limit="0.95")
            return {"identity": payload}

        def methods(self):
            return []

    import analytical.tests.test_services as module

    module.Tightened = Tightened
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = "analytical.tests.test_services.Tightened"
    assert any("superseded requirement" in b for b in blockers(lot))
    assert gates.lot_evidence(fresh(lot))["results"] == []


def test_null_reporting_precision_compares_exact_values():
    from analytical.contracts import parse_requirement

    payload = requirement_payload("assay")
    payload["reporting_decimals"] = None
    spec = parse_requirement(payload)
    mean, reportable, conforms = spec.evaluate([Decimal("99.5"), Decimal("100.0")])
    assert (reportable, conforms) == (Decimal("99.75"), True)
    with pytest.raises(ValidationError, match="not exact"):
        spec.evaluate([Decimal("100"), Decimal("100.00000001")])  # mean needs 9 decimals


def test_catalog_translator_output_matches_analytical_contract():
    """Frozen catalog test line -> catalog.services.test_requirement -> analytical parser, as is."""
    from analytical.contracts import parse_requirement
    from catalog.services import test_requirement as translate

    line = {
        "code": "assay",
        "name": "Assay",
        "result_type": "numeric",
        "unit": "%",
        "lower_limit": "95",
        "lower_inclusive": True,
        "upper_limit": "105",
        "upper_inclusive": True,
        "reporting_decimals": 1,
        "replicates": 2,
        "replicate_limits": True,
        "max_retests": 1,
        "expected_text": "",
        "required": True,
        "method": {
            "code": "syn-hplc",
            "version": 2,
            "requires_batch": True,
            "qc_checks": [
                {
                    "code": "blank",
                    "name": "Blank",
                    "unit": "%",
                    "lower_limit": None,
                    "upper_limit": "0.05",
                }
            ],
        },
    }
    spec = parse_requirement(translate(line, "catalog:SPEC@1:abc"))
    assert (spec.method.revision, spec.replicates, spec.max_retests) == (2, 2, 1)
    for change in [{"upper_inclusive": False}, {"result_type": "qualitative"}]:
        with pytest.raises(ValidationError):
            parse_requirement(translate({**line, **change}, "catalog:SPEC@1:abc"))
