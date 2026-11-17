"""The expiry date and the retest date of a lot's material.

While a lot is in quarantine an analyst or a quality person records them with their basis, and
corrects them by adding a record that replaces the one in force; nothing is edited. Recording or
correcting advances the lot revision, so a disposition page opened before it is refused, and
whoever recorded them is an author of the lot's data who cannot sign its disposition. A rule set
may require dates (``material_dates`` in its policy). The release is refused while a required
date is missing, after the expiry date and from the retest date on, and freezes the record in
force with the disposition. After release the dates are read, never changed: the lot shows that
its retest is due or that it has expired, and no certificate is issued for it then. A
reassessment of the released lot (``quality.reassessment``) may give it a later retest date,
which is then the one in force, or end its use; the record frozen at release stays as it was.

The expiry date is the last day the material may be used; the retest date is the first day on
which it must be examined again before it is used. Both are compared with the local date.
"""

import datetime
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.audit import record_event
from core.services import MATERIAL_DATES, MATERIAL_DATES_RULES, require_role

from .models import LotDates, LotState, Reassessment

RECORD_ROLES = ("analyst", "quality")
DATES_STALE = (
    "The lot's dates changed after this page was opened. Nothing was recorded. Review them as "
    "they are now."
)
NOT_QUARANTINED = "Only lots in quarantine accept expiry and retest dates."
# Lots whose dates still matter: a rejected or cancelled lot is never used.
LIVE_STATES = (LotState.QUARANTINE, LotState.RELEASED)
EXPIRED = "expired"
RETEST_DUE = "retest_due"
USE_ENDED = "use_ended"
STATUS_LABELS = {
    USE_ENDED: ("Use ended", "danger"),
    EXPIRED: ("Expired", "danger"),
    RETEST_DUE: ("Retest due", "warning"),
}
SOON_DAYS = 30


def today():
    return timezone.localdate()


def current_dates(lot):
    """The lot's dates in force: the record that no correction has replaced, or None."""
    return (
        LotDates.objects.filter(lot_id=lot.pk, replaced_by__isnull=True)
        .select_related("recorded_by")
        .first()
    )


@dataclass
class InForce:
    """A lot's dates as they stand: the expiry date of the record in force, and the retest
    date of the latest reassessment that gave one or else of that record. ``use_ended`` is
    the reassessment that ended the lot's use, or None."""

    record: LotDates | None
    reassessment: Reassessment | None
    use_ended: Reassessment | None

    @property
    def expiry_on(self):
        return self.record.expiry_on if self.record else None

    @property
    def retest_on(self):
        if self.reassessment is not None:
            return self.reassessment.retest_on
        return self.record.retest_on if self.record else None

    @property
    def stated(self):
        return self.expiry_on is not None or self.retest_on is not None


def in_force(lot):
    """The lot's dates as they stand (``InForce``). Reassessments are concluded only on
    released lots, so before release this is the record in force."""
    concluded = Reassessment.objects.filter(
        lot_id=lot.pk, state=Reassessment.State.CONCLUDED
    ).order_by("-decided_at", "-pk")
    return InForce(
        record=current_dates(lot),
        reassessment=concluded.filter(outcome=Reassessment.Outcome.SUITABLE).first(),
        use_ended=concluded.filter(outcome=Reassessment.Outcome.NOT_SUITABLE).first(),
    )


def annotate_in_force(lots):
    """Lots annotated for lists with ``date_expiry`` and ``date_retest`` in force (as
    ``in_force``), ``date_use_ended`` and ``date_reassessing`` (a reassessment is open)."""
    record = LotDates.objects.filter(lot=OuterRef("pk"), replaced_by__isnull=True)
    concluded = Reassessment.objects.filter(
        lot=OuterRef("pk"), state=Reassessment.State.CONCLUDED
    ).order_by("-decided_at", "-pk")
    return lots.annotate(
        date_expiry=Subquery(record.values("expiry_on")[:1]),
        date_retest=Coalesce(
            Subquery(
                concluded.filter(outcome=Reassessment.Outcome.SUITABLE).values("retest_on")[:1]
            ),
            Subquery(record.values("retest_on")[:1]),
        ),
        date_use_ended=Exists(concluded.filter(outcome=Reassessment.Outcome.NOT_SUITABLE)),
        date_reassessing=Exists(
            Reassessment.objects.filter(lot=OuterRef("pk"), state=Reassessment.State.OPEN)
        ),
    )


REASSESSING = "reassessing"
SOON = "soon"


def usable(lots, on):
    """Released lots from ``annotate_in_force`` that can take a certificate on the local date
    ``on``: their use has not ended, they have not expired and their retest date is not
    reached (as ``reporting.evidence.date_blockers`` decides)."""
    # Positive conditions only: a missing date (NULL) is neither reached nor not reached.
    return lots.filter(
        Q(date_expiry__isnull=True) | Q(date_expiry__gte=on),
        Q(date_retest__isnull=True) | Q(date_retest__gt=on),
        date_use_ended=False,
    )


def filter_in_force(lots, wanted, on):
    """Lots from ``annotate_in_force`` narrowed to one Dates filter of the lot list: lots in
    quarantine or released whose retest is due, that expired or whose retest or expiry date is
    within ``SOON_DAYS``, whose use ended, or with a reassessment open. A lot whose use ended is
    listed only as such."""
    live = lots.filter(state__in=LIVE_STATES)
    if wanted == USE_ENDED:
        return live.filter(date_use_ended=True)
    if wanted == REASSESSING:
        return live.filter(date_reassessing=True)
    live = live.filter(date_use_ended=False)
    # Positive conditions only: a missing date (NULL) is neither reached nor not reached.
    not_expired = Q(date_expiry__isnull=True) | Q(date_expiry__gte=on)
    not_due = Q(date_retest__isnull=True) | Q(date_retest__gt=on)
    if wanted == EXPIRED:
        return live.filter(date_expiry__lt=on)
    if wanted == RETEST_DUE:
        return live.filter(not_expired, date_retest__lte=on)
    horizon = on + datetime.timedelta(days=SOON_DAYS)
    soon = Q(date_expiry__lte=horizon) | Q(date_retest__lte=horizon)
    return live.filter(soon, not_expired, not_due)


def dates_content(record):
    """A dates record as audit and frozen evidence: ISO dates, the basis as recorded."""
    return {
        "lot": record.lot_id,
        "expiry_on": record.expiry_on.isoformat() if record.expiry_on else None,
        "retest_on": record.retest_on.isoformat() if record.retest_on else None,
        "basis": record.basis,
        "replaces": record.replaces_id,
    }


def frozen(lot):
    """What a signed decision on the lot freezes of its dates, or None when it has none (also
    after a correction to no dates), so that the evidence of such a lot keeps its shape."""
    record = current_dates(lot)
    if record is None or not record.stated:
        return None
    return {
        "id": record.pk,
        **{k: v for k, v in dates_content(record).items() if k not in ("lot", "replaces")},
        "recorded_by": record.recorded_by_id,
        "recorded_at": record.recorded_at.isoformat(),
    }


def status(expiry_on, retest_on, on=None, use_ended=False):
    """USE_ENDED once a reassessment ended the lot's use, EXPIRED after the expiry date,
    RETEST_DUE from the retest date, else ""."""
    on = on or today()
    if use_ended:
        return USE_ENDED
    if expiry_on is not None and on > expiry_on:
        return EXPIRED
    if retest_on is not None and on >= retest_on:
        return RETEST_DUE
    return ""


def status_label(lot_state, expiry_on, retest_on, on=None, use_ended=False):
    """(label, tone) of a lot's dates for the record and the list, or None."""
    if lot_state not in LIVE_STATES:
        return None
    return STATUS_LABELS.get(status(expiry_on, retest_on, on, use_ended))


def required_dates(lot):
    """(rule set, rule) for each rule set the lot is under that requires dates: its own, then
    the additional ones frozen with its current requirements."""
    from sampling.services import applied_rules

    found = []
    for rule in applied_rules(lot):
        policy = rule.policy if isinstance(rule.policy, dict) else {}
        rule_text = policy.get(MATERIAL_DATES)
        if isinstance(rule_text, str) and rule_text in MATERIAL_DATES_RULES:
            found.append((rule, rule_text))
    return found


def _meets(rule, expiry_on, retest_on):
    has_expiry, has_retest = expiry_on is not None, retest_on is not None
    return {
        "expiry": has_expiry,
        "retest": has_retest,
        "expiry_or_retest": has_expiry or has_retest,
        "expiry_and_retest": has_expiry and has_retest,
    }[rule]


def lot_blockers(lot, on=None):
    """Why the lot's dates keep it from being released now; empty when they do not. Read-only:
    the disposition calls it under its lock on the lot."""
    on = on or today()
    record = current_dates(lot)
    expiry_on = record.expiry_on if record else None
    retest_on = record.retest_on if record else None
    problems = [
        f"Rule set {rule} requires {MATERIAL_DATES_RULES[key]} for the lot. Record its dates."
        for rule, key in required_dates(lot)
        if not _meets(key, expiry_on, retest_on)
    ]
    state = status(expiry_on, retest_on, on)
    if state == EXPIRED:
        problems.append(
            f"The lot expired after {expiry_on.isoformat()}. An expired lot is not released."
        )
    elif state == RETEST_DUE:
        problems.append(
            f"The lot's retest date, {retest_on.isoformat()}, has been reached. A lot is not "
            "released on or after its retest date; correct the dates if its testing supports a "
            "later one."
        )
    return problems


def dates_author_ids(lot):
    """Everyone who recorded or corrected the lot's dates, replaced records included."""
    return set(LotDates.objects.filter(lot_id=lot.pk).values_list("recorded_by_id", flat=True))


def _date(value, label):
    if value is None:
        return None
    if not isinstance(value, datetime.date) or isinstance(value, datetime.datetime):
        raise ValidationError({label: "Enter a date."})
    return value


def _values(*, expiry_on, retest_on, basis, reason, replaces):
    expiry_on = _date(expiry_on, "expiry_on")
    retest_on = _date(retest_on, "retest_on")
    basis = (basis or "").strip()
    errors = {}
    if not (reason or "").strip():
        errors["reason"] = "A reason is required."
    if expiry_on is None and retest_on is None:
        if replaces is None:
            errors["expiry_on"] = "Enter an expiry date, a retest date or both."
        elif basis:
            errors["basis"] = "A correction to no dates states no basis; give the reason instead."
    elif not basis:
        errors["basis"] = (
            "State where the dates come from: the supplier's label or certificate, or the shelf "
            "life or retest period assigned and its reference."
        )
    if expiry_on is not None and retest_on is not None and retest_on > expiry_on:
        errors["retest_on"] = "The retest date cannot be after the expiry date."
    if errors:
        raise ValidationError(errors)
    return expiry_on, retest_on, basis


@transaction.atomic
def record_dates(*, actor, lot, expected, reason, expiry_on, retest_on, basis):
    """Record the lot's dates, or correct the record in force (``expected``: the id of the record
    the page showed, None when it showed none). The record replaced is kept."""
    require_role(actor, *RECORD_ROLES)
    from .services import lock_quarantined

    lot = lock_quarantined(actor, lot, NOT_QUARANTINED)
    current = current_dates(lot)
    if (current.pk if current else None) != expected:
        raise ValidationError(DATES_STALE)
    expiry_on, retest_on, basis = _values(
        expiry_on=expiry_on, retest_on=retest_on, basis=basis, reason=reason, replaces=current
    )
    record = LotDates(
        lot=lot,
        expiry_on=expiry_on,
        retest_on=retest_on,
        basis=basis,
        reason=reason.strip(),
        recorded_by=actor,
        replaces=current,
    )
    if current is not None and _stated(record) == _stated(current):
        raise ValidationError("The correction changes nothing.")
    record.full_clean()
    record.save()
    record_event(
        actor=actor,
        action="lot.dates_corrected" if current else "lot.dates_recorded",
        obj=record,
        reason=record.reason,
        before=dates_content(current) if current else None,
        after=dates_content(record),
    )
    lot.revision += 1
    lot.save(update_fields=["revision"])
    return record


def _stated(record):
    return (record.expiry_on, record.retest_on, record.basis)


def history(lot):
    """Every dates record of a lot, oldest first; a correction lists what it changed."""
    records = list(LotDates.objects.filter(lot_id=lot.pk).select_related("recorded_by"))
    labels = (("expiry_on", "Expiry date"), ("retest_on", "Retest date"), ("basis", "Basis"))
    shown = {
        record.pk: {
            "expiry_on": record.expiry_on.isoformat() if record.expiry_on else "None",
            "retest_on": record.retest_on.isoformat() if record.retest_on else "None",
            "basis": record.basis,
        }
        for record in records
    }
    return [
        {
            "record": record,
            "title": "Dates corrected" if record.replaces_id else "Dates recorded",
            "icon": "pencil-square" if record.replaces_id else "",
            "changes": [
                (label, shown[record.replaces_id][key], shown[record.pk][key])
                for key, label in labels
                if shown[record.replaces_id][key] != shown[record.pk][key]
            ]
            if record.replaces_id
            else [],
        }
        for record in records
    ]


def describe(expiry_on, retest_on):
    """The dates as one phrase: "expiry date 2027-05-31, retest date 2026-12-01"."""
    parts = []
    if expiry_on is not None:
        parts.append(f"expiry date {expiry_on.isoformat()}")
    if retest_on is not None:
        parts.append(f"retest date {retest_on.isoformat()}")
    return ", ".join(parts)


def disposition_notices(lot):
    """What the release freezes of the lot's dates, for the signer to check."""
    record = current_dates(lot)
    if record is None or not record.stated:
        return []
    return [
        f"The release freezes the lot's {describe(record.expiry_on, record.retest_on)} "
        f"(basis: {record.basis}). Check them against their basis before you sign."
    ]
