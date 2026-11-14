"""Supplier certificates: what a supplier's certificate of analysis states for a lot.

Each result is recorded against one approved requirement of the lot and compared with it. These
are the supplier's results and stay apart from the laboratory's own tests: nothing here answers a
requirement, and the testing and disposition gates never read these records.

Published for other modules:
- ``certificate_author_ids(lot)`` -> ids of everyone who recorded, corrected or withdrew a
  supplier certificate of the lot; they must not sign its QC disposition.
- ``disposition_notices(lot)`` -> what a disposition signer should see; never a blocker.
"""

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from core.services import require_role

from .models import (
    ReceiptSource,
    SupplierCertificate,
    SupplierCertificateResult,
    SupplierCertificateWithdrawal,
)
from .services import current_receipt, lock_quarantined

# What a certificate states about itself. Every key is required, exactly as entered.
HEADER_FIELDS = ("number", "issued_by", "issued_on", "stated_lot", "document_ref", "notes")
HEADER_REQUIRED = {
    "number": "Enter the certificate number.",
    "issued_by": "Enter who issued the certificate.",
    "stated_lot": "Enter the lot number printed on the certificate.",
    "document_ref": "Enter where the certificate is kept.",
}
# One result as stated on the certificate. Every key is required; nothing is defaulted.
RESULT_FIELDS = ("test_code", "value", "qualifier", "outcome", "stated_text", "method", "limits")

QUARANTINE_ONLY = "Only quarantined lots accept supplier certificate records."
NO_RECEIPT = "Record the lot's receipt details before its supplier certificate."
NOT_SUPPLIED = "Only a lot received from a supplier has a supplier certificate."
NO_REQUIREMENTS = (
    "Assign approved requirements to the lot first: supplier results are recorded against them."
)
REQUIREMENTS_STALE = (
    "The lot's requirements changed after this page was opened. Reload and review the results "
    "against the current requirements."
)
CERTIFICATE_STALE = "The certificate record changed. Reload and review it before changing it."
WITHDRAWN = "A withdrawn certificate record cannot be changed."
NO_RESULTS = "Enter at least one result stated on the certificate."
DUPLICATE = (
    "This lot already holds a certificate with this number. Correct that record, or withdraw "
    "it if it does not belong to this lot."
)


def lot_requirements(lot):
    """({test_code: (payload, requirement)}, hold reasons) for the lot's approved requirements.

    The same resolution testing uses, in specification order; a held requirement is left out.
    """
    from analytical.contracts import parse_requirement, resolve

    accepted, reasons = resolve(lot)
    return {code: (payload, parse_requirement(payload)) for code, payload in accepted.items()}, (
        reasons
    )


def _hashes(required):
    from analytical.contracts import canonical_hash

    return {code: canonical_hash(payload) for code, (payload, _) in required.items()}


def requirements_basis(required):
    """One hash of the requirements a page showed; a page opened before they changed is refused."""
    from analytical.contracts import canonical_hash

    return canonical_hash(_hashes(required))


def recording_blocker(lot):
    """Why a supplier certificate cannot be recorded for this lot now, or None.

    Read-only preflight for pages; the services repeat it under the lot lock.
    """
    if lot.state != "quarantine":
        return QUARANTINE_ONLY
    receipt = current_receipt(lot)
    if receipt is None:
        return NO_RECEIPT
    if receipt.source != ReceiptSource.SUPPLIER:
        return NOT_SUPPLIED
    return None


def recording_requirements(lot):
    """(requirements, why nothing can be recorded for the lot now, or "").

    One read for pages: the lot's state and receipt first, then its requirements with the
    reasons they are held.
    """
    if blocker := recording_blocker(lot):
        return {}, blocker
    required, holds = lot_requirements(lot)
    return required, "" if required else " ".join([NO_REQUIREMENTS, *holds])


def is_withdrawn(certificate):
    return hasattr(certificate, "withdrawal")


def change_blocker(certificate):
    """Why this certificate record cannot be corrected or withdrawn now, or None."""
    if SupplierCertificate.objects.filter(corrects_id=certificate.pk).exists():
        return CERTIFICATE_STALE
    if SupplierCertificateWithdrawal.objects.filter(certificate_id=certificate.pk).exists():
        return WITHDRAWN
    return None


def result_content(line):
    return {
        "test_code": line.test_code,
        "result": line.value_text,
        "qualifier": line.qualifier,
        "outcome": line.outcome,
        "stated": line.stated_text,
        "method": line.method,
        "limits": line.limits,
        "conforms": line.conforms,
        "requirement_hash": line.requirement_hash,
    }


def certificate_content(certificate, lines=None):
    """A certificate record as audit evidence: exact text, results in specification order."""
    lines = certificate.results.all() if lines is None else lines
    return {
        "lot": certificate.lot_id,
        "number": certificate.number,
        "issued_by": certificate.issued_by,
        "issued_on": certificate.issued_on.isoformat(),
        "stated_lot": certificate.stated_lot,
        "document_ref": certificate.document_ref,
        "notes": certificate.notes,
        "corrects": certificate.corrects_id,
        "results": [result_content(line) for line in lines],
    }


def _stated(content):
    return {key: value for key, value in content.items() if key != "corrects"}


def _header_values(values):
    if not isinstance(values, dict) or set(values) != set(HEADER_FIELDS):
        raise ValidationError("Certificate details are incomplete.")
    data = dict(values)
    for name in HEADER_FIELDS:
        if name != "issued_on":
            data[name] = (data[name] or "").strip()
    errors = {name: message for name, message in HEADER_REQUIRED.items() if not data[name]}
    issued = data["issued_on"]
    if not isinstance(issued, datetime.date) or isinstance(issued, datetime.datetime):
        errors["issued_on"] = "Enter the date of the certificate."
    elif issued > timezone.localdate():
        errors["issued_on"] = "The date of the certificate cannot be in the future."
    if errors:
        raise ValidationError(errors)
    return data


def stated_result(spec, *, value, qualifier, outcome, stated_text):
    """Check one stated result against its requirement; return (reading, text as recorded).

    The same reading rules as the laboratory's own results: an exact number, a number reported
    as less than a value, a whole count, or one outcome of the requirement's controlled pair.
    A qualitative result also keeps the certificate's own wording.
    """
    from analytical.contracts import Reading

    if value is not None and not isinstance(value, Decimal):
        raise ValidationError("Enter the result as an exact decimal number.")
    reading = Reading(value=value, qualifier=qualifier or "", outcome=outcome or "")
    spec.check_reading(reading)
    stated = (stated_text or "").strip()
    if spec.is_qualitative:
        if not stated:
            raise ValidationError("Enter the wording of the result on the certificate.")
        return reading, dict(spec.outcomes)[reading.outcome]
    if stated:
        raise ValidationError("Only a qualitative result records the certificate's wording.")
    return reading, f"{reading.qualifier}{format(value, 'f')}"


def _result_lines(required, results):
    """Unsaved result rows in specification order, each compared with its frozen requirement."""
    from analytical.contracts import canonical_hash

    if not isinstance(results, (list, tuple)) or not results:
        raise ValidationError(NO_RESULTS)
    order = {code: position for position, code in enumerate(required, start=1)}
    lines = {}
    for item in results:
        if not isinstance(item, dict) or set(item) != set(RESULT_FIELDS):
            raise ValidationError("Certificate results are incomplete.")
        code = item["test_code"]
        if code not in required:
            raise ValidationError(f"{code} is not an approved requirement of this lot.")
        if code in lines:
            raise ValidationError(f"{code} is stated more than once.")
        payload, spec = required[code]
        try:
            reading, text = stated_result(
                spec,
                value=item["value"],
                qualifier=item["qualifier"],
                outcome=item["outcome"],
                stated_text=item["stated_text"],
            )
        except ValidationError as exc:
            raise ValidationError([f"{spec.name}: {message}" for message in exc.messages]) from exc
        line = SupplierCertificateResult(
            position=order[code],
            test_code=code,
            value=reading.value,
            qualifier=reading.qualifier,
            outcome=reading.outcome,
            value_text=text,
            stated_text=(item["stated_text"] or "").strip() if spec.is_qualitative else "",
            method=(item["method"] or "").strip(),
            limits=(item["limits"] or "").strip(),
            requirement=payload,
            requirement_hash=canonical_hash(payload),
            conforms=spec.conforms(reading),
        )
        try:
            line.clean_fields(exclude=["certificate"])
        except ValidationError as exc:
            raise ValidationError([f"{spec.name}: {message}" for message in exc.messages]) from exc
        lines[code] = line
    return sorted(lines.values(), key=lambda line: line.position)


def _add_certificate(*, actor, lot, reason, basis, header, results, corrects=None):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")
    if blocker := recording_blocker(lot):
        raise ValidationError(blocker)
    required, holds = lot_requirements(lot)
    if not required:
        raise ValidationError([NO_REQUIREMENTS, *holds])
    if basis != requirements_basis(required):
        raise ValidationError(REQUIREMENTS_STALE)
    lines = _result_lines(required, results)
    certificate = SupplierCertificate(
        lot=lot,
        recorded_by=actor,
        reason=reason,
        corrects=corrects,
        result_count=len(lines),
        **_header_values(header),
    )
    # One current record per certificate number on a lot: a second one is a duplicate entry.
    same_number = SupplierCertificate.objects.filter(
        lot=lot,
        number__iexact=certificate.number,
        corrected_by__isnull=True,
        withdrawal__isnull=True,
    )
    if corrects is not None:
        same_number = same_number.exclude(pk=corrects.pk)
    if same_number.exists():
        raise ValidationError({"number": DUPLICATE})
    content = certificate_content(certificate, lines)
    before = certificate_content(corrects) if corrects is not None else None
    if before is not None and _stated(content) == _stated(before):
        raise ValidationError("The correction changes nothing.")
    certificate.full_clean()
    certificate.save()
    for line in lines:
        line.certificate = certificate
        line.save()
    lot.revision += 1
    lot.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="supplier_certificate.corrected" if corrects else "supplier_certificate.recorded",
        obj=certificate,
        reason=reason,
        before=before,
        after=content,
    )
    return certificate


def _current(certificate):
    """The record re-read under the lot lock; refused when it was replaced or withdrawn."""
    current = SupplierCertificate.objects.get(pk=certificate.pk)
    if blocker := change_blocker(current):
        raise ValidationError(blocker)
    return current


@transaction.atomic
def record_certificate(*, actor, lot, reason, basis, results, **header):
    """Record what a supplier's certificate states for a quarantined lot, or nothing."""
    require_role(actor, "analyst")
    lot = lock_quarantined(actor, lot, QUARANTINE_ONLY)
    return _add_certificate(
        actor=actor, lot=lot, reason=reason, basis=basis, header=header, results=results
    )


@transaction.atomic
def correct_certificate(*, actor, certificate, reason, basis, results, **header):
    """Replace a certificate record with a linked record; the one it replaces is kept."""
    require_role(actor, "analyst")
    lot = lock_quarantined(actor, certificate.lot, QUARANTINE_ONLY)
    return _add_certificate(
        actor=actor,
        lot=lot,
        reason=reason,
        basis=basis,
        header=header,
        results=results,
        corrects=_current(certificate),
    )


@transaction.atomic
def withdraw_certificate(*, actor, certificate, reason):
    """State that a certificate record is void; the record and its results are kept."""
    require_role(actor, "analyst")
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")
    lot = lock_quarantined(actor, certificate.lot, QUARANTINE_ONLY)
    current = _current(certificate)
    withdrawal = SupplierCertificateWithdrawal(
        certificate=current, reason=reason, withdrawn_by=actor
    )
    withdrawal.full_clean()
    withdrawal.save()
    lot.revision += 1
    lot.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="supplier_certificate.withdrawn",
        obj=current,
        reason=reason,
        before=certificate_content(current),
        after={"withdrawn": True},
    )
    return withdrawal


# Reading the records ----------------------------------------------------------------------------


def lot_chains(lot):
    """Every certificate of a lot as its chain of records, oldest record first.

    Chains are ordered by their first record; the last record of a chain is the current one.
    """
    rows = list(
        SupplierCertificate.objects.filter(lot=lot)
        .select_related("recorded_by", "withdrawal__withdrawn_by")
        .prefetch_related("results")
    )
    by_pk = {row.pk: row for row in rows}
    replaced = {row.corrects_id for row in rows if row.corrects_id}
    chains = []
    for head in rows:
        if head.pk in replaced:
            continue
        chain = [head]
        while chain[0].corrects_id:
            chain.insert(0, by_pk[chain[0].corrects_id])
        chains.append(chain)
    return sorted(chains, key=lambda chain: (chain[0].recorded_at, chain[0].pk))


def current_hashes(lot):
    """{test_code: hash} of the lot's approved requirements as they stand now."""
    return _hashes(lot_requirements(lot)[0])


def result_rows(certificate, hashes):
    """A certificate's results for display, each with the requirement it was compared with.

    ``replaced`` marks a result whose requirement is not the lot's current one (the
    requirements were assigned again, or are now held): its comparison stands as recorded and
    a correction compares it with the current requirement.
    """
    from analytical.contracts import parse_requirement

    rows = []
    for line in certificate.results.all():
        spec = parse_requirement(line.requirement)
        rows.append(
            {
                "line": line,
                "name": spec.name,
                "unit": spec.unit,
                "acceptance": spec.acceptance,
                "source": spec.source,
                "replaced": hashes.get(line.test_code) != line.requirement_hash,
            }
        )
    return rows


def lot_number_check(certificate, receipt):
    """The lot number printed on the certificate against the receipt's lot numbers.

    "match" when it equals the supplier's or the manufacturer's lot number (ignoring case and
    surrounding spaces), "differs" when it equals neither, "" when the receipt states neither.
    """
    stated = (receipt.supplier_lot, receipt.manufacturer_lot) if receipt else ()
    known = {number.strip().casefold() for number in stated if number.strip()}
    if not known:
        return ""
    return "match" if certificate.stated_lot.strip().casefold() in known else "differs"


def lot_summary(lot):
    """The current record of each certificate of a lot, with its results, oldest first."""
    hashes = current_hashes(lot)
    receipt = current_receipt(lot)
    summary = []
    for chain in lot_chains(lot):
        head = chain[-1]
        rows = result_rows(head, hashes)
        summary.append(
            {
                "certificate": head,
                "withdrawn": is_withdrawn(head),
                "lot_check": lot_number_check(head, receipt),
                "rows": rows,
                "failing": [row for row in rows if not row["line"].conforms],
                "replaced": [row for row in rows if row["replaced"]],
            }
        )
    return summary


def disposition_notices(lot):
    """What the supplier's certificates say that a disposition signer should see.

    Supplier results never block disposition; a result that does not meet the specification is
    shown so that the decision is taken knowing it.
    """
    notices = []
    for item in lot_summary(lot):
        if item["withdrawn"] or not item["failing"]:
            continue
        names = ", ".join(row["name"] for row in item["failing"])
        notices.append(
            f"Supplier certificate {item['certificate'].number} states a result that does not "
            f"meet the specification: {names}. Supplier results are not laboratory tests and do "
            "not block this disposition."
        )
    return notices


def certificate_author_ids(lot):
    """Everyone who recorded, corrected or withdrew a supplier certificate of the lot."""
    ids = set(SupplierCertificate.objects.filter(lot=lot).values_list("recorded_by_id", flat=True))
    ids.update(
        SupplierCertificateWithdrawal.objects.filter(certificate__lot=lot).values_list(
            "withdrawn_by_id", flat=True
        )
    )
    return ids
