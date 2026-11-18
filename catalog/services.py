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

from core import file_imports, formulas
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
    """New draft version; QC checks, the calculation and the file import are copied from the
    latest prior version.

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
        file_import=copy.deepcopy(previous.file_import) if previous else None,
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


@transaction.atomic
def set_file_import(
    *,
    actor,
    revision,
    reason,
    source,
    delimiter,
    decimal,
    encoding,
    header_row,
    id_column,
    columns,
    filter_column="",
    filter_value="",
):
    """Set or replace how the instrument's export file is read, on a draft.

    ``columns`` maps each field (a calculation input code, or ``value`` for a result entered
    directly) to the name of its column; a blank column leaves that input to the analyst. The
    mapping's own shape is checked here; that its fields match the calculation is checked when
    the version is approved, so the calculation can still change.
    """
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(revision)
    data = {
        "schema": file_imports.SCHEMA,
        "source": (source or "").strip(),
        "delimiter": delimiter,
        "decimal": decimal,
        "encoding": encoding,
        "header_row": header_row,
        "id_column": (id_column or "").strip(),
        "filter_column": (filter_column or "").strip(),
        "filter_value": (filter_value or "").strip(),
        "columns": [
            {"field": field, "column": column.strip()}
            for field, column in columns.items()
            if (column or "").strip()
        ],
    }
    try:
        file_imports.parse(data)
    except file_imports.FileImportError as exc:
        raise ValidationError(str(exc)) from exc
    before = locked.file_import
    locked.file_import = data
    locked.revision += 1
    locked.save(update_fields=["file_import", "revision"])
    record_event(
        actor=actor,
        action="method_revision.file_import_set",
        obj=locked,
        before=before or {},
        after=data,
        reason=reason,
    )
    return locked


@transaction.atomic
def clear_file_import(*, actor, revision, reason):
    """Remove the file import from a draft: its results are then entered by hand."""
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = _locked_draft(revision)
    before = locked.file_import
    if before is None:
        raise ValidationError("This version has no file import.")
    locked.file_import = None
    locked.revision += 1
    locked.save(update_fields=["file_import", "revision"])
    record_event(
        actor=actor,
        action="method_revision.file_import_cleared",
        obj=locked,
        before=before,
        reason=reason,
    )
    return locked


def file_import_problems(revision):
    """What to fix before a version's file import can be approved; empty when absent or valid."""
    if revision.file_import is None:
        return []
    return file_imports.problems(revision.file_import, revision.import_fields)


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
    if problems := file_import_problems(revision):
        raise ValidationError(["File import: " + problem for problem in problems])


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
    payload = {
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
    # Only a version with a file import carries the key, so the payloads (and the hashes of
    # the lot assignments that freeze them) of every other version stay as they were.
    if file_import := revision.approved_content.get("file_import"):
        payload["file_import"] = file_import
    return payload


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


def statement_text(line):
    """A requirement line in full, for choosing between statements of one test:
    ``requirement_text`` and what it leaves out, where that is not the default."""
    line = {**LINE_DEFAULTS, **line}
    parts = [requirement_text(line)]
    if line["result_type"] == "count":
        parts.append("whole-number count")
    if line["replicates"] != 1 and not line.get("replicate_limits", True):
        parts.append("replicates judged by their mean only")
    if retests := line.get("max_retests", 0):
        parts.append(f"up to {retests} retest{'' if retests == 1 else 's'}")
    return " · ".join(parts)


# What a difference between two statements of a test is called, by the key of the frozen
# test requirement (``test_requirement``) that differs. The schema follows from the others.
DIFFERENCES = {
    "schema": "",
    "name": "name",
    "result_type": "result type",
    "unit": "unit",
    "bounds": "limits",
    "lower_limit": "limits",
    "upper_limit": "limits",
    "lower_inclusive": "limits",
    "upper_inclusive": "limits",
    "expected_result": "expected outcome",
    "criterion": "expected outcome",
    "reporting_decimals": "rounding",
    "replicates": "replicates",
    "replicate_limits": "whether each replicate must meet the limits",
    "max_retests": "retests allowed",
    "method": "method version",
    "required": "required or information only",
}


def _differences(lines):
    """What several statements of one test differ in, in words: everything testing would
    freeze differently, and whether the test is required."""
    shapes = []
    for line in lines:
        try:
            shapes.append({**test_requirement(line, ""), "required": line["required"]})
        except KeyError:
            return ["how the line was approved"]
    found = []
    for key in dict.fromkeys(key for shape in shapes for key in shape):
        # An absent key and an empty text mean the same; 0 and False do not.
        values = {
            json.dumps(None if shape.get(key) == "" else shape.get(key), sort_keys=True)
            for shape in shapes
        }
        label = DIFFERENCES.get(key, key)
        if len(values) > 1 and label and label not in found:
            found.append(label)
    return found


# Keys of an approved specification line in plain words, for a difference that has no visible
# effect on the wording of a statement.
PLAIN_KEYS = {
    "result_type": "result type",
    "unit": "unit",
    "lower_limit": "lower limit",
    "lower_inclusive": "lower limit included",
    "upper_limit": "upper limit",
    "upper_inclusive": "upper limit included",
    "reporting_decimals": "rounding decimals",
    "expected_result": "expected outcome",
    "expected_text": "criterion",
    "replicates": "replicates",
    "replicate_limits": "each replicate must meet the limits",
    "max_retests": "retests allowed",
}


def _plain(value):
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "not stated" if value in (None, "") else str(value)


def _tell_apart(statements, lines):
    """Statements of one test differ, yet two can read the same when the difference has no
    visible effect (a replicate rule with one replicate, the inclusion of a limit that is
    not set, a unit on a qualitative line). Each then states the differing values as
    approved, so that no two statements a signer chooses between read alike."""
    shown = [(item["name"], item["text"], item["required"]) for item in statements]
    if len(set(shown)) == len(shown):
        return
    lines = [{**LINE_DEFAULTS, **line} for line in lines]
    for key, words in PLAIN_KEYS.items():
        values = [_plain(line.get(key)) for line in lines]
        if len(set(values)) > 1:
            for item, value in zip(statements, values, strict=True):
                item["text"] += f" · {words}: {value}"


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
        "text": statement_text(line),
        "required": line["required"],
    }


class Applicable:
    """Everything that applies to a material at a stage under one or more scopes, read once.

    Every specification of a named scope applies in full, and so does every additional rule
    set in force that names the material, stage or one of the scopes (``rules`` is the lot's
    own rule set; additional ones are selected only when it is given). ``freeze`` turns what
    was read into the requirement payload and reads nothing more, so a page, the token of
    what it showed and the signature that follows a choice all rest on the same versions.
    """

    def __init__(self, *, material, stage, scopes, rules=None, at=None):
        self.material, self.stage = material, stage
        self.at = at or timezone.now()
        self.scopes = normalize_scopes(scopes)
        self.reasons = []  # what is missing or not in force, whatever is chosen
        self.rules_payload = None
        self.extra = []
        at = self.at
        if rules is not None:
            try:
                validate_rules(rules, at)
                self.rules_payload = _rules_payload(rules)
            except ValidationError:
                self.reasons.append(f"Rule set {rules} is not approved and effective.")
            self.extra = additional_rules(
                material=material.code,
                stage=stage,
                scopes=self.scopes,
                at=at,
                exclude_code=rules.code,
            )
        self.combined = len(self.scopes) > 1 or bool(self.extra)
        # A scope may select rule sets only; one that selects nothing at all is incomplete.
        ruled = {name for rule in self.extra for name in rule.policy[APPLIES_TO].get("scopes", [])}
        self.specifications = []  # [(scope, specification, revision in force)]
        for name in self.scopes:
            spec = Specification.objects.filter(material=material, stage=stage, scope=name).first()
            revision = effective_revision(SpecificationRevision, spec, at) if spec else None
            if spec is None:
                if name not in ruled:
                    self.reasons.append(
                        f"No specification exists for {material.code} at stage {stage} and "
                        f"scope {name}."
                    )
            elif revision is None:
                self.reasons.append(
                    f"Specification {spec.code} has no approved version effective now."
                )
            else:
                self.specifications.append((name, spec, revision))
        if not self.specifications and not self.reasons:
            self.reasons.append(
                f"No specification applies to {material.code} at stage {stage}: "
                f"{', '.join(self.scopes)} select{'s' if len(self.scopes) == 1 else ''} rule "
                "sets only."
            )
        self.methods = {}  # method code -> payload of the version in force, or None
        stated = {}  # test code -> [(scope, specification, revision, line with its method)]
        self.required_as_stated = {}  # test code -> required by a specification at all
        for name, spec, revision in self.specifications:
            for line in revision.approved_content["tests"]:
                code = line["code"]
                self.required_as_stated[code] = (
                    self.required_as_stated.get(code, False) or line["required"]
                )
                if line["method"] not in self.methods:
                    method = Method.objects.get(code=line["method"])
                    method_revision = effective_revision(MethodRevision, method, at)
                    self.methods[line["method"]] = (
                        _method_payload(method_revision) if method_revision else None
                    )
                    if method_revision is None:
                        self.reasons.append(
                            f"Method {method.code} has no approved version effective now."
                        )
                if self.methods[line["method"]] is None:
                    continue
                stated.setdefault(code, []).append(
                    (name, spec, revision, {**line, "method": self.methods[line["method"]]})
                )
        # test code -> the distinct ways the specifications state it, each a list of the
        # (scope, specification, revision, line) that state it so.
        self.statements = {}
        for code, candidates in stated.items():
            groups = []
            for candidate in candidates:
                for group in groups:
                    if same_requirement(group[0][3], candidate[3]):
                        group.append(candidate)
                        break
                else:
                    groups.append([candidate])
            self.statements[code] = groups

    @property
    def differing(self):
        """The tests the specifications state differently, each with its statements, what
        they differ in and the reason it holds a lot until one is chosen."""
        found = []
        for code, groups in self.statements.items():
            if len(groups) < 2:
                continue
            statements = [_statement(group) for group in groups]
            _tell_apart(statements, [group[0][3] for group in groups])
            found.append(
                {
                    "code": code,
                    "name": groups[0][0][3]["name"],
                    "differs": _differences([group[0][3] for group in groups]),
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
        return found

    @property
    def agreed(self):
        """The tests stated one way only, by one specification or by several alike."""
        return [
            {
                "code": code,
                "name": groups[0][0][3]["name"],
                "text": statement_text(groups[0][0][3]),
                "required": groups[0][0][3]["required"],
                "sources": [candidate[0] for candidate in groups[0]],
            }
            for code, groups in self.statements.items()
            if len(groups) == 1
        ]

    @property
    def applied(self):
        """The versions that were read, for the token of what a page showed: every
        specification, additional rule set and method version in force."""
        return {
            "rules": self.rules_payload["id"] if self.rules_payload else None,
            "additional_rules": [rule.pk for rule in self.extra],
            "specifications": [
                [name, revision.pk, revision.approved_hash]
                for name, _, revision in self.specifications
            ],
            "methods": sorted(
                [code, payload["revision_id"] if payload else None]
                for code, payload in self.methods.items()
            ),
        }

    def line(self, code, scope):
        """The requirement line that ``scope`` states for the test, or None."""
        for group in self.statements.get(code, []):
            for name, _, _, line in group:
                if name == scope:
                    return line
        return None

    def freeze(self, decisions=None):
        """The requirement payload, or ``ApplicabilityHold``.

        A test that the specifications state alike is one requirement. A test they state
        differently is a conflict: nothing is merged and neither the stricter nor the wider
        statement is picked; it holds until ``decisions`` ({test code: scope whose statement
        applies}) names a scope that states the test. A missing specification, method or
        rule coverage is a hold for the quality owner. Reads nothing: the same object can be
        frozen again with other decisions.
        """
        decisions = dict(decisions or {})
        reasons = list(self.reasons)
        differing = {conflict["code"]: conflict for conflict in self.differing}
        tests, decided, conflicts = [], [], []
        required_codes = {code for code, required in self.required_as_stated.items() if required}
        for code, groups in self.statements.items():
            chosen = groups[0]
            if len(groups) > 1:
                wanted = decisions.get(code)
                index = next(
                    (i for i, g in enumerate(groups) if any(c[0] == wanted for c in g)), None
                )
                if index is None:
                    conflicts.append(differing[code])
                    continue
                chosen = groups[index]
                # The statement as it reads among the others (see ``_tell_apart``).
                stated = differing[code]["candidates"][index]
                decided.append(
                    {
                        "code": code,
                        **stated,
                        # The scope that was named; ``scopes`` lists all that state it so.
                        "scope": wanted,
                        "differs": differing[code]["differs"],
                        "alternatives": [
                            item for item in differing[code]["candidates"] if item is not stated
                        ],
                    }
                )
            line = chosen[0][3]
            if line["required"]:
                required_codes.add(code)
            else:
                required_codes.discard(code)
            tests.append({**line, "sources": [c[0] for c in chosen]} if self.combined else line)
        if self.specifications:
            for payload in [self.rules_payload, *(_rules_payload(rule) for rule in self.extra)]:
                if payload is None:
                    continue
                uncovered = sorted(set(payload["required_tests"]) - required_codes)
                if uncovered and not self.combined:
                    reasons.append(
                        "Rule set requires tests missing from the specification: "
                        + ", ".join(uncovered)
                    )
                elif uncovered:
                    reasons.append(
                        f"Rule set {payload['code']} v{payload['version']} requires tests that "
                        "no specification applying to the lot requires: " + ", ".join(uncovered)
                    )
        if reasons or conflicts:
            raise ApplicabilityHold(reasons, conflicts)
        name, spec, revision = self.specifications[0]
        payload = {
            "schema": REQUIREMENTS_SCHEMA_V2 if self.combined else REQUIREMENTS_SCHEMA,
            "resolved_at": self.at.isoformat(),
            "material": {
                "id": self.material.pk,
                "code": self.material.code,
                "name": self.material.name,
                "kind": self.material.kind,
            },
            "stage": self.stage,
            "scope": name,
            "rules": self.rules_payload,
            "specification": _specification_payload(spec, revision),
            "tests": tests,
        }
        if self.combined:
            payload.update(
                scopes=self.scopes,
                additional_rules=[
                    {**_rules_payload(rule), "applies_to": rule.policy[APPLIES_TO]}
                    for rule in self.extra
                ],
                specifications=[
                    {"scope": name, **_specification_payload(spec, revision)}
                    for name, spec, revision in self.specifications
                ],
                decisions=decided,
            )
        return payload


def resolve_requirements(
    *, material, stage, scope=GENERAL, scopes=None, rules=None, at=None, decisions=None
):
    """Resolve the approved, effective requirements for a material at a stage under one or
    more scopes (``general`` and named market or customer overlays), or raise
    ``ApplicabilityHold`` (see ``Applicable``). The payload is plain JSON to be frozen by
    the caller.

    One scope without additional rule sets yields ``oq.requirements/1`` exactly as before;
    anything more yields ``oq.requirements/2``, which keeps the same keys (``specification``
    is the first one) and adds ``scopes``, ``specifications``, ``additional_rules``,
    ``decisions`` and, on each test, the ``sources`` (scopes) that state it.
    """
    read = Applicable(
        material=material,
        stage=stage,
        scopes=scopes if scopes is not None else [scope],
        rules=rules,
        at=at,
    )
    return read.freeze(decisions)


# Analytical testing contract (oq.test-requirement/1 and /2) -------------------------------------

TEST_REQUIREMENT_SCHEMA = "oq.test-requirement/1"
TEST_REQUIREMENT_SCHEMA_V2 = "oq.test-requirement/2"
TEST_REQUIREMENT_SCHEMA_V3 = "oq.test-requirement/3"
TEST_REQUIREMENT_SCHEMA_V4 = "oq.test-requirement/4"


def method_requirement(method):
    """Analytical method shape from a catalog method payload; QC check limits are inclusive.

    A method without a calculation and without resource flags keeps exactly the four keys that
    tests in progress froze. Any other method adds ``requires_equipment``, ``requires_reagent``
    and ``calculation``; payloads frozen earlier lack those keys and read as absent. A method
    with a file import adds ``file_import`` to those seven keys.
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
    file_import = method.get("file_import")
    if calculation is None and not equipment and not reagent and file_import is None:
        return shape
    shape.update(
        requires_equipment=equipment,
        requires_reagent=reagent,
        calculation=copy.deepcopy(calculation),
    )
    if file_import is not None:
        shape["file_import"] = copy.deepcopy(file_import)
    return shape


def test_requirement(test, source):
    """Translate one frozen catalog test line to the analytical keys without coercion.

    A numeric line with both bounds inclusive is emitted as ``oq.test-requirement/1``, byte for
    byte as before, because tests in progress froze that payload and its hash. Every other shape
    is ``oq.test-requirement/2``, or ``/3`` (the same keys) when the method adds the resource flags
    or a calculation, or ``/4`` (the same keys again) when it also reads an instrument file.
    Values pass through as frozen, so shapes the analytical parser cannot execute (for example
    a qualitative line approved without an expected outcome, which yields
    ``expected_result: None``) are held there, never repaired here.
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
        "schema": (
            TEST_REQUIREMENT_SCHEMA_V4
            if "file_import" in method
            else TEST_REQUIREMENT_SCHEMA_V3
            if extended
            else TEST_REQUIREMENT_SCHEMA_V2
        ),
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
    "statement_text",
    "Applicable",
]
