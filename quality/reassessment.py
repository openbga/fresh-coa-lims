"""The reassessment of a released lot's material.

A released lot whose retest date is near or reached is examined again on a sample taken for the
purpose. An analyst or a quality person starts the reassessment and records that sample; its
tests are assigned from the specifications in force for the lot's material, stage and scopes
(``sampling.services.requirements_in_force``), not those frozen at release, and belong to the
reassessment, never to the lot: the testing module sees a reassessment through
``config.integrations.Reassessments`` as it sees a stability pull. They are recorded, reviewed
and investigated like any test; a failing result is retested on the same sample, never
resampled. The lot's record, its dates as frozen at release and its disposition are not
changed.

A quality person who started the reassessment, produced none of its test data and investigated
none of it concludes it with a signature (meaning ``reassessed``). The material is suitable for
use until a new retest date, which is after the day of signing and never after the lot's expiry
date, only when every required test has a reviewed result that conforms and nothing is in
progress; that date is then the lot's retest date in force (``dates.in_force``). Otherwise its
use ends, which is also how a failure is concluded: the lot keeps its released disposition and
shows that its use ended, takes no certificate and no further reassessment. A reassessment
started in error is withdrawn by quality with a signature, unless a result of it failed. One
reassessment of a lot is open at a time.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import record_event
from core.services import require_role, sign_transition

from . import dates
from .models import Lot, LotState, Reassessment

START_ROLES = ("analyst", "quality")
QUALITY = "quality"
RESULTS_SCHEMA = "oq.reassessment-results/1"
STATE = Reassessment.State
OUTCOME = Reassessment.Outcome

ONE_OPEN = "A reassessment of this lot is already open."
SELF_CONCLUSION = (
    "You started this reassessment, produced test data for it or investigated one of its "
    "results. Another quality person concludes it."
)
NOT_OPEN = "This reassessment is no longer open."


def status_of(item):
    """(label, tone) of a reassessment: its outcome once concluded, else its state."""
    if item.state == STATE.CONCLUDED:
        if item.outcome == OUTCOME.SUITABLE:
            return "Suitable", "success"
        return "Use ended", "danger"
    if item.state == STATE.OPEN:
        return "Open", "progress"
    return "Withdrawn", "neutral"


def refusal(reassessment):
    """Why the tests of this reassessment take no more work, or None."""
    if reassessment.state == STATE.CONCLUDED:
        return f"{reassessment.label} is concluded; its tests take no more work."
    if reassessment.state == STATE.WITHDRAWN:
        return f"{reassessment.label} was withdrawn; its tests take no more work."
    return None


def lock(reassessment_ids, refuse=True):
    """Lock the reassessments in key order and refuse one that takes no more testing. The
    caller advances each returned reassessment's revision with the evidence change, so a
    conclusion opened earlier goes stale. With ``refuse`` false nothing is refused and each
    returned reassessment carries ``closed``: why it takes no more testing, or None."""
    found = list(
        Reassessment.objects.select_for_update().filter(pk__in=set(reassessment_ids)).order_by("pk")
    )
    for item in found:
        item.closed = refusal(item)
        if refuse and item.closed:
            raise ValidationError(item.closed)
    return found


def requirements(reassessment):
    """{test_code: oq.test-requirement payload} for the reassessment's tests, or
    ``RequirementHold``: the required tests of the specifications in force for the lot."""
    from analytical.contracts import RequirementHold
    from catalog.services import ApplicabilityHold
    from sampling.services import requirements_in_force

    try:
        return requirements_in_force(reassessment.lot)
    except ApplicabilityHold as hold:
        raise RequirementHold(hold.reasons) from hold


# Starting --------------------------------------------------------------------------------------


def open_reassessment(lot):
    return Reassessment.objects.filter(lot_id=lot.pk, state=STATE.OPEN).first()


def _basis(lot):
    """The lot's dates in force, as a reassessment freezes them when it starts."""
    found = dates.in_force(lot)
    return {
        "expiry_on": found.expiry_on.isoformat() if found.expiry_on else None,
        "retest_on": found.retest_on.isoformat() if found.retest_on else None,
        "dates_record": found.record.pk if found.record else None,
        "reassessment": found.reassessment.pk if found.reassessment else None,
    }


def start_refusal(lot, on=None):
    """Why a reassessment of the lot cannot start now, or None. Read-only."""
    from sampling.services import current_assignment

    if lot.state != LotState.RELEASED:
        return "Only a released lot is reassessed."
    found = dates.in_force(lot)
    if found.use_ended is not None:
        return f"The use of this lot ended with {found.use_ended.label}."
    if (current := open_reassessment(lot)) is not None:
        return f"{current.label} of this lot is open."
    if found.retest_on is None:
        return (
            "The lot has no retest date. A reassessment gives a released lot a later retest date."
        )
    on = on or dates.today()
    if found.expiry_on is not None and on > found.expiry_on:
        return f"The lot expired after {found.expiry_on.isoformat()}; it is not reassessed."
    if found.expiry_on is not None and on == found.expiry_on:
        return (
            f"The lot expires at the end of today, {found.expiry_on.isoformat()}: a reassessment "
            "could not give it a later retest date."
        )
    assignment = current_assignment(lot)
    if assignment is None or assignment.status != "ready":
        return "The lot was released without requirements assigned in the system."
    return None


def earliest_sample(lot):
    """The first day a sample for a new reassessment can be taken: the local date of the
    lot's release, or of the conclusion of its latest reassessment, whichever is later."""
    from core.models import ElectronicSignature

    moments = [
        found.signed_at
        for found in ElectronicSignature.objects.filter(
            object_type="quality.lot", object_id=str(lot.pk), meaning="approved"
        ).order_by("-signed_at")[:1]
    ]
    last = (
        Reassessment.objects.filter(lot_id=lot.pk, state=STATE.CONCLUDED)
        .order_by("-decided_at")
        .values_list("decided_at", flat=True)
        .first()
    )
    moments += [last] if last else []
    return timezone.localdate(max(moments)) if moments else None


def _quantity(value):
    try:
        quantity = Decimal(str(value).strip())
    except InvalidOperation, ValueError:
        raise ValidationError({"quantity": "Enter a number."}) from None
    if not quantity.is_finite() or quantity <= 0:
        raise ValidationError({"quantity": "Enter a quantity greater than zero."})
    return quantity


def content(item):
    """A reassessment as audit and frozen evidence."""
    return {
        "lot": item.lot_id,
        "reason": item.reason,
        "sample_reference": item.sample_reference,
        "sampled_on": item.sampled_on.isoformat(),
        "quantity": str(item.quantity),
        "quantity_unit": item.quantity_unit,
        "containers": item.containers,
        "dates_basis": item.dates_basis,
    }


@transaction.atomic
def start(*, actor, lot, reason, sample_reference, sampled_on, quantity, quantity_unit, containers):
    """Start the reassessment of a released lot with the sample taken for it."""
    require_role(actor, *START_ROLES)
    # The account first, as every signature and laboratory write, then the lot: two starts of
    # the same lot serialize here and the second finds the first open.
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)
    lot = Lot.objects.select_for_update().get(pk=lot.pk)
    if reason_text := start_refusal(lot):
        raise ValidationError(reason_text)
    errors = {}
    if not (reason or "").strip():
        errors["reason"] = "A reason is required."
    if not (sample_reference or "").strip():
        errors["sample_reference"] = "Name the sample taken for the reassessment."
    if not (containers or "").strip():
        errors["containers"] = "Say which containers were sampled and where the lot is stored."
    if not isinstance(sampled_on, datetime.date) or isinstance(sampled_on, datetime.datetime):
        errors["sampled_on"] = "Enter a date."
    elif sampled_on > dates.today():
        errors["sampled_on"] = "The sample cannot be taken in the future."
    elif (earliest := earliest_sample(lot)) is not None and sampled_on < earliest:
        errors["sampled_on"] = (
            f"The sample must be taken on or after {earliest.isoformat()}, when the lot was "
            "released or last reassessed."
        )
    if errors:
        raise ValidationError(errors)
    item = Reassessment(
        lot=lot,
        reason=reason.strip(),
        sample_reference=sample_reference.strip(),
        sampled_on=sampled_on,
        quantity=_quantity(quantity),
        quantity_unit=quantity_unit,
        containers=containers.strip(),
        dates_basis=_basis(lot),
        started_by=actor,
    )
    item.full_clean()
    try:
        with transaction.atomic():
            item.save()
    except IntegrityError as exc:
        # The sample reference is unique; the lot lock already serialized two starts.
        raise ValidationError(
            {"sample_reference": "Another reassessment already uses this sample reference."}
        ) from exc
    record_event(
        actor=actor,
        action="lot.reassessment_started",
        obj=item,
        reason=item.reason,
        after=content(item),
    )
    return item


# What the tests show -------------------------------------------------------------------------


def tests_of(reassessment):
    from analytical.models import AnalyticalTest

    return AnalyticalTest.objects.filter(reassessment_id=reassessment.pk)


def investigations_of(reassessment):
    from analytical.models import Investigation

    return Investigation.objects.filter(test__reassessment_id=reassessment.pk)


def author_ids(reassessment):
    """Who may not conclude the reassessment: whoever started it, produced data for any of its
    tests or investigated any of its results. Assigning tests, reviewing, authorizing a retest
    or concluding an investigation is not authorship."""
    from analytical.gates import data_author_ids, investigation_author_ids

    ids = {reassessment.started_by_id}
    for test in tests_of(reassessment):
        ids |= data_author_ids(test)
    return ids | investigation_author_ids(investigations_of(reassessment))


@dataclass
class Review:
    """What the conclusion page shows and what the signature rechecks under the lock."""

    reassessment: Reassessment
    codes: list = field(default_factory=list)
    assigned: set = field(default_factory=set)
    rows: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    in_progress: list = field(default_factory=list)
    outcome: str = ""  # of the results: conforms, fails or "" while undecided
    failed: bool = False
    expiry_on: datetime.date | None = None
    retest_on: datetime.date | None = None
    investigations: list = field(default_factory=list)

    @property
    def suitable_refusal(self):
        """Why the material cannot be found suitable now, or ""."""
        from analytical.outcomes import CONFORMS

        if not self.assigned:
            return "No test of the reassessment is assigned."
        if self.blockers:
            return "Testing is not complete: " + " ".join(self.blockers)
        if self.outcome != CONFORMS:
            return "A result does not meet its acceptance criterion; the material is not suitable."
        return ""

    @property
    def end_refusal(self):
        """Why the reassessment cannot conclude that the material's use ends now, or ""."""
        if self.in_progress:
            return "Testing is in progress: " + " ".join(self.in_progress)
        return ""

    @property
    def withdraw_refusal(self):
        if self.in_progress:
            return "Testing is in progress: " + " ".join(self.in_progress)
        if self.failed:
            return (
                "A result of this reassessment does not meet its acceptance criterion. Conclude "
                "that the material is not suitable instead."
            )
        return ""


def review(reassessment):
    """Read the reassessment's tests and investigations once: their outcome, what blocks a
    conclusion, and the lot's dates in force."""
    from analytical import outcomes
    from analytical.contracts import resolve_reassessment

    tests = list(tests_of(reassessment).order_by("test_code", "pk"))
    investigations = list(investigations_of(reassessment).order_by("pk"))
    assigned = {test.test_code for test in tests}
    # The material is judged against every test the specifications in force require now, also
    # one added after the tests were assigned: it is a blocker until it is assigned and decided.
    required, holds = resolve_reassessment(reassessment) if assigned else ({}, [])
    codes = sorted(assigned | set(required))
    blockers, rows, outcome = outcomes.results(codes, tests, investigations)
    if holds:
        blockers = [f"The requirements in force cannot be resolved: {' '.join(holds)}", *blockers]
        outcome = ""
    found = dates.in_force(reassessment.lot)
    return Review(
        reassessment=reassessment,
        codes=codes,
        assigned=assigned,
        rows=rows,
        blockers=blockers,
        in_progress=outcomes.work_in_progress(
            tests_of(reassessment), investigations_of(reassessment)
        ),
        outcome=outcome,
        failed=outcomes.failed(rows),
        expiry_on=found.expiry_on,
        retest_on=found.retest_on,
        investigations=investigations,
    )


def _frozen(item, found, authors):
    from analytical import outcomes

    return {
        "schema": RESULTS_SCHEMA,
        "lot": {"id": item.lot_id, "number": item.lot.number},
        "reassessment": item.label,
        "sample_reference": item.sample_reference,
        "sampled_on": item.sampled_on.isoformat(),
        "dates_basis": item.dates_basis,
        "outcome": found.outcome,
        "blockers": found.blockers,
        "results": outcomes.frozen_rows(found.rows),
        "investigations": outcomes.frozen_investigations(found.investigations),
        "author_ids": sorted(authors),
    }


def _lock_lot(reassessment):
    """``prepare`` of a conclusion or a withdrawal: lock the lot after the signer and before
    the reassessment (the order of ``start``). Issuing or amending a certificate locks the lot
    and reads its dates, so it waits for a conclusion in progress and then reads its outcome:
    no certificate is issued beside a conclusion that ends the lot's use. Testing never locks
    the lot, so no cycle forms with it."""

    def prepare():
        Lot.objects.select_for_update().get(pk=reassessment.lot_id)

    return prepare


def retest_refusal(retest_on, on, expiry_on):
    """Why ``retest_on`` cannot be the lot's new retest date on the local date ``on``, or ""."""
    if not isinstance(retest_on, datetime.date) or isinstance(retest_on, datetime.datetime):
        return "Enter the new retest date."
    if retest_on <= on:
        return "The new retest date must be after today."
    if expiry_on is not None and retest_on > expiry_on:
        return (
            f"The new retest date cannot be after the lot's expiry date, {expiry_on.isoformat()}."
        )
    return ""


def conclude(*, actor, pin, reassessment, expected_revision, outcome, retest_on, reason):
    """Conclude the reassessment with a signature: the material is suitable until
    ``retest_on``, or its use ends (``retest_on`` None)."""
    if outcome not in OUTCOME.values:
        raise ValidationError("Choose the outcome of the reassessment.")

    def apply(locked):
        if locked.state != STATE.OPEN:
            raise ValidationError(NOT_OPEN)
        if actor.pk in author_ids(locked):
            raise PermissionDenied(SELF_CONCLUSION)
        # Every change to the reassessment's tests advanced its revision under its lock, so
        # what is read here is what the signer saw.
        found = review(locked)
        if outcome == OUTCOME.SUITABLE:
            if refused := found.suitable_refusal:
                raise ValidationError(refused)
            on = timezone.localdate(locked._signing_timestamp)
            if refused := retest_refusal(retest_on, on, found.expiry_on):
                raise ValidationError({"retest_on": refused})
            locked.retest_on = retest_on
        else:
            if refused := found.end_refusal:
                raise ValidationError(refused)
            if retest_on is not None:
                raise ValidationError(
                    {"retest_on": "A reassessment that ends the material's use sets no date."}
                )
        locked.result_evidence = _frozen(locked, found, author_ids(locked))
        locked.outcome = outcome
        locked.state = STATE.CONCLUDED
        locked.decided_at = locked._signing_timestamp
        locked.decision_reason = reason.strip()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=reassessment,
        expected_revision=expected_revision,
        meaning="reassessed",
        reason=reason,
        permission=QUALITY,
        apply=apply,
        prepare=_lock_lot(reassessment),
    )


def withdraw(*, actor, pin, reassessment, expected_revision, reason):
    """Withdraw a reassessment started in error, with a signature. Refused while testing is
    in progress and when a result failed: a failure is concluded, never withdrawn."""

    def apply(locked):
        if locked.state != STATE.OPEN:
            raise ValidationError(NOT_OPEN)
        if refused := review(locked).withdraw_refusal:
            raise ValidationError(refused)
        locked.state = STATE.WITHDRAWN
        locked.decided_at = locked._signing_timestamp
        locked.decision_reason = reason.strip()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=reassessment,
        expected_revision=expected_revision,
        meaning="withdrawn",
        reason=reason,
        permission=QUALITY,
        apply=apply,
        prepare=_lock_lot(reassessment),
    )
