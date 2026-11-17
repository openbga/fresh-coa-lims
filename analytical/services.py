"""Testing, QC and OOS transitions.

Lock order for every transition: QC batch, investigation, tests (by pk), then lots (by pk).
Assigning tests takes the lot's tests before the lot too, because a repeat links to a test.
Signed transitions go through core.services.sign_transition, which locks its record first.
Every evidence change bumps the lot revision so a disposition opened earlier becomes stale.

Observations and batch QC entries also pass the configured bench (contracts.bench): its
``lock_actor`` runs first inside the transaction, ``authorize`` just before the row is created,
and a refusal rolls the entry back before ``record_refusal`` audits it.

A result reported by a contract laboratory is recorded as the test's observations, every
replicate at once, behind the same bench: ``authorize_contract`` checks the laboratory's approval
for the method instead of the analyst and the resources. A test is tested at this bench or
reported by a contract laboratory, never both.

A supplier's certificate result accepted in place of a test is never an observation. While a
proposal or an acceptance stands for a requirement of the lot, a test of that requirement takes
no observation, no reported result, no raw-data file and no QC batch (``supplier_refusal``),
and no test is assigned for it.

A test belongs to the testing of a lot or to a stability pull. For a pull's test the pull
stands where the lot stands: ``_lock_subjects`` locks the lots (by pk), then the pulls and
their studies (through ``contracts.stability_pulls``), refuses a lot that left quarantine and
a pull that takes no more testing, and every evidence change advances the revision of what it
locked. A pull's test names no lot, so the lot of its study is neither locked nor changed.
"""

import datetime
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from psycopg.errors import UniqueViolation

from core.audit import record_event
from core.services import (
    require_role,
    sign_transition,
    validate_approved_rules,
    validate_rules,
)
from quality.models import Lot, Sample

from .contracts import (
    CONTRACT,
    LESS_THAN,
    Reading,
    WorkRefused,
    batch_methods,
    bench,
    canonical_hash,
    contract_source,
    parse_method,
    reported_source,
    require_additional_rules,
    resolve,
    resolve_pull,
    stability_pulls,
    supplier_standing,
)
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
# Closed by a signed record of their own, keeping what they held: never invalidated or rerun.
CLOSED_BY_RECORD = {AnalyticalTest.State.SUPERSEDED, AnalyticalTest.State.NOT_COMPLETED}
BATCH_NUMBER_CONSTRAINT = "analytical_qcbatch_number_key"


def _require_reason(reason):
    if not reason or not reason.strip():
        raise ValidationError("A reason is required.")


def _raise(refusal):
    if refusal:
        raise ValidationError(refusal)


# A lot rejected or cancelled while in quarantine keeps its tests wherever they stood.
DECIDED_WITHOUT_RELEASE = frozenset({"rejected", "cancelled"})


def quarantine_refusal(lot):
    """Reason analytical evidence cannot change on this lot, or None."""
    if lot.state != "quarantine":
        return f"Lot {lot.number} is no longer in quarantine."
    return None


def _lock_lots(*lot_ids, refuse=True):
    lots = list(Lot.objects.select_for_update().filter(pk__in=set(lot_ids)).order_by("pk"))
    for lot in lots if refuse else ():
        _raise(quarantine_refusal(lot))
    return lots


def _lock_subjects(*tests):
    """Lock what the tests belong to and return it: their lots, then their stability pulls.
    A lot that left quarantine and a pull that takes no more testing are refused."""
    lots = _lock_lots(*(test.lot_id for test in tests if test.lot_id is not None))
    pull_ids = {test.pull_id for test in tests if test.pull_id is not None}
    return [*lots, *(stability_pulls().lock(pull_ids) if pull_ids else [])]


def subject_refusal(test):
    """Reason the evidence of this test cannot change now, or None: its lot left quarantine,
    or its stability pull takes no more testing. Shared by the pages; the locked services
    recheck through ``_lock_subjects``."""
    if test.pull_id is None:
        return quarantine_refusal(test.lot)
    try:
        return stability_pulls().refusal(test.pull)
    except ValidationError as exc:
        return " ".join(exc.messages)


def _bump(*subjects):
    """Advance the revision of each locked lot or stability pull: a disposition or an
    acceptance opened before this change is then stale."""
    for subject in subjects:
        subject.revision += 1
        subject.save(update_fields=["revision"])


STALE = "Record changed. Reload and review before continuing."
# Tests whose evidence can still change: of a lot in quarantine, or of a stability pull that
# was pulled and not yet accepted, in a study that is still active.
IN_PROGRESS_SUBJECT = Q(lot__state="quarantine") | Q(
    pull__state="pulled", pull__study__state="active"
)


def _check_revision(record, expected_revision):
    if expected_revision is not None and record.revision != expected_revision:
        raise ValidationError(STALE)


def _touch(record):
    record.revision += 1
    record.save()


def _test_authors(test):
    return data_author_ids(test)


def supplier_refusal(test):
    """Why this test takes no laboratory work now, or None: a supplier's certificate result is
    proposed or accepted in place of it. Shared by the pages and the locked services. A
    supplier's result never stands in for a test of a stability pull."""
    if test.lot_id is None:
        return None
    label = supplier_standing(test.lot).get(test.test_code)
    if label is None:
        return None
    return (
        f"A supplier's result is proposed or accepted in place of this test ({label}). "
        "Withdraw it on the lot record before testing the requirement in the laboratory."
    )


# Test assignment and observations ----------------------------------------------------------


def _lineages(lot, sample):
    """{test_code: tests, oldest first} of the lineages that start with an original test of
    ``sample``: the original and every rerun, retest, resample or repeat that answers for it,
    on whichever sample of the lot it was made."""
    tests = list(AnalyticalTest.objects.filter(lot_id=lot.pk).order_by("pk"))
    by_pk = {test.pk: test for test in tests}
    lineages = {}
    for test in tests:
        root = test
        while root.kind != AnalyticalTest.Kind.ORIGINAL:
            root = by_pk[root.parent_id]
        if root.sample_id == sample.pk:
            lineages.setdefault(test.test_code, []).append(test)
    return lineages


def assign_tests(*, actor, sample, reason):
    """Create the tests a sample still needs for the lot's required codes; return the tests
    and the hold reasons for codes that cannot be tested.

    A code the sample has no test for gets an original test. A code whose tests were all
    superseded when the lot's requirements were replaced gets a linked repeat under the
    current requirement (kind ``revised``), on the sample the superseded test was made on.
    """
    require_role(actor, ANALYST)
    _require_reason(reason)
    with transaction.atomic():
        # The account first, the order of signing and of every other lot writer: the new
        # tests name it, and that reference must not be the last lock taken here.
        get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)
        lot_id = Sample.objects.get(pk=sample.pk).lot_id
        # Tests before the lot, as everywhere in testing: a repeat is inserted with a link to
        # the superseded test it follows, and that link locks the superseded row. Taking the
        # lot's tests first keeps a replacement or a batch rejection that holds them from
        # meeting this request the other way round.
        list(
            AnalyticalTest.objects.select_for_update(no_key=True)
            .filter(lot_id=lot_id)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        (lot,) = _lock_lots(lot_id)
        # Every rule set version the lot is under must be in force: its own, and the ones
        # that apply in addition to it.
        validate_rules(lot.rules)
        require_additional_rules(lot)
        lineages = _lineages(lot, sample)
        accepted, holds = resolve(lot)
        # A requirement a supplier's result is proposed or accepted for gets no test; one is
        # assigned here later if that is withdrawn.
        relied = supplier_standing(lot)
        created = []
        for code, payload in accepted.items():
            if code in relied:
                continue
            lineage = lineages.get(code, [])
            superseded = [t for t in lineage if t.state == AnalyticalTest.State.SUPERSEDED]
            if lineage and (
                not superseded
                or any(t.state in OPEN_STATES | {AnalyticalTest.State.REVIEWED} for t in lineage)
            ):
                # The lineage has a test in progress or reviewed, or was closed by an
                # investigation or a rejected batch, which decide what follows.
                continue
            parent = superseded[-1] if superseded else None
            test = AnalyticalTest.objects.create(
                lot=lot,
                sample_id=parent.sample_id if parent else sample.pk,
                test_code=code,
                requirement=payload,
                requirement_hash=canonical_hash(payload),
                kind=AnalyticalTest.Kind.REVISED if parent else AnalyticalTest.Kind.ORIGINAL,
                parent=parent,
                created_by=actor,
            )
            created.append(test)
            record_event(
                actor=actor,
                action="test.assigned",
                obj=test,
                after={
                    "sample": test.sample_id,
                    "test_code": code,
                    "requirement": payload["source"],
                    "requirement_hash": test.requirement_hash,
                    **({"repeats": parent.pk} if parent else {}),
                },
                reason=reason,
            )
        if created:
            _bump(lot)
        return created, holds


def pull_criteria_hash(accepted):
    """Token of the acceptance criteria a page showed for a pull's tests: the payloads
    ``resolve_pull`` returned, which name the specification and method versions."""
    return canonical_hash(accepted)


CRITERIA_CHANGED = (
    "The acceptance criteria in force changed since this page was opened. Review the "
    "criteria shown now before assigning the tests."
)


def assign_pull_tests(*, actor, pull, reason, criteria_hash):
    """Create the tests of a stability pull: one for each test of its time point, under the
    acceptance criteria of the protocol as they are in force now. Returns the tests created.

    ``criteria_hash`` is ``pull_criteria_hash`` of the criteria the analyst was shown; the
    criteria are read again under the pull lock and a difference is refused, so nothing
    approved in between is frozen unseen. All or nothing: when a test of the time point
    cannot be resolved nothing is assigned and the reasons are raised. The tests belong to
    the pull and name no lot.
    """
    require_role(actor, ANALYST)
    _require_reason(reason)
    with transaction.atomic():
        # Same order as ``assign_tests``: the account, the pull's tests, then the pull.
        get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)
        list(
            AnalyticalTest.objects.select_for_update(no_key=True)
            .filter(pull_id=pull.pk)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        (locked,) = stability_pulls().lock([pull.pk])
        # Read after the pull lock: tests another analyst assigned while this waited are seen.
        existing = set(
            AnalyticalTest.objects.filter(pull_id=locked.pk).values_list("test_code", flat=True)
        )
        accepted, holds = resolve_pull(locked)
        if holds:
            raise ValidationError(holds)
        if pull_criteria_hash(accepted) != criteria_hash:
            raise ValidationError(CRITERIA_CHANGED)
        created = []
        for code, payload in accepted.items():
            if code in existing:
                continue  # its lineage decides what follows: review, rerun or investigation
            test = AnalyticalTest.objects.create(
                pull=locked,
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
                    "pull": locked.pk,
                    "test_code": code,
                    "requirement": payload["source"],
                    "requirement_hash": test.requirement_hash,
                },
                reason=reason,
            )
        if created:
            _bump(locked)
        return created


def _reading(spec, value, qualifier, outcome, observed_text):
    """Validate a reading against the frozen requirement; return (reading, text as recorded)."""
    reading = Reading(value=value, qualifier=qualifier or "", outcome=outcome or "")
    spec.check_reading(reading)
    if spec.is_qualitative:
        if not (observed_text or "").strip():
            raise ValidationError(
                "Describe what was observed; the outcome alone is not a complete record."
            )
        return reading, dict(spec.outcomes)[reading.outcome]
    return reading, f"{reading.qualifier}{value}"


def _entry(spec, *, value, qualifier, outcome, observed_text, inputs):
    """Observation fields for an entered or a calculated result, validated against the spec."""
    calculation = spec.calculation
    if calculation is None:
        if inputs:
            raise ValidationError("This method has no calculation; enter the observed value.")
        reading, text = _reading(spec, value, qualifier, outcome, observed_text)
        return {
            "value": reading.value,
            "qualifier": reading.qualifier,
            "outcome": reading.outcome,
            "value_text": text,
            "observed_text": observed_text,
            "inputs": [],
            "calculation": {},
        }
    if value is not None or qualifier or outcome:
        raise ValidationError(
            "This result is calculated from its inputs; enter the inputs, not the value. "
            "A calculated result cannot be reported as less than a value."
        )
    number, entered = calculation.compute(inputs)
    spec.check_reading(Reading(value=number))
    return {
        "value": number,
        "qualifier": "",
        "outcome": "",
        "value_text": format(number, "f"),
        "observed_text": "",
        "inputs": entered,
        "calculation": calculation.record(spec.method),
    }


def _recheck_calculations(spec, observations, refusal):
    """Recompute every calculated observation from its stored inputs with the frozen formula."""
    calculation = spec.calculation
    for observation in observations:
        if calculation is None and not observation.is_calculated:
            continue
        try:
            if calculation is None or observation.calculation != calculation.record(spec.method):
                raise ValidationError("The calculation applied differs from the frozen method.")
            number, _ = calculation.compute({i["code"]: i["value"] for i in observation.inputs})
        except (ValidationError, KeyError, TypeError) as exc:
            raise ValidationError(refusal) from exc
        if number != observation.value or format(number, "f") != observation.value_text:
            raise ValidationError(refusal)


def _bench_observations(observations):
    """Observations made at this bench. A value reported by a contract laboratory is entered as
    reported and has no stored inputs to recalculate from."""
    return [o for o in observations if o.contract is None]


def _reading_record(observation):
    """The reading as recorded, for audit events."""
    return {
        "value": observation.value_text,
        "qualifier": observation.qualifier,
        "outcome": observation.outcome,
        "observed": observation.observed_text,
        "inputs": observation.inputs,
        "calculation": observation.calculation,
    }


def _resource_ids(ids, label):
    try:
        return sorted({int(i) for i in ids or ()})
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Unknown {label} selected.") from exc


def _with_bench(actor, work, refused="record_refusal"):
    """Run ``work(desk, attempt)`` in one transaction behind the configured bench.

    ``lock_actor`` is the first statement. The work fills ``attempt`` before calling the bench,
    so a WorkRefused rolls everything back and is then audited by the bench's ``refused`` method.
    """
    desk = bench()
    attempt = {}
    try:
        with transaction.atomic():
            desk.lock_actor(actor)
            return work(desk, attempt)
    except WorkRefused as exc:
        if attempt:
            getattr(desk, refused)(actor=actor, refusals=exc.refusals, **attempt)
        raise


def _authorize(
    desk, attempt, *, actor, method, test_code, context, equipment_ids, reagent_ids, reason
):
    """Refuse missing required resources, then ask the bench; return the frozen evidence."""
    errors = {}
    if method.requires_equipment and not equipment_ids:
        errors["equipment_ids"] = (
            f"Method {method.code} requires at least one instrument; select the equipment used."
        )
    if method.requires_reagent and not reagent_ids:
        errors["reagent_ids"] = (
            f"Method {method.code} requires at least one reagent or standard lot; select the "
            "lots used."
        )
    if errors:
        raise ValidationError(errors)
    context_type, context_id = context
    attempt.update(
        method_code=method.code,
        test_code=test_code,
        context_type=context_type,
        context_id=context_id,
        reason=reason,
    )
    evidence = desk.authorize(
        actor=actor,
        method_code=method.code,
        test_code=test_code,
        context_type=context_type,
        context_id=context_id,
        equipment_ids=equipment_ids,
        reagent_ids=reagent_ids,
        reason=reason,
    )
    if not isinstance(evidence, dict):
        raise ValidationError("Bench evidence is missing.")
    if CONTRACT in evidence:
        # Only record_contract_result marks an observation as reported by a contract laboratory;
        # that mark waives this laboratory's batch QC and recalculation.
        raise ValidationError("Bench evidence cannot name a contract laboratory.")
    json.dumps(evidence)  # must be storable as frozen evidence
    return evidence


def record_observation(
    *,
    actor,
    test,
    raw_reference,
    value=None,
    qualifier="",
    outcome="",
    observed_text="",
    inputs=None,
    equipment_ids=(),
    reagent_ids=(),
    reason="",
):
    """Record the next replicate: a number (optionally reported as less than it), an outcome,
    or, when the method has a calculation, the inputs the value is calculated from."""
    require_role(actor, ANALYST)
    if not raw_reference.strip():
        raise ValidationError("Record where the original observation is kept.")
    equipment_ids = _resource_ids(equipment_ids, "equipment")
    reagent_ids = _resource_ids(reagent_ids, "reagent or standard lot")

    def work(desk, attempt):
        locked = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        subjects = _lock_subjects(locked)
        if locked.state != AnalyticalTest.State.OPEN:
            raise ValidationError("This test is not accepting observations.")
        _raise(supplier_refusal(locked))
        spec = locked.spec
        if locked.contract_source() is not None:
            raise ValidationError(REPORTED)
        if spec.method.requires_batch and locked.batch_id is None:
            raise ValidationError("Assign this test to a QC batch before recording results.")
        count = locked.current_observations().count()
        if count >= spec.replicates:
            raise ValidationError("All replicates are recorded. Correct a value instead.")
        fields = _entry(
            spec,
            value=value,
            qualifier=qualifier,
            outcome=outcome,
            observed_text=observed_text,
            inputs=inputs,
        )
        eligibility = _authorize(
            desk,
            attempt,
            actor=actor,
            method=spec.method,
            test_code=locked.test_code,
            context=("analytical.analyticaltest", locked.pk),
            equipment_ids=equipment_ids,
            reagent_ids=reagent_ids,
            reason=reason or f"Replicate {count + 1} of {locked.label} {locked.test_code}",
        )
        observation = Observation(
            test=locked,
            replicate=count + 1,
            unit=spec.unit,
            raw_reference=raw_reference,
            reason=reason,
            eligibility=eligibility,
            recorded_by=actor,
            **fields,
        )
        observation.full_clean()
        observation.save()
        _touch(locked)
        _bump(*subjects)
        record_event(
            actor=actor,
            action="observation.recorded",
            obj=locked,
            after={
                "observation": observation.pk,
                "replicate": observation.replicate,
                **_reading_record(observation),
                "unit": spec.unit,
                "raw_reference": raw_reference,
                "eligibility": eligibility,
            },
            reason=reason or "Observation recorded.",
        )
        return observation

    return _with_bench(actor, work)


def correct_observation(
    *,
    actor,
    observation,
    raw_reference,
    reason,
    value=None,
    qualifier="",
    outcome="",
    observed_text="",
    inputs=None,
    equipment_ids=(),
    reagent_ids=(),
):
    """Add a linked correction; the original row (and its inputs) is preserved and visible."""
    require_role(actor, ANALYST)
    _require_reason(reason)
    equipment_ids = _resource_ids(equipment_ids, "equipment")
    reagent_ids = _resource_ids(reagent_ids, "reagent or standard lot")

    def work(desk, attempt):
        test = AnalyticalTest.objects.select_for_update().get(pk=observation.test_id)
        subjects = _lock_subjects(test)
        if test.state != AnalyticalTest.State.OPEN:
            raise ValidationError(
                "Only open tests can be corrected. A reviewer must return a submitted test first."
            )
        original = Observation.objects.get(pk=observation.pk)
        if Observation.objects.filter(supersedes=original).exists():
            raise ValidationError("This observation has already been corrected.")
        if original.contract is not None:
            raise ValidationError(CONTRACT_REPLICATE)
        spec = test.spec
        fields = _entry(
            spec,
            value=value,
            qualifier=qualifier,
            outcome=outcome,
            observed_text=observed_text,
            inputs=inputs,
        )
        eligibility = _authorize(
            desk,
            attempt,
            actor=actor,
            method=spec.method,
            test_code=test.test_code,
            context=("analytical.analyticaltest", test.pk),
            equipment_ids=equipment_ids,
            reagent_ids=reagent_ids,
            reason=reason,
        )
        correction = Observation(
            test=test,
            replicate=original.replicate,
            unit=original.unit,
            raw_reference=raw_reference,
            supersedes=original,
            reason=reason,
            eligibility=eligibility,
            recorded_by=actor,
            **fields,
        )
        correction.full_clean()
        correction.save()
        _touch(test)
        _bump(*subjects)
        record_event(
            actor=actor,
            action="observation.corrected",
            obj=test,
            before={
                "observation": original.pk,
                **_reading_record(original),
                "raw_reference": original.raw_reference,
            },
            after={
                "observation": correction.pk,
                **_reading_record(correction),
                "raw_reference": raw_reference,
                "eligibility": eligibility,
            },
            reason=reason,
        )
        return correction

    return _with_bench(actor, work)


# Results reported by a contract laboratory ---------------------------------------------------

NOT_ACCEPTING = "This test is not accepting results."
IN_BATCH = (
    "This test is in a QC batch of this laboratory. It is tested here; a contract laboratory's "
    "result cannot be recorded on it."
)
OWN_OBSERVATIONS = (
    "This test holds observations made in this laboratory. A test is tested here or reported "
    "by a contract laboratory, never both."
)
REPORTED = (
    "This test holds a result reported by a contract laboratory. It takes no observation made "
    "in this laboratory; correct the contract laboratory result instead."
)
CONTRACT_REPLICATE = (
    "This replicate was reported by a contract laboratory. Correct the contract laboratory "
    "result as a whole."
)
# One replicate as the report states it. Every key is required; nothing is defaulted.
CONTRACT_READING = ("value", "qualifier", "outcome", "observed_text")
REPORT_NUMBER_LENGTH = 120


def contract_refusal(test, current=None):
    """Why a contract laboratory's result cannot be recorded or corrected on this test, or None.

    Shared by the page and the locked service. ``current`` are the test's current observations
    when the caller has already read them.
    """
    if test.state != AnalyticalTest.State.OPEN:
        return NOT_ACCEPTING
    if test.batch_id is not None:
        return IN_BATCH
    current = list(test.current_observations()) if current is None else current
    if current and reported_source(current) is None:
        return OWN_OBSERVATIONS
    return None


def _contract_readings(spec, readings):
    """Observation fields for each replicate a report states, checked against the requirement.

    The value is entered as reported, also when the method has a calculation: the inputs stay in
    the contract laboratory's own records.
    """
    if not isinstance(readings, (list, tuple)) or len(readings) != spec.replicates:
        raise ValidationError(
            f"Enter the {spec.replicates} replicate result{'s' if spec.replicates != 1 else ''} "
            "the report states."
        )
    fields = []
    for number, item in enumerate(readings, start=1):
        if not isinstance(item, dict) or set(item) != set(CONTRACT_READING):
            raise ValidationError("The contract laboratory result is incomplete.")
        value = item["value"]
        try:
            if value is not None and not isinstance(value, Decimal):
                raise ValidationError("Enter the result as an exact decimal number.")
            if spec.is_qualitative and not (item["observed_text"] or "").strip():
                raise ValidationError("Enter the wording of the result on the report.")
            if not spec.is_qualitative and value is None:
                raise ValidationError("Enter the value the report states.")
            reading, text = _reading(
                spec, value, item["qualifier"], item["outcome"], item["observed_text"]
            )
        except ValidationError as exc:
            raise ValidationError(
                [f"Replicate {number}: {message}" for message in exc.messages]
            ) from exc
        fields.append(
            {
                "value": reading.value,
                "qualifier": reading.qualifier,
                "outcome": reading.outcome,
                "value_text": text,
                "observed_text": (item["observed_text"] or "").strip()
                if spec.is_qualitative
                else "",
                "inputs": [],
                "calculation": {},
            }
        )
    return fields


def _contract_record(observations):
    """A contract laboratory result as audit evidence: what was reported, by whom and where."""
    first = observations[0]
    source = first.contract or {}
    return {
        "observations": [o.pk for o in observations],
        "replicates": [_reading_record(o) for o in observations],
        "raw_reference": first.raw_reference,
        "laboratory": source.get("laboratory", {}).get("code"),
        "report": source.get("report"),
        "approval": source.get("approval", {}).get("id"),
    }


def record_contract_result(
    *,
    actor,
    test,
    expected_revision,
    laboratory_id,
    report_number,
    report_date,
    raw_reference,
    readings,
    reason="",
):
    """Record what a contract laboratory's report states for a test: every replicate at once.

    The laboratory needs a signed approval for the test's method that covers the date of the
    report; the evidence relied on is frozen on each observation. A test that already holds a
    contract laboratory's result is corrected the same way: each replicate gets a linked row,
    the originals stay, and a reason is required. A correction that keeps the laboratory and the
    report keeps the evidence already relied on; naming another laboratory or another report is
    a new acceptance and is checked against the approval again.
    """
    require_role(actor, ANALYST)
    report_number = (report_number or "").strip()
    raw_reference = (raw_reference or "").strip()
    errors = {}
    if not report_number:
        errors["report_number"] = "Enter the number of the laboratory's report."
    elif len(report_number) > REPORT_NUMBER_LENGTH:
        errors["report_number"] = (
            f"The report number has at most {REPORT_NUMBER_LENGTH} characters."
        )
    if not raw_reference:
        errors["raw_reference"] = "Record where the laboratory's report is kept."
    if not isinstance(report_date, datetime.date) or isinstance(report_date, datetime.datetime):
        errors["report_date"] = "Enter the date of the report."
    elif report_date > timezone.localdate():
        errors["report_date"] = "The report cannot be dated in the future."
    if errors:
        raise ValidationError(errors)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        # The page always states the revision it showed; without one a stale entry could
        # replace a result recorded since.
        raise ValidationError(STALE)

    def work(desk, attempt):
        locked = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        _check_revision(locked, expected_revision)
        subjects = _lock_subjects(locked)
        current = list(locked.current_observations().order_by("replicate", "pk"))
        _raise(contract_refusal(locked, current) or supplier_refusal(locked))
        spec = locked.spec
        fields = _contract_readings(spec, readings)
        if current:
            _require_reason(reason)
            if len(current) != spec.replicates:
                raise ValidationError(NOT_ACCEPTING)
        report = {"number": report_number, "date": report_date.isoformat()}
        before = current[0].contract if current else None
        same_report = (
            before is not None
            and before["laboratory"].get("id") == laboratory_id
            and before["report"] == report
        )
        if same_report:
            # The same report of the same laboratory: the acceptance already made stands and
            # nothing new is relied on, so a transcription error can be corrected whatever has
            # happened to the approval since.
            evidence = before
            unchanged = all(o.raw_reference == raw_reference for o in current) and all(
                (o.value, o.qualifier, o.outcome, o.value_text, o.observed_text)
                == (
                    new["value"],
                    new["qualifier"],
                    new["outcome"],
                    new["value_text"],
                    new["observed_text"],
                )
                for o, new in zip(current, fields, strict=True)
            )
            if unchanged:
                raise ValidationError("The correction changes nothing.")
        else:
            # A first entry, another laboratory or another report: a new acceptance, checked
            # against the laboratory's approval for the method.
            context = ("analytical.analyticaltest", locked.pk)
            note = reason or f"Contract laboratory result for {locked.label} {locked.test_code}"
            attempt.update(
                method_code=spec.method.code,
                test_code=locked.test_code,
                context_type=context[0],
                context_id=context[1],
                laboratory_id=laboratory_id,
                report_number=report_number,
                report_date=report_date,
                reason=note,
            )
            evidence = desk.authorize_contract(
                actor=actor,
                laboratory_id=laboratory_id,
                method_code=spec.method.code,
                test_code=locked.test_code,
                context_type=context[0],
                context_id=context[1],
                report_number=report_number,
                report_date=report_date,
            )
            if contract_source({CONTRACT: evidence}) is None:
                raise ValidationError("Contract laboratory evidence is missing.")
            json.dumps(evidence)  # must be storable as frozen evidence
        observations = []
        for index, values in enumerate(fields):
            observation = Observation(
                test=locked,
                replicate=index + 1,
                unit=spec.unit,
                raw_reference=raw_reference,
                supersedes=current[index] if current else None,
                reason=reason,
                eligibility={CONTRACT: evidence},
                recorded_by=actor,
                **values,
            )
            observation.full_clean()
            observation.save()
            observations.append(observation)
        _touch(locked)
        _bump(*subjects)
        record_event(
            actor=actor,
            action="contract_result.corrected" if current else "contract_result.recorded",
            obj=locked,
            before=_contract_record(current) if current else None,
            after={**_contract_record(observations), "unit": spec.unit, "contract": evidence},
            reason=reason or "Contract laboratory result recorded.",
        )
        return observations

    return _with_bench(actor, work, refused="record_contract_refusal")


TRIGGER_LENGTH = Investigation._meta.get_field("trigger").max_length


def _oos_trigger(test, readings):
    """Why a submitted result opened an investigation, worded for its result type."""
    spec = test.spec
    if spec.is_qualitative:
        text = (
            f"Out-of-specification {test.test_code}: observed {test.reportable_display}, "
            f"expected {spec.expected_label}"
        )
    elif any(r.qualifier == LESS_THAN for r in readings):
        text = (
            f"Out-of-specification {test.test_code}: {test.reportable_with_unit} cannot be "
            f"shown to meet {spec.acceptance}"
        )
    else:
        text = f"Out-of-specification {test.test_code}: reportable {test.reportable_with_unit}"
    return text if len(text) <= TRIGGER_LENGTH else text[: TRIGGER_LENGTH - 1] + "…"


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
        subjects = _lock_subjects(test)
        if test.state != AnalyticalTest.State.OPEN or test.batch_id != batch_id:
            raise ValidationError("This test cannot be submitted.")
        spec = test.spec
        current = list(test.current_observations())
        # A contract laboratory runs the method's QC itself; its report is the evidence and
        # the reviewer checks it there. A test reported by one is never in a batch here.
        reported = test.batch_id is None and reported_source(current) is not None
        if spec.method.requires_batch and not reported:
            if batch is None or batch.state != QCBatch.State.OPEN:
                raise ValidationError("An open QC batch is required.")
            status, _ = batch.qc_status()
            if status != "passed":
                raise ValidationError(f"Batch QC is {status}; tests cannot be submitted.")
        _recheck_calculations(
            spec,
            _bench_observations(current),
            "Calculated result changed; correct the observation before submitting.",
        )
        readings = [o.reading for o in current]
        test.mean_value, test.reportable_value, test.reportable_text, test.conforms = spec.evaluate(
            readings
        )
        test.evaluated_at = timezone.now()
        test.submitted_by = actor
        test.state = AnalyticalTest.State.SUBMITTED
        _touch(test)
        _bump(*subjects)
        record_event(
            actor=actor,
            action="test.submitted",
            obj=test,
            after={
                "values": [o.value_text for o in current],
                "mean": None if test.mean_value is None else str(test.mean_value),
                "reportable": test.reportable_display,
                "conforms": test.conforms,
                "requirement_hash": test.requirement_hash,
            },
            reason=reason,
        )
        investigation = None
        if not test.conforms and test.investigation_id is None:
            investigation = _open_investigation(
                actor=actor, test=test, trigger=_oos_trigger(test, readings)
            )
        return test, investigation


# Refusal predicates: shared by the locked service transitions (authoritative) and by the views,
# which call them before rendering an action or signing form so impossible actions show a reason
# instead of a PIN prompt. Each returns a user-facing reason, or None when the action may proceed.


def return_refusal(actor, test):
    if test.state != AnalyticalTest.State.SUBMITTED:
        return "Only submitted tests can be returned."
    if actor.pk in _test_authors(test):
        return "You cannot review your own test."
    if not test.conforms:
        return (
            "Out-of-specification results cannot be returned for correction; "
            "the investigation decides whether the result is invalid."
        )
    return None


def review_refusal(actor, test):
    if test.state != AnalyticalTest.State.SUBMITTED:
        return "This test is not awaiting review."
    if actor.pk in _test_authors(test):
        return "You cannot review your own test."
    if test.batch_id:
        batch = QCBatch.objects.get(pk=test.batch_id)
        if batch.state != QCBatch.State.OPEN or batch.qc_status()[0] != "passed":
            return "Batch QC no longer passes; this test cannot be reviewed."
    return None


def results_submitted(batch):
    """True once a test of the batch has been submitted: the batch's QC is then fixed and it
    takes no more tests. A test superseded before it was ever submitted does not count; one
    superseded after submission does, because its result relied on the QC as it stood. A test
    recorded as not completed was never submitted."""
    return (
        batch.tests.exclude(state=AnalyticalTest.State.OPEN)
        .exclude(
            state__in=[AnalyticalTest.State.SUPERSEDED, AnalyticalTest.State.NOT_COMPLETED],
            evaluated_at__isnull=True,
        )
        .exists()
    )


def batch_join_refusal(batch):
    """Batch-side preconditions for adding a test: open and no results submitted yet."""
    if batch.state != QCBatch.State.OPEN:
        return "Only open tests can join an open batch."
    if results_submitted(batch):
        return "This batch already has submitted results; start a new batch."
    return None


def batching_refusal(test):
    """Test-side preconditions for joining a QC batch (batch-side checks stay in the service)."""
    if test.state != AnalyticalTest.State.OPEN:
        return "Only open tests can join an open batch."
    if test.batch_id is not None or test.observations.exists():
        return "This test already has a batch or recorded observations."
    return None


def return_test(*, actor, test, expected_revision, reason):
    """Reviewer sends a conforming submission back for correction; OOS results cannot return."""
    require_role(actor, REVIEWER)
    _require_reason(reason)
    with transaction.atomic():
        test = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        _check_revision(test, expected_revision)
        subjects = _lock_subjects(test)
        _raise(return_refusal(actor, test))
        before = {
            "mean": None if test.mean_value is None else str(test.mean_value),
            "reportable": test.reportable_display,
        }
        test.state = AnalyticalTest.State.OPEN
        test.mean_value = test.reportable_value = test.conforms = test.evaluated_at = None
        test.reportable_text = ""
        test.submitted_by = None
        _touch(test)
        _bump(*subjects)
        record_event(actor=actor, action="test.returned", obj=test, before=before, reason=reason)
        return test


def review_test(*, actor, pin, test, expected_revision, reason):
    def apply(locked):
        subjects = _lock_subjects(locked)
        _raise(review_refusal(actor, locked))
        # The review evaluates what was recorded against the requirement frozen on the test.
        # It does not need the lot's rule version to be in force still: that is checked when
        # tests are assigned and at disposition, so a version retired meanwhile strands
        # neither a result awaiting review nor the investigation of a failing one. A stability
        # pull is under no rule set: its criteria are those of its protocol.
        if locked.lot_id is not None:
            validate_approved_rules(subjects[0].rules)
        current = list(locked.current_observations())
        _recheck_calculations(
            locked.spec,
            _bench_observations(current),
            "Calculated result changed; return the test for resubmission.",
        )
        readings = [o.reading for o in current]
        _, reportable, text, conforms = locked.spec.evaluate(readings)
        # Tests submitted before the reportable text was frozen carry none to compare.
        text_changed = bool(locked.reportable_text) and text != locked.reportable_text
        if reportable != locked.reportable_value or conforms != locked.conforms or text_changed:
            raise ValidationError("Calculated result changed; return the test for resubmission.")
        locked.state = AnalyticalTest.State.REVIEWED
        _bump(*subjects)

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


# A test that cannot be completed --------------------------------------------------------------

NOT_COMPLETED_SCHEMA = "oq.test-not-completed/1"
CAUSE = AnalyticalTest.NotCompletedCause
SAME, OTHER_SAMPLE = "same", "sample"
# What follows the record, decided by the test and never by the signer's choice alone.
REPEATED, UNDER_INVESTIGATION, OPENS_INVESTIGATION = "repeat", "investigation", "opens"
SELF_NOT_COMPLETED = (
    "You recorded or submitted data on this test, recorded QC of its batch or attached its raw "
    "data. Another quality person must record that it cannot be completed."
)


def outside_limits(test):
    """The current readings of an open test that fail its frozen requirement on their own, as
    recorded: the comparison batch rejection and lot rejection make."""
    spec = test.spec
    return [o.value_text for o in test.current_observations() if not spec.conforms(o.reading)]


def not_completed_follow_up(test, outside=None):
    """What follows when the open test is recorded as not completed: the investigation it
    belongs to decides (an authorized retest or resample, or a rerun of one); readings outside
    the limits open an investigation, which decides; otherwise the test is repeated."""
    if test.investigation_id is not None:
        return UNDER_INVESTIGATION
    if outside is None:
        outside = outside_limits(test)
    return OPENS_INVESTIGATION if outside else REPEATED


def not_completed_refusal(actor, test):
    """Why ``actor`` cannot record now that this test cannot be completed, or None."""
    if test.state == AnalyticalTest.State.SUBMITTED:
        return (
            "This test awaits review: its result is reviewed or, when it conforms, returned "
            "for correction. Only an open test is recorded as not completed."
        )
    if test.state != AnalyticalTest.State.OPEN:
        return "Only an open test is recorded as not completed."
    if refusal := supplier_refusal(test):
        return refusal
    if actor.pk in _test_authors(test):
        return SELF_NOT_COMPLETED
    return None


def _root_sample_id(test):
    while test.kind != AnalyticalTest.Kind.ORIGINAL:
        test = AnalyticalTest.objects.get(pk=test.parent_id)
    return test.sample_id


def repeat_samples(test):
    """The other samples of the test's lot that a repeat may be made on: a sample holding no
    original test whose every test answers for the same sample as this one, so that a new
    sample stands in for one sample of the lot, never for several. Empty for a stability pull,
    which is repeated on the material pulled."""
    if test.lot_id is None:
        return Sample.objects.none()
    root = _root_sample_id(test)
    tests = AnalyticalTest.objects.filter(lot_id=test.lot_id).exclude(sample_id=test.sample_id)
    blocked = set()
    for other in tests.select_related("parent"):
        if other.kind == AnalyticalTest.Kind.ORIGINAL or _root_sample_id(other) != root:
            blocked.add(other.sample_id)
    return (
        Sample.objects.filter(lot_id=test.lot_id)
        .exclude(pk=test.sample_id)
        .exclude(pk__in=blocked)
        .order_by("-pk")
    )


def record_not_completed(
    *, actor, pin, test, expected_revision, cause, reason, repeat="", sample=None
):
    """Quality signs that an open test cannot be completed, keeping everything it holds.

    The signer recorded none of its data. What follows depends on the test, not on a choice:
    a test of an investigation (an authorized retest or resample) is left to that
    investigation; a test holding current readings outside its limits opens an investigation
    on itself, so that they are investigated; any other test is repeated by a linked test of
    the kind ``repeat``, on the same sample or material (``repeat="same"``) or on another
    sample of the lot that stands in for this one (``repeat="sample"``). The record freezes
    the cause, the readings and what follows on the test, signed with the meaning
    ``not_completed``.
    """
    if cause not in CAUSE.values:
        raise ValidationError("Choose the cause.")
    held = {}

    def prepare():
        # An investigation is locked before its tests, as in every other transition.
        investigation_id = (
            AnalyticalTest.objects.filter(pk=test.pk).values_list("investigation_id", flat=True)
        ).get()
        if investigation_id is not None:
            held["investigation"] = Investigation.objects.select_for_update().get(
                pk=investigation_id
            )

    def apply(locked):
        subjects = _lock_subjects(locked)
        _raise(not_completed_refusal(actor, locked))
        if locked.investigation_id != getattr(held.get("investigation"), "pk", None):
            raise ValidationError(STALE)
        current = list(locked.current_observations())
        outside = outside_limits(locked)
        follow = not_completed_follow_up(locked, outside)
        investigation = held.get("investigation")
        child = None
        if follow != REPEATED:
            if repeat:
                raise ValidationError(
                    "This test is not repeated: the investigation decides what follows."
                )
        elif repeat == SAME:
            child = _repeat(actor, locked, locked.sample_id)
        elif repeat == OTHER_SAMPLE:
            if locked.pull_id is not None:
                raise ValidationError(PULL_RESAMPLE)
            if sample is None or not repeat_samples(locked).filter(pk=sample.pk).exists():
                raise ValidationError(
                    "Choose a sample of this lot that holds no tests of its own and stands in "
                    "for no other sample."
                )
            child = _repeat(actor, locked, sample.pk)
        else:
            raise ValidationError("Choose where the test is repeated.")
        if follow == UNDER_INVESTIGATION:
            if not investigation.is_open:
                raise ValidationError("This test's investigation is closed.")
            # A conclusion page opened before this record is stale.
            _touch(investigation)
        elif follow == OPENS_INVESTIGATION:
            investigation = _open_investigation(
                actor=actor,
                test=locked,
                trigger=f"Out-of-limit {locked.test_code} values {', '.join(outside)} in a "
                "test that could not be completed",
            )
        files = locked.raw_files.count()
        locked.state = AnalyticalTest.State.NOT_COMPLETED
        locked.not_completed_record = {
            "schema": NOT_COMPLETED_SCHEMA,
            "cause": cause,
            "recorded": [o.value_text for o in current],
            "outside_limits": outside,
            "raw_data_files": files,
            "batch": locked.batch.number if locked.batch_id else None,
            # Anything recorded on the test, corrected readings included: such a test used
            # an authorized retest even though it gave no result.
            "held_work": bool(files or locked.observations.exists()),
            "follow_up": follow,
            "repeat": None
            if child is None
            else {"test": child.pk, "sample": child.sample.reference if child.sample_id else None},
            "investigation": None
            if investigation is None
            else {"id": investigation.pk, "label": investigation.label},
        }
        _bump(*subjects)

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=test,
        expected_revision=expected_revision,
        meaning="not_completed",
        reason=reason,
        permission=QUALITY,
        apply=apply,
        prepare=prepare,
    )


def _repeat(actor, test, sample_id):
    """The linked test that repeats ``test`` under the requirement frozen on it."""
    child = AnalyticalTest.objects.create(
        lot_id=test.lot_id,
        sample_id=sample_id if test.lot_id is not None else None,
        pull_id=test.pull_id,
        test_code=test.test_code,
        requirement=test.requirement,
        requirement_hash=test.requirement_hash,
        kind=AnalyticalTest.Kind.REPEAT,
        parent=test,
        created_by=actor,
    )
    record_event(
        actor=actor,
        action="test.assigned",
        obj=child,
        after={
            "sample": child.sample_id,
            "pull": child.pull_id,
            "test_code": child.test_code,
            "requirement_hash": child.requirement_hash,
            "repeats": test.pk,
        },
        reason=f"Repeat of {test.label}, which could not be completed",
    )
    return child


# QC batches ---------------------------------------------------------------------------------


NO_EARLIER_BATCH = (
    "No test in progress is frozen to this method revision. A new QC batch uses the revision "
    "in force."
)


def earlier_batch_methods():
    """{(code, revision): method payload} of method revisions that are not the one in force
    and that open tests of lots in quarantine, or of stability pulls being tested, not yet in
    a batch, are frozen to.

    A lot keeps the versions frozen for it, so such a test still gets a QC batch of its own
    method revision: without one a test that cannot be superseded (a retest under an open
    investigation, a test that holds raw data) would have no way forward. The payload is the
    one frozen on the test; a revision nothing in progress needs gets no new batch.
    """
    in_force = {code: payload["revision"] for code, payload in batch_methods().items()}
    found = {}
    waiting = AnalyticalTest.objects.filter(
        IN_PROGRESS_SUBJECT,
        state=AnalyticalTest.State.OPEN,
        batch__isnull=True,
        requirement__method__requires_batch=True,
    )
    for test in waiting.order_by("pk"):
        method = test.requirement["method"]
        key = (method.get("code"), method.get("revision"))
        if key in found or in_force.get(key[0]) == key[1]:
            continue
        try:
            parse_method(method)
        except ValidationError:
            continue
        found[key] = method
    return found


def create_batch(*, actor, number, method_code, reason, revision=None):
    """A QC batch of the method revision in force or, when ``revision`` names an earlier one,
    of the revision that tests in progress are frozen to (``earlier_batch_methods``)."""
    require_role(actor, ANALYST)
    _require_reason(reason)
    methods = batch_methods()
    payload = methods.get(method_code)
    if revision is not None and (payload is None or payload["revision"] != revision):
        payload = earlier_batch_methods().get((method_code, revision))
        if payload is None:
            raise ValidationError(NO_EARLIER_BATCH)
    elif payload is None:
        raise ValidationError("No approved batch method with this code.")
    try:
        with transaction.atomic():
            return _create_batch(actor, number, method_code, payload, reason)
    except IntegrityError as exc:
        # Only a concurrent insert of the same number is expected; anything else is a real fault.
        cause = exc.__cause__
        if not (
            isinstance(cause, UniqueViolation)
            and cause.diag.constraint_name == BATCH_NUMBER_CONSTRAINT
        ):
            raise
        raise ValidationError("This batch number already exists.") from exc


def _create_batch(actor, number, method_code, payload, reason):
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
        subjects = _lock_subjects(test)
        _raise(batch_join_refusal(batch) or batching_refusal(test) or supplier_refusal(test))
        method = test.spec.method
        if not method.requires_batch or (method.code, method.revision) != (
            batch.method_spec.code,
            batch.method_spec.revision,
        ):
            raise ValidationError("The test's method revision does not match this batch.")
        test.batch = batch
        _touch(test)
        _touch(batch)
        _bump(*subjects)
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
    if results_submitted(batch):
        raise ValidationError("QC cannot change after test results in this batch are submitted.")


def _qc_reason(batch, check_code):
    return f"QC check {check_code} of batch {batch.number}"


def record_qc(
    *,
    actor,
    batch,
    check_code,
    value,
    raw_reference,
    equipment_ids=(),
    reagent_ids=(),
    reason="",
):
    require_role(actor, ANALYST)
    if not raw_reference.strip():
        raise ValidationError("Record where the original QC observation is kept.")
    equipment_ids = _resource_ids(equipment_ids, "equipment")
    reagent_ids = _resource_ids(reagent_ids, "reagent or standard lot")

    def work(desk, attempt):
        locked = QCBatch.objects.select_for_update().get(pk=batch.pk)
        _qc_guard(locked)
        method = locked.method_spec
        check = method.check(check_code)
        if locked.current_qc().filter(check_code=check_code).exists():
            raise ValidationError("This QC check is recorded. Correct it instead.")
        eligibility = _authorize(
            desk,
            attempt,
            actor=actor,
            method=method,
            test_code=check_code,
            context=("analytical.qcbatch", locked.pk),
            equipment_ids=equipment_ids,
            reagent_ids=reagent_ids,
            reason=reason or _qc_reason(locked, check_code),
        )
        result = QCResult(
            batch=locked,
            check_code=check_code,
            value=value,
            value_text=str(value),
            unit=check.unit,
            raw_reference=raw_reference,
            reason=reason,
            eligibility=eligibility,
            recorded_by=actor,
        )
        result.full_clean()
        result.save()
        _touch(locked)
        record_event(
            actor=actor,
            action="qc.recorded",
            obj=locked,
            after={
                "qc_result": result.pk,
                "check": check_code,
                "value": str(value),
                "unit": check.unit,
                "conforms": check.conforms(value),
                "raw_reference": raw_reference,
                "eligibility": eligibility,
            },
            reason=reason or "QC observation recorded.",
        )
        return result

    return _with_bench(actor, work)


def correct_qc(*, actor, qc_result, value, raw_reference, reason, equipment_ids=(), reagent_ids=()):
    require_role(actor, ANALYST)
    _require_reason(reason)
    equipment_ids = _resource_ids(equipment_ids, "equipment")
    reagent_ids = _resource_ids(reagent_ids, "reagent or standard lot")

    def work(desk, attempt):
        batch = QCBatch.objects.select_for_update().get(pk=qc_result.batch_id)
        _qc_guard(batch)
        original = QCResult.objects.get(pk=qc_result.pk)
        if QCResult.objects.filter(supersedes=original).exists():
            raise ValidationError("This QC result has already been corrected.")
        eligibility = _authorize(
            desk,
            attempt,
            actor=actor,
            method=batch.method_spec,
            test_code=original.check_code,
            context=("analytical.qcbatch", batch.pk),
            equipment_ids=equipment_ids,
            reagent_ids=reagent_ids,
            reason=reason,
        )
        correction = QCResult(
            batch=batch,
            check_code=original.check_code,
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
        _touch(batch)
        record_event(
            actor=actor,
            action="qc.corrected",
            obj=batch,
            before={"qc_result": original.pk, "value": original.value_text},
            after={"qc_result": correction.pk, "value": str(value), "eligibility": eligibility},
            reason=reason,
        )
        return correction

    return _with_bench(actor, work)


def reject_batch(*, actor, pin, batch, expected_revision, reason):
    """Invalidate a QC-failed run; add linked reruns and investigate any out-of-limit values."""

    def apply(locked):
        if locked.state != QCBatch.State.OPEN:
            raise ValidationError("Only open batches can be rejected.")
        if locked.qc_status()[0] != "failed":
            raise ValidationError("Only a batch with failed QC can be rejected.")
        members = list(locked.tests.select_for_update().order_by("pk"))
        recorders = set(locked.qc_results.values_list("recorded_by_id", flat=True))
        for test in members:
            recorders |= _test_authors(test)
        if actor.pk in recorders:
            raise ValidationError("You cannot reject a batch containing your own work.")
        # A superseded test is closed and stays as it is: it is not invalidated or rerun,
        # though whoever worked on it is still an author of the batch. So is an open test of a
        # stability pull that takes no more testing (missed, or its study closed): it held
        # nothing but its place in the batch, which must not keep the batch from rejection.
        # A test of a rejected lot stays with the lot's record as it was signed, for the same
        # reason: the rejection ended the lot's testing wherever its tests stood. A test
        # recorded as not completed is closed by its own signed record, which kept what it held.
        tests = [t for t in members if t.state not in CLOSED_BY_RECORD]
        lots = _lock_lots(*(t.lot_id for t in tests if t.lot_id is not None), refuse=False)
        ended = {lot.pk for lot in lots if lot.state in DECIDED_WITHOUT_RELEASE}
        for lot in lots:
            if lot.pk not in ended:
                _raise(quarantine_refusal(lot))
        pull_ids = {t.pull_id for t in tests if t.pull_id is not None}
        pulls = stability_pulls().lock(pull_ids, refuse=False) if pull_ids else []
        closed = {pull.pk for pull in pulls if pull.closed}
        tests = [t for t in tests if t.pull_id not in closed and t.lot_id not in ended]
        subjects = [
            *(lot for lot in lots if lot.pk not in ended),
            *(pull for pull in pulls if pull.pk not in closed),
        ]
        for test in tests:
            if test.state not in OPEN_STATES:
                raise ValidationError(
                    "Only open or awaiting-review tests can be invalidated by batch rejection."
                )
            spec = test.spec
            out_of_limits = [
                o.value_text for o in test.current_observations() if not spec.conforms(o.reading)
            ]
            test.state = AnalyticalTest.State.INVALIDATED
            _touch(test)
            # A rerun of an authorized retest stays inside that investigation's lineage.
            rerun = AnalyticalTest.objects.create(
                lot_id=test.lot_id,
                sample_id=test.sample_id,
                pull_id=test.pull_id,
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
        _bump(*subjects)

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


def _assessment_refusal(investigation):
    if not investigation.entries.filter(kind=InvestigationEntry.Kind.ASSESSMENT).exists():
        return "Record the laboratory assessment first."
    return None


def retests_used(investigation):
    """How many of the specification's retests or resamples the investigation has used. A run
    invalidated by a rejected QC batch is replaced by a linked rerun and does not count. An
    authorized test recorded as not completed before it held any result, correction or raw-data
    file gave no result and does not count either; one that held any does."""
    used = 0
    for test in investigation.tests.exclude(state=AnalyticalTest.State.INVALIDATED):
        record = test.not_completed_record
        if test.state == AnalyticalTest.State.NOT_COMPLETED and not record.get("held_work"):
            continue
        used += 1
    return used


def authorize_refusal(actor, investigation, original):
    if not investigation.is_open:
        return "This investigation is closed."
    if actor.pk in _test_authors(original):
        return "You cannot authorize retesting of your own result."
    if refusal := _assessment_refusal(investigation):
        return refusal
    if retests_used(investigation) >= original.spec.max_retests:
        return "The approved specification allows no further retests or resamples."
    return None


def conclude_refusal(actor, investigation, original, children):
    """Outcome-independent preconditions; outcome-specific rules are checked on signing."""
    if not investigation.is_open:
        return "This investigation is already closed."
    # Same independence set as lot disposition: data authors and investigators.
    authors = investigation_author_ids(Investigation.objects.filter(pk=investigation.pk))
    authors |= _test_authors(original)
    for child in children:
        authors |= _test_authors(child)
    if actor.pk in authors:
        return "You cannot conclude an investigation of your own work."
    if refusal := _assessment_refusal(investigation):
        return refusal
    # A test recorded as not completed opened its investigation with readings outside the
    # limits: those readings are what is investigated, and they are never reviewed as a result.
    if original.state not in {
        AnalyticalTest.State.REVIEWED,
        AnalyticalTest.State.INVALIDATED,
        AnalyticalTest.State.NOT_COMPLETED,
    }:
        return "The original result needs independent data review first."
    if any(c.state in OPEN_STATES for c in children):
        return "Authorized retests or resamples are still incomplete."
    return None


PULL_RESAMPLE = (
    "A stability pull has no other sample: authorize a retest of the material that was pulled."
)


def authorize_retest(*, actor, pin, investigation, expected_revision, kind, reason, sample=None):
    """Quality authorizes one justified retest/resample within the specification's limit."""
    if kind not in {AnalyticalTest.Kind.RETEST, AnalyticalTest.Kind.RESAMPLE}:
        raise ValidationError("Choose retest or resample.")

    def apply(locked):
        original = AnalyticalTest.objects.select_for_update().get(pk=locked.test_id)
        subjects = _lock_subjects(original)
        _raise(authorize_refusal(actor, locked, original))
        if kind == AnalyticalTest.Kind.RETEST:
            target = original.sample_id
        elif original.pull_id is not None:
            raise ValidationError(PULL_RESAMPLE)
        else:
            if sample is None:
                raise ValidationError("Choose the newly collected sample to test.")
            fresh = Sample.objects.get(pk=sample.pk)
            if (
                fresh.lot_id != original.lot_id
                or fresh.pk == original.sample_id
                or AnalyticalTest.objects.filter(sample=fresh).exists()
            ):
                raise ValidationError("A resample must be a new, untested sample of this lot.")
            target = fresh.pk
        child = AnalyticalTest.objects.create(
            lot_id=original.lot_id,
            sample_id=target,
            pull_id=original.pull_id,
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
        _bump(*subjects)

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
        original = AnalyticalTest.objects.select_for_update().get(pk=locked.test_id)
        children = list(locked.tests.select_for_update().order_by("pk"))
        subjects = _lock_subjects(original)
        _raise(conclude_refusal(actor, locked, original, children))
        if outcome == Investigation.Outcome.INVALIDATED:
            if not assignable_cause.strip():
                raise ValidationError("Invalidation requires a documented assignable cause.")
            reviewed = [c for c in children if c.state == AnalyticalTest.State.REVIEWED]
            unfinished = [c.label for c in children if c.not_completed_record.get("outside_limits")]
            if unfinished:
                raise ValidationError(
                    f"{', '.join(unfinished)} could not be completed and held readings outside "
                    "the limits; the result cannot be invalidated."
                )
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
        _bump(*subjects)

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
