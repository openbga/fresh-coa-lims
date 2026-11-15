"""Contract laboratories: who tests for this laboratory, and the approval that lets a result
they report be relied on.

The register holds identity only. An approval covers one method between two dates; one quality
person records its evidence and another signs it. A reported result is accepted only under an
approved, unrevoked approval for the method whose dates include the date of the report, and each
acceptance is kept as a `ContractUse` row so that the results relying on an approval can be
listed when it is revoked.

Lock order: the actor's account first (the caller of `use_contract_report` has already taken
it), then the caller's own records, then the approval rows. Signing an approval locks the
signer's account and that approval row only, so the two never wait on each other in a cycle.

Published for testing (through the configured bench):
- ``contract_choices(method_code)`` -> laboratories holding an approved approval for the method.
- ``use_contract_report(...)`` -> the evidence relied on, written inside the caller's transaction.
- ``reliance_notice(evidence)`` -> what has happened to that approval since, or "".
"""

import datetime
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from psycopg.errors import UniqueViolation

from core.audit import record_event, snapshot
from core.services import require_role, sign_transition

from .eligibility import DUE_SOON_DAYS
from .models import ContractApproval, ContractLaboratory, ContractUse
from .services import lock_account

KEEPER_ROLE = "quality"
STATE = ContractApproval.State


@dataclass(frozen=True)
class ContractFinding:
    subject: str
    ok: bool
    reasons: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)


class ContractBlocked(ValidationError):
    """Raised when no approval lets the laboratory's report be relied on; carries the finding."""

    def __init__(self, finding):
        self.finding = finding
        super().__init__([f"{finding.subject}: {reason}" for reason in finding.reasons])


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


# --- Register --------------------------------------------------------------------------------


CODE_TAKEN = "This contract laboratory code already exists."
CODE_CONSTRAINT = "laboratory_contractlaboratory_code_key"


def register_contract_laboratory(*, actor, code, name, location, reason):
    """Add an outside laboratory to the register. Its identity cannot be edited afterwards."""
    require_role(actor, KEEPER_ROLE)
    _require_reason(reason)
    try:
        with transaction.atomic():
            lock_account(actor)
            if ContractLaboratory.objects.filter(code=code).exists():
                raise ValidationError({"code": CODE_TAKEN})
            laboratory = ContractLaboratory(
                code=code,
                name=(name or "").strip(),
                location=(location or "").strip(),
                created_by=actor,
            )
            laboratory.full_clean()
            laboratory.save()
            record_event(
                actor=actor,
                action="contract_laboratory.registered",
                obj=laboratory,
                after=snapshot(laboratory),
                reason=reason,
            )
            return laboratory
    except IntegrityError as exc:
        # Only a concurrent insert of the same code is expected; anything else is a real fault.
        cause = exc.__cause__
        if not (
            isinstance(cause, UniqueViolation) and cause.diag.constraint_name == CODE_CONSTRAINT
        ):
            raise
        raise ValidationError({"code": CODE_TAKEN}) from exc


# --- Approvals -------------------------------------------------------------------------------


@transaction.atomic
def record_contract_approval(
    *,
    actor,
    laboratory,
    method_code,
    evidence_ref,
    valid_from,
    valid_until,
    reason,
    scope_note="",
    evidence_url="",
):
    """Record the evidence for approving a laboratory for one method. It approves nothing until
    a different quality person signs it."""
    require_role(actor, KEEPER_ROLE)
    _require_reason(reason)
    lock_account(actor)
    approval = ContractApproval(
        laboratory=laboratory,
        method_code=(method_code or "").strip(),
        scope_note=(scope_note or "").strip(),
        evidence_ref=(evidence_ref or "").strip(),
        evidence_url=evidence_url or "",
        valid_from=valid_from,
        valid_until=valid_until,
        recorded_by=actor,
    )
    approval.full_clean()
    approval.save()
    record_event(
        actor=actor,
        action="contract_approval.recorded",
        obj=approval,
        after=snapshot(approval),
        reason=reason,
    )
    return approval


SELF_APPROVAL = "You cannot approve contract laboratory evidence you recorded."


def approval_denial(actor, approval, *, approve):
    """Why this person cannot sign this approval now, or "". Signing repeats it under lock."""
    if approval.state == STATE.REVOKED:
        return "This approval was revoked. A revoked approval is final; record a new one."
    if approve and approval.state == STATE.APPROVED:
        return "This approval is already signed."
    if not approve and approval.state == STATE.RECORDED:
        return "This approval is not signed yet; there is nothing to revoke."
    if approve and approval.recorded_by_id == actor.pk:
        return SELF_APPROVAL
    return ""


def approve_contract_approval(*, actor, pin, approval, expected_revision, reason):
    """Sign the recorded evidence. Its dates may lie in the past: an approval covers reports
    dated within it, whenever they are recorded."""

    def apply(locked):
        if locked.state != STATE.RECORDED:
            raise ValidationError("Only recorded approvals can be approved.")
        if locked.recorded_by_id == actor.pk:
            raise PermissionDenied(SELF_APPROVAL)
        locked.state = STATE.APPROVED
        locked.approved_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=approval,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission=KEEPER_ROLE,
        apply=apply,
    )


def revoke_contract_approval(*, actor, pin, approval, expected_revision, reason):
    """Protective: any quality person may revoke, the recorder included."""

    def apply(locked):
        if locked.state != STATE.APPROVED:
            raise ValidationError("Only approved approvals can be revoked.")
        locked.state = STATE.REVOKED
        locked.revoked_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=approval,
        expected_revision=expected_revision,
        meaning="revoked",
        reason=reason,
        permission=KEEPER_ROLE,
        apply=apply,
    )


# --- Reading ---------------------------------------------------------------------------------


def approval_status(approval, today=None):
    """Display status: (label, tone)."""
    today = today or timezone.localdate()
    if approval.state == STATE.RECORDED:
        return "Awaiting approval", "progress"
    if approval.state == STATE.REVOKED:
        return "Revoked", "danger"
    if today < approval.valid_from:
        return "Approved, starts later", "info"
    if today > approval.valid_until:
        return "Expired", "danger"
    if (approval.valid_until - today).days <= DUE_SOON_DAYS:
        return "Expiring soon", "warning"
    return "Approved", "success"


def covers(approval, report_date):
    """Whether this approval lets a report of that date be relied on: signed, not revoked, and
    dated within its validity (both days inclusive)."""
    return (
        approval.state == STATE.APPROVED
        and approval.valid_from <= report_date <= approval.valid_until
    )


def _same_method(queryset, method_code):
    return queryset.filter(method_code__iexact=(method_code or "").strip())


def contract_eligibility(laboratory, method_code, report_date, approvals=None, today=None):
    """Whether a report of `report_date` from this laboratory may be relied on for the method.

    `approvals` are the laboratory's approvals for the method when the caller has locked them.
    """
    today = today or timezone.localdate()
    method_code = (method_code or "").strip()
    subject = laboratory.code
    if not isinstance(report_date, datetime.date) or isinstance(report_date, datetime.datetime):
        return ContractFinding(subject, False, ("Enter the date of the report.",))
    if report_date > today:
        return ContractFinding(subject, False, ("The report cannot be dated in the future.",))
    if approvals is None:
        approvals = list(_same_method(laboratory.approvals.all(), method_code))
    covering = [a for a in approvals if covers(a, report_date)]
    if covering:
        approval = max(covering, key=lambda a: a.pk)
        return ContractFinding(
            subject,
            True,
            (),
            {
                "laboratory": {
                    "id": laboratory.pk,
                    "code": laboratory.code,
                    "name": laboratory.name,
                    "location": laboratory.location,
                },
                "approval": {
                    "id": approval.pk,
                    "method_code": approval.method_code,
                    "valid_from": approval.valid_from.isoformat(),
                    "valid_until": approval.valid_until.isoformat(),
                    "evidence_ref": approval.evidence_ref,
                    "scope": approval.scope_note,
                    "approved_at": approval.approved_at.isoformat(),
                },
            },
        )
    day = report_date.isoformat()
    dated = [a for a in approvals if a.valid_from <= report_date <= a.valid_until]
    if any(a.state == STATE.REVOKED for a in dated):
        reason = (
            f"The approval for method “{method_code}” that covered {day} was revoked; a revoked "
            "approval is relied on no further."
        )
    elif any(a.state == STATE.RECORDED for a in dated):
        reason = (
            f"The approval for method “{method_code}” that covers {day} is still awaiting its "
            "signature."
        )
    elif any(a.state == STATE.APPROVED for a in approvals):
        reason = f"No approval for method “{method_code}” covers a report dated {day}."
    else:
        reason = f"The laboratory is not approved for method “{method_code}”."
    return ContractFinding(subject, False, (reason,))


def contract_choices(method_code):
    """Laboratories that hold an approved approval for the method: (pk, label), by code.

    The dates are shown because the approval must cover the date of the report, which is not
    known until the report is entered.
    """
    approvals = _same_method(
        ContractApproval.objects.filter(state=STATE.APPROVED), method_code
    ).select_related("laboratory")
    by_laboratory = {}
    for approval in approvals.order_by("valid_from", "pk"):
        by_laboratory.setdefault(approval.laboratory, []).append(
            f"{approval.valid_from.isoformat()} to {approval.valid_until.isoformat()}"
        )
    return [
        (laboratory.pk, f"{laboratory.code} · {laboratory.name} · approved {'; '.join(periods)}")
        for laboratory, periods in sorted(by_laboratory.items(), key=lambda item: item[0].code)
    ]


def use_contract_report(
    *,
    actor,
    laboratory_id,
    method_code,
    context_type,
    context_id,
    report_number,
    report_date,
    test_code="",
):
    """Check that the laboratory's report may be relied on for the method and record that it
    was, inside the caller's transaction. Returns the evidence relied on.

    The caller owns the actor's role, the account lock and the lock on its own records. Nothing
    is written when the check fails (`ContractBlocked`); the caller rolls back and then calls
    `record_blocked_contract` outside its transaction.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("A contract report must be accepted in the caller's transaction.")
    report_number = (report_number or "").strip()
    if not report_number:
        raise ValidationError("Enter the number of the laboratory's report.")
    try:
        laboratory = ContractLaboratory.objects.get(pk=laboratory_id)
    except (ContractLaboratory.DoesNotExist, TypeError, ValueError) as exc:
        raise ValidationError("The selected contract laboratory does not exist.") from exc
    # Approving and revoking lock the row they sign, so locking the laboratory's approvals for
    # the method serializes this check with both. Evidence is read only after the locks.
    approvals = list(
        _same_method(
            ContractApproval.objects.select_for_update(of=("self",)).filter(laboratory=laboratory),
            method_code,
        ).order_by("pk")
    )
    finding = contract_eligibility(laboratory, method_code, report_date, approvals)
    if not finding.ok:
        raise ContractBlocked(finding)
    use = ContractUse(
        approval_id=finding.evidence["approval"]["id"],
        context_type=context_type,
        context_id=str(context_id),
        method_code=(method_code or "").strip(),
        test_code=test_code,
        report_number=report_number,
        report_date=report_date,
        used_by=actor,
    )
    use.full_clean()
    use.save()
    return {
        **finding.evidence,
        "report": {"number": report_number, "date": report_date.isoformat()},
        "use": use.pk,
    }


def record_blocked_contract(
    *,
    actor,
    method_code,
    context_type,
    context_id,
    refusals,
    reason,
    laboratory_id=None,
    report_number="",
    report_date=None,
):
    """Audit a refused contract report in its own transaction, so it survives the rollback."""
    with transaction.atomic():
        record_event(
            actor=actor,
            action="contract.report_refused",
            obj=actor,
            after={
                "context": f"{context_type}:{context_id}",
                "method": (method_code or "").strip(),
                "laboratory": laboratory_id,
                "report": {
                    "number": report_number,
                    "date": report_date.isoformat() if report_date else None,
                },
                "refusals": [
                    {"subject": r["subject"], "reasons": list(r["reasons"])} for r in refusals
                ],
            },
            reason=reason,
        )


def reliance_notice(evidence):
    """What a reader of a result should know about the approval it relied on, or "".

    Reads the approval named in frozen evidence; unknown or unreadable evidence says nothing.
    """
    try:
        approval = ContractApproval.objects.get(pk=evidence["approval"]["id"])
    except ContractApproval.DoesNotExist, KeyError, TypeError, ValueError:
        return ""
    if approval.state != STATE.REVOKED or approval.revoked_at is None:
        return ""
    revoked = timezone.localtime(approval.revoked_at).strftime("%Y-%m-%d %H:%M %Z")
    return (
        f"The approval this result relied on ({approval.label}) was revoked on {revoked}. The "
        "result stands as recorded. The approval's record lists every result that relied on "
        "it, for quality to assess under the laboratory's procedure."
    )
