"""Reminders: the calibrations, stability pulls and reagent or standard lots that fall due within
a window of days, read from the same queries as their lists. Nothing is stored or sent: the page
lists what is due, and each row opens the record that resolves it."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.urls import reverse

from laboratory.eligibility import equipment_queryset
from laboratory.models import Calibration, Equipment, ReagentLot
from stability.models import Pull, Study
from stability.views import _with_windows

KINDS = {
    "calibration": "Calibration",
    "pull": "Stability pull",
    "reagent": "Reagent or standard",
}


@dataclass(frozen=True)
class Reminder:
    kind: str
    on: date  # the date the row is sorted by: calibration due, pull due, expiry
    label: str
    detail: str
    href: str
    status: str
    tone: str

    @property
    def kind_label(self):
        return KINDS[self.kind]


def _days(count):
    return f"{count} day{'s' if count != 1 else ''}"


def _calibrations(today, until):
    """In-service equipment whose latest counting calibration passed and runs out by
    ``until``, overdue ones included. Unlike the Equipment list's Due soon, equipment that is not
    qualified is included: its calibration still falls due. Equipment never calibrated or whose
    latest calibration failed has no due date and no reminder (Equipment list: Not calibrated or
    qualified)."""
    in_service = equipment_queryset(today).filter(
        state=Equipment.State.IN_SERVICE, last_outcome=Calibration.Outcome.PASS
    )
    for item in in_service.filter(last_due__lte=until).order_by("last_due", "asset_id"):
        days = (item.last_due - today).days
        if days < 0:
            status, tone = f"Overdue by {_days(-days)}", "danger"
        elif days == 0:
            status, tone = "Due today", "warning"
        else:
            status, tone = f"Due in {_days(days)}", "warning" if days <= 7 else "neutral"
        yield Reminder(
            "calibration",
            item.last_due,
            f"{item.asset_id} · {item.description}",
            f"Calibration valid until {item.last_due.isoformat()}",
            reverse("laboratory:equipment_detail", args=[item.pk]),
            status,
            tone,
        )


def _pulls(today, until):
    """Scheduled pulls of active studies whose window opens by ``until``: upcoming, due now and
    overdue (the Stability pulls list's filters)."""
    pulls = _with_windows(
        Pull.objects.filter(state=Pull.State.SCHEDULED, study__state=Study.State.ACTIVE)
    ).select_related("study", "timepoint__condition")
    for pull in pulls.filter(opens__lte=until).order_by("due_date", "pk"):
        opens, closes = pull.window
        if today > closes:
            status, tone = f"Overdue: window closed {closes.isoformat()}", "danger"
        elif today >= opens:
            status, tone = f"Due now, until {closes.isoformat()}", "warning"
        else:
            status, tone = f"Window opens in {_days((opens - today).days)}", "neutral"
        yield Reminder(
            "pull",
            pull.due_date,
            pull.label,
            f"Due {pull.due_date.isoformat()}, window {opens.isoformat()} to {closes.isoformat()}",
            reverse("stability:pull_detail", args=[pull.pk]),
            status,
            tone,
        )


def _reagents(today, until):
    """Released lots whose last day of use falls from today to ``until``."""
    lots = ReagentLot.objects.filter(
        state=ReagentLot.State.RELEASED, expiry_date__gte=today, expiry_date__lte=until
    )
    for lot in lots.order_by("expiry_date", "identifier"):
        days = (lot.expiry_date - today).days
        status = "Expires today" if days == 0 else f"Expires in {_days(days)}"
        yield Reminder(
            "reagent",
            lot.expiry_date,
            f"{lot.identifier} · {lot.name}",
            f"{lot.get_kind_display()}, lot {lot.lot_number}, last day of use "
            f"{lot.expiry_date.isoformat()}",
            reverse("laboratory:reagent_detail", args=[lot.pk]),
            status,
            "warning" if days <= 7 else "neutral",
        )


SOURCES = {"calibration": _calibrations, "pull": _pulls, "reagent": _reagents}


def reminders(today, within, kind=""):
    """Every reminder due by ``today + within`` days, earliest first."""
    until = today + timedelta(days=within)
    found = []
    for key, source in SOURCES.items():
        if not kind or kind == key:
            found.extend(source(today, until))
    return sorted(found, key=lambda r: (r.on, list(SOURCES).index(r.kind), r.label))


def expired_reagents(today):
    """Released lots already past their last day of use (they need no reminder: the Reagents
    list's Released but expired filter shows them)."""
    return ReagentLot.objects.filter(state=ReagentLot.State.RELEASED, expiry_date__lt=today)
