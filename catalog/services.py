"""Controlled specification/method services and the published requirement contract.

Published contract for other apps (stable names):
- ``resolve_requirements(material=, stage=, scopes=, rules=, at=, decisions=)`` -> requirement
  payload dict, or raises ``ApplicabilityHold`` listing every reason the material cannot be
  assessed and the conflicts between the specifications that apply.
- ``approved_snapshot(revision)`` -> the frozen content and hash bound by the approval signature.
- ``conforms(test, value)`` -> True/False against one payload test line; exact Decimal comparison.
"""

import copy
import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone

from core import formulas
from core.audit import record_event, snapshot
from core.models import AuditEvent
from core.services import (
    APPLIES_TO,
    additional_rules,
    applies_at,
    require_role,
    sign_transition,
    supersede,
    supersession_plan,
    validate_rules,
)

from .models import (
    ExpectedResult,
    Material,
    Method,
    MethodCalculationInput,
    MethodQCCheck,
    MethodRevision,
    RevisionStatus,
    Specification,
    SpecificationRevision,
    SpecificationTest,
)
from .units import INPUT_UNITS, RESULT_UNITS, plain, rounded

AUTHOR_ROLE = "quality"
READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
CONFIG_LOCK = 681250  # Serializes approvals so supersession of overlapped versions cannot race.
REQUIREMENTS_SCHEMA = "oq.requirements/1"
# Several scopes, an additional rule set or a decided conflict: the same keys and more.
REQUIREMENTS_SCHEMA_V2 = "oq.requirements/2"
GENERAL = "general"


class ApplicabilityHold(ValidationError):
    """Requirements cannot be determined; the lot must stay on hold until resolved.

    ``reasons`` is everything that holds the lot. ``conflicts`` is the part of it a quality
    decision settles (specifications that apply state different requirements for one test)
    and ``blocking`` the part it cannot (something is missing or not in force).
    """

    def __init__(self, reasons, conflicts=()):
        self.blocking = list(reasons)
        self.conflicts = list(conflicts)
        self.reasons = self.blocking + [conflict["reason"] for conflict in self.conflicts]
        super().__init__(self.reasons)


def digest(content):
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


def _check_interval(effective_from, effective_until):
    if not effective_from or not effective_until or effective_until <= effective_from:
        raise ValidationError("The effective end must be after the effective start.")


def _lock_config():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CONFIG_LOCK])


def _next_version(model, parent_field, parent):
    latest = model.objects.filter(**{parent_field: parent}).order_by("-version").first()
    return latest.version + 1 if latest else 1


def _locked_draft(revision):
    locked = type(revision).objects.select_for_update().get(pk=revision.pk)
    if locked.status != RevisionStatus.DRAFT:
        raise ValidationError("Only draft revisions can be changed.")
    return locked


# Materials -------------------------------------------------------------------------------------


@transaction.atomic
def create_material(*, actor, code, name, kind, reason):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    material = Material(code=code, name=name, kind=kind, created_by=actor)
    material.full_clean()
    material.save()
    record_event(
        actor=actor,
        action="material.created",
        obj=material,
        after=snapshot(material),
        reason=reason,
    )
    return material


# Methods ---------------------------------------------------------------------------------------


@transaction.atomic
def create_method(*, actor, code, title, reason, **revision_fields):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    method = Method(code=code, title=title, created_by=actor)
    method.full_clean()
    method.save()
    record_event(
        actor=actor, action="method.created", obj=method, after=snapshot(method), reason=reason
    )
    revision = new_method_revision(actor=actor, method=method, reason=reason, **revision_fields)
    return method, revision


@transaction.atomic
def new_method_revision(
    *,
    actor,
    method,
    technique,
    document_ref,
    suitability_kind,
    suitability_ref,
    effective_from,
    effective_until,
    reason,
    summary="",
    requires_batch=False,
    requires_equipment=None,
    requires_reagent=None,
):
    """New draft version; QC checks and the calculation are copied from the latest prior version.

    The two resource flags are taken from the prior version when not given.
    """
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    _check_interval(effective_from, effective_until)
    Method.objects.select_for_update().get(pk=method.pk)
    previous = MethodRevision.objects.filter(method=method).order_by("-version").first()
    if requires_equipment is None:
        requires_equipment = previous.requires_equipment if previous else False
    if requires_reagent is None:
        requires_reagent = previous.requires_reagent if previous else False
    revision = MethodRevision(
        method=method,
        version=_next_version(MethodRevision, "method", method),
        technique=technique,
        document_ref=document_ref,
        suitability_kind=suitability_kind,
        suitability_ref=suitability_ref,
        summary=summary,
        requires_batch=requires_batch,
        requires_equipment=requires_equipment,
        requires_reagent=requires_reagent,
        calculation_formula=previous.calculation_formula if previous else "",
        calculation_unit=previous.calculation_unit if previous else "",
        calculation_decimals=previous.calculation_decimals if previous else None,
        effective_from=effective_from,
        effective_until=effective_until,
        change_reason=reason,
        author=actor,
    )
    revision.full_clean()
    revision.save()
    if previous and requires_batch:
        for check in previous.qc_checks.all():
            check.pk = None
            check.method_revision = revision
            check.created_by = actor
            check.save()
    if previous:
        for item in previous.calculation_inputs.all():
            item.pk = None
            item.method_revision = revision
            item.created_by = actor
            item.save()
    record_event(
        actor=actor,
        action="method_revision.created",
        obj=revision,
        after=snapshot(revision),
        reason=reason,
    )
    return revision


@transaction.atomic
def add_qc_check(*, actor, revision, reason, code, name, unit, lower_limit=None, upper_limit=None):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(revision)
    if not locked.requires_batch:
        raise ValidationError("QC checks apply only to methods that run in a QC batch.")
    if locked.qc_checks.filter(code=code).exists():
        raise ValidationError({"code": "This QC check code is already on the version."})
    if lower_limit is None and upper_limit is None:
        raise ValidationError({"lower_limit": "Enter at least one limit."})
    if lower_limit is not None and upper_limit is not None and lower_limit > upper_limit:
        raise ValidationError({"upper_limit": "The upper limit must not be below the lower limit."})
    check = MethodQCCheck(
        method_revision=locked,
        code=code,
        name=name,
        unit=unit,
        lower_limit=lower_limit,
        upper_limit=upper_limit,
        created_by=actor,
    )
    check.full_clean()
    check.save()
    locked.revision += 1
    locked.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="method_revision.qc_check_added",
        obj=locked,
        after=check.content(),
        reason=reason,
    )
    return check


@transaction.atomic
def remove_qc_check(*, actor, check, reason):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(check.method_revision)
    check = MethodQCCheck.objects.select_for_update().get(pk=check.pk, method_revision=locked)
    before = check.content()
    check.delete()
    locked.revision += 1
    locked.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="method_revision.qc_check_removed",
        obj=locked,
        before=before,
        reason=reason,
    )
    return locked


MAX_CALCULATION_INPUTS = 12
MAX_NAME_LENGTH = 160


def _bump(locked):
    locked.revision += 1
    locked.save(update_fields=["revision"])


@transaction.atomic
def add_calculation_input(*, actor, revision, reason, code, name, unit):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(revision)
    code = (code or "").strip()
    if not formulas.is_name(code):
        raise ValidationError(
            {
                "code": "Use a lower-case letter followed by lower-case letters, digits or "
                "underscores (40 at most)."
            }
        )
    if locked.calculation_inputs.filter(code=code).exists():
        raise ValidationError({"code": "This input code is already on the version."})
    if locked.calculation_inputs.count() >= MAX_CALCULATION_INPUTS:
        raise ValidationError(f"A calculation has at most {MAX_CALCULATION_INPUTS} inputs.")
    if unit not in dict(INPUT_UNITS):
        raise ValidationError({"unit": "Choose a unit from the list."})
    item = MethodCalculationInput(
        method_revision=locked, code=code, name=(name or "").strip(), unit=unit, created_by=actor
    )
    item.full_clean()
    item.save()
    _bump(locked)
    record_event(
        actor=actor,
        action="method_revision.calculation_input_added",
        obj=locked,
        after=item.content(),
        reason=reason,
    )
    return item


@transaction.atomic
def remove_calculation_input(*, actor, item, reason):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(item.method_revision)
    item = MethodCalculationInput.objects.select_for_update().get(
        pk=item.pk, method_revision=locked
    )
    before = item.content()
    item.delete()
    _bump(locked)
    record_event(
        actor=actor,
        action="method_revision.calculation_input_removed",
        obj=locked,
        before=before,
        reason=reason,
    )
    return locked


@transaction.atomic
def set_calculation(*, actor, revision, reason, formula, unit, decimals):
    """Set or replace the formula, result unit and decimals on a draft.

    Only the formula's syntax is checked here, so inputs can be added in any order; names against
    inputs and completeness are checked when the version is approved.
    """
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(revision)
    errors = {}
    try:
        parsed = formulas.parse(formula)
    except formulas.FormulaError as exc:
        errors["formula"] = str(exc)
    if unit not in dict(RESULT_UNITS):
        errors["unit"] = "Choose a unit from the list."
    if (
        not isinstance(decimals, int)
        or isinstance(decimals, bool)
        or not 0 <= decimals <= formulas.MAX_DECIMALS
    ):
        errors["decimals"] = f"Use a whole number from 0 to {formulas.MAX_DECIMALS}."
    if errors:
        raise ValidationError(errors)
    before = locked.calculation()
    locked.calculation_formula = parsed.expression
    locked.calculation_unit = unit
    locked.calculation_decimals = decimals
    locked.revision += 1
    locked.save(
        update_fields=[
            "calculation_formula",
            "calculation_unit",
            "calculation_decimals",
            "revision",
        ]
    )
    record_event(
        actor=actor,
        action="method_revision.calculation_set",
        obj=locked,
        before=before or {},
        after=locked.calculation(),
        reason=reason,
    )
    return locked


@transaction.atomic
def clear_calculation(*, actor, revision, reason):
    """Remove the formula, unit, decimals and every input from a draft."""
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(revision)
    before = locked.calculation()
    if before is None:
        raise ValidationError("This version has no calculation.")
    locked.calculation_inputs.all().delete()
    locked.calculation_formula = ""
    locked.calculation_unit = ""
    locked.calculation_decimals = None
    locked.revision += 1
    locked.save(
        update_fields=[
            "calculation_formula",
            "calculation_unit",
            "calculation_decimals",
            "revision",
        ]
    )
    record_event(
        actor=actor,
        action="method_revision.calculation_cleared",
        obj=locked,
        before=before,
        reason=reason,
    )
    return locked


# Specifications --------------------------------------------------------------------------------


@transaction.atomic
def create_specification(
    *, actor, code, title, material, stage, scope, basis, effective_from, effective_until, reason
):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    spec = Specification(
        code=code, title=title, material=material, stage=stage, scope=scope, created_by=actor
    )
    spec.full_clean()
    spec.save()
    record_event(
        actor=actor, action="specification.created", obj=spec, after=snapshot(spec), reason=reason
    )
    revision = new_specification_revision(
        actor=actor,
        specification=spec,
        basis=basis,
        effective_from=effective_from,
        effective_until=effective_until,
        reason=reason,
    )
    return spec, revision


@transaction.atomic
def new_specification_revision(
    *, actor, specification, basis, effective_from, effective_until, reason
):
    """New draft version; tests are copied from the latest prior version as a starting point."""
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    _check_interval(effective_from, effective_until)
    spec = Specification.objects.select_for_update().get(pk=specification.pk)
    previous = spec.revisions.order_by("-version").first()
    revision = SpecificationRevision(
        specification=spec,
        version=_next_version(SpecificationRevision, "specification", spec),
        basis=basis,
        effective_from=effective_from,
        effective_until=effective_until,
        change_reason=reason,
        author=actor,
    )
    revision.full_clean()
    revision.save()
    if previous:
        for line in previous.tests.all():
            line.pk = None
            line.specification_revision = revision
            line.created_by = actor
            line.save()
    record_event(
        actor=actor,
        action="specification_revision.created",
        obj=revision,
        after={**snapshot(revision), "copied_from": previous.pk if previous else None},
        reason=reason,
    )
    return revision


def _whole_non_negative(value):
    return value >= 0 and value == value.to_integral_value()


def validate_test_line(line):
    """Shape rules shared by forms and services; the database repeats the basic shape.

    Rules the database cannot hold for legacy rows (expected outcome of qualitative lines, equal
    limits, whole-number count limits) are enforced here, on every add and again at approval.
    """
    errors = {}
    low, high = line.lower_limit, line.upper_limit
    if line.result_type in ("numeric", "count"):
        kind = "count" if line.result_type == "count" else "numeric"
        if not line.unit:
            errors["unit"] = f"A {kind} test needs a unit."
        if low is None and high is None:
            errors["lower_limit"] = "Enter at least one limit."
        if line.expected_text:
            errors["expected_text"] = "The criterion text applies only to qualitative tests."
        if line.expected_result:
            errors["expected_result"] = "The expected outcome applies only to qualitative tests."
        if low is not None and high is not None:
            if low > high:
                errors["upper_limit"] = "The upper limit must not be below the lower limit."
            elif low == high and not (line.lower_inclusive and line.upper_inclusive):
                errors["upper_limit"] = (
                    "Equal lower and upper limits must both be inclusive; otherwise no result "
                    "can conform."
                )
        if kind == "count":
            for field, value in (("lower_limit", low), ("upper_limit", high)):
                if value is not None and not _whole_non_negative(value):
                    errors.setdefault(field, "Count limits must be whole numbers of 0 or more.")
    elif line.result_type == "qualitative":
        if not line.expected_result:
            errors["expected_result"] = "Choose the expected outcome."
        if not line.expected_text.strip():
            errors["expected_text"] = "Enter the criterion, e.g. Absent in 25 g."
        if low is not None or high is not None:
            errors["lower_limit"] = "Qualitative tests have no numeric limits."
        if line.reporting_decimals is not None:
            errors["reporting_decimals"] = "Rounding applies only to numeric and count tests."
        if not (line.lower_inclusive and line.upper_inclusive and line.replicate_limits):
            errors["replicate_limits"] = (
                "Qualitative tests have no limits and every replicate must match the expected "
                "outcome; leave the inclusive and each-replicate options set."
            )
    if not 1 <= (line.replicates or 0) <= 10:
        errors["replicates"] = "Use 1 to 10 replicates."
    if not 0 <= (line.max_retests or 0) <= 3:
        errors["max_retests"] = "Use 0 to 3 retests."
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def add_test_line(*, actor, revision, reason, **fields):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(revision)
    if locked.tests.filter(code=fields.get("code")).exists():
        raise ValidationError({"code": "This test code is already on the revision."})
    line = SpecificationTest(specification_revision=locked, created_by=actor, **fields)
    validate_test_line(line)
    line.full_clean()
    line.save()
    locked.revision += 1
    locked.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="specification_revision.test_added",
        obj=locked,
        after=line.content(),
        reason=reason,
    )
    return line


@transaction.atomic
def remove_test_line(*, actor, line, reason):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(line.specification_revision)
    line = SpecificationTest.objects.select_for_update().get(
        pk=line.pk, specification_revision=locked
    )
    before = line.content()
    line.delete()
    locked.revision += 1
    locked.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="specification_revision.test_removed",
        obj=locked,
        before=before,
        reason=reason,
    )
    return locked


# Approval and withdrawal -----------------------------------------------------------------------


def ensure_independent(actor, revision):
    """No self-review: the author and anyone who edited the draft cannot approve it."""
    if revision.author_id == actor.pk:
        raise PermissionDenied("You authored this revision; another quality approver must sign.")
    edited = AuditEvent.objects.filter(
        object_type=revision._meta.label_lower, object_id=str(revision.pk), actor=actor
    ).exclude(action__startswith="signed.")
    if edited.exists():
        raise PermissionDenied("You edited this draft; another quality approver must sign.")


def calculation_problems(revision):
    """What to fix before a version's calculation can be approved; empty when absent or valid."""
    if not revision.has_calculation:
        return []
    problems = []
    inputs = list(revision.calculation_inputs.all())
    codes = {item.code for item in inputs}
    formula = revision.calculation_formula.strip()
    if not formula:
        problems.append("Set the formula, or clear the calculation to remove its inputs.")
    else:
        try:
            used = formulas.parse(formula).names
        except formulas.FormulaError as exc:
            problems.append(f"The formula is not valid: {exc}")
        else:
            if missing := sorted(used - codes):
                problems.append("The formula uses names that are not inputs: " + ", ".join(missing))
            if unused := sorted(codes - used):
                problems.append("These inputs are not used by the formula: " + ", ".join(unused))
    if not 1 <= len(inputs) <= MAX_CALCULATION_INPUTS:
        problems.append(f"A calculation needs 1 to {MAX_CALCULATION_INPUTS} inputs.")
    if not revision.calculation_unit:
        problems.append("Set the unit of the calculated result.")
    if revision.calculation_decimals is None:
        problems.append("Set the number of decimals of the calculated result.")
    return problems


def _check_method_revision(revision):
    if not revision.document_ref.strip() or not revision.suitability_ref.strip():
        raise ValidationError("Link the controlled procedure and suitability evidence.")
    if revision.requires_batch and not revision.qc_checks.exists():
        raise ValidationError("A method that runs in a QC batch needs at least one QC check.")
    if problems := calculation_problems(revision):
        raise ValidationError(["Calculation: " + problem for problem in problems])


def _check_specification_revision(revision):
    lines = list(revision.tests.select_related("method"))
    if not lines:
        raise ValidationError("Add at least one test before approval.")
    missing = []
    for line in lines:
        if line.result_type == "qualitative" and not line.expected_result:
            raise ValidationError(
                f"Test {line.code} has no expected outcome (it was copied from a version approved "
                "before outcomes were recorded). Remove the test and add it again with the "
                "expected outcome, then approve."
            )
        try:
            validate_test_line(line)
        except ValidationError as exc:
            raise ValidationError([f"Test {line.code}: {m}" for m in exc.messages]) from exc
        # The method version that will apply when the specification does: at its start, or
        # now for a specification whose start has already passed.
        method_revision = effective_revision(
            MethodRevision, line.method, max(revision.effective_from, timezone.now())
        )
        if method_revision is None:
            missing.append(line.method.code)
            continue
        calculation = method_revision.approved_content.get("calculation")
        if calculation and (line.result_type != "numeric" or line.unit != calculation["unit"]):
            raise ValidationError(
                f"Test {line.code}: method {line.method.code} version {method_revision.version} "
                f"calculates its result in {calculation['unit']}, so the test must be numeric "
                f"with the unit {calculation['unit']}."
            )
    if missing:
        raise ValidationError(
            "No approved method revision applies when this specification takes effect: "
            + ", ".join(sorted(set(missing)))
        )


CHECKS = {
    MethodRevision: _check_method_revision,
    SpecificationRevision: _check_specification_revision,
}


def register_check(model, check):
    """Sibling controlled-revision models (sampling plans) register their approval checks."""
    CHECKS[model] = check


def retirements(revision, at=None):
    """[(earlier approved version, moment it stops applying)] if ``revision`` is approved at
    ``at`` (now by default). Read-only: the approval page shows it and signing repeats it under
    the configuration lock. Raises ValidationError when a later version is already approved for
    the same dates."""
    siblings = (
        type(revision)
        .objects.filter(**{revision.PARENT_FIELD: revision.parent})
        .exclude(pk=revision.pk)
    )
    return supersession_plan(siblings, revision, at or timezone.now())


def approve_revision(*, actor, pin, revision, expected_revision, reason):
    """Sign a draft version as approved and retire the approved versions it overlaps.

    An earlier approved version of the same document whose period overlaps stops applying when
    this one takes over (see ``core.services.supersession_plan``); each retirement is audited
    in the same transaction as the signature. Lots keep the versions frozen for them.
    """
    model = type(revision)
    check = CHECKS[model]

    def apply(locked):
        _lock_config()
        if locked.status != RevisionStatus.DRAFT:
            raise ValidationError("Only draft revisions can be approved.")
        ensure_independent(actor, locked)
        check(locked)
        supersede(
            actor=actor,
            plan=retirements(locked, locked._signing_timestamp),
            revision=locked,
            action="revision.superseded",
            reason=reason,
        )
        content = locked.content()
        locked.approved_content = content
        locked.approved_hash = digest(content)
        locked.status = RevisionStatus.APPROVED

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=revision,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission=AUTHOR_ROLE,
        apply=apply,
    )


@transaction.atomic
def withdraw_revision(*, actor, revision, expected_revision, reason):
    """Withdraw a draft that will not be approved. Approved versions are never withdrawn here."""
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    try:
        locked = _locked_draft(revision)
    except ValidationError as exc:
        raise ValidationError("Only draft revisions can be withdrawn.") from exc
    if locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before withdrawing.")
    before = snapshot(locked)
    locked.status = RevisionStatus.WITHDRAWN
    locked.revision += 1
    locked.save()
    record_event(
        actor=actor,
        action="revision.withdrawn",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


def approved_snapshot(revision):
    if revision.status != RevisionStatus.APPROVED:
        raise ValidationError("Only approved revisions have a frozen snapshot.")
    return {"content": revision.approved_content, "hash": revision.approved_hash}


# Effective selection and requirement resolution ------------------------------------------------


def effective_revision(model, parent, at):
    """The approved revision that applies at ``at``, or None: inside its effective period and
    not superseded by then. The latest version wins where a version was approved after its own
    start, while the one it retired still applied."""
    return (
        model.objects.filter(applies_at(at), **{model.PARENT_FIELD: parent})
        .order_by("-version")
        .first()
    )


def _method_payload(revision):
    return {
        "revision_id": revision.pk,
        "code": revision.method.code,
        "version": revision.version,
        "document_ref": revision.document_ref,
        "suitability_kind": revision.suitability_kind,
        "suitability_ref": revision.suitability_ref,
        "requires_batch": revision.approved_content.get("requires_batch", False),
        "qc_checks": revision.approved_content.get("qc_checks", []),
        "requires_equipment": revision.approved_content.get("requires_equipment", False),
        "requires_reagent": revision.approved_content.get("requires_reagent", False),
        "calculation": revision.approved_content.get("calculation"),
        "approved_hash": revision.approved_hash,
    }


def effective_batch_methods(at=None):
    """Payloads of methods whose approved version effective at ``at`` runs in a QC batch."""
    at = at or timezone.now()
    revisions = (
        MethodRevision.objects.filter(applies_at(at), requires_batch=True)
        .select_related("method")
        .order_by("method__code", "version")
    )
    # One version per method: the latest of those that apply (see ``effective_revision``).
    latest = {revision.method_id: revision for revision in revisions}
    return [_method_payload(revision) for revision in latest.values()]


def normalize_scopes(scopes):
    """The scopes named for a lot, each once: ``general`` first, then the overlays by name."""
    names = sorted(set(scopes))
    return [name for name in names if name == GENERAL] + [n for n in names if n != GENERAL]


def _rules_payload(rules):
    return {
        "id": rules.pk,
        "code": rules.code,
        "version": rules.version,
        "segment": rules.segment,
        "required_tests": list(rules.policy["required_tests"]),
    }


def _specification_payload(spec, revision):
    return {
        "revision_id": revision.pk,
        "code": spec.code,
        "version": revision.version,
        "approved_hash": revision.approved_hash,
        "effective_from": revision.effective_from.isoformat(),
        "effective_until": revision.effective_until.isoformat(),
    }


def same_requirement(before, after):
    """True when testing would freeze the same requirement for both lines (see
    ``test_requirement``) and both are required alike; a line an earlier release froze
    without today's keys counts as different."""
    if before["required"] != after["required"]:
        return False
    try:
        return test_requirement(before, "") == test_requirement(after, "")
    except KeyError:
        return False


# Keys a line frozen by an earlier release may lack; they read as that release meant them.
LINE_DEFAULTS = {
    "lower_inclusive": True,
    "upper_inclusive": True,
    "expected_result": "",
    "reporting_decimals": None,
    "replicates": 1,
}


def requirement_text(line):
    """One requirement line as text: acceptance, rounding, replicates and method version."""
    line = {**LINE_DEFAULTS, **line}
    parts = [describe_limits(line)]
    if line["result_type"] != "qualitative" and line["reporting_decimals"] is not None:
        parts.append(f"rounded to {line['reporting_decimals']} decimals")
    if line["replicates"] != 1:
        parts.append(f"{line['replicates']} replicates")
    parts.append(f"method {line['method']['code']} v{line['method']['version']}")
    return " · ".join(parts)


def _statement(group):
    """One way a test is stated, with the scopes and specifications that state it so."""
    scope, spec, revision, line = group[0]
    return {
        "scope": scope,
        "scopes": [candidate[0] for candidate in group],
        "specification": {
            "revision_id": revision.pk,
            "code": spec.code,
            "version": revision.version,
        },
        "name": line["name"],
        "text": requirement_text(line),
        "required": line["required"],
    }


def resolve_requirements(
    *, material, stage, scope=GENERAL, scopes=None, rules=None, at=None, decisions=None
):
    """Resolve the approved, effective requirements for a material at a stage under one or
    more scopes (``general`` and named market or customer overlays).

    Every specification of a named scope applies in full, and so does every additional rule
    set in force that names the material, stage or one of the scopes (``rules`` is the lot's
    own rule set; additional ones are selected only when it is given). A test that the
    specifications state alike is one requirement. A test they state differently is a
    conflict: nothing is merged and neither the stricter nor the wider statement is picked;
    the lot is held until quality decides which one applies (``decisions``, {test code: scope
    whose statement applies}). A missing specification, method or rule coverage is a hold for
    the quality owner. The payload is plain JSON to be frozen by the caller.

    One scope without additional rule sets yields ``oq.requirements/1`` exactly as before;
    anything more yields ``oq.requirements/2``, which keeps the same keys (``specification``
    is the first one) and adds ``scopes``, ``specifications``, ``additional_rules``,
    ``decisions`` and, on each test, the ``sources`` (scopes) that state it.
    """
    at = at or timezone.now()
    scopes = normalize_scopes(scopes if scopes is not None else [scope])
    decisions = dict(decisions or {})
    reasons = []
    rules_payload = None
    extra = []
    if rules is not None:
        try:
            validate_rules(rules, at)
            rules_payload = _rules_payload(rules)
        except ValidationError:
            reasons.append(f"Rule set {rules} is not approved and effective.")
        extra = additional_rules(
            material=material.code, stage=stage, scopes=scopes, at=at, exclude_code=rules.code
        )
    combined = len(scopes) > 1 or bool(extra)
    # A scope may select rule sets only; one that selects nothing at all is incomplete.
    ruled = {name for rule in extra for name in rule.policy[APPLIES_TO].get("scopes", [])}
    specifications = []
    for name in scopes:
        spec = Specification.objects.filter(material=material, stage=stage, scope=name).first()
        revision = effective_revision(SpecificationRevision, spec, at) if spec else None
        if spec is None:
            if name not in ruled:
                reasons.append(
                    f"No specification exists for {material.code} at stage {stage} and scope "
                    f"{name}."
                )
        elif revision is None:
            reasons.append(f"Specification {spec.code} has no approved version effective now.")
        else:
            specifications.append((name, spec, revision))
    if not specifications and not reasons:
        reasons.append(
            f"No specification applies to {material.code} at stage {stage}: "
            f"{', '.join(scopes)} select{'s' if len(scopes) == 1 else ''} rule sets only."
        )
    methods = {}
    stated = {}  # test code -> [(scope, specification, revision, line with its method)]
    required_as_stated = {}  # test code -> required by a specification, method resolved or not
    for name, spec, revision in specifications:
        for line in revision.approved_content["tests"]:
            code = line["code"]
            required_as_stated[code] = required_as_stated.get(code, False) or line["required"]
            if line["method"] not in methods:
                method = Method.objects.get(code=line["method"])
                method_revision = effective_revision(MethodRevision, method, at)
                methods[line["method"]] = (
                    _method_payload(method_revision) if method_revision else None
                )
                if method_revision is None:
                    reasons.append(f"Method {method.code} has no approved version effective now.")
            if methods[line["method"]] is None:
                continue
            stated.setdefault(code, []).append(
                (name, spec, revision, {**line, "method": methods[line["method"]]})
            )
    tests, decided, conflicts = [], [], []
    required_codes = {code for code, required in required_as_stated.items() if required}
    for code, candidates in stated.items():
        groups = []  # the distinct ways the specifications state this test
        for candidate in candidates:
            for group in groups:
                if same_requirement(group[0][3], candidate[3]):
                    group.append(candidate)
                    break
            else:
                groups.append([candidate])
        chosen = groups[0]
        if len(groups) > 1:
            statements = [_statement(group) for group in groups]
            wanted = decisions.get(code)
            chosen = next((g for g in groups if any(c[0] == wanted for c in g)), None)
            if chosen is None:
                conflicts.append(
                    {
                        "code": code,
                        "name": candidates[0][3]["name"],
                        "candidates": statements,
                        "reason": "Specifications "
                        + " and ".join(
                            f"{item['specification']['code']} v{item['specification']['version']}"
                            f" ({', '.join(item['scopes'])})"
                            for item in statements
                        )
                        + f" state different requirements for {code}. Quality decides which "
                        "one applies to this lot.",
                    }
                )
                continue
            picked = _statement(chosen)
            decided.append(
                {
                    "code": code,
                    **picked,
                    "alternatives": [item for item in statements if item != picked],
                }
            )
        line = chosen[0][3]
        if line["required"]:
            required_codes.add(code)
        else:
            required_codes.discard(code)
        tests.append({**line, "sources": [c[0] for c in chosen]} if combined else line)
    if specifications:
        for payload in [rules_payload, *(_rules_payload(rule) for rule in extra)]:
            if payload is None:
                continue
            uncovered = sorted(set(payload["required_tests"]) - required_codes)
            if uncovered and not combined:
                reasons.append(
                    "Rule set requires tests missing from the specification: "
                    + ", ".join(uncovered)
                )
            elif uncovered:
                reasons.append(
                    f"Rule set {payload['code']} v{payload['version']} requires tests that no "
                    "specification applying to the lot requires: " + ", ".join(uncovered)
                )
    if reasons or conflicts:
        raise ApplicabilityHold(reasons, conflicts)
    name, spec, revision = specifications[0]
    payload = {
        "schema": REQUIREMENTS_SCHEMA_V2 if combined else REQUIREMENTS_SCHEMA,
        "resolved_at": at.isoformat(),
        "material": {
            "id": material.pk,
            "code": material.code,
            "name": material.name,
            "kind": material.kind,
        },
        "stage": stage,
        "scope": name,
        "rules": rules_payload,
        "specification": _specification_payload(spec, revision),
        "tests": tests,
    }
    if combined:
        payload.update(
            scopes=scopes,
            additional_rules=[
                {**_rules_payload(rule), "applies_to": rule.policy[APPLIES_TO]} for rule in extra
            ],
            specifications=[
                {"scope": name, **_specification_payload(spec, revision)}
                for name, spec, revision in specifications
            ],
            decisions=decided,
        )
    return payload


# Analytical testing contract (oq.test-requirement/1 and /2) -------------------------------------

TEST_REQUIREMENT_SCHEMA = "oq.test-requirement/1"
TEST_REQUIREMENT_SCHEMA_V2 = "oq.test-requirement/2"
TEST_REQUIREMENT_SCHEMA_V3 = "oq.test-requirement/3"


def method_requirement(method):
    """Analytical method shape from a catalog method payload; QC check limits are inclusive.

    A method without a calculation and without resource flags keeps exactly the four keys that
    tests in progress froze. Any other method adds ``requires_equipment``, ``requires_reagent``
    and ``calculation``; payloads frozen earlier lack those keys and read as absent.
    """
    shape = {
        "code": method["code"],
        "revision": method["version"],
        "requires_batch": method["requires_batch"],
        "qc_checks": [dict(check) for check in method["qc_checks"]],
    }
    equipment = bool(method.get("requires_equipment", False))
    reagent = bool(method.get("requires_reagent", False))
    calculation = method.get("calculation")
    if calculation is None and not equipment and not reagent:
        return shape
    shape.update(
        requires_equipment=equipment,
        requires_reagent=reagent,
        calculation=copy.deepcopy(calculation),
    )
    return shape


def test_requirement(test, source):
    """Translate one frozen catalog test line to the analytical keys without coercion.

    A numeric line with both bounds inclusive is emitted as ``oq.test-requirement/1``, byte for
    byte as before, because tests in progress froze that payload and its hash. Every other shape
    is ``oq.test-requirement/2``, or ``/3`` (the same keys) when the method adds the resource flags
    or a calculation. Values pass through as frozen, so shapes the analytical parser
    cannot execute (for example a qualitative line approved without an expected outcome, which
    yields ``expected_result: None``) are held there, never repaired here.
    ``reporting_decimals: None`` passes through as exact comparison without rounding.
    """
    method = method_requirement(test["method"])
    extended = "calculation" in method
    if (
        test["result_type"] == "numeric"
        and test["lower_inclusive"]
        and test["upper_inclusive"]
        and not extended
    ):
        return {
            "schema": TEST_REQUIREMENT_SCHEMA,
            "source": source,
            "test_code": test["code"],
            "name": test["name"],
            "result_type": test["result_type"],
            "bounds": "inclusive",
            "unit": test["unit"],
            "lower_limit": test["lower_limit"],
            "upper_limit": test["upper_limit"],
            "replicates": test["replicates"],
            "reporting_decimals": test["reporting_decimals"],
            "replicate_limits": test["replicate_limits"],
            "max_retests": test["max_retests"],
            "method": method,
        }
    return {
        "schema": TEST_REQUIREMENT_SCHEMA_V3 if extended else TEST_REQUIREMENT_SCHEMA_V2,
        "source": source,
        "test_code": test["code"],
        "name": test["name"],
        "result_type": test["result_type"],
        "unit": test["unit"],
        "lower_limit": test["lower_limit"],
        "upper_limit": test["upper_limit"],
        "lower_inclusive": test["lower_inclusive"],
        "upper_inclusive": test["upper_inclusive"],
        "expected_result": test.get("expected_result") or None,
        "criterion": test["expected_text"],
        "replicates": test["replicates"],
        "reporting_decimals": test["reporting_decimals"],
        "replicate_limits": test["replicate_limits"],
        "max_retests": test["max_retests"],
        "method": method,
    }


def batch_method_requirements(at=None):
    return [method_requirement(m) for m in effective_batch_methods(at)]


# Limits ----------------------------------------------------------------------------------------


def describe_limits(test):
    """Acceptance text of one frozen test line.

    For example "98 – 102 % w/w", "> 5 and ≤ 10 mg/g", "< 10 CFU/g" or
    "Absent: Not detected in 25 g".

    Accepts lines frozen before ``expected_result`` existed: their criterion is shown alone.
    """
    if test["result_type"] == "qualitative":
        expected = test.get("expected_result") or ""
        if not expected:
            return test["expected_text"]
        return f"{ExpectedResult(expected).label}: {test['expected_text']}"
    unit = f" {test['unit']}" if test["unit"] else ""
    low, high = test["lower_limit"], test["upper_limit"]
    lower = f"{'≥' if test['lower_inclusive'] else '>'} {low}"
    upper = f"{'≤' if test['upper_inclusive'] else '<'} {high}"
    if low is not None and high is not None:
        if test["lower_inclusive"] and test["upper_inclusive"]:
            return f"{low} – {high}{unit}"
        return f"{lower} and {upper}{unit}"
    if low is not None:
        return f"{lower}{unit}"
    return f"{upper}{unit}"


def conforms(test, value):
    """Compare one observation with a payload test line. Missing values never conform.

    Qualitative lines compare with the expected outcome (its code or label); a line frozen
    before outcomes existed compares with its criterion text. Counts compare as numbers.
    """
    if value is None or value == "":
        return False
    if test["result_type"] == "qualitative":
        observed = str(value).strip().casefold()
        expected = test.get("expected_result") or ""
        if expected:
            return observed in {expected, ExpectedResult(expected).label.casefold()}
        return observed == test["expected_text"].strip().casefold()
    try:
        observed = rounded(Decimal(str(value)), test["reporting_decimals"])
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("A numeric result must be an exact decimal value.") from exc
    if not observed.is_finite():
        raise ValidationError("A numeric result must be finite.")
    if test["lower_limit"] is not None:
        low = Decimal(test["lower_limit"])
        if observed < low or (observed == low and not test["lower_inclusive"]):
            return False
    if test["upper_limit"] is not None:
        high = Decimal(test["upper_limit"])
        if observed > high or (observed == high and not test["upper_inclusive"]):
            return False
    return True


__all__ = [
    "ApplicabilityHold",
    "approved_snapshot",
    "conforms",
    "describe_limits",
    "effective_batch_methods",
    "batch_method_requirements",
    "test_requirement",
    "plain",
    "requirement_text",
    "resolve_requirements",
    "same_requirement",
]
