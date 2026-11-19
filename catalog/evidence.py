"""Records of the evidence that a method is suitable for its intended use, and the suitability a
method version relies on.

A record summarizes a validation, a compendial verification, a transfer or another documented
demonstration of fitness for use, kept in full in the laboratory's document system. An analyst,
a reviewer or a quality person records it and its characteristics as a draft; a quality person
who neither recorded nor changed it approves it with a signature that freezes its content.
Quality withdraws an approved record with a signature; a draft is withdrawn by its recorder or
by quality. The database refuses any other change (migration 0009).

A draft method version relies either on an approved record of its method that concludes the
method is suitable, or on an external reference only; its approval checks the record again
under lock and freezes it with the version.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from core.audit import record_event, snapshot
from core.models import AuditEvent
from core.services import require_role, sign_transition

from .models import (
    SOURCED_KINDS,
    MethodEvidence,
    MethodEvidenceCharacteristic,
    MethodRevision,
    SuitabilityKind,
)

RECORDERS = ("analyst", "reviewer", "quality")
APPROVER = "quality"
MAX_CHARACTERISTICS = 30
FIELDS = (
    "kind",
    "title",
    "procedure_ref",
    "intended_use",
    "source",
    "transfer_approach",
    "protocol_ref",
    "report_ref",
    "report_url",
    "completed_on",
    "conclusion",
    "statement",
    "deviations",
)
INDEPENDENT = "You recorded or changed this record; another quality person approves it."


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


def _cleaned(values):
    """The record's fields as stored, with the rules of its kind applied: a compendial
    verification or a transfer names its source, only a transfer has an approach, and the
    report is not completed in the future."""
    unknown = set(values) - set(FIELDS)
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}.")
    data = {name: values.get(name) for name in FIELDS}
    for name in FIELDS:
        if isinstance(data[name], str):
            data[name] = data[name].strip()
        elif data[name] is None and name not in ("completed_on",):
            data[name] = ""
    errors = {}
    kind = data["kind"]
    if kind in SOURCED_KINDS and not data["source"]:
        errors["source"] = (
            "Name the pharmacopoeial text that was verified, with its edition."
            if kind == SuitabilityKind.COMPENDIAL_VERIFICATION
            else "Name the laboratory that transferred the method."
        )
    if kind == SuitabilityKind.TRANSFER:
        if data["transfer_approach"] not in MethodEvidence.TransferApproach.values:
            errors["transfer_approach"] = "Choose how the transfer was performed."
    else:
        data["transfer_approach"] = ""
    completed = data["completed_on"]
    if completed and completed > timezone.localdate():
        errors["completed_on"] = "A report cannot be completed in the future."
    if errors:
        raise ValidationError(errors)
    return data


def _locked_draft(evidence, expected_revision=None):
    locked = MethodEvidence.objects.select_for_update().get(pk=evidence.pk)
    if locked.state != MethodEvidence.State.DRAFT:
        raise ValidationError("Only a draft record can be changed.")
    if expected_revision is not None and locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before saving.")
    return locked


def _bump(locked):
    locked.revision += 1
    locked.save(update_fields=["revision"])


# Recording and changing a draft -----------------------------------------------------------


@transaction.atomic
def record_evidence(*, actor, method, reason, **values):
    """Record the evidence for ``method`` as a draft. It supports no method version until a
    quality person approves it."""
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    evidence = MethodEvidence(method=method, recorded_by=actor, **_cleaned(values))
    evidence.full_clean()
    evidence.save()
    record_event(
        actor=actor,
        action="method_evidence.recorded",
        obj=evidence,
        after=snapshot(evidence),
        reason=reason,
    )
    return evidence


@transaction.atomic
def change_evidence(*, actor, evidence, expected_revision, reason, **values):
    """Change the fields of a draft. Whoever changes it cannot approve it."""
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    locked = _locked_draft(evidence, expected_revision)
    data = _cleaned(values)
    if all(getattr(locked, name) == value for name, value in data.items()):
        raise ValidationError("Nothing was changed.")
    before = snapshot(locked)
    for name, value in data.items():
        setattr(locked, name, value)
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="method_evidence.changed",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


@transaction.atomic
def add_characteristic(
    *,
    actor,
    evidence,
    reason,
    characteristic,
    detail,
    criterion,
    result,
    outcome,
    expected_revision=None,
):
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    locked = _locked_draft(evidence, expected_revision)
    if locked.characteristics.count() >= MAX_CHARACTERISTICS:
        raise ValidationError(f"A record has at most {MAX_CHARACTERISTICS} characteristics.")
    item = MethodEvidenceCharacteristic(
        evidence=locked,
        characteristic=characteristic,
        detail=(detail or "").strip(),
        criterion=(criterion or "").strip(),
        result=(result or "").strip(),
        outcome=outcome,
        created_by=actor,
    )
    if item.characteristic == item.Characteristic.OTHER and not item.detail:
        raise ValidationError({"detail": "Say what was evaluated."})
    item.full_clean()
    item.save()
    _bump(locked)
    record_event(
        actor=actor,
        action="method_evidence.characteristic_added",
        obj=locked,
        after=item.content(),
        reason=reason,
    )
    return item


@transaction.atomic
def remove_characteristic(*, actor, item, reason, expected_revision=None):
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    locked = _locked_draft(item.evidence, expected_revision)
    item = MethodEvidenceCharacteristic.objects.select_for_update().get(pk=item.pk, evidence=locked)
    before = item.content()
    item.delete()
    _bump(locked)
    record_event(
        actor=actor,
        action="method_evidence.characteristic_removed",
        obj=locked,
        before=before,
        reason=reason,
    )
    return locked


# Approval and withdrawal ------------------------------------------------------------------


def changed_by(evidence):
    """Who recorded the record or changed it as a draft (signatures are not changes)."""
    edited = (
        AuditEvent.objects.filter(
            object_type=evidence._meta.label_lower, object_id=str(evidence.pk)
        )
        .exclude(action__startswith="signed.")
        .values_list("actor_id", flat=True)
    )
    return {evidence.recorded_by_id, *edited}


def approval_problems(evidence):
    """What keeps a draft from being approved, in the words of the page; empty when ready."""
    items = list(evidence.characteristics.all())
    problems = []
    waiver = evidence.transfer_approach == MethodEvidence.TransferApproach.WAIVER
    if not items and not waiver:
        problems.append(
            "Add the characteristics that were evaluated, each with its criterion and result."
        )
    not_met = [item for item in items if item.outcome == item.Outcome.NOT_MET]
    if (
        not_met
        and evidence.conclusion == MethodEvidence.Conclusion.SUITABLE
        and not evidence.deviations.strip()
    ):
        problems.append(
            "A criterion was not met but the record concludes that the method is suitable: "
            "state under Deviations how this was assessed."
        )
    if evidence.completed_on > timezone.localdate():
        problems.append("The report is dated in the future.")
    return problems


@sensitive_variables("pin")
def approve_evidence(*, actor, pin, evidence, expected_revision, reason):
    """Sign a draft as approved, freezing it and its characteristics. The approver is a quality
    person who neither recorded nor changed it."""

    def apply(locked):
        if locked.state != MethodEvidence.State.DRAFT:
            raise ValidationError("Only a draft record can be approved.")
        if actor.pk in changed_by(locked):
            raise PermissionDenied(INDEPENDENT)
        if problems := approval_problems(locked):
            raise ValidationError(problems)
        content = locked.frozen()
        locked.content = content
        locked.content_hash = digest(content)
        locked.state = MethodEvidence.State.APPROVED
        locked.approved_at = locked._signing_timestamp

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=evidence,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission=APPROVER,
        apply=apply,
    )


@sensitive_variables("pin")
def withdraw_evidence(*, actor, pin, evidence, expected_revision, reason):
    """Quality withdraws an approved record with a signature. Its approved content stays, and
    the method versions approved on it keep it as approved; no draft can link it again."""

    def apply(locked):
        if locked.state != MethodEvidence.State.APPROVED:
            raise ValidationError("Only an approved record is withdrawn with a signature.")
        locked.state = MethodEvidence.State.WITHDRAWN
        locked.withdrawn_at = locked._signing_timestamp

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=evidence,
        expected_revision=expected_revision,
        meaning="withdrawn",
        reason=reason,
        permission=APPROVER,
        apply=apply,
    )


@transaction.atomic
def discard_evidence(*, actor, evidence, expected_revision, reason):
    """Withdraw a draft that will not be approved: its recorder or a quality person."""
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    locked = _locked_draft(evidence, expected_revision)
    if actor.pk != locked.recorded_by_id and not actor.groups.filter(name=APPROVER).exists():
        raise PermissionDenied("Only the person who recorded this draft or quality withdraws it.")
    before = snapshot(locked)
    locked.state = MethodEvidence.State.WITHDRAWN
    locked.withdrawn_at = timezone.now()
    locked.revision += 1
    locked.save()
    record_event(
        actor=actor,
        action="method_evidence.withdrawn",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


def digest(content):
    from .services import digest as content_digest

    return content_digest(content)


# The suitability a method version relies on ----------------------------------------------


def evidence_refusal(evidence, method_id):
    """Why a draft version of ``method_id`` cannot rely on ``evidence``, or None."""
    if evidence.method_id != method_id:
        return f"{evidence.identifier} is evidence for another method."
    if evidence.state == MethodEvidence.State.WITHDRAWN:
        return f"{evidence.identifier} was withdrawn."
    if evidence.state != MethodEvidence.State.APPROVED:
        return f"{evidence.identifier} is not approved yet."
    if evidence.conclusion != MethodEvidence.Conclusion.SUITABLE:
        return f"{evidence.identifier} concludes that the method is not suitable."
    return None


def check_relied_on(revision):
    """At approval of a method version, under its lock: the record it relies on is still
    approved, suitable and of its method. The record is locked so that a withdrawal signed
    meanwhile waits for the approval, or the approval for the withdrawal."""
    if not revision.evidence_id:
        return
    evidence = MethodEvidence.objects.select_for_update(no_key=True).get(pk=revision.evidence_id)
    if refusal := evidence_refusal(evidence, revision.method_id):
        raise ValidationError(f"Suitability evidence: {refusal}")
    if revision.suitability_kind != evidence.kind:
        raise ValidationError("Suitability evidence: the kind does not match the record.")
    revision.evidence = evidence


def relied_on_refusal(revision):
    """Read-only, for the pages: why approving ``revision`` would be refused because of the
    record it relies on, or None. ``check_relied_on`` repeats it under lock when signing."""
    if not getattr(revision, "evidence_id", None):
        return None
    evidence = MethodEvidence.objects.get(pk=revision.evidence_id)
    if refusal := evidence_refusal(evidence, revision.method_id):
        return f"Suitability evidence: {refusal}"
    return None


def relied_on_choices(method):
    """The records a draft version of ``method`` can rely on, newest first."""
    return MethodEvidence.objects.filter(
        method=method,
        state=MethodEvidence.State.APPROVED,
        conclusion=MethodEvidence.Conclusion.SUITABLE,
    ).order_by("-completed_on", "-pk")


@transaction.atomic
def set_suitability(
    *,
    actor,
    revision,
    reason,
    evidence=None,
    suitability_kind="",
    suitability_ref="",
    expected_revision=None,
):
    """Set what a draft method version relies on: an approved record kept here (its kind and
    report are taken from it) or an external reference only. Whoever sets it cannot approve
    the version."""
    from .services import AUTHOR_ROLE
    from .services import _locked_draft as locked_version

    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    locked = locked_version(revision)
    if expected_revision is not None and locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before saving.")
    before = {
        "evidence": locked.evidence_id,
        "suitability_kind": locked.suitability_kind,
        "suitability_ref": locked.suitability_ref,
    }
    if evidence is not None:
        evidence = MethodEvidence.objects.select_for_update(no_key=True).get(pk=evidence.pk)
        if refusal := evidence_refusal(evidence, locked.method_id):
            raise ValidationError({"evidence": refusal})
        locked.evidence = evidence
        locked.suitability_kind = evidence.kind
        locked.suitability_ref = evidence.report_ref
    else:
        errors = {}
        if suitability_kind not in SuitabilityKind.values:
            errors["suitability_kind"] = "Choose the kind of evidence."
        if not (suitability_ref or "").strip():
            errors["suitability_ref"] = "Name the report and where it is kept."
        if errors:
            raise ValidationError(errors)
        locked.evidence = None
        locked.suitability_kind = suitability_kind
        locked.suitability_ref = suitability_ref.strip()
    after = {
        "evidence": locked.evidence_id,
        "suitability_kind": locked.suitability_kind,
        "suitability_ref": locked.suitability_ref,
    }
    if after == before:
        raise ValidationError("Nothing was changed.")
    locked.revision += 1
    locked.full_clean()
    locked.save(update_fields=["evidence", "suitability_kind", "suitability_ref", "revision"])
    record_event(
        actor=actor,
        action="method_revision.suitability_set",
        obj=locked,
        before=before,
        after=after,
        reason=reason,
    )
    return locked


def relying_versions(evidence):
    return MethodRevision.objects.filter(evidence=evidence).order_by("-version")
