"""Supplier results accepted in place of the laboratory's own tests.

A result stated on a supplier's certificate answers a requirement of a lot only through an
acceptance: an analyst proposes it and a reviewer who authored none of the certificate's records
signs it. The proposal is refused unless the lot's rule set allows reliance for the test, a
signed supplier qualification covers the supplier, the material, the test and the date the lot
was received, the certificate record is the current one and states the method and the limits,
the stated result meets the lot's current requirement, and the laboratory has not started
testing that requirement itself. What was relied on is frozen on the acceptance.

Nothing is edited: an acceptance is signed or withdrawn, and a withdrawn one is replaced by a
new proposal. Whatever changes underneath it afterwards (the certificate record, the receipt,
the requirement) does not change the acceptance; it stops standing and blocks the disposition
until it is withdrawn.

Lock order: the actor's account, then the acceptance row when one exists, then the lot, then
the supplier's qualification rows.

Published for other modules:
- ``lot_reliance(lot)`` -> what the testing gate reads (through ``config.integrations``).
- ``standing_codes(lot)`` -> {test_code: label} of proposals and acceptances that stand.
- ``acceptance_author_ids(lot)`` -> everyone who proposed one; they must not sign the lot's
  QC disposition.
- ``disposition_notices(lot)`` -> what a disposition signer should see; never a blocker.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from core.models import ElectronicSignature
from core.services import own_tests, require_role, sign_transition, supplier_reliance_refusal
from core.services import validate_rules as check_rules

from . import certificates
from .models import (
    Lot,
    ReceiptSource,
    SupplierCertificate,
    SupplierCertificateResult,
    SupplierResultAcceptance,
)
from .services import current_receipt

PROPOSER_ROLE = "analyst"
ACCEPTOR_ROLE = "reviewer"
WITHDRAW_ROLES = ("analyst", "reviewer", "quality")
STATE = SupplierResultAcceptance.State
STANDING = (STATE.PROPOSED, STATE.ACCEPTED)
SCHEMA = "quality.supplier-result-acceptance/1"
SIGNED_TYPE = "quality.supplierresultacceptance"

QUARANTINE_ONLY = "Supplier results are accepted only while the lot is in quarantine."
NOT_SUPPLIED = "Only a lot received from a supplier can rely on a supplier's result."
NOT_CURRENT = (
    "This certificate record was corrected or withdrawn. Only the current record of a supplier "
    "certificate can be relied on."
)
REQUIREMENT_CHANGED = (
    "The result was compared with a requirement that is not the lot's current one. Correct the "
    "certificate record so that it is compared with the current requirements first."
)
DOES_NOT_MEET = (
    "The supplier's stated result does not meet the specification, so it cannot stand in for a "
    "test. Test the requirement in the laboratory."
)
NOT_STATED = (
    "The certificate record states no method or no limits for this result. A result is relied "
    "on only when the certificate states how it was obtained and against which limits."
)
ALREADY = (
    "A supplier's result is already proposed or accepted for this requirement of the lot. "
    "Withdraw it before proposing another."
)
STALE = "The record changed. Reload and review it before continuing."
BASIS_CHANGED = (
    "What this proposal relied on has changed since it was made. Withdraw it and propose the "
    "supplier's result again."
)
SELF_ACCEPTANCE = "You cannot accept a supplier's result you proposed."
CERTIFICATE_AUTHOR = (
    "You recorded or corrected the supplier certificate this result comes from; another "
    "reviewer accepts it."
)


class RelianceRefused(ValidationError):
    """Nothing lets the supplier's result be relied on: the rule set does not allow it, or no
    signed qualification covers it. The refusal is audited; ``subject`` names what refused."""

    def __init__(self, subject, reasons):
        self.subject = subject
        self.reasons = [str(reason) for reason in reasons]
        super().__init__(self.reasons)


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


def _lock_account(actor):
    # Signing locks the actor before any record; serialize here before taking a record lock.
    # NO KEY UPDATE stays compatible with deferred foreign-key checks on this account.
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)


# What is relied on -------------------------------------------------------------------------------


def _chain_author_ids(certificate):
    """Everyone who recorded the certificate record or a record it corrects."""
    ids, record = set(), certificate
    while record is not None:
        ids.add(record.recorded_by_id)
        record = (
            SupplierCertificate.objects.filter(pk=record.corrects_id).first()
            if record.corrects_id
            else None
        )
    return ids


def _tested_here(lot, test_code):
    from analytical.gates import tested_here

    return tested_here(lot, test_code)


def _material(lot):
    from sampling.services import current_assignment

    assignment = current_assignment(lot)
    return assignment.material if assignment is not None else None


def _evidence(*, lot, result, receipt, qualification):
    """What an acceptance relies on, as frozen with it. Built the same way when the proposal is
    made and when it is signed, so a difference means something underneath has changed."""
    from analytical.contracts import parse_requirement
    from suppliers.qualification import qualification_evidence

    spec = parse_requirement(result.requirement)
    certificate, supplier, rules = result.certificate, receipt.supplier, lot.rules
    return {
        "schema": SCHEMA,
        "test_code": result.test_code,
        "name": spec.name,
        "result_type": spec.result_type,
        "unit": spec.unit,
        "acceptance": spec.acceptance,
        "requirement_source": spec.source,
        "requirement_hash": result.requirement_hash,
        "method": {"code": spec.method.code, "revision": spec.method.revision},
        "stated": {
            "result": result.value_text,
            "wording": result.stated_text,
            "method": result.method,
            "limits": result.limits,
        },
        "certificate": {
            "id": certificate.pk,
            "number": certificate.number,
            "issued_by": certificate.issued_by,
            "issued_on": certificate.issued_on.isoformat(),
            "stated_lot": certificate.stated_lot,
            "document_ref": certificate.document_ref,
            "author_ids": sorted(_chain_author_ids(certificate)),
        },
        "supplier": {
            "id": supplier.pk,
            "code": supplier.code,
            "name": supplier.name,
            "location": supplier.location,
        },
        "received_on": receipt.received_on.isoformat(),
        "qualification": qualification_evidence(qualification),
        "rules": {
            "id": rules.pk,
            "code": rules.code,
            "version": rules.version,
            "own_tests": own_tests(rules),
        },
    }


def _record_checks(lot, result):
    """The checks on the lot's own records; returns the current receipt. Raises ValidationError
    with the reason when the stated result cannot be relied on as the records stand."""
    from analytical.contracts import canonical_hash

    certificate = result.certificate
    if certificate.lot_id != lot.pk:
        raise ValidationError("The supplier result belongs to another lot.")
    if lot.state != "quarantine":
        raise ValidationError(QUARANTINE_ONLY)
    if certificates.change_blocker(certificate):
        raise ValidationError(NOT_CURRENT)
    receipt = current_receipt(lot)
    if receipt is None or receipt.source != ReceiptSource.SUPPLIER:
        raise ValidationError(NOT_SUPPLIED)
    required, _ = certificates.lot_requirements(lot)
    code = result.test_code
    if code not in required or canonical_hash(required[code][0]) != result.requirement_hash:
        raise ValidationError(REQUIREMENT_CHANGED)
    if not result.conforms:
        raise ValidationError(DOES_NOT_MEET)
    if not result.method.strip() or not result.limits.strip():
        raise ValidationError(NOT_STATED)
    if started := _tested_here(lot, code):
        raise ValidationError(started)
    return receipt


def _authorization(lot, result, receipt, *, lock):
    """The rule set and the supplier qualification; returns the qualification relied on.
    Raises RelianceRefused when either does not let the result be relied on."""
    from suppliers.models import SupplierQualification
    from suppliers.qualification import lock_qualifications, reliance_finding

    check_rules(lot.rules)
    code = result.test_code
    if refusal := supplier_reliance_refusal(lot.rules, code):
        raise RelianceRefused(str(lot.rules), [refusal])
    material = _material(lot)
    qualifications = lock_qualifications(receipt.supplier, material) if lock else None
    finding = reliance_finding(
        receipt.supplier, material, code, receipt.received_on, qualifications
    )
    if not finding.ok:
        raise RelianceRefused(finding.subject, finding.reasons)
    return SupplierQualification.objects.select_related("supplier", "material").get(
        pk=finding.evidence["id"]
    )


def proposal_refusal(lot, result):
    """Why this stated result cannot be proposed in place of a test now, or "".

    Read-only preflight for pages; the service repeats it under the locks.
    """
    if SupplierResultAcceptance.objects.filter(
        lot=lot, test_code=result.test_code, state__in=STANDING
    ).exists():
        return ALREADY
    try:
        receipt = _record_checks(lot, result)
        _authorization(lot, result, receipt, lock=False)
    except ValidationError as exc:
        return " ".join(exc.messages)
    return ""


def proposal_basis(lot, result):
    """The evidence a proposal made now would freeze, for the page that asks for the reason."""
    receipt = _record_checks(lot, result)
    qualification = _authorization(lot, result, receipt, lock=False)
    return _evidence(lot=lot, result=result, receipt=receipt, qualification=qualification)


def acceptance_content(acceptance):
    """An acceptance as audit evidence."""
    return {
        "lot": acceptance.lot_id,
        "test_code": acceptance.test_code,
        "result": acceptance.result_id,
        "qualification": acceptance.qualification_id,
        "state": acceptance.state,
        "evidence": acceptance.evidence,
    }


# Transitions -------------------------------------------------------------------------------------


def _audit_refusal(actor, lot, result, refusal, reason):
    """A refused proposal is audited on the lot in its own transaction, after the rollback."""
    with transaction.atomic():
        record_event(
            actor=actor,
            action="supplier_result.refused",
            obj=lot,
            after={
                "test_code": result.test_code,
                "result": result.pk,
                "certificate": result.certificate.number,
                "refused_by": refusal.subject,
                "reasons": refusal.reasons,
            },
            reason=reason,
        )


def propose_acceptance(*, actor, result, reason):
    """Propose that a result stated on the supplier's certificate stands in for the laboratory's
    test of that requirement. It answers nothing until a reviewer signs it."""
    require_role(actor, PROPOSER_ROLE)
    _require_reason(reason)
    result = SupplierCertificateResult.objects.select_related("certificate__lot").get(pk=result.pk)
    lot = result.certificate.lot
    try:
        with transaction.atomic():
            _lock_account(actor)
            lot = Lot.objects.select_related("rules").select_for_update(of=("self",)).get(pk=lot.pk)
            if lot.state != "quarantine":
                raise ValidationError(QUARANTINE_ONLY)
            if SupplierResultAcceptance.objects.filter(
                lot=lot, test_code=result.test_code, state__in=STANDING
            ).exists():
                raise ValidationError(ALREADY)
            receipt = _record_checks(lot, result)
            qualification = _authorization(lot, result, receipt, lock=True)
            acceptance = SupplierResultAcceptance(
                lot=lot,
                test_code=result.test_code,
                result=result,
                qualification=qualification,
                requirement_hash=result.requirement_hash,
                evidence=_evidence(
                    lot=lot, result=result, receipt=receipt, qualification=qualification
                ),
                reason=reason,
                proposed_by=actor,
            )
            acceptance.full_clean()
            acceptance.save()
            lot.revision += 1
            lot.save(update_fields=["revision"])
            record_event(
                actor=actor,
                action="supplier_result.proposed",
                obj=acceptance,
                after=acceptance_content(acceptance),
                reason=reason,
            )
            return acceptance
    except RelianceRefused as refusal:
        _audit_refusal(actor, lot, result, refusal, reason)
        raise


def acceptance_denial(actor, acceptance):
    """Why this person cannot sign this acceptance now, or "". Signing repeats it under lock."""
    if acceptance.state == STATE.WITHDRAWN:
        return "This proposal was withdrawn. Propose the supplier's result again."
    if acceptance.state == STATE.ACCEPTED:
        return "This supplier result is already accepted."
    if acceptance.proposed_by_id == actor.pk:
        return SELF_ACCEPTANCE
    if actor.pk in _chain_author_ids(acceptance.result.certificate):
        return CERTIFICATE_AUTHOR
    return ""


def accept_result(*, actor, pin, acceptance, expected_revision, reason):
    """Sign that the supplier's stated result stands in for the laboratory's test. Everything
    the proposal relied on is checked again under the locks and must be unchanged."""

    def apply(locked):
        from suppliers.models import SupplierQualification
        from suppliers.qualification import covers

        lot = (
            Lot.objects.select_related("rules")
            .select_for_update(of=("self",))
            .get(pk=locked.lot_id)
        )
        if lot.state != "quarantine":
            raise ValidationError(QUARANTINE_ONLY)
        if locked.state != STATE.PROPOSED:
            raise ValidationError(acceptance_denial(actor, locked))
        result = SupplierCertificateResult.objects.select_related("certificate").get(
            pk=locked.result_id
        )
        if actor.pk == locked.proposed_by_id:
            raise PermissionDenied(SELF_ACCEPTANCE)
        if actor.pk in _chain_author_ids(result.certificate):
            raise PermissionDenied(CERTIFICATE_AUTHOR)
        receipt = _record_checks(lot, result)
        check_rules(lot.rules)
        if refusal := supplier_reliance_refusal(lot.rules, locked.test_code):
            raise ValidationError(refusal)
        # The qualification the proposal named, locked: a revocation being signed is waited for.
        qualification = (
            SupplierQualification.objects.select_for_update(of=("self",))
            .select_related("supplier", "material")
            .get(pk=locked.qualification_id)
        )
        if not covers(qualification, locked.test_code, receipt.received_on):
            raise ValidationError(
                f"{qualification.label} no longer covers this result: it was revoked, or the "
                "lot's date of receipt is outside its dates. " + BASIS_CHANGED
            )
        if (
            qualification.supplier_id != receipt.supplier_id
            or qualification.material_id != getattr(_material(lot), "pk", None)
            or _evidence(lot=lot, result=result, receipt=receipt, qualification=qualification)
            != locked.evidence
        ):
            raise ValidationError(BASIS_CHANGED)
        locked.state = STATE.ACCEPTED
        locked.accepted_at = timezone.now()
        lot.revision += 1
        lot.save(update_fields=["revision"])

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=acceptance,
        expected_revision=expected_revision,
        meaning="accepted",
        reason=reason,
        permission=ACCEPTOR_ROLE,
        apply=apply,
    )


def withdrawal_refusal(acceptance):
    """Why this proposal or acceptance cannot be withdrawn now, or ""."""
    if acceptance.lot.state != "quarantine":
        return QUARANTINE_ONLY
    if acceptance.state == STATE.WITHDRAWN:
        return "This record is already withdrawn."
    return ""


@transaction.atomic
def withdraw_acceptance(*, actor, acceptance, expected_revision, reason):
    """Withdraw a proposal or an acceptance: the requirement is then answered by a test in the
    laboratory, or by a new proposal. The record is kept."""
    require_role(actor, *WITHDRAW_ROLES)
    _require_reason(reason)
    _lock_account(actor)
    locked = SupplierResultAcceptance.objects.select_for_update(of=("self",)).get(pk=acceptance.pk)
    if locked.revision != expected_revision:
        raise ValidationError(STALE)
    lot = Lot.objects.select_for_update().get(pk=locked.lot_id)
    locked.lot = lot
    if refusal := withdrawal_refusal(locked):
        raise ValidationError(refusal)
    before = {"state": locked.state}
    locked.state = STATE.WITHDRAWN
    locked.withdrawn_by = actor
    locked.withdrawn_at = timezone.now()
    locked.withdrawal_reason = reason.strip()
    locked.revision += 1
    locked.full_clean()
    locked.save()
    lot.revision += 1
    lot.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="supplier_result.withdrawn",
        obj=locked,
        before=before,
        after={"state": locked.state, "test_code": locked.test_code, "lot": lot.pk},
        reason=reason,
    )
    return locked


# Reading -----------------------------------------------------------------------------------------


def standing_problems(acceptance, lot=None, required=None):
    """Why a proposal or an acceptance no longer stands on what it relied on (empty when it
    does). A revoked qualification is not among them: an acceptance already signed stands, and
    the revocation is shown as a notice."""
    from analytical.contracts import canonical_hash

    lot = lot or acceptance.lot
    evidence, problems = acceptance.evidence, []
    certificate = acceptance.result.certificate
    if certificates.change_blocker(certificate):
        problems.append(
            f"supplier certificate {certificate.number} was corrected or withdrawn after the "
            "result was taken from it"
        )
    receipt = current_receipt(lot)
    qualification = acceptance.qualification
    if receipt is None or receipt.source != ReceiptSource.SUPPLIER:
        problems.append("the receipt details no longer name a supplier")
    elif receipt.supplier_id != evidence["supplier"]["id"]:
        problems.append("the receipt details now name another supplier")
    elif not qualification.valid_from <= receipt.received_on <= qualification.valid_until:
        problems.append(
            f"the date received is now {receipt.received_on.isoformat()}, outside the dates of "
            f"{qualification.label}"
        )
    if required is None:
        required, _ = certificates.lot_requirements(lot)
    code = acceptance.test_code
    if code not in required or canonical_hash(required[code][0]) != acceptance.requirement_hash:
        problems.append("the lot's requirement for this test has changed")
    if started := _tested_here(lot, code):
        problems.append(started.rstrip("."))
    return problems


def lot_acceptances(lot):
    """Every proposal and acceptance of the lot for display, oldest first, each with the
    reasons it no longer stands and what has happened to its qualification since."""
    from suppliers.qualification import reliance_notice

    rows = list(
        SupplierResultAcceptance.objects.filter(lot=lot).select_related(
            "result__certificate", "qualification", "proposed_by", "withdrawn_by"
        )
    )
    required = certificates.lot_requirements(lot)[0] if rows else {}
    for row in rows:
        row.problems = standing_problems(row, lot, required) if row.stands else []
        row.notice = reliance_notice(row.evidence) if row.state == STATE.ACCEPTED else ""
    return rows


def standing_codes(lot):
    """{test_code: label} of the lot's proposals and acceptances that have not been withdrawn."""
    rows = SupplierResultAcceptance.objects.filter(lot_id=lot.pk, state__in=STANDING)
    return {row.test_code: row.label for row in rows}


def standing_by_lot(lot_ids):
    """{(lot id, test_code): label} for a page of tests; one query."""
    rows = SupplierResultAcceptance.objects.filter(lot_id__in=set(lot_ids), state__in=STANDING)
    return {(row.lot_id, row.test_code): row.label for row in rows}


def acceptance_signature(acceptance):
    return (
        ElectronicSignature.objects.filter(
            object_type=SIGNED_TYPE, object_id=str(acceptance.pk), meaning="accepted"
        )
        .order_by("-signed_at", "-pk")
        .first()
    )


def _gate_entry(acceptance):
    """An accepted supplier result as the lot's analytical evidence holds it."""
    evidence, signature = acceptance.evidence, acceptance_signature(acceptance)
    qualification = evidence["qualification"]
    return {
        "acceptance": acceptance.pk,
        "label": acceptance.label,
        "test_code": acceptance.test_code,
        "name": evidence["name"],
        "requirement_source": evidence["requirement_source"],
        "requirement_hash": acceptance.requirement_hash,
        "method": evidence["method"],
        "result_type": evidence["result_type"],
        "unit": evidence["unit"],
        "criterion": evidence["acceptance"],
        "stated": evidence["stated"],
        "certificate": {
            key: evidence["certificate"][key]
            for key in ("number", "issued_by", "issued_on", "stated_lot", "document_ref")
        },
        "supplier": {key: evidence["supplier"][key] for key in ("code", "name", "location")},
        "received_on": evidence["received_on"],
        "qualification": {
            key: qualification[key]
            for key in ("id", "label", "evidence_ref", "valid_from", "valid_until")
        },
        "proposed_by": acceptance.proposed_by.get_username(),
        "proposed_at": acceptance.proposed_at.isoformat(),
        "signature": None
        if signature is None
        else {
            "id": signature.pk,
            "signer": signature.signer_name,
            "meaning": signature.meaning,
            "signed_at": signature.signed_at.isoformat(),
            "revision": signature.revision,
            "content_hash": signature.content_hash,
        },
    }


def lot_reliance(lot):
    """What the testing gate reads about the lot's supplier results.

    ``accepted`` holds, by test code, each signed acceptance that still stands; ``blockers``
    name the proposals awaiting a signature and the acceptances that no longer stand;
    ``author_ids`` are the people whose data an accepted result is (the proposer and everyone
    who recorded the certificate).
    """
    rows = [row for row in lot_acceptances(lot) if row.stands]
    accepted, blockers, authors = {}, [], set()
    for row in rows:
        if row.state == STATE.PROPOSED:
            blockers.append(
                f"{row.label}: the supplier's result for {row.test_code} awaits acceptance by "
                "a reviewer."
            )
        elif row.problems:
            blockers.append(
                f"{row.label}: the accepted supplier result for {row.test_code} no longer "
                f"stands: {'; '.join(row.problems)}. Withdraw it, then propose the supplier's "
                "result again or test the requirement in the laboratory."
            )
        else:
            accepted[row.test_code] = _gate_entry(row)
            authors.add(row.proposed_by_id)
            authors.update(row.evidence["certificate"]["author_ids"])
    return {
        "standing": {row.test_code: row.label for row in rows},
        "accepted": accepted,
        "blockers": blockers,
        "author_ids": sorted(authors),
    }


def acceptance_author_ids(lot):
    """Everyone who proposed a supplier's result for the lot, withdrawn proposals included."""
    return set(
        SupplierResultAcceptance.objects.filter(lot=lot).values_list("proposed_by_id", flat=True)
    )


def stated_text(evidence):
    """The stated result as words: "99.60 %" or "Conforms (stated as: Complies)"."""
    stated = evidence["stated"]
    if stated["wording"]:
        return f"{stated['result']} (stated as: {stated['wording']})"
    return f"{stated['result']} {evidence['unit']}".strip()


def disposition_notices(lot):
    """What a disposition signer should see about supplier results accepted in place of tests:
    which requirements they answer, and a qualification revoked since. Never a blocker."""
    notices = []
    for row in lot_acceptances(lot):
        if row.state != STATE.ACCEPTED or row.problems:
            continue  # A proposal or an acceptance that no longer stands blocks the gate.
        evidence = row.evidence
        notices.append(
            f"{evidence['name']}: the supplier's stated result {stated_text(evidence)} on "
            f"certificate {evidence['certificate']['number']} was accepted in place of a "
            f"laboratory test ({row.label}, {evidence['qualification']['label']})."
            + (f" {row.notice} This does not block the disposition." if row.notice else "")
        )
    return notices
