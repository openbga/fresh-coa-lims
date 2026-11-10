"""Controlled specification/method services and the published requirement contract.

Published contract for other packages (stable names):
- ``resolve_requirements(material=, stage=, scope=, rules=, at=)`` -> requirement payload dict, or
  raises ``ApplicabilityHold`` listing every reason the material cannot be assessed.
- ``approved_snapshot(revision)`` -> the frozen content and hash bound by the approval signature.
- ``conforms(test, value)`` -> True/False against one payload test line; exact Decimal comparison.
"""

import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone

from core.audit import record_event, snapshot
from core.models import AuditEvent
from core.services import require_role, sign_transition, validate_rules

from .models import (
    Material,
    Method,
    MethodQCCheck,
    MethodRevision,
    RevisionStatus,
    Specification,
    SpecificationRevision,
    SpecificationTest,
)
from .units import plain, rounded

AUTHOR_ROLE = "quality"
READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
CONFIG_LOCK = 681250  # Serializes approvals so overlap checks cannot race.
REQUIREMENTS_SCHEMA = "oq.requirements/1"


class ApplicabilityHold(ValidationError):
    """Requirements cannot be determined; the lot must stay on hold until resolved."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
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
):
    """New draft version; QC checks are copied from the latest prior version as a start."""
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    _check_interval(effective_from, effective_until)
    Method.objects.select_for_update().get(pk=method.pk)
    previous = MethodRevision.objects.filter(method=method).order_by("-version").first()
    revision = MethodRevision(
        method=method,
        version=_next_version(MethodRevision, "method", method),
        technique=technique,
        document_ref=document_ref,
        suitability_kind=suitability_kind,
        suitability_ref=suitability_ref,
        summary=summary,
        requires_batch=requires_batch,
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


def validate_test_line(line):
    """Shape rules shared by forms and services; the database repeats them as constraints."""
    errors = {}
    if line.result_type == "numeric":
        if not line.unit:
            errors["unit"] = "A numeric test needs a unit."
        if line.lower_limit is None and line.upper_limit is None:
            errors["lower_limit"] = "Enter at least one limit."
        if line.expected_text:
            errors["expected_text"] = "Expected text applies only to qualitative tests."
        if (
            line.lower_limit is not None
            and line.upper_limit is not None
            and line.lower_limit > line.upper_limit
        ):
            errors["upper_limit"] = "The upper limit must not be below the lower limit."
    elif line.result_type == "qualitative":
        if not line.expected_text:
            errors["expected_text"] = "Enter the expected result."
        if line.lower_limit is not None or line.upper_limit is not None:
            errors["lower_limit"] = "Qualitative tests have no numeric limits."
        if line.reporting_decimals is not None:
            errors["reporting_decimals"] = "Rounding applies only to numeric tests."
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


def _check_method_revision(revision):
    if not revision.document_ref.strip() or not revision.suitability_ref.strip():
        raise ValidationError("Link the controlled procedure and suitability evidence.")
    if revision.requires_batch and not revision.qc_checks.exists():
        raise ValidationError("A method that runs in a QC batch needs at least one QC check.")


def _check_specification_revision(revision):
    lines = list(revision.tests.select_related("method"))
    if not lines:
        raise ValidationError("Add at least one test before approval.")
    missing = []
    for line in lines:
        validate_test_line(line)
        if effective_revision(MethodRevision, line.method, revision.effective_from) is None:
            missing.append(line.method.code)
    if missing:
        raise ValidationError(
            "No approved method revision is effective at the specification start: "
            + ", ".join(sorted(set(missing)))
        )


CHECKS = {
    MethodRevision: _check_method_revision,
    SpecificationRevision: _check_specification_revision,
}


def register_check(model, check):
    """Sibling controlled-revision models (sampling plans) register their approval checks."""
    CHECKS[model] = check


def approve_revision(*, actor, pin, revision, expected_revision, reason):
    model = type(revision)
    check = CHECKS[model]

    def apply(locked):
        _lock_config()
        if locked.status != RevisionStatus.DRAFT:
            raise ValidationError("Only draft revisions can be approved.")
        ensure_independent(actor, locked)
        check(locked)
        overlaps = (
            model.objects.filter(
                **{locked.PARENT_FIELD: locked.parent},
                status=RevisionStatus.APPROVED,
                effective_from__lt=locked.effective_until,
                effective_until__gt=locked.effective_from,
            )
            .exclude(pk=locked.pk)
            .exists()
        )
        if overlaps:
            raise ValidationError("Effective dates overlap an approved version.")
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
    """The single approved revision effective at ``at`` (intervals cannot overlap), or None."""
    return (
        model.objects.filter(
            **{model.PARENT_FIELD: parent},
            status=RevisionStatus.APPROVED,
            effective_from__lte=at,
            effective_until__gt=at,
        )
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
        "approved_hash": revision.approved_hash,
    }


def effective_batch_methods(at=None):
    """Payloads of methods whose approved version effective at ``at`` runs in a QC batch."""
    at = at or timezone.now()
    revisions = MethodRevision.objects.filter(
        status=RevisionStatus.APPROVED,
        requires_batch=True,
        effective_from__lte=at,
        effective_until__gt=at,
    ).select_related("method")
    return [_method_payload(revision) for revision in revisions.order_by("method__code")]


def resolve_requirements(*, material, stage, scope="general", rules=None, at=None):
    """Resolve the approved, effective requirements for a material at a stage and scope.

    Never merges or picks among obligations: a missing specification, method or rule coverage is a
    hold for the quality owner. The payload is plain JSON to be frozen by the caller.
    """
    at = at or timezone.now()
    reasons = []
    rules_payload = None
    if rules is not None:
        try:
            validate_rules(rules, at)
            rules_payload = {
                "id": rules.pk,
                "code": rules.code,
                "version": rules.version,
                "segment": rules.segment,
                "required_tests": list(rules.policy["required_tests"]),
            }
        except ValidationError:
            reasons.append(f"Rule set {rules} is not approved and effective.")
    spec = Specification.objects.filter(material=material, stage=stage, scope=scope).first()
    revision = effective_revision(SpecificationRevision, spec, at) if spec else None
    tests = []
    if spec is None:
        reasons.append(
            f"No specification exists for {material.code} at stage {stage} and scope {scope}."
        )
    elif revision is None:
        reasons.append(f"Specification {spec.code} has no approved version effective now.")
    else:
        for line in revision.approved_content["tests"]:
            method = Method.objects.get(code=line["method"])
            method_revision = effective_revision(MethodRevision, method, at)
            if method_revision is None:
                reasons.append(f"Method {method.code} has no approved version effective now.")
                continue
            tests.append({**line, "method": _method_payload(method_revision)})
    if rules_payload and revision is not None:
        required_codes = {t["code"] for t in revision.approved_content["tests"] if t["required"]}
        uncovered = sorted(set(rules_payload["required_tests"]) - required_codes)
        if uncovered:
            reasons.append(
                "Rule set requires tests missing from the specification: " + ", ".join(uncovered)
            )
    if reasons:
        raise ApplicabilityHold(reasons)
    return {
        "schema": REQUIREMENTS_SCHEMA,
        "resolved_at": at.isoformat(),
        "material": {
            "id": material.pk,
            "code": material.code,
            "name": material.name,
            "kind": material.kind,
        },
        "stage": stage,
        "scope": scope,
        "rules": rules_payload,
        "specification": {
            "revision_id": revision.pk,
            "code": spec.code,
            "version": revision.version,
            "approved_hash": revision.approved_hash,
            "effective_from": revision.effective_from.isoformat(),
            "effective_until": revision.effective_until.isoformat(),
        },
        "tests": tests,
    }


# Testing contract (package B: oq.test-requirement/1) --------------------------------------------

TEST_REQUIREMENT_SCHEMA = "oq.test-requirement/1"


def method_requirement(method):
    """B's method shape from an A method payload; QC check limits are inclusive."""
    return {
        "code": method["code"],
        "revision": method["version"],
        "requires_batch": method["requires_batch"],
        "qc_checks": [dict(check) for check in method["qc_checks"]],
    }


def test_requirement(test, source):
    """Translate one frozen A test line to B's exact keys without coercion.

    Shapes B cannot represent are passed through faithfully so B's parser holds them:
    qualitative ``result_type``, ``bounds: "exclusive"`` and ``reporting_decimals: None``.
    """
    inclusive = test["lower_inclusive"] and test["upper_inclusive"]
    return {
        "schema": TEST_REQUIREMENT_SCHEMA,
        "source": source,
        "test_code": test["code"],
        "name": test["name"],
        "result_type": test["result_type"],
        "bounds": "inclusive" if inclusive else "exclusive",
        "unit": test["unit"],
        "lower_limit": test["lower_limit"],
        "upper_limit": test["upper_limit"],
        "replicates": test["replicates"],
        "reporting_decimals": test["reporting_decimals"],
        "replicate_limits": test["replicate_limits"],
        "max_retests": test["max_retests"],
        "method": method_requirement(test["method"]),
    }


def batch_method_requirements(at=None):
    return [method_requirement(m) for m in effective_batch_methods(at)]


# Limits ----------------------------------------------------------------------------------------


def describe_limits(test):
    if test["result_type"] == "qualitative":
        return test["expected_text"]
    unit = f" {test['unit']}" if test["unit"] else ""
    low, high = test["lower_limit"], test["upper_limit"]
    if low is not None and high is not None:
        return f"{low} – {high}{unit}" + (
            "" if test["lower_inclusive"] and test["upper_inclusive"] else " (exclusive bound)"
        )
    if low is not None:
        return f"{'≥' if test['lower_inclusive'] else '>'} {low}{unit}"
    return f"{'≤' if test['upper_inclusive'] else '<'} {high}{unit}"


def conforms(test, value):
    """Compare one observation with a payload test line. Missing values never conform."""
    if value is None or value == "":
        return False
    if test["result_type"] == "qualitative":
        return str(value).strip().casefold() == test["expected_text"].strip().casefold()
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
    "resolve_requirements",
]
