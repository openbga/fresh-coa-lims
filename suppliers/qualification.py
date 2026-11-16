"""Supplier qualification: the approved evidence that lets a supplier's certificate result be
relied on in place of the laboratory's own test.

A qualification covers one supplier, one material and named tests between two dates. One quality
person records its evidence and another signs it. It decides nothing about a lot by itself: the
lot's rule set must allow reliance, and each result is accepted on the lot's own record.

Lock order: the actor's account first, then the caller's own records (the lot), then the
qualification rows. Signing a qualification locks the signer's account and that row only, so the
two never wait on each other in a cycle.

Published for the lot record:
- ``reliance_finding(...)`` -> whether a qualification covers the supplier, material, test and
  date of receipt, with the evidence relied on or the reason it does not.
- ``lock_qualifications(supplier, material)`` -> the candidate rows, locked.
- ``reliance_notice(evidence)`` -> what has happened to that qualification since, or "".
"""

import datetime
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import record_event, snapshot
from core.services import require_role, sign_transition

from .models import SupplierQualification

KEEPER_ROLE = "quality"
STATE = SupplierQualification.State
DUE_SOON_DAYS = 30
MAX_CODES = 60


@dataclass(frozen=True)
class RelianceFinding:
    subject: str
    ok: bool
    reasons: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


def lock_account(actor):
    """The same first lock as signing and every other unsigned write (FOR NO KEY UPDATE)."""
    from django.contrib.auth import get_user_model

    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)


# --- Scope -----------------------------------------------------------------------------------


def material_test_codes(material):
    """{code: name} of every test a specification of the material states, latest name wins.

    Withdrawn drafts are left out. The scope of a qualification is chosen from these, so a
    code no specification of the material uses cannot be qualified by a slip of the keyboard.
    """
    from catalog.models import RevisionStatus, SpecificationTest

    lines = (
        SpecificationTest.objects.filter(
            specification_revision__specification__material=material,
        )
        .exclude(specification_revision__status=RevisionStatus.WITHDRAWN)
        .order_by("code", "specification_revision__version", "pk")
        .values_list("code", "name")
    )
    return dict(lines)


def _scope(material, test_codes):
    if not isinstance(test_codes, (list, tuple)) or not test_codes:
        raise ValidationError({"test_codes": "Select at least one test."})
    codes = []
    for code in test_codes:
        if not isinstance(code, str) or not code.strip():
            raise ValidationError({"test_codes": "Select at least one test."})
        if code.strip() not in codes:
            codes.append(code.strip())
    if len(codes) > MAX_CODES:
        raise ValidationError({"test_codes": f"A qualification covers at most {MAX_CODES} tests."})
    known = material_test_codes(material)
    unknown = [code for code in codes if code not in known]
    if unknown:
        raise ValidationError(
            {
                "test_codes": f"No specification of {material.code} states "
                f"{', '.join(unknown)}. Choose tests from the material's specifications."
            }
        )
    return sorted(codes)


# --- Recording and signing -------------------------------------------------------------------


@transaction.atomic
def record_qualification(
    *,
    actor,
    supplier,
    material,
    test_codes,
    basis,
    evidence_ref,
    valid_from,
    valid_until,
    reason,
    evidence_url="",
):
    """Record the evidence for relying on a supplier's results for a material. It qualifies
    nothing until a different quality person signs it."""
    require_role(actor, KEEPER_ROLE)
    _require_reason(reason)
    lock_account(actor)
    qualification = SupplierQualification(
        supplier=supplier,
        material=material,
        test_codes=_scope(material, test_codes),
        basis=(basis or "").strip(),
        evidence_ref=(evidence_ref or "").strip(),
        evidence_url=evidence_url or "",
        valid_from=valid_from,
        valid_until=valid_until,
        recorded_by=actor,
    )
    qualification.full_clean()
    qualification.save()
    record_event(
        actor=actor,
        action="supplier_qualification.recorded",
        obj=qualification,
        after=snapshot(qualification),
        reason=reason,
    )
    return qualification


SELF_APPROVAL = "You cannot approve supplier qualification evidence you recorded."


def qualification_denial(actor, qualification, *, approve):
    """Why this person cannot sign this qualification now, or "". Signing repeats it under lock."""
    if qualification.state == STATE.REVOKED:
        return "This qualification was revoked. A revoked qualification is final; record a new one."
    if approve and qualification.state == STATE.APPROVED:
        return "This qualification is already signed."
    if not approve and qualification.state == STATE.RECORDED:
        return "This qualification is not signed yet; there is nothing to revoke."
    if approve and qualification.recorded_by_id == actor.pk:
        return SELF_APPROVAL
    return ""


def approve_qualification(*, actor, pin, qualification, expected_revision, reason):
    """Sign the recorded evidence. Its dates may lie in the past: a qualification covers lots
    received within it, whenever their results are accepted."""

    def apply(locked):
        if locked.state != STATE.RECORDED:
            raise ValidationError("Only recorded qualifications can be approved.")
        if locked.recorded_by_id == actor.pk:
            raise PermissionDenied(SELF_APPROVAL)
        locked.state = STATE.APPROVED
        locked.approved_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=qualification,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission=KEEPER_ROLE,
        apply=apply,
    )


def revoke_qualification(*, actor, pin, qualification, expected_revision, reason):
    """Protective: any quality person may revoke, the recorder included."""

    def apply(locked):
        if locked.state != STATE.APPROVED:
            raise ValidationError("Only approved qualifications can be revoked.")
        locked.state = STATE.REVOKED
        locked.revoked_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=qualification,
        expected_revision=expected_revision,
        meaning="revoked",
        reason=reason,
        permission=KEEPER_ROLE,
        apply=apply,
    )


# --- Reading ---------------------------------------------------------------------------------


def qualification_status(qualification, today=None):
    """Display status: (label, tone)."""
    today = today or timezone.localdate()
    if qualification.state == STATE.RECORDED:
        return "Awaiting approval", "progress"
    if qualification.state == STATE.REVOKED:
        return "Revoked", "danger"
    if today < qualification.valid_from:
        return "Approved, starts later", "info"
    if today > qualification.valid_until:
        return "Expired", "danger"
    if (qualification.valid_until - today).days <= DUE_SOON_DAYS:
        return "Expiring soon", "warning"
    return "Approved", "success"


def covers(qualification, test_code, received_on):
    """Whether this qualification lets the supplier's result for the test be relied on for a
    lot received that day: signed, not revoked, the test in its scope and the day within its
    validity (both days inclusive)."""
    return (
        qualification.state == STATE.APPROVED
        and test_code in qualification.test_codes
        and qualification.valid_from <= received_on <= qualification.valid_until
    )


def lock_qualifications(supplier, material):
    """The supplier's qualifications for the material, locked. Approving and revoking lock the
    row they sign, so a reliance check made on these rows serializes with both."""
    return list(
        SupplierQualification.objects.select_for_update(of=("self",))
        .filter(supplier=supplier, material=material)
        .order_by("pk")
    )


def qualification_evidence(qualification):
    """The qualification as frozen on a result that relies on it."""
    return {
        "id": qualification.pk,
        "label": qualification.label,
        "material": qualification.material.code,
        "test_codes": list(qualification.test_codes),
        "valid_from": qualification.valid_from.isoformat(),
        "valid_until": qualification.valid_until.isoformat(),
        "evidence_ref": qualification.evidence_ref,
        "basis": qualification.basis,
        "approved_at": qualification.approved_at.isoformat(),
    }


def reliance_finding(supplier, material, test_code, received_on, qualifications=None):
    """Whether the supplier's result for the test may be relied on for a lot of the material
    received on ``received_on``.

    ``qualifications`` are the supplier's qualifications for the material when the caller has
    locked them. The newest covering qualification is the one relied on.
    """
    subject = f"{supplier.code} · {material.code}"
    if not isinstance(received_on, datetime.date) or isinstance(received_on, datetime.datetime):
        return RelianceFinding(subject, False, ("The date the lot was received is not known.",))
    if qualifications is None:
        qualifications = list(
            SupplierQualification.objects.filter(supplier=supplier, material=material)
        )
    covering = [q for q in qualifications if covers(q, test_code, received_on)]
    if covering:
        qualification = max(covering, key=lambda q: q.pk)
        return RelianceFinding(
            subject,
            True,
            (),
            {"qualification": qualification_evidence(qualification), "id": qualification.pk},
        )
    day = received_on.isoformat()
    scoped = [q for q in qualifications if test_code in q.test_codes]
    dated = [q for q in scoped if q.valid_from <= received_on <= q.valid_until]
    if any(q.state == STATE.REVOKED for q in dated):
        reason = (
            f"The qualification of {supplier.code} for {test_code} of {material.code} that "
            f"covered {day} was revoked; a revoked qualification is relied on no further."
        )
    elif any(q.state == STATE.RECORDED for q in dated):
        reason = (
            f"The qualification of {supplier.code} for {test_code} of {material.code} that "
            f"covers {day} is still awaiting its signature."
        )
    elif any(q.state == STATE.APPROVED for q in scoped):
        reason = (
            f"No qualification of {supplier.code} for {test_code} of {material.code} covers a "
            f"lot received on {day}."
        )
    elif any(q.state == STATE.APPROVED for q in qualifications):
        reason = (
            f"The qualification of {supplier.code} for {material.code} does not cover {test_code}."
        )
    else:
        reason = f"{supplier.code} is not qualified for {material.code}."
    return RelianceFinding(subject, False, (reason,))


def reliance_notice(evidence):
    """What a reader of an accepted result should know about the qualification it relied on,
    or "". Unknown or unreadable evidence says nothing."""
    try:
        qualification = SupplierQualification.objects.get(pk=evidence["qualification"]["id"])
    except SupplierQualification.DoesNotExist, KeyError, TypeError, ValueError:
        return ""
    if qualification.state != STATE.REVOKED or qualification.revoked_at is None:
        return ""
    revoked = timezone.localtime(qualification.revoked_at).strftime("%Y-%m-%d %H:%M %Z")
    return (
        f"The supplier qualification this acceptance relied on ({qualification.label}) was "
        f"revoked on {revoked}. The acceptance stands as signed. The qualification's record "
        "lists every result accepted under it, for quality to assess under the laboratory's "
        "procedure."
    )
