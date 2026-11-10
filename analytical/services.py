"""Testing, QC and OOS transitions.

Lock order for every transition: QC batch, investigation, tests (by pk), then lots (by pk).
Signed transitions go through core.services.sign_transition, which locks its record first.
Every evidence change bumps the lot revision so a disposition opened earlier becomes stale.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from core.services import require_role, sign_transition, validate_rules
from quality.models import Lot, Sample

from .contracts import batch_methods, canonical_hash, check_eligibility, resolve
from .gates import data_author_ids, investigation_author_ids
from .models import (
    AnalyticalTest,
    Investigation,
    InvestigationEntry,
    Observation,
    QCBatch,
    QCResult,
)

ANALYST = "analyst"
REVIEWER = "reviewer"
QUALITY = "quality"
OPEN_STATES = {AnalyticalTest.State.OPEN, AnalyticalTest.State.SUBMITTED}


def _require_reason(reason):
    if not reason or not reason.strip():
        raise ValidationError("A reason is required.")


def _lock_lots(*lot_ids):
    lots = list(Lot.objects.select_for_update().filter(pk__in=set(lot_ids)).order_by("pk"))
    for lot in lots:
        if lot.state != "quarantine":
            raise ValidationError(f"Lot {lot.number} is no longer in quarantine.")
    return lots


def _bump(*lots):
    for lot in lots:
        lot.revision += 1
        lot.save(update_fields=["revision"])


def _check_revision(record, expected_revision):
    if expected_revision is not None and record.revision != expected_revision:
        raise ValidationError("Record changed. Reload and review before continuing.")


def _touch(record):
    record.revision += 1
    record.save()


def _test_authors(test):
    return data_author_ids(test)


# Test assignment and observations ----------------------------------------------------------


def assign_tests(*, actor, sample, reason):
    """Create original tests for supported required codes; return hold reasons for the rest."""
    require_role(actor, ANALYST)
    _require_reason(reason)
    with transaction.atomic():
        (lot,) = _lock_lots(Sample.objects.get(pk=sample.pk).lot_id)
        validate_rules(lot.rules)
        existing = set(
            AnalyticalTest.objects.filter(sample_id=sample.pk, kind="original").values_list(
                "test_code", flat=True
            )
        )
        accepted, holds = resolve(lot)
        created = []
        for code, payload in accepted.items():
            if code in existing:
                continue
            test = AnalyticalTest.objects.create(
                lot=lot,
                sample_id=sample.pk,
                test_code=code,
                requirement=payload,
                requirement_hash=canonical_hash(payload),
                created_by=actor,
            )
            created.append(test)
            record_event(
                actor=actor,
                action="test.assigned",
                obj=test,
                after={
                    "sample": sample.pk,
                    "test_code": code,
                    "requirement": payload["source"],
                    "requirement_hash": test.requirement_hash,
                },
                reason=reason,
            )
        if created:
            _bump(lot)
        return created, holds


def record_observation(*, actor, test, value, raw_reference, reason=""):
    require_role(actor, ANALYST)
    if not raw_reference.strip():
        raise ValidationError("Record where the original observation is kept.")
    with transaction.atomic():
        test = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        (lot,) = _lock_lots(test.lot_id)
        if test.state != AnalyticalTest.State.OPEN:
            raise ValidationError("This test is not accepting observations.")
        spec = test.spec
        if spec.method.requires_batch and test.batch_id is None:
            raise ValidationError("Assign this test to a QC batch before recording results.")
        count = test.current_observations().count()
        if count >= spec.replicates:
            raise ValidationError("All replicates are recorded. Correct a value instead.")
        eligibility = check_eligibility(actor=actor, test=test)
        observation = Observation(
            test=test,
            replicate=count + 1,
            value=value,
            value_text=str(value),
            unit=spec.unit,
            raw_reference=raw_reference,
            reason=reason,
            eligibility=eligibility,
            recorded_by=actor,
        )
        observation.full_clean()
        observation.save()
        _touch(test)
        _bump(lot)
        record_event(
            actor=actor,
            action="observation.recorded",
            obj=test,
            after={
                "observation": observation.pk,
                "replicate": observation.replicate,
                "value": str(value),
                "unit": spec.unit,
                "raw_reference": raw_reference,
                "eligibility": eligibility,
            },
            reason=reason or "Observation recorded.",
        )
        return observation


def correct_observation(*, actor, observation, value, raw_reference, reason):
    """Add a linked correction; the original row is preserved and remains visible."""
    require_role(actor, ANALYST)
    _require_reason(reason)
    with transaction.atomic():
        test = AnalyticalTest.objects.select_for_update().get(pk=observation.test_id)
        (lot,) = _lock_lots(test.lot_id)
        if test.state != AnalyticalTest.State.OPEN:
            raise ValidationError(
                "Only open tests can be corrected. A reviewer must return a submitted test first."
            )
        original = Observation.objects.get(pk=observation.pk)
        if Observation.objects.filter(supersedes=original).exists():
            raise ValidationError("This observation has already been corrected.")
        eligibility = check_eligibility(actor=actor, test=test)
        correction = Observation(
            test=test,
            replicate=original.replicate,
            value=value,
            value_text=str(value),
            unit=original.unit,
            raw_reference=raw_reference,
            supersedes=original,
            reason=reason,
            eligibility=eligibility,
            recorded_by=actor,
        )
        correction.full_clean()
        correction.save()
        _touch(test)
        _bump(lot)
        record_event(
            actor=actor,
            action="observation.corrected",
            obj=test,
            before={
                "observation": original.pk,
                "value": original.value_text,
                "raw_reference": original.raw_reference,
            },
            after={
                "observation": correction.pk,
                "value": str(value),
                "raw_reference": raw_reference,
                "eligibility": eligibility,
            },
            reason=reason,
        )
        return correction


def _open_investigation(*, actor, test, trigger):
    investigation = Investigation.objects.create(
        lot_id=test.lot_id, test=test, trigger=trigger, opened_by=actor
    )
    record_event(
        actor=actor,
        action="investigation.opened",
        obj=investigation,
        after={"test": test.pk, "trigger": trigger},
        reason=trigger,
    )
    return investigation


def submit_test(*, actor, test, expected_revision, reason):
    """Freeze the calculation; an out-of-specification result opens an investigation and hold."""
    require_role(actor, ANALYST)
    _require_reason(reason)
    with transaction.atomic():
        batch_id = AnalyticalTest.objects.get(pk=test.pk).batch_id
        batch = QCBatch.objects.select_for_update().get(pk=batch_id) if batch_id else None
        test = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        _check_revision(test, expected_revision)
        (lot,) = _lock_lots(test.lot_id)
        if test.state != AnalyticalTest.State.OPEN or test.batch_id != batch_id:
            raise ValidationError("This test cannot be submitted.")
        spec = test.spec
        if spec.method.requires_batch:
            if batch is None or batch.state != QCBatch.State.OPEN:
                raise ValidationError("An open QC batch is required.")
            status, _ = batch.qc_status()
            if status != "passed":
                raise ValidationError(f"Batch QC is {status}; tests cannot be submitted.")
        values = [o.value for o in test.current_observations()]
        test.mean_value, test.reportable_value, test.conforms = spec.evaluate(values)
        test.evaluated_at = timezone.now()
        test.submitted_by = actor
        test.state = AnalyticalTest.State.SUBMITTED
        _touch(test)
        _bump(lot)
        record_event(
            actor=actor,
            action="test.submitted",
            obj=test,
            after={
                "values": [str(v) for v in values],
                "mean": str(test.mean_value),
                "reportable": test.reportable_display,
                "conforms": test.conforms,
                "requirement_hash": test.requirement_hash,
            },
            reason=reason,
        )
        investigation = None
        if not test.conforms and test.investigation_id is None:
            investigation = _open_investigation(
                actor=actor,
                test=test,
                trigger=f"Out-of-specification {test.test_code}: reportable "
                f"{test.reportable_display} {spec.unit}",
            )
        return test, investigation


def return_test(*, actor, test, expected_revision, reason):
    """Reviewer sends a conforming submission back for correction; OOS results cannot return."""
    require_role(actor, REVIEWER)
    _require_reason(reason)
    with transaction.atomic():
        test = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        _check_revision(test, expected_revision)
        (lot,) = _lock_lots(test.lot_id)
        if test.state != AnalyticalTest.State.SUBMITTED:
            raise ValidationError("Only submitted tests can be returned.")
        if actor.pk in _test_authors(test):
            raise ValidationError("You cannot review your own test.")
        if not test.conforms:
            raise ValidationError(
                "Out-of-specification results cannot be returned for correction; "
                "the investigation decides whether the result is invalid."
            )
        before = {"mean": str(test.mean_value), "reportable": str(test.reportable_value)}
        test.state = AnalyticalTest.State.OPEN
        test.mean_value = test.reportable_value = test.conforms = test.evaluated_at = None
        test.submitted_by = None
        _touch(test)
        _bump(lot)
        record_event(actor=actor, action="test.returned", obj=test, before=before, reason=reason)
        return test


def review_test(*, actor, pin, test, expected_revision, reason):
    def apply(locked):
        (lot,) = _lock_lots(locked.lot_id)
        if locked.state != AnalyticalTest.State.SUBMITTED:
            raise ValidationError("This test is not awaiting review.")
        if actor.pk in _test_authors(locked):
            raise ValidationError("You cannot review your own test.")
        validate_rules(lot.rules)
        if locked.batch_id:
            batch = QCBatch.objects.get(pk=locked.batch_id)
            if batch.state != QCBatch.State.OPEN or batch.qc_status()[0] != "passed":
                raise ValidationError("Batch QC no longer passes; this test cannot be reviewed.")
        values = [o.value for o in locked.current_observations()]
        _, reportable, conforms = locked.spec.evaluate(values)
        if reportable != locked.reportable_value or conforms != locked.conforms:
            raise ValidationError("Calculated result changed; return the test for resubmission.")
        locked.state = AnalyticalTest.State.REVIEWED
        _bump(lot)

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=test,
        expected_revision=expected_revision,
        meaning="reviewed",
        reason=reason,
        permission=REVIEWER,
        apply=apply,
    )


# QC batches ---------------------------------------------------------------------------------


def create_batch(*, actor, number, method_code, reason):
    require_role(actor, ANALYST)
    _require_reason(reason)
    methods = batch_methods()
    if method_code not in methods:
        raise ValidationError("No approved batch method with this code.")
    payload = methods[method_code]
    with transaction.atomic():
        if QCBatch.objects.filter(number=number).exists():
            raise ValidationError("This batch number already exists.")
        batch = QCBatch.objects.create(
            number=number,
            method_code=method_code,
            method=payload,
            method_hash=canonical_hash(payload),
            created_by=actor,
        )
        record_event(
            actor=actor,
            action="batch.created",
            obj=batch,
            after={
                "number": number,
                "method": method_code,
                "revision": payload["revision"],
                "method_hash": batch.method_hash,
            },
            reason=reason,
        )
        return batch


def assign_to_batch(*, actor, test, batch, reason):
    require_role(actor, ANALYST)
    _require_reason(reason)
    with transaction.atomic():
        batch = QCBatch.objects.select_for_update().get(pk=batch.pk)
        test = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        (lot,) = _lock_lots(test.lot_id)
        if batch.state != QCBatch.State.OPEN or test.state != AnalyticalTest.State.OPEN:
            raise ValidationError("Only open tests can join an open batch.")
        if test.batch_id is not None or test.observations.exists():
            raise ValidationError("This test already has a batch or recorded observations.")
        if batch.tests.exclude(state=AnalyticalTest.State.OPEN).exists():
            raise ValidationError("This batch already has submitted results; start a new batch.")
        method = test.spec.method
        if not method.requires_batch or (method.code, method.revision) != (
            batch.method_spec.code,
            batch.method_spec.revision,
        ):
            raise ValidationError("The test's method revision does not match this batch.")
        test.batch = batch
        _touch(test)
        _touch(batch)
        _bump(lot)
        record_event(
            actor=actor,
            action="test.batched",
            obj=test,
            after={"batch": batch.number},
            reason=reason,
        )
        return test


def _qc_guard(batch):
    if batch.state != QCBatch.State.OPEN:
        raise ValidationError("This batch is closed to QC entries.")
    if batch.tests.exclude(state=AnalyticalTest.State.OPEN).exists():
        raise ValidationError("QC cannot change after test results in this batch are submitted.")


def record_qc(*, actor, batch, check_code, value, raw_reference, reason=""):
    require_role(actor, ANALYST)
    if not raw_reference.strip():
        raise ValidationError("Record where the original QC observation is kept.")
    with transaction.atomic():
        batch = QCBatch.objects.select_for_update().get(pk=batch.pk)
        _qc_guard(batch)
        check = batch.method_spec.check(check_code)
        if batch.current_qc().filter(check_code=check_code).exists():
            raise ValidationError("This QC check is recorded. Correct it instead.")
        result = QCResult(
            batch=batch,
            check_code=check_code,
            value=value,
            value_text=str(value),
            unit=check.unit,
            raw_reference=raw_reference,
            reason=reason,
            recorded_by=actor,
        )
        result.full_clean()
        result.save()
        _touch(batch)
        record_event(
            actor=actor,
            action="qc.recorded",
            obj=batch,
            after={
                "qc_result": result.pk,
                "check": check_code,
                "value": str(value),
                "unit": check.unit,
                "conforms": check.conforms(value),
                "raw_reference": raw_reference,
            },
            reason=reason or "QC observation recorded.",
        )
        return result


def correct_qc(*, actor, qc_result, value, raw_reference, reason):
    require_role(actor, ANALYST)
    _require_reason(reason)
    with transaction.atomic():
        batch = QCBatch.objects.select_for_update().get(pk=qc_result.batch_id)
        _qc_guard(batch)
        original = QCResult.objects.get(pk=qc_result.pk)
        if QCResult.objects.filter(supersedes=original).exists():
            raise ValidationError("This QC result has already been corrected.")
        correction = QCResult(
            batch=batch,
            check_code=original.check_code,
            value=value,
            value_text=str(value),
            unit=original.unit,
            raw_reference=raw_reference,
            supersedes=original,
            reason=reason,
            recorded_by=actor,
        )
        correction.full_clean()
        correction.save()
        _touch(batch)
        record_event(
            actor=actor,
            action="qc.corrected",
            obj=batch,
            before={"qc_result": original.pk, "value": original.value_text},
            after={"qc_result": correction.pk, "value": str(value)},
            reason=reason,
        )
        return correction


def reject_batch(*, actor, pin, batch, expected_revision, reason):
    """Invalidate a QC-failed run; add linked reruns and investigate any out-of-limit values."""

    def apply(locked):
        if locked.state != QCBatch.State.OPEN:
            raise ValidationError("Only open batches can be rejected.")
        if locked.qc_status()[0] != "failed":
            raise ValidationError("Only a batch with failed QC can be rejected.")
        tests = list(locked.tests.select_for_update().order_by("pk"))
        recorders = set(locked.qc_results.values_list("recorded_by_id", flat=True))
        for test in tests:
            recorders |= _test_authors(test)
        if actor.pk in recorders:
            raise ValidationError("You cannot reject a batch containing your own work.")
        lots = _lock_lots(*[t.lot_id for t in tests])
        for test in tests:
            if test.state not in OPEN_STATES:
                raise ValidationError(
                    "Only open or awaiting-review tests can be invalidated by batch rejection."
                )
            spec = test.spec
            out_of_limits = [
                o.value_text for o in test.current_observations() if not spec.conforms(o.value)
            ]
            test.state = AnalyticalTest.State.INVALIDATED
            _touch(test)
            # A rerun of an authorized retest stays inside that investigation's lineage.
            rerun = AnalyticalTest.objects.create(
                lot_id=test.lot_id,
                sample_id=test.sample_id,
                test_code=test.test_code,
                requirement=test.requirement,
                requirement_hash=test.requirement_hash,
                kind=test.kind if test.investigation_id else AnalyticalTest.Kind.RERUN,
                parent=test,
                investigation_id=test.investigation_id,
                created_by=actor,
            )
            record_event(
                actor=actor,
                action="test.invalidated",
                obj=test,
                after={
                    "batch": locked.number,
                    "rerun": rerun.pk,
                    "out_of_limit_values": out_of_limits,
                },
                reason=reason,
            )
            if out_of_limits and test.investigation_id is None:
                _open_investigation(
                    actor=actor,
                    test=test,
                    trigger=f"Out-of-limit {test.test_code} values {', '.join(out_of_limits)} "
                    f"in QC-failed batch {locked.number}",
                )
        locked.state = QCBatch.State.REJECTED
        _bump(*lots)

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=batch,
        expected_revision=expected_revision,
        meaning="rejected",
        reason=reason,
        permission=REVIEWER,
        apply=apply,
    )


# Investigations -----------------------------------------------------------------------------


def add_entry(*, actor, investigation, kind, text, external_reference=""):
    require_role(actor, ANALYST, REVIEWER, QUALITY)
    if kind not in {
        InvestigationEntry.Kind.ASSESSMENT,
        InvestigationEntry.Kind.HYPOTHESIS,
        InvestigationEntry.Kind.EVIDENCE,
        InvestigationEntry.Kind.IMPACT,
    }:
        raise ValidationError("Choose an investigation entry type.")
    _require_reason(text)
    with transaction.atomic():
        investigation = Investigation.objects.select_for_update().get(pk=investigation.pk)
        if not investigation.is_open:
            raise ValidationError("This investigation is closed.")
        entry = InvestigationEntry.objects.create(
            investigation=investigation,
            kind=kind,
            text=text,
            external_reference=external_reference,
            author=actor,
        )
        _touch(investigation)
        record_event(
            actor=actor,
            action=f"investigation.{kind}",
            obj=investigation,
            after={"entry": entry.pk, "external_reference": external_reference},
            reason=text,
        )
        return entry


def escalate(*, actor, investigation, expected_revision, reason):
    require_role(actor, REVIEWER, QUALITY)
    _require_reason(reason)
    with transaction.atomic():
        investigation = Investigation.objects.select_for_update().get(pk=investigation.pk)
        _check_revision(investigation, expected_revision)
        if investigation.phase != Investigation.Phase.LABORATORY:
            raise ValidationError("Only a Phase I investigation can be escalated.")
        investigation.phase = Investigation.Phase.FULL
        InvestigationEntry.objects.create(
            investigation=investigation, kind="escalation", text=reason, author=actor
        )
        _touch(investigation)
        record_event(
            actor=actor,
            action="investigation.escalated",
            obj=investigation,
            before={"phase": "laboratory"},
            after={"phase": "full"},
            reason=reason,
        )
        return investigation


def _require_assessment(investigation):
    if not investigation.entries.filter(kind=InvestigationEntry.Kind.ASSESSMENT).exists():
        raise ValidationError("Record the laboratory assessment first.")


def authorize_retest(*, actor, pin, investigation, expected_revision, kind, reason, sample=None):
    """Quality authorizes one justified retest/resample within the specification's limit."""
    if kind not in {AnalyticalTest.Kind.RETEST, AnalyticalTest.Kind.RESAMPLE}:
        raise ValidationError("Choose retest or resample.")

    def apply(locked):
        if not locked.is_open:
            raise ValidationError("This investigation is closed.")
        original = AnalyticalTest.objects.select_for_update().get(pk=locked.test_id)
        (lot,) = _lock_lots(locked.lot_id)
        if actor.pk in _test_authors(original):
            raise ValidationError("You cannot authorize retesting of your own result.")
        _require_assessment(locked)
        # Runs invalidated by a rejected QC batch are replaced by linked reruns, not counted.
        used = locked.tests.exclude(state=AnalyticalTest.State.INVALIDATED).count()
        if used >= original.spec.max_retests:
            raise ValidationError(
                "The approved specification allows no further retests or resamples."
            )
        if kind == AnalyticalTest.Kind.RETEST:
            target = original.sample_id
        else:
            if sample is None:
                raise ValidationError("Choose the newly collected sample to test.")
            fresh = Sample.objects.get(pk=sample.pk)
            if (
                fresh.lot_id != lot.pk
                or fresh.pk == original.sample_id
                or AnalyticalTest.objects.filter(sample=fresh).exists()
            ):
                raise ValidationError("A resample must be a new, untested sample of this lot.")
            target = fresh.pk
        child = AnalyticalTest.objects.create(
            lot=lot,
            sample_id=target,
            test_code=original.test_code,
            requirement=original.requirement,
            requirement_hash=original.requirement_hash,
            kind=kind,
            parent=original,
            investigation=locked,
            created_by=actor,
        )
        InvestigationEntry.objects.create(
            investigation=locked,
            kind="plan",
            text=reason,
            author=actor,
            external_reference=f"{child.label} {kind}",
        )
        _bump(lot)

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=investigation,
        expected_revision=expected_revision,
        meaning="authorized",
        reason=reason,
        permission=QUALITY,
        apply=apply,
    )


def conclude(*, actor, pin, investigation, expected_revision, outcome, assignable_cause, reason):
    """Independent quality conclusion. Invalidation needs a cause and conforming retest data."""
    if outcome not in Investigation.Outcome.values:
        raise ValidationError("Choose an investigation outcome.")

    def apply(locked):
        if not locked.is_open:
            raise ValidationError("This investigation is already closed.")
        original = AnalyticalTest.objects.select_for_update().get(pk=locked.test_id)
        children = list(locked.tests.select_for_update().order_by("pk"))
        (lot,) = _lock_lots(locked.lot_id)
        # Same independence set as lot disposition: data authors and investigators.
        authors = investigation_author_ids(Investigation.objects.filter(pk=locked.pk))
        authors |= _test_authors(original)
        for child in children:
            authors |= _test_authors(child)
        if actor.pk in authors:
            raise ValidationError("You cannot conclude an investigation of your own work.")
        _require_assessment(locked)
        if original.state not in {AnalyticalTest.State.REVIEWED, AnalyticalTest.State.INVALIDATED}:
            raise ValidationError("The original result needs independent data review first.")
        if any(c.state in OPEN_STATES for c in children):
            raise ValidationError("Authorized retests or resamples are still incomplete.")
        if outcome == Investigation.Outcome.INVALIDATED:
            if not assignable_cause.strip():
                raise ValidationError("Invalidation requires a documented assignable cause.")
            reviewed = [c for c in children if c.state == AnalyticalTest.State.REVIEWED]
            if any(not c.conforms for c in reviewed):
                raise ValidationError(
                    "A retest or resample is also out of specification; the result cannot be "
                    "invalidated."
                )
            if not reviewed:
                raise ValidationError(
                    "Invalidation requires a reviewed retest or resample result to report."
                )
            if original.state == AnalyticalTest.State.REVIEWED:
                original.state = AnalyticalTest.State.INVALIDATED
                _touch(original)
        locked.outcome = outcome
        locked.assignable_cause = assignable_cause
        locked.conclusion = reason
        locked.phase = Investigation.Phase.CLOSED
        locked.closed_at = timezone.now()
        _bump(lot)

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=investigation,
        expected_revision=expected_revision,
        meaning="concluded",
        reason=reason,
        permission=QUALITY,
        apply=apply,
    )
