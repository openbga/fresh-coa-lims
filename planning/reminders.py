"""Reminders: the calibrations, stability pulls, reagent or standard lots, qualifications and
proficiency testing results that fall due within a window of days, and the out-of-trend alerts no
evaluation covers yet, read from the same queries as their lists. Nothing is stored or sent: the
page lists what is due, and each row opens the record that resolves it."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import DateField, Exists, ExpressionWrapper, OuterRef, Q
from django.urls import reverse
from django.utils import timezone

from catalog.models import ProficiencyParticipation
from laboratory.eligibility import equipment_queryset
from laboratory.models import Calibration, Equipment, Qualification, ReagentLot
from stability.models import Pull, Study
from stability.views import _with_windows

KINDS = {
    "calibration": "Calibration",
    "pull": "Stability pull",
    "reagent": "Reagent or standard",
    "qualification": "Qualification",
    "proficiency": "Proficiency testing",
    "trend": "Out-of-trend alert",
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


def renewed(subject):
    """An approved, unrevoked qualification of the same person or instrument (``subject``:
    "user" or "equipment"), for the same activity (any case) and work, that takes over by the
    day after this one's last valid day and runs past it: once it exists, this one needs no
    reminder."""
    day_after = ExpressionWrapper(
        OuterRef("valid_until") + timedelta(days=1), output_field=DateField()
    )
    return Qualification.objects.filter(
        **{subject: OuterRef(subject)},
        state=Qualification.State.APPROVED,
        activity__iexact=OuterRef("activity"),
        work=OuterRef("work"),
        valid_until__gt=OuterRef("valid_until"),
        valid_from__lte=day_after,
    ).exclude(pk=OuterRef("pk"))


def expiring_qualifications(today, until):
    """Approved qualifications in effect today whose last valid day falls from today to
    ``until`` and that no approved renewal follows. A revoked one is not reminded of, nor one of
    an inactive account or of equipment out of service (as calibrations are reminded of only
    for equipment in service)."""
    return (
        Qualification.objects.filter(
            Q(user__is_active=True) | Q(equipment__state=Equipment.State.IN_SERVICE),
            state=Qualification.State.APPROVED,
            valid_from__lte=today,
            valid_until__gte=today,
            valid_until__lte=until,
        )
        .alias(renewed=Exists(renewed("user")) | Exists(renewed("equipment")))
        .filter(renewed=False)
        .select_related("user", "equipment")
    )


def _qualifications(today, until):
    for item in expiring_qualifications(today, until).order_by("valid_until", "activity", "pk"):
        days = (item.valid_until - today).days
        status = "Last valid day today" if days == 0 else f"Expires in {_days(days)}"
        subject = (
            (item.user.get_full_name() or item.user.get_username())
            if item.user_id
            else item.equipment.asset_id
        )
        purpose = item.get_work_display().lower() if item.user_id else "intended use"
        yield Reminder(
            "qualification",
            item.valid_until,
            f"QUAL-{item.pk} · {item.activity}",
            f"{subject}, {purpose}, valid until {item.valid_until.isoformat()}",
            reverse("laboratory:qualification_detail", args=[item.pk]),
            status,
            "warning" if days <= 7 else "neutral",
        )


def _proficiency(today, until):
    """Open participations whose results are due by ``until`` and are not reported yet, overdue
    ones included: they stay listed until the report is recorded or the participation is
    cancelled."""
    planned = ProficiencyParticipation.objects.filter(
        state=ProficiencyParticipation.State.OPEN,
        reported_on__isnull=True,
        results_due__lte=until,
    ).select_related("method")
    for item in planned.order_by("results_due", "pk"):
        days = (item.results_due - today).days
        if days < 0:
            status, tone = f"Overdue by {_days(-days)}", "danger"
        elif days == 0:
            status, tone = "Due today", "warning"
        else:
            status, tone = f"Due in {_days(days)}", "warning" if days <= 7 else "neutral"
        yield Reminder(
            "proficiency",
            item.results_due,
            f"{item.identifier} · {item.method.code}",
            f"{item.provider}, {item.round_ref}: results due {item.results_due.isoformat()}",
            reverse("catalog:proficiency_detail", args=[item.pk]),
            status,
            tone,
        )


def _trend_alerts(today, until):
    """Results that raised an out-of-trend alert no evaluation covers yet, whatever the window:
    like an overdue item, an alert stays listed until quality evaluates it. Dated by the day its
    review was signed."""
    from trending.rules import describe
    from trending.series import all_series

    for series in all_series():
        chart = series.chart
        for point in series.open_alerts:
            limits = point.limits
            rules = "; ".join(
                describe(rule, run_length=limits.run_length, trend_length=limits.trend_length)
                for rule in point.rules
            )
            yield Reminder(
                "trend",
                timezone.localtime(point.reviewed_at).date(),
                f"{chart.identifier} · {point.test.label}",
                f"{chart.name} of {chart.material.code}, lot {point.test.lot.number}: "
                f"{point.text} {chart.unit}. {rules}",
                reverse("trending:chart_detail", args=[chart.pk]),
                "Not evaluated",
                "danger",
            )


SOURCES = {
    "calibration": _calibrations,
    "pull": _pulls,
    "reagent": _reagents,
    "qualification": _qualifications,
    "proficiency": _proficiency,
    "trend": _trend_alerts,
}


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
