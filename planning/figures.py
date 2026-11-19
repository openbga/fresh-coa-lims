"""Turnaround and right-first-time figures of the tests reviewed in a period. Read-only: the
figures are derived from the records the testing keeps (the review signature, the audited
returns, the corrected readings and the repeats), so they need no table of their own and can
never disagree with the record.

A test counts in the period of its review signature (the local day it was signed). Its
turnaround is the number of calendar days from the local day it was assigned to that day, and
it is on time when it was reviewed on or before its due date (the planner's date, else the
turnaround target in force when it was assigned, ``services.with_due``). It is right first time
when it was never returned for correction, none of its readings was corrected, and it is neither
a repeat of an earlier test (a retest, resample, rerun after a QC failure or repeat of a test
not completed) nor followed by one. A repeat under replaced requirements is new work under new
requirements, not a repeat of failed work, so it counts neither way.
"""

from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    Exists,
    F,
    Func,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.fields.json import KT
from django.db.models.functions import Cast, Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from analytical.models import AnalyticalTest, Investigation, Observation
from core.models import AuditEvent, ElectronicSignature

from .models import Work
from .services import WORK_SUBJECT, with_due

TEST_TYPE = AnalyticalTest._meta.label_lower
REVIEWED = "reviewed"  # the meaning of the review signature (analytical.services.review_test)
RETURNED = "test.returned"  # the audit action of a return for correction
Kind = AnalyticalTest.Kind
REPEAT_KINDS = (Kind.RETEST, Kind.RESAMPLE, Kind.RERUN, Kind.REPEAT)
MAX_PERIOD_DAYS = 366
DEFAULT_PERIOD_DAYS = 30

ON_TIME, LATE, NO_DUE = "on_time", "late", "no_due"
TIMELINESS = [(ON_TIME, "On time"), (LATE, "Late"), (NO_DUE, "No due date")]
FIRST_TIME, NOT_FIRST_TIME = "yes", "no"
RETURNED_KEY, CORRECTED_KEY, REPEAT_KEY = "returned", "corrected", "repeat"
FIRST_TIME_CHOICES = [
    (FIRST_TIME, "Right first time"),
    (NOT_FIRST_TIME, "Not right first time"),
    (RETURNED_KEY, "Returned for correction"),
    (CORRECTED_KEY, "A reading corrected"),
    (REPEAT_KEY, "A repeat, or repeated"),
]

RESULTS = [
    ("oos", "Out of specification"),
    ("invalidated", "Invalidated after investigation"),
]

GROUPS = [
    ("work", "Kind of work"),
    ("material", "Material"),
    ("method", "Method"),
    ("analyst", "Analyst"),
    ("month", "Month reviewed"),
]


class DaysBetween(Func):
    """PostgreSQL ``date - date``: the whole number of days between two dates."""

    arg_joiner = " - "
    template = "(%(expressions)s)"
    output_field = IntegerField()


def _pk_text():
    return Cast(OuterRef("pk"), CharField())


def _reviews():
    """Review signatures of tests, reached through their audit events (indexed by record)."""
    return ElectronicSignature.objects.filter(meaning=REVIEWED, audit_event__object_type=TEST_TYPE)


def _count(queryset):
    return Coalesce(
        Subquery(
            queryset.order_by().values(group=Value(1)).annotate(n=Count("pk")).values("n")[:1],
            output_field=IntegerField(),
        ),
        0,
    )


def period_bounds(start, end):
    """The aware datetimes of the local days ``start`` to ``end`` inclusive: [from, until)."""
    zone = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start, time.min), zone),
        timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), zone),
    )


def default_period(today):
    return today - timedelta(days=DEFAULT_PERIOD_DAYS - 1), today


def reviewed_tests(start, end):
    """The tests whose review was signed on a local day from ``start`` to ``end``, annotated
    with what the figures count: ``reviewed_at``, ``reviewed_on``, ``assigned_on``, ``due``,
    ``turnaround`` (days), ``timeliness``, ``returns``, ``corrections``, ``is_repeat``,
    ``repeated``, ``invalidated`` (an investigation of its result concluded that it was invalid),
    ``first_time``, ``work``, ``material``, ``method`` and ``month``."""
    since, until = period_bounds(start, end)
    in_period = _reviews().filter(signed_at__gte=since, signed_at__lt=until)
    zone = timezone.get_current_timezone()
    # The signatures of the period name their tests by text; their ids, as integers, select
    # the tests by primary key (only rows of the test type are cast).
    ids = in_period.values(test_id=Cast("audit_event__object_id", IntegerField()))
    tests = AnalyticalTest.objects.filter(pk__in=Subquery(ids)).select_related(
        "lot",
        "sample",
        "pull__study__lot",
        "pull__timepoint__condition",
        "reassessment__lot",
        "submitted_by",
        "plan",
    )
    tests = with_due(tests).annotate(
        reviewed_at=Subquery(
            _reviews()
            .filter(audit_event__object_id=_pk_text())
            .order_by("signed_at")
            .values("signed_at")[:1]
        ),
        reviewed_on=TruncDate("reviewed_at", tzinfo=zone),
        month=TruncMonth("reviewed_at", tzinfo=zone),
        turnaround=DaysBetween(F("reviewed_on"), F("assigned_on")),
        timeliness=Case(
            When(due__isnull=True, then=Value(NO_DUE)),
            When(reviewed_on__lte=F("due"), then=Value(ON_TIME)),
            default=Value(LATE),
        ),
        returns=_count(
            AuditEvent.objects.filter(object_type=TEST_TYPE, object_id=_pk_text(), action=RETURNED)
        ),
        corrections=_count(
            Observation.objects.filter(test=OuterRef("pk"), supersedes__isnull=False)
        ),
        is_repeat=Case(
            When(kind__in=REPEAT_KINDS, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        repeated=Exists(
            AnalyticalTest.objects.filter(parent=OuterRef("pk"), kind__in=REPEAT_KINDS)
        ),
        invalidated=Exists(
            Investigation.objects.filter(
                test=OuterRef("pk"), outcome=Investigation.Outcome.INVALIDATED
            )
        ),
        work=Case(
            *(When(subject, then=Value(work.value)) for work, subject in WORK_SUBJECT.items()),
            output_field=CharField(),
        ),
        material=Coalesce(
            "lot__material", "pull__study__lot__material", "reassessment__lot__material"
        ),
        method=KT("requirement__method__code"),
    )
    return tests.annotate(
        first_time=Case(
            When(Q(returns=0, corrections=0, is_repeat=False, repeated=False), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    )


def first_time_filter(tests, key):
    match key:
        case "yes":
            return tests.filter(first_time=True)
        case "no":
            return tests.filter(first_time=False)
        case "returned":
            return tests.filter(returns__gt=0)
        case "corrected":
            return tests.filter(corrections__gt=0)
        case "repeat":
            return tests.filter(Q(is_repeat=True) | Q(repeated=True))
    return tests


def filter_reviewed(tests, data):
    """The Reviewed tests list's filters (the figures' links set the same keys)."""
    if data.get("work"):
        tests = tests.filter(WORK_SUBJECT[data["work"]])
    if data.get("material"):
        tests = tests.filter(material=data["material"])
    if data.get("method"):
        tests = tests.filter(method=data["method"])
    match data.get("analyst"):
        case "" | None:
            pass
        case "none":
            tests = tests.filter(submitted_by__isnull=True)
        case analyst:
            tests = tests.filter(submitted_by_id=int(analyst))
    if data.get("timeliness"):
        tests = tests.filter(timeliness=data["timeliness"])
    if data.get("first_time"):
        tests = first_time_filter(tests, data["first_time"])
    match data.get("result"):
        case "oos":
            tests = tests.filter(conforms=False)
        case "invalidated":
            tests = tests.filter(invalidated=True)
    return tests


# What one row of the figures reads of each test (reviewed_tests annotations).
MEASURED = (
    "turnaround",
    "timeliness",
    "first_time",
    "returns",
    "corrections",
    "is_repeat",
    "repeated",
    "conforms",
    "invalidated",
)

GROUP_FIELD = {
    "work": "work",
    "material": "material",
    "method": "method",
    "analyst": "submitted_by",
    "month": "month",
}


def median(days):
    """The median of sorted whole days, halfway between the two middle ones for an even count,
    exactly (Decimal to one place); None for no days."""
    n = len(days)
    if not n:
        return None
    middle = Decimal(days[n // 2]) if n % 2 else (Decimal(days[n // 2 - 1]) + days[n // 2]) / 2
    return middle.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def ninth_decile(days):
    """The fewest days that at least nine in ten of the sorted ``days`` did not exceed."""
    if not days:
        return None
    return days[-(-9 * len(days) // 10) - 1]


def measure(rows):
    """The figures of rows of MEASURED values (dicts)."""
    days = sorted(row["turnaround"] for row in rows)
    count = {
        "reviewed": len(rows),
        "on_time": 0,
        "late": 0,
        "no_due": 0,
        "first_time": 0,
        "returned": 0,
        "corrected": 0,
        "repeat": 0,
        "oos": 0,
        "invalidated": 0,
    }
    for row in rows:
        count[row["timeliness"]] += 1
        count["first_time"] += row["first_time"]
        count["returned"] += row["returns"] > 0
        count["corrected"] += row["corrections"] > 0
        count["repeat"] += row["is_repeat"] or row["repeated"]
        count["oos"] += row["conforms"] is False
        count["invalidated"] += row["invalidated"]
    return {
        **count,
        "with_due": count["on_time"] + count["late"],
        "median": median(days),
        "ninth": ninth_decile(days),
    }


def rows_of(tests, group=None):
    """One row of MEASURED values per test (and its ``key`` in ``group``), in one query."""
    extra = {"key": F(GROUP_FIELD[group])} if group else {}
    return list(tests.order_by().values(*MEASURED, **extra))


def grouped(rows, group):
    """[{key, **figures}] for each value of ``key`` in ``rows`` (rows_of with ``group``):
    months in order, anything else most reviewed first."""
    found = {}
    for row in rows:
        found.setdefault(row["key"], []).append(row)
    groups = [{"key": key, **measure(items)} for key, items in found.items()]
    if group == "month":
        return sorted(groups, key=lambda item: item["key"])
    return sorted(groups, key=lambda item: (-item["reviewed"], str(item["key"] or "")))


def totals(tests):
    """The figures of every test in ``tests``."""
    return measure(rows_of(tests))


def by_group(tests, group):
    """[{key, **figures}] for each value of the group (GROUPS)."""
    return grouped(rows_of(tests, group), group)


def share(part, whole):
    """``part`` of ``whole`` as a whole percentage, rounded half up; None without a whole."""
    if not whole:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


WORK_LABELS = dict(Work.choices)


def filter_options(tests):
    """The materials, method codes and analysts (ids) of ``tests``: the choices of the Reviewed
    tests filters, so they stay as short as the period's own work."""
    materials, methods, analysts = set(), set(), set()
    for material, method, analyst in (
        tests.order_by().values_list("material", "method", "submitted_by").distinct()
    ):
        materials.add(material)
        methods.add(method)
        analysts.add(analyst)
    return {
        "material": sorted(m for m in materials if m),
        "method": sorted(m for m in methods if m),
        "analyst": analysts - {None},
    }
