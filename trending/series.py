"""The results a trend chart plots and the alerts they raise, read from the record. Nothing here
writes: a result is plotted, judged and flagged from what testing, sampling and the chart's
approved limits already hold, so the alerts can never disagree with the record.

A chart plots each reviewed test of a lot whose current assignment is the chart's material and
stage, with the chart's test code, a numeric or count result and a reportable value in the
chart's unit, in the order the reviews were signed. A test of a stability pull or of a
reassessment names no lot and is not plotted; neither is an invalidated, superseded or
unfinished test. A reviewed test without a value in the chart's unit (a result below a reporting
limit, a qualitative result, another unit) is listed as not plotted, with the reason.

Each result is judged by the limits version in force when its review was signed (approved at or
before that moment and not yet superseded), together with the results before it. A result that
conforms to its specification and breaks a rule of that version raises an alert; one reviewed
before any version was approved raises none, and one that fails its specification is left to
its out-of-specification investigation. Results are judged as the record stands: when an earlier
result is invalidated, or its lot is assigned to another material, the results after it are
judged again, so an alert can appear or go; a result an evaluation covers keeps what was
evaluated.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.db.models import CharField, OuterRef, Q, Subquery
from django.db.models.functions import Cast

from analytical.models import AnalyticalTest
from catalog.units import plain
from core.models import ElectronicSignature

from .models import Chart, EvaluationAlert, Limits
from .rules import Judge, broken

TEST_TYPE = AnalyticalTest._meta.label_lower
REVIEWED = "reviewed"  # the meaning of the review signature (analytical.services.review_test)
CHARTED_TYPES = ("numeric", "count")


@dataclass
class Point:
    test: AnalyticalTest
    value: Decimal
    reviewed_at: datetime
    index: int = 0
    limits: Limits | None = None
    rules: list = field(default_factory=list)  # the rules broken under ``limits``
    covered: EvaluationAlert | None = None  # the evaluation that covers its alert

    @property
    def text(self):
        """The result as reported (its reporting precision), else the value exactly."""
        return self.test.reportable_display or plain(self.value)

    @property
    def conforms(self):
        return self.test.conforms is not False

    @property
    def raised(self):
        """Whether the result raises an alert: it broke a rule of the version in force and
        conforms to its specification."""
        return bool(self.rules) and self.conforms

    @property
    def open_alert(self):
        return self.raised and self.covered is None

    @property
    def spec_limits(self):
        requirement = self.test.requirement
        return _decimal(requirement.get("lower_limit")), _decimal(requirement.get("upper_limit"))


@dataclass
class Unplotted:
    test: AnalyticalTest
    reviewed_at: datetime
    reason: str


@dataclass
class Series:
    chart: Chart
    points: list
    unplotted: list
    versions: list  # approved versions, oldest first

    @property
    def alerts(self):
        return [point for point in self.points if point.raised]

    @property
    def open_alerts(self):
        return [point for point in self.points if point.open_alert]

    @property
    def current(self):
        """The approved version in force now, or None."""
        return next((v for v in reversed(self.versions) if v.superseded_at is None), None)


def _decimal(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _review_moment():
    return Subquery(
        ElectronicSignature.objects.filter(
            meaning=REVIEWED,
            audit_event__object_type=TEST_TYPE,
            audit_event__object_id=Cast(OuterRef("pk"), CharField()),
        )
        .order_by("signed_at")
        .values("signed_at")[:1]
    )


def _assignment(column):
    from sampling.models import LotAssignment

    return Subquery(
        LotAssignment.objects.filter(lot=OuterRef("lot"))
        .order_by("-assigned_at", "-id")
        .values(column)[:1]
    )


def reviewed_tests(charts):
    """The reviewed lot tests of the charts in ``charts``: their test code, of a lot whose
    current assignment is their material and stage (all filtered in SQL), annotated with
    ``reviewed_at`` and that material and stage."""
    charts = list(charts)
    belongs = Q(pk__in=[])
    for chart in charts:
        belongs |= Q(
            test_code=chart.test_code,
            assigned_material=chart.material_id,
            assigned_stage=chart.stage,
        )
    return (
        AnalyticalTest.objects.filter(
            lot__isnull=False,
            state=AnalyticalTest.State.REVIEWED,
            test_code__in={chart.test_code for chart in charts},
        )
        .annotate(
            assigned_material=_assignment("material"),
            assigned_stage=_assignment("stage"),
        )
        .filter(belongs)
        .annotate(reviewed_at=_review_moment())
        .filter(reviewed_at__isnull=False)
        .select_related("lot", "sample")
        .order_by("reviewed_at", "pk")
    )


def _unplotted_reason(chart, test):
    requirement = test.requirement
    if requirement.get("result_type") not in CHARTED_TYPES:
        return "Not a numeric result"
    if requirement.get("unit") != chart.unit:
        return f"In another unit ({requirement.get('unit') or 'none'})"
    if test.reportable_value is None:
        return f"Reported as {test.reportable_display or 'no value'}"
    return ""


def in_force(versions, moment):
    """The approved version in force at ``moment``, or None."""
    for version in reversed(versions):
        if version.approved_at <= moment and (
            version.superseded_at is None or moment < version.superseded_at
        ):
            return version
    return None


def series_of(chart, tests=None, versions=None, covered=None):
    """The chart's points, judged and flagged. ``all_series`` passes the reviewed tests, the
    approved versions and the covered alerts it read for several charts at once.

    A result an evaluation covers keeps the version and the rules recorded with its alert: what
    was evaluated stays shown as evaluated even if an earlier result was invalidated since and
    the result, judged again, would break no rule. Every other result is judged as the record
    now stands, so such a change can also raise an alert on a later result."""
    if tests is None:
        tests = reviewed_tests([chart])
    if versions is None:
        versions = list(
            Limits.objects.filter(chart=chart, state=Limits.State.APPROVED).order_by("approved_at")
        )
    if covered is None:
        covered = {
            alert.test_id: alert
            for alert in EvaluationAlert.objects.filter(evaluation__chart=chart).select_related(
                "evaluation", "limits"
            )
        }
    mine = [
        test
        for test in tests
        if test.test_code == chart.test_code
        and test.assigned_material == chart.material_id
        and test.assigned_stage == chart.stage
    ]
    points, unplotted = [], []
    for test in mine:
        if reason := _unplotted_reason(chart, test):
            unplotted.append(Unplotted(test, test.reviewed_at, reason))
        else:
            points.append(Point(test, test.reportable_value, test.reviewed_at))
    values = [point.value for point in points]
    judges = {}
    for index, point in enumerate(points):
        point.index = index
        point.covered = covered.get(point.test.pk)
        if point.covered is not None:
            point.limits, point.rules = point.covered.limits, list(point.covered.rules)
            continue
        point.limits = in_force(versions, point.reviewed_at)
        if point.limits is not None:
            judge = judges.setdefault(point.limits.pk, Judge.of(point.limits))
            point.rules = broken(values, index, judge)
    return Series(chart, points, unplotted, versions)


def all_series(charts=None):
    """Every chart's series (or those of ``charts``), reading the reviewed tests, the approved
    versions and the covered alerts once for all of them."""
    charts = list(charts if charts is not None else Chart.objects.select_related("material"))
    if not charts:
        return []
    ids = [chart.pk for chart in charts]
    tests = list(reviewed_tests(charts))
    versions = {pk: [] for pk in ids}
    for version in Limits.objects.filter(chart_id__in=ids, state=Limits.State.APPROVED).order_by(
        "approved_at"
    ):
        versions[version.chart_id].append(version)
    covered = {pk: {} for pk in ids}
    for alert in EvaluationAlert.objects.filter(evaluation__chart_id__in=ids).select_related(
        "evaluation", "limits"
    ):
        covered[alert.evaluation.chart_id][alert.test_id] = alert
    return [series_of(c, tests, versions[c.pk], covered[c.pk]) for c in charts]


def lot_alerts(lot):
    """The alerts raised by the lot's results that no evaluation has concluded: (point, chart,
    evaluation or None), for the disposition page."""
    tests = AnalyticalTest.objects.filter(lot=lot, state=AnalyticalTest.State.REVIEWED)
    codes = set(tests.values_list("test_code", flat=True))
    if not codes:
        return []
    from sampling.services import current_assignment

    assignment = current_assignment(lot)
    if assignment is None:
        return []
    charts = Chart.objects.filter(
        material_id=assignment.material_id, stage=assignment.stage, test_code__in=codes
    ).select_related("material")
    found = []
    for series in all_series(charts):
        for point in series.alerts:
            if point.test.lot_id != lot.pk:
                continue
            evaluation = point.covered.evaluation if point.covered else None
            if evaluation is None or evaluation.state == evaluation.State.OPEN:
                found.append((point, series.chart, evaluation))
    return found
