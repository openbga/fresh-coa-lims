"""Signed decisions that end a lot's quarantine without releasing it.

``reject_lot``: quality rejects a lot that failed its requirements or cannot be used. The lot
need not be fully tested, but an investigation that is still open is concluded first, and a
result recorded outside its limits and not yet submitted is submitted first, so that a failure is
evaluated and investigated whatever is decided about the lot. Results within their limits that
were never submitted (a test that cannot be finished) are frozen with the rejection as recorded.

``cancel_receipt``: quality cancels a lot that was recorded in error, while nothing has been done
with its material: no sample, test, reserve sample or stability study, and no supplier result
standing in place of a test.

Both are signed on the lot by a quality person who authored none of the lot's records, like the
release. The page shows what the signature will freeze; signing reads it again under the lot lock
and refuses anything that differs from what was shown (``basis``). The lot's records are kept
exactly as they were; nothing on the lot changes afterwards. Segregating, returning, reprocessing
or destroying the material is decided and recorded in the laboratory's quality system, which
``reference`` can name.
"""

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import models
from django.views.decorators.debug import sensitive_variables

from catalog.services import digest
from core.services import sign_transition

from .models import Lot, LotState, SupplierResultAcceptance
from .services import current_receipt, disposition_authors, receipt_content

REJECTION_SCHEMA = "oq.lot-rejection/1"
CANCELLATION_SCHEMA = "oq.lot-cancellation/1"


class RejectionGrounds(models.TextChoices):
    RESULTS = "results", "Results do not meet the requirements"
    RECEIPT = "receipt", "Condition or documents on receipt"
    SUPPLIER = "supplier", "The supplier or the supplier's certificate"
    OTHER = "other", "Another reason, stated below"


SELF_REJECTION = (
    "You cannot reject a lot containing your own receipt, supplier certificate, sampling or "
    "test data, or a supplier result you proposed in place of a test. Another quality person "
    "must sign."
)
SELF_CANCELLATION = (
    "You cannot cancel a lot you received or whose records you made. Another quality person "
    "must sign."
)
NOT_QUARANTINED = {
    LotState.RELEASED: "Lot {number} was released; its decision cannot change.",
    LotState.REJECTED: "Lot {number} was rejected; its decision cannot change.",
    LotState.CANCELLED: "Lot {number} was cancelled as received in error.",
}
CLOSURE_STALE = (
    "The lot's record changed after this page was opened. Nothing was signed. Review the lot as "
    "it is now and sign again."
)
REFERENCE_MAX = 200


def closed_refusal(lot):
    """Why this lot takes no rejection or cancellation, or "": its quarantine has ended."""
    if lot.state == LotState.QUARANTINE:
        return ""
    return NOT_QUARANTINED.get(lot.state, "Lot {number} is not in quarantine.").format(
        number=lot.number
    )


@dataclass
class Closure:
    """What rejecting or cancelling a lot now would freeze, read once for the page and again
    under the lot lock for the signature. ``reasons`` refuse the signature; ``basis`` is the
    digest of ``evidence``, everything the signer was shown."""

    lot: Lot
    decision: str
    blocker: str = ""
    reasons: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    basis: str = ""

    @property
    def possible(self):
        return not self.blocker and not self.reasons


def _tests(lot):
    from analytical.models import AnalyticalTest, Observation, RawDataFile

    current = Observation.objects.filter(test__lot_id=lot.pk, correction__isnull=True)
    worked = set(current.values_list("test_id", flat=True))
    tests = list(
        AnalyticalTest.objects.filter(lot_id=lot.pk).select_related("sample").order_by("pk")
    )
    # Results recorded on an open test were never evaluated. Each one is compared on its own
    # with the test's frozen requirement, as batch rejection does, so that one outside its
    # limits is never set aside unseen.
    by_pk = {test.pk: test for test in tests}
    unsubmitted = {test.pk: ([], []) for test in tests if test.state == "open"}
    specs = {}
    for observation in current.filter(test_id__in=unsubmitted).order_by("test_id", "pk"):
        test = by_pk[observation.test_id]
        if test.pk not in specs:
            specs[test.pk] = test.spec
        spec = specs[test.pk]
        recorded, outside = unsubmitted[test.pk]
        recorded.append(observation.value_text)
        if not spec.conforms(observation.reading):
            outside.append(observation.value_text)
    # A raw-data file is not a result: it is kept with the test and evaluated by nobody, so the
    # signer sees that it is there.
    files = set(RawDataFile.objects.filter(test__lot_id=lot.pk).values_list("test_id", flat=True))
    return [
        {
            "test": test.pk,
            "label": test.label,
            "test_code": test.test_code,
            "sample": test.sample.reference if test.sample_id else None,
            "kind": test.kind,
            "state": test.state,
            "conforms": test.conforms,
            "results": test.pk in worked,
            "raw_data": test.pk in files,
            "unsubmitted": unsubmitted.get(test.pk, ([], []))[0],
            "outside_limits": unsubmitted.get(test.pk, ([], []))[1],
        }
        for test in tests
    ]


def _investigations(lot):
    from analytical.models import Investigation

    return [
        {
            "investigation": item.pk,
            "label": item.label,
            "test": item.test_id,
            "phase": item.phase,
            "outcome": item.outcome or None,
        }
        for item in Investigation.objects.filter(lot_id=lot.pk).order_by("pk")
    ]


def _certificates(lot):
    from .certificates import lot_summary

    return [
        {
            "certificate": item["certificate"].pk,
            "number": item["certificate"].number,
            "withdrawn": item["withdrawn"],
            "failing": [row["line"].test_code for row in item["failing"]],
        }
        for item in lot_summary(lot)
    ]


def _acceptances(lot):
    return [
        {
            "acceptance": item.pk,
            "label": item.label,
            "test_code": item.test_code,
            "state": item.state,
        }
        for item in SupplierResultAcceptance.objects.filter(lot=lot).order_by("pk")
    ]


def _holds(lot):
    from stability.gates import active_holds

    return [
        {"hold": hold.identifier, "kind": hold.kind, "reason": hold.reason}
        for hold in active_holds(lot).order_by("pk")
    ]


def _requirements(lot):
    from sampling.services import current_assignment

    assignment = current_assignment(lot)
    if assignment is None:
        return None
    return {
        "assignment": assignment.pk,
        "status": assignment.status,
        "hash": assignment.payload_hash,
    }


def _receipt(lot):
    receipt = current_receipt(lot)
    if receipt is None:
        return None
    return {"id": receipt.pk, **receipt_content(receipt)}


def _outstanding(lot):
    """What would stand in the way of releasing the lot now, as the release gates say it."""
    from analytical.gates import lot_blockers as analytical_blockers
    from sampling.services import lot_blockers as sampling_blockers

    return [*sampling_blockers(lot), *analytical_blockers(lot)]


def _closure(lot, decision, schema, reasons, evidence):
    closure = Closure(lot=lot, decision=decision)
    if refusal := closed_refusal(lot):
        closure.blocker = refusal
        return closure
    closure.reasons = reasons
    closure.evidence = {"schema": schema, "decision": decision, **evidence}
    closure.basis = digest(closure.evidence)
    return closure


def rejection_preview(lot):
    """Read once what rejecting the lot now would freeze and why it is refused, if it is."""
    if closed_refusal(lot):
        return _closure(lot, LotState.REJECTED, REJECTION_SCHEMA, [], {})
    tests = _tests(lot)
    investigations = _investigations(lot)
    reasons = [
        f"{item['label']} is open. Conclude it before the lot is rejected: the investigation is "
        "completed whatever is decided about the lot."
        for item in investigations
        if item["phase"] != "closed"
    ]
    reasons += [
        f"{row['label']} {row['test_code']} holds a result outside its limits that was not "
        f"submitted ({', '.join(row['outside_limits'])}). Submit it first or, if the test "
        "cannot be completed, record that on the test, which opens an investigation, so that "
        "the result is evaluated and investigated."
        for row in tests
        if row["outside_limits"]
    ]
    evidence = {
        "requirements": _requirements(lot),
        "receipt": _receipt(lot),
        "outstanding": _outstanding(lot),
        "tests": tests,
        "investigations": investigations,
        "supplier_certificates": _certificates(lot),
        "supplier_results": _acceptances(lot),
        "holds": _holds(lot),
    }
    return _closure(lot, LotState.REJECTED, REJECTION_SCHEMA, reasons, evidence)


def _material_used(lot):
    """What shows that the lot's material was received and handled, as refusal messages."""
    from stability.models import ReserveSample, Study

    from .models import Sample

    reasons = []
    samples = list(
        Sample.objects.filter(lot=lot).order_by("pk").values_list("reference", flat=True)
    )
    if samples:
        reasons.append(f"Samples were taken from this lot: {', '.join(samples)}.")
    tests = _tests(lot)
    if tests and not samples:
        reasons.append("Tests were assigned to this lot.")
    reserves = list(
        ReserveSample.objects.filter(lot_id=lot.pk)
        .order_by("pk")
        .values_list("identifier", flat=True)
    )
    if reserves:
        reasons.append(f"Reserve samples were recorded for this lot: {', '.join(reserves)}.")
    studies = list(
        Study.objects.filter(lot_id=lot.pk).order_by("pk").values_list("identifier", flat=True)
    )
    if studies:
        reasons.append(f"A stability study was started on this lot: {', '.join(studies)}.")
    if reasons:
        reasons.append(
            "Its material was received and handled, so its receipt was not made in error. If "
            "the lot cannot be used, reject it."
        )
    standing = [row for row in _acceptances(lot) if row["state"] != "withdrawn"]
    reasons += [
        f"{row['label']} proposes or accepts the supplier's result for {row['test_code']} in "
        "place of a test. Withdraw it first."
        for row in standing
    ]
    return reasons


def cancellation_preview(lot):
    """Read once what cancelling the lot as received in error would freeze, and why it is
    refused, if it is."""
    if closed_refusal(lot):
        return _closure(lot, LotState.CANCELLED, CANCELLATION_SCHEMA, [], {})
    evidence = {
        "requirements": _requirements(lot),
        "receipt": _receipt(lot),
        "supplier_certificates": _certificates(lot),
        "supplier_results": _acceptances(lot),
        "holds": _holds(lot),
    }
    return _closure(lot, LotState.CANCELLED, CANCELLATION_SCHEMA, _material_used(lot), evidence)


def rejection_denial(actor, lot):
    """Why this person cannot sign the rejection, or "". Shown before any PIN is requested;
    signing repeats it under the lock."""
    return SELF_REJECTION if actor.pk in disposition_authors(lot) else ""


def cancellation_denial(actor, lot):
    """Why this person cannot sign the cancellation, or "": whoever received the lot or made
    any of its records."""
    if actor.pk == lot.created_by_id or actor.pk in disposition_authors(lot):
        return SELF_CANCELLATION
    return ""


def _reference(reference):
    reference = (reference or "").strip()
    if len(reference) > REFERENCE_MAX:
        raise ValidationError(f"The reference is at most {REFERENCE_MAX} characters.")
    return reference


def _sign(*, actor, pin, lot, expected_revision, reason, basis, preview, denial, extra):
    def apply(locked):
        if refusal := closed_refusal(locked):
            raise ValidationError(refusal)
        if message := denial(actor, locked):
            raise ValidationError(message)
        closure = preview(locked)
        if closure.reasons:
            raise ValidationError(closure.reasons)
        if closure.basis != basis:
            raise ValidationError(CLOSURE_STALE)
        locked.disposition_evidence = {**closure.evidence, **extra}
        locked.state = closure.decision

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=lot,
        expected_revision=expected_revision,
        meaning=extra["decision"],
        reason=reason,
        permission="quality",
        apply=apply,
    )


@sensitive_variables("pin")
def reject_lot(*, actor, pin, lot, expected_revision, grounds, reason, basis, reference=""):
    """Sign the rejection of a lot in quarantine, freezing what the page showed."""
    if grounds not in RejectionGrounds.values:
        raise ValidationError("Choose the grounds for the rejection.")
    return _sign(
        actor=actor,
        pin=pin,
        lot=lot,
        expected_revision=expected_revision,
        reason=reason,
        basis=basis,
        preview=rejection_preview,
        denial=rejection_denial,
        extra={
            "decision": LotState.REJECTED.value,
            "grounds": grounds,
            "reference": _reference(reference),
        },
    )


@sensitive_variables("pin")
def cancel_receipt(*, actor, pin, lot, expected_revision, reason, basis, reference=""):
    """Sign the cancellation of a lot received in error, freezing what the page showed."""
    return _sign(
        actor=actor,
        pin=pin,
        lot=lot,
        expected_revision=expected_revision,
        reason=reason,
        basis=basis,
        preview=cancellation_preview,
        denial=cancellation_denial,
        extra={"decision": LotState.CANCELLED.value, "reference": _reference(reference)},
    )
