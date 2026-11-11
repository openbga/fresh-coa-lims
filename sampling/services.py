"""Sampling plans, lot requirement assignment and sampling provenance.

Published contract for other packages:
- ``current_requirements(lot)`` -> frozen requirement payload (tests, methods, limits, plan)
  for the lot's current assignment, or raises ``ApplicabilityHold``. Disposition must treat a hold
  as blocking.
- ``current_assignment(lot)`` -> latest LotAssignment or None.
- ``lot_blockers(lot)`` -> sampling reasons blocking QC disposition (call under the lot lock).
- ``test_requirements(lot)`` -> {test_code: oq.test-requirement/1 payload} for package B, or hold.
- ``catalog.services.batch_method_requirements()`` -> B method payloads for batch creation.
"""

from decimal import ROUND_CEILING, Decimal
from math import isqrt

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import RevisionStatus
from catalog.services import (
    AUTHOR_ROLE,
    ApplicabilityHold,
    _check_interval,
    _next_version,
    _require_reason,
    digest,
    effective_revision,
    register_check,
    resolve_requirements,
    test_requirement,
)
from core.audit import record_event, snapshot
from core.services import require_role, sign_transition
from quality.models import Lot, Sample
from quality.services import add_sample

from .models import (
    AssignmentStatus,
    DeviationReview,
    DeviationStatus,
    LotAssignment,
    SamplingBasis,
    SamplingPlan,
    SamplingPlanRevision,
    SamplingPurpose,
    SamplingRecord,
)


def containers_required(basis, parameter, total):
    """Containers the approved plan requires for a lot of ``total`` containers (exact integers)."""
    if total < 1:
        raise ValidationError("A lot has at least one container.")
    if basis == SamplingBasis.ALL:
        needed = total
    elif basis == SamplingBasis.FIXED:
        needed = int(parameter)
    elif basis == SamplingBasis.SQRT_PLUS_ONE:
        root = isqrt(total)
        needed = 1 + (root if root * root == total else root + 1)
    elif basis == SamplingBasis.PERCENT:
        needed = int((Decimal(total) * Decimal(parameter) / 100).to_integral_value(ROUND_CEILING))
    else:
        raise ValidationError("Unknown sampling basis.")
    return max(1, min(total, needed))


def validate_plan_shape(basis, parameter):
    if basis in (SamplingBasis.FIXED, SamplingBasis.PERCENT):
        if parameter is None or parameter <= 0:
            raise ValidationError({"parameter": "Enter a positive count or percentage."})
        if basis == SamplingBasis.FIXED and parameter != parameter.to_integral_value():
            raise ValidationError({"parameter": "A fixed plan needs a whole number of containers."})
        if basis == SamplingBasis.PERCENT and parameter > 100:
            raise ValidationError({"parameter": "A percentage cannot exceed 100."})
    elif parameter is not None:
        raise ValidationError({"parameter": "This basis takes no parameter."})


def _check_plan_revision(revision):
    validate_plan_shape(revision.basis, revision.parameter)
    if not revision.rationale.strip() or not revision.instructions.strip():
        raise ValidationError("Sampling instructions and rationale are required.")


register_check(SamplingPlanRevision, _check_plan_revision)


@transaction.atomic
def create_plan(*, actor, code, title, material, stage, reason, **revision_fields):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    plan = SamplingPlan(code=code, title=title, material=material, stage=stage, created_by=actor)
    plan.full_clean()
    plan.save()
    record_event(
        actor=actor, action="sampling_plan.created", obj=plan, after=snapshot(plan), reason=reason
    )
    revision = new_plan_revision(actor=actor, plan=plan, reason=reason, **revision_fields)
    return plan, revision


@transaction.atomic
def new_plan_revision(
    *,
    actor,
    plan,
    basis,
    minimum_quantity,
    quantity_unit,
    instructions,
    rationale,
    effective_from,
    effective_until,
    reason,
    parameter=None,
    composite_allowed=False,
):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    _check_interval(effective_from, effective_until)
    validate_plan_shape(basis, parameter)
    SamplingPlan.objects.select_for_update().get(pk=plan.pk)
    revision = SamplingPlanRevision(
        plan=plan,
        version=_next_version(SamplingPlanRevision, "plan", plan),
        basis=basis,
        parameter=parameter,
        minimum_quantity=minimum_quantity,
        quantity_unit=quantity_unit,
        composite_allowed=composite_allowed,
        instructions=instructions,
        rationale=rationale,
        effective_from=effective_from,
        effective_until=effective_until,
        change_reason=reason,
        author=actor,
    )
    revision.full_clean()
    revision.save()
    record_event(
        actor=actor,
        action="sampling_plan_revision.created",
        obj=revision,
        after=snapshot(revision),
        reason=reason,
    )
    return revision


# Lot requirements ------------------------------------------------------------------------------


def current_assignment(lot):
    return LotAssignment.objects.filter(lot=lot).order_by("-assigned_at", "-id").first()


def current_requirements(lot):
    assignment = current_assignment(lot)
    if assignment is None:
        raise ApplicabilityHold(["No specification or sampling requirements are assigned."])
    if assignment.status != AssignmentStatus.READY:
        raise ApplicabilityHold(assignment.hold_reasons)
    return assignment.payload


def test_requirements(lot):
    """{test_code: oq.test-requirement/1 payload} for the lot's required tests, or hold.

    Information-only tests are not requirements. ``source`` names the frozen specification
    version and the lot's requirement payload hash, so it changes whenever requirements do.
    """
    payload = current_requirements(lot)
    assignment = current_assignment(lot)
    spec = payload["specification"]
    source = (
        f"catalog:{spec['code']}@v{spec['version']}#rev{spec['revision_id']}"
        f"/lot-req:{assignment.payload_hash[:16]}"
    )
    return {t["code"]: test_requirement(t, source) for t in payload["tests"] if t["required"]}


def _plan_payload(material, stage, at, reasons):
    plan = SamplingPlan.objects.filter(material=material, stage=stage).first()
    revision = effective_revision(SamplingPlanRevision, plan, at) if plan else None
    if plan is None:
        reasons.append(f"No sampling plan exists for {material.code} at stage {stage}.")
    elif revision is None:
        reasons.append(f"Sampling plan {plan.code} has no approved version effective now.")
    else:
        return revision, {
            "revision_id": revision.pk,
            "code": plan.code,
            "version": revision.version,
            "approved_hash": revision.approved_hash,
            **{
                key: revision.approved_content[key]
                for key in (
                    "basis",
                    "parameter",
                    "minimum_quantity",
                    "quantity_unit",
                    "composite_allowed",
                    "instructions",
                )
            },
        }
    return None, None


REASSIGNMENT_REFUSED = (
    "Testing has started on this lot, so its requirements cannot be reassigned. Controlled "
    "supersession of requirements after testing is not supported."
)


def testing_started(lot):
    """True when native analytical tests exist for the lot.

    Read through the app registry so A does not import the testing package; the testing package
    locks the same lot row when it creates tests, so this check serializes with test assignment.
    """
    if not apps.is_installed("analytical"):
        return False
    return apps.get_model("analytical", "AnalyticalTest").objects.filter(lot=lot).exists()


# Read-only preflights shared by pages (GET) and services (under the lot lock) --------------------


def assignment_blocker(lot):
    """Why requirements cannot be (re)assigned to this lot now, or None."""
    if lot.state != "quarantine":
        return "Only quarantined lots can receive requirements."
    if testing_started(lot):
        return REASSIGNMENT_REFUSED
    return None


def sampling_preflight(lot):
    """(assignment, blocker) from ONE read of the current assignment.

    Pages render from the returned assignment so a concurrent reassignment cannot swap in a
    different (e.g. held, plan-less) assignment between the check and the form; submission
    re-reads and re-checks everything under the lot lock.
    """
    assignment = current_assignment(lot)
    if lot.state != "quarantine":
        return assignment, "Only quarantined lots accept new samples."
    if assignment is None:
        return None, "Assign approved requirements before recording sampling."
    if assignment.status != AssignmentStatus.READY:
        return assignment, "Applicability hold: " + "; ".join(assignment.hold_reasons)
    if assignment.plan_revision.status != RevisionStatus.APPROVED:
        return assignment, "The assigned sampling plan is not approved."
    return assignment, None


def sampling_blocker(lot):
    """Why sampling cannot be recorded for this lot now, or None. Hold reasons are listed."""
    return sampling_preflight(lot)[1]


def correction_blocker(record):
    """Why this sampling record cannot be corrected now, or None."""
    if Lot.objects.get(pk=record.lot_id).state != "quarantine":
        return "Sampling for a dispositioned lot cannot be corrected here."
    if SamplingRecord.objects.filter(corrects_id=record.pk).exists():
        return "This record was already corrected. Correct the latest record."
    return None


def assessment_blocker(review, actor=None):
    """(reason, is_permission) why the deviation cannot be assessed now, or (None, False)."""
    record = SamplingRecord.objects.get(pk=review.record_id)
    if Lot.objects.get(pk=record.lot_id).state != "quarantine":
        return "Only deviations of quarantined lots can be assessed.", False
    if review.status != DeviationStatus.PENDING:
        return "This deviation has already been assessed.", False
    if SamplingRecord.objects.filter(corrects_id=record.pk).exists():
        return "This record was corrected; assess the latest record instead.", False
    if actor is not None and actor.pk in {record.sampled_by_id, record.recorded_by_id}:
        return "You sampled or recorded this sample; another person must assess.", True
    return None, False


@transaction.atomic
def assign_requirements(*, actor, lot, material, stage, reason, scope="general"):
    """Freeze the effective specification, methods and sampling plan for a lot, or record a hold.

    A new assignment supersedes the previous one; earlier assignments and their payloads remain.
    The lot revision increments so a disposition prepared against old requirements goes stale.
    Once testing has started the requirements are fixed: tests are bound to the frozen payload
    and there is no controlled supersession of them in the current scope.
    """
    require_role(actor, "analyst", "quality")
    _require_reason(reason)
    locked = Lot.objects.select_for_update().get(pk=lot.pk)
    if blocker := assignment_blocker(locked):
        raise ValidationError(blocker)
    previous = current_assignment(locked)
    at = timezone.now()
    reasons = []
    spec_payload = None
    try:
        spec_payload = resolve_requirements(
            material=material, stage=stage, scope=scope, rules=locked.rules, at=at
        )
    except ApplicabilityHold as hold:
        reasons.extend(hold.reasons)
    plan_revision, plan_payload = _plan_payload(material, stage, at, reasons)
    assignment = LotAssignment(
        lot=locked,
        material=material,
        stage=stage,
        scope=scope,
        reason=reason,
        assigned_by=actor,
        supersedes=previous,
    )
    if reasons:
        assignment.status = AssignmentStatus.HOLD
        assignment.hold_reasons = reasons
    else:
        payload = {**spec_payload, "lot": {"id": locked.pk, "number": locked.number}}
        payload["sampling_plan"] = plan_payload
        assignment.status = AssignmentStatus.READY
        assignment.payload = payload
        assignment.payload_hash = digest(payload)
        assignment.specification_revision_id = spec_payload["specification"]["revision_id"]
        assignment.plan_revision = plan_revision
    assignment.full_clean()
    assignment.save()
    Lot.objects.filter(pk=locked.pk).update(revision=F("revision") + 1)
    record_event(
        actor=actor,
        action="lot.requirements_" + ("assigned" if not reasons else "held"),
        obj=assignment,
        before={"assignment": previous.pk} if previous else {},
        after={
            "lot": locked.pk,
            "status": assignment.status,
            "hold_reasons": reasons,
            "specification_revision": assignment.specification_revision_id,
            "plan_revision": assignment.plan_revision_id,
            "payload_hash": assignment.payload_hash,
        },
        reason=reason,
    )
    return assignment


# Sampling provenance ---------------------------------------------------------------------------


def _check_observation(
    *,
    plan_revision,
    containers_total,
    containers_sampled,
    quantity,
    quantity_unit,
    sampled_at,
    deviation,
):
    errors = {}
    if not plan_revision.effective_from <= sampled_at < plan_revision.effective_until:
        raise ValidationError(
            {
                "sampled_at": f"Sampling plan {plan_revision} is not effective at this sampling "
                "time. Assign current requirements to the lot first."
            }
        )
    required = containers_required(plan_revision.basis, plan_revision.parameter, containers_total)
    if containers_sampled > containers_total:
        errors["containers_sampled"] = "More containers sampled than the lot contains."
    if sampled_at > timezone.now():
        errors["sampled_at"] = "Sampling time cannot be in the future."
    if quantity is None or quantity <= 0:
        errors["quantity"] = "Enter the amount collected."
    if quantity_unit != plan_revision.quantity_unit:
        errors["quantity_unit"] = (
            f"The approved plan states amounts in {plan_revision.quantity_unit}."
        )
    if errors:
        raise ValidationError(errors)
    shortfalls = []
    if containers_sampled < required:
        shortfalls.append(f"plan requires {required} containers; {containers_sampled} sampled")
    if quantity < plan_revision.minimum_quantity:
        shortfalls.append(
            f"plan requires at least {plan_revision.minimum_quantity.normalize():f} "
            f"{plan_revision.quantity_unit}"
        )
    if shortfalls and not deviation.strip():
        raise ValidationError({"deviation": "Record a deviation: " + "; ".join(shortfalls) + "."})
    return required


@transaction.atomic
def record_sampling(
    *,
    actor,
    lot,
    reference,
    sampled_at,
    containers_total,
    containers_sampled,
    container_ids,
    quantity,
    quantity_unit,
    location,
    reason,
    deviation="",
    purpose=SamplingPurpose.ROUTINE,
    resample_of=None,
):
    """Record actual sampling against the lot's approved plan and create the foundation sample.

    A resample (``purpose="resample"``) names the original sample of the same lot it replaces
    for an investigation; the testing package decides whether the resample is authorized.
    """
    require_role(actor, "analyst")
    _require_reason(reason)
    locked = Lot.objects.select_for_update().get(pk=lot.pk)
    assignment = current_assignment(locked)
    if locked.state == "quarantine" and (
        assignment is None or assignment.status != AssignmentStatus.READY
    ):
        current_requirements(locked)  # raises the hold with its reasons
    if blocker := sampling_blocker(locked):
        raise ValidationError(blocker)
    plan_revision = assignment.plan_revision
    if Sample.objects.filter(reference=reference).exists():
        raise ValidationError({"reference": "This sample reference already exists."})
    if purpose == SamplingPurpose.RESAMPLE:
        if (
            resample_of is None
            or resample_of.lot_id != locked.pk
            or not SamplingRecord.objects.filter(sample=resample_of).exists()
        ):
            raise ValidationError(
                {"resample_of": "Choose a sampled original sample of this lot to resample."}
            )
    elif purpose == SamplingPurpose.ROUTINE:
        if resample_of is not None:
            raise ValidationError({"resample_of": "Only a resample names an original sample."})
    else:
        raise ValidationError({"purpose": "Unknown sampling purpose."})
    required = _check_observation(
        plan_revision=plan_revision,
        containers_total=containers_total,
        containers_sampled=containers_sampled,
        quantity=quantity,
        quantity_unit=quantity_unit,
        sampled_at=sampled_at,
        deviation=deviation,
    )
    sample = add_sample(
        actor=actor, lot=locked, reference=reference, collected_at=sampled_at, reason=reason
    )
    record = SamplingRecord(
        lot=locked,
        sample=sample,
        assignment=assignment,
        plan_revision=plan_revision,
        containers_total=containers_total,
        containers_required=required,
        containers_sampled=containers_sampled,
        container_ids=container_ids,
        quantity=quantity,
        quantity_unit=quantity_unit,
        location=location,
        sampled_at=sampled_at,
        sampled_by=actor,
        recorded_by=actor,
        deviation=deviation,
        reason=reason,
        purpose=purpose,
        resample_of=resample_of,
    )
    record.full_clean()
    record.save()
    if record.deviation:
        DeviationReview.objects.create(record=record)
    record_event(
        actor=actor, action="sampling.recorded", obj=record, after=snapshot(record), reason=reason
    )
    return record


@transaction.atomic
def correct_sampling(
    *,
    actor,
    record,
    reason,
    sampled_at,
    containers_total,
    containers_sampled,
    container_ids,
    quantity,
    quantity_unit,
    location,
    deviation="",
):
    """Add a linked correction; the original sampling record is preserved unchanged."""
    require_role(actor, "analyst")
    _require_reason(reason)
    locked_lot = Lot.objects.select_for_update().get(pk=record.lot_id)
    original = SamplingRecord.objects.select_for_update().get(pk=record.pk)
    if blocker := correction_blocker(original):
        raise ValidationError(blocker)
    required = _check_observation(
        plan_revision=original.plan_revision,
        containers_total=containers_total,
        containers_sampled=containers_sampled,
        quantity=quantity,
        quantity_unit=quantity_unit,
        sampled_at=sampled_at,
        deviation=deviation,
    )
    correction = SamplingRecord(
        lot=locked_lot,
        sample=original.sample,
        assignment=original.assignment,
        plan_revision=original.plan_revision,
        containers_total=containers_total,
        containers_required=required,
        containers_sampled=containers_sampled,
        container_ids=container_ids,
        quantity=quantity,
        quantity_unit=quantity_unit,
        location=location,
        sampled_at=sampled_at,
        sampled_by=original.sampled_by,
        recorded_by=actor,
        deviation=deviation,
        reason=reason,
        corrects=original,
        purpose=original.purpose,
        resample_of=original.resample_of,
    )
    correction.full_clean()
    correction.save()
    if correction.deviation:
        DeviationReview.objects.create(record=correction)
    Lot.objects.filter(pk=locked_lot.pk).update(revision=F("revision") + 1)
    record_event(
        actor=actor,
        action="sampling.corrected",
        obj=correction,
        before=snapshot(original),
        after=snapshot(correction),
        reason=reason,
    )
    return correction


# Deviation assessment -------------------------------------------------------------------------


def assess_deviation(*, actor, pin, review, expected_revision, accept, reason):
    """Independent quality decision on a sampling deviation, signed with PIN re-entry."""

    def apply(locked):
        record = SamplingRecord.objects.get(pk=locked.record_id)
        lot = Lot.objects.select_for_update().get(pk=record.lot_id)
        reason, is_permission = assessment_blocker(locked, actor)
        if reason:
            raise (PermissionDenied if is_permission else ValidationError)(reason)
        locked.status = DeviationStatus.ACCEPTED if accept else DeviationStatus.REJECTED
        locked.decided_by = actor
        locked.decided_at = timezone.now()
        Lot.objects.filter(pk=lot.pk).update(revision=F("revision") + 1)

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=review,
        expected_revision=expected_revision,
        meaning="accepted" if accept else "rejected",
        reason=reason,
        permission=AUTHOR_ROLE,
        apply=apply,
    )


# Disposition gate ------------------------------------------------------------------------------


def current_records(lot):
    """{sample_id: latest SamplingRecord in its correction chain} for the lot."""
    records = list(
        SamplingRecord.objects.filter(lot=lot).select_related(
            "sample", "plan_revision", "deviation_review"
        )
    )
    corrected = {r.corrects_id for r in records if r.corrects_id}
    return {r.sample_id: r for r in records if r.pk not in corrected}


def lot_blockers(lot):
    """Reasons this lot's sampling cannot support QC disposition; empty when it can.

    Read-only; call under the caller's lock on the lot row. Every sample of the lot needs current
    sampling provenance against the plan of the current requirement assignment; deviations need
    an accepted independent assessment. An approved plan alone is not evidence of sampling.
    """
    assignment = current_assignment(lot)
    if assignment is None:
        return ["Applicability hold: no specification or sampling requirements are assigned."]
    if assignment.status != AssignmentStatus.READY:
        return [f"Applicability hold: {reason}" for reason in assignment.hold_reasons]
    samples = list(Sample.objects.filter(lot=lot).order_by("reference"))
    if not samples:
        return ["No sampling has been recorded against the approved sampling plan."]
    current = current_records(lot)
    reasons = []
    for sample in samples:
        record = current.get(sample.pk)
        if record is None:
            reasons.append(
                f"Sample {sample.reference} has no sampling record against the approved plan."
            )
            continue
        if record.plan_revision_id != assignment.plan_revision_id:
            reasons.append(
                f"Sample {sample.reference} was sampled under {record.plan_revision}; the current "
                f"requirements use {assignment.plan_revision}."
            )
        if record.deviation:
            review = getattr(record, "deviation_review", None)
            status = review.status if review else DeviationStatus.PENDING
            if status == DeviationStatus.PENDING:
                reasons.append(
                    f"Sampling deviation for sample {sample.reference} awaits quality assessment."
                )
            elif status == DeviationStatus.REJECTED:
                reasons.append(
                    f"Sampling deviation for sample {sample.reference} was rejected; correct the "
                    "record or resample."
                )
    return reasons
