"""The results a shelf-life evaluation uses and what the statistics make of them, read from the
record. Nothing here writes; ``stability.services`` drafts, changes, withdraws and concludes.

An evaluation uses, for each of its studies, the accepted pulls tested in the system at its
storage condition, and the study's time-zero pull when that condition has none of its own (time
zero is often tested once, under one condition). Of each pull it uses the results reported for
the evaluation's test: those its acceptance rested on (``analytical.outcomes``), so a result an
investigation invalidated is left out and a confirmed failure stays in. A result is used when it
is numeric or a count, in the evaluation's unit, with a reportable value; a reviewed result
reported below a limit, or in another unit, is listed as not used with the reason, and so is a
pull not yet accepted, missed or accepted on evidence kept outside the system's tests.

Time on stability is the interval of the pull's time point in the approved protocol, in months
of 365.25 / 12 days: a pull taken within its window counts at its time point. A study with
results at fewer than three time points is listed but not fitted.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from catalog.units import plain

from . import regression
from .evidence import study_results
from .models import Pull, ShelfLifeEvaluation, Study

USED_TYPES = ("numeric", "count")
SCHEMA = "oq.shelf-life/1"
ADVISED_BATCHES = 3  # ICH Q1A(R2) and Q1E: data from at least three primary batches
MAX_STUDIES = 20  # the most studies one evaluation uses


@dataclass
class Point:
    study: Study
    pull: Pull
    test: object  # analytical.models.AnalyticalTest, read through stability.evidence
    value: Decimal
    days: int
    condition: str

    @property
    def months(self):
        return regression.months(self.days)

    @property
    def text(self):
        return self.test.reportable_display or plain(self.value)

    @property
    def conforms(self):
        return self.test.conforms is not False


@dataclass
class Unused:
    study: Study
    pull: Pull
    test: object | None
    reason: str


@dataclass
class Batch:
    study: Study
    points: list = field(default_factory=list)
    # A concluded evaluation keeps whether each study was fitted, and why not, as it was signed.
    frozen_fitted: bool | None = None
    frozen_reason: str = ""

    @property
    def times(self):
        return sorted({point.days for point in self.points})

    @property
    def fitted(self):
        if self.frozen_fitted is not None:
            return self.frozen_fitted
        return len(self.times) >= regression.MIN_TIMES

    @property
    def reason(self):
        if self.frozen_fitted is not None:
            return self.frozen_reason
        if self.fitted:
            return ""
        count = len(self.times)
        return (
            f"Results at {count} time point{'' if count == 1 else 's'}; a study needs "
            f"{regression.MIN_TIMES} to be fitted."
        )


@dataclass
class Scope:
    """What an evaluation (or a draft being written) is of."""

    protocol_code: str
    container_closure: str
    condition: str
    test_code: str
    unit: str
    lower_limit: Decimal | None
    upper_limit: Decimal | None
    direction: str
    decimals: int | None

    @classmethod
    def of(cls, evaluation):
        return cls(
            protocol_code=evaluation.protocol_code,
            container_closure=evaluation.container_closure,
            condition=evaluation.condition,
            test_code=evaluation.test_code,
            unit=evaluation.unit,
            lower_limit=evaluation.lower_limit,
            upper_limit=evaluation.upper_limit,
            direction=evaluation.direction,
            decimals=evaluation.decimals,
        )


@dataclass
class Result:
    """The evaluation's results with the statistics worked out from them."""

    scope: Scope
    batches: list
    unused: list
    analysis: regression.Analysis | None = None
    estimate: regression.Estimate | None = None
    problem: str = ""

    @property
    def fitted(self):
        return [batch for batch in self.batches if batch.fitted]

    @property
    def points(self):
        return [point for batch in self.batches for point in batch.points]

    @property
    def used_points(self):
        return [point for batch in self.fitted for point in batch.points]

    @property
    def covered_months(self):
        """The longest time on stability with a result used: the period the data cover."""
        points = self.used_points
        return max(point.months for point in points) if points else None

    @property
    def estimate_months(self):
        """The estimated shelf life, rounded down to a tenth of a month, or None."""
        if self.estimate is None or self.estimate.months is None:
            return None
        return regression.round_down(self.estimate.months, 1)

    @property
    def longest_supported(self):
        """The longest whole number of months a conclusion may record: the estimate rounded
        down, or the horizon when the limit does not meet the criterion within it."""
        if self.estimate is None:
            return None
        if self.estimate.months is None:
            return regression.HORIZON
        return int(regression.round_down(self.estimate.months, 0))

    @property
    def data(self):
        """The used and unused results as frozen evidence, in a fixed order."""
        return {
            "results": [
                {
                    "study": point.study.identifier,
                    "lot": point.study.lot.number,
                    "pull": point.pull.pk,
                    "condition": point.condition,
                    "timepoint": point.pull.timepoint.label,
                    "interval_days": point.days,
                    "test": point.test.pk,
                    "value": plain(point.value),
                    "reportable": point.text,
                    "conforms": point.test.conforms,
                    "fitted": batch.fitted,
                }
                for batch in self.batches
                for point in sorted(batch.points, key=lambda p: (p.days, p.test.pk))
            ],
            "unused": [
                {
                    "study": item.study.identifier,
                    "pull": item.pull.pk,
                    "test": item.test.pk if item.test else None,
                    "reason": item.reason,
                }
                for item in self.unused
            ],
        }

    @property
    def tests(self):
        return [point.test for point in self.points]


def studies_of(protocol_code, container_closure):
    """The studies an evaluation of this protocol code and container closure can use."""
    return (
        Study.objects.filter(protocol__code=protocol_code, container_closure=container_closure)
        .select_related("protocol", "lot")
        .order_by("start_date", "pk")
    )


def _unit_reason(scope, test):
    requirement = test.requirement
    if requirement.get("result_type") not in USED_TYPES:
        return "Not a numeric result"
    if requirement.get("unit") != scope.unit:
        return f"In another unit ({requirement.get('unit') or 'none'})"
    if test.reportable_value is None:
        return f"Reported as {test.reportable_display or 'no value'}"
    return ""


def choose(pulls, condition):
    """Of ``pulls`` (in study, interval and record order), those at ``condition``, and for each
    study whose condition has no time-zero pull, one time-zero pull of another condition: an
    accepted one first, else the first recorded."""
    zero_here = {
        pull.study_id
        for pull in pulls
        if pull.timepoint.condition.label == condition and pull.timepoint.interval_days == 0
    }
    stand_ins = {}
    for pull in pulls:
        if (
            pull.timepoint.condition.label != condition
            and pull.timepoint.interval_days == 0
            and pull.study_id not in zero_here
        ):
            best = stand_ins.get(pull.study_id)
            if best is None or (
                best.state != Pull.State.ACCEPTED and pull.state == Pull.State.ACCEPTED
            ):
                stand_ins[pull.study_id] = pull
    return [
        pull
        for pull in pulls
        if pull.timepoint.condition.label == condition or stand_ins.get(pull.study_id) is pull
    ]


def _pulls(scope, studies):
    """The pulls of ``studies`` whose time point tests the scope's test (``choose``)."""
    pulls = [
        pull
        for pull in Pull.objects.filter(study__in=studies)
        .select_related("timepoint__condition", "study__lot", "study__protocol")
        .order_by("study_id", "timepoint__interval_days", "pk")
        if scope.test_code in pull.timepoint.test_codes
    ]
    return choose(pulls, scope.condition)


def read(scope, studies):
    """The results of ``studies`` (Study instances) for ``scope``, sorted into batches."""
    studies = list(studies)
    batches = {study.pk: Batch(study) for study in studies}
    unused = []
    pulls = _pulls(scope, studies)
    tested = [pull for pull in pulls if pull.state == Pull.State.ACCEPTED]
    results = study_results(tested)
    for pull in pulls:
        study = batches[pull.study_id].study
        if pull.state == Pull.State.SCHEDULED:
            continue
        if pull.state == Pull.State.MISSED:
            unused.append(Unused(study, pull, None, "The pull was missed."))
            continue
        if pull.state == Pull.State.PULLED:
            unused.append(Unused(study, pull, None, "The pull is not yet accepted."))
            continue
        if pull.pk not in results:
            unused.append(
                Unused(
                    study,
                    pull,
                    None,
                    "Accepted on a linked sample or external evidence; its results are not "
                    "read here.",
                )
            )
            continue
        _, rows, _ = results[pull.pk]
        row = next((row for row in rows if row["test_code"] == scope.test_code), None)
        for test in row["tests"] if row else []:
            if reason := _unit_reason(scope, test):
                unused.append(Unused(study, pull, test, reason))
                continue
            batches[pull.study_id].points.append(
                Point(
                    study=study,
                    pull=pull,
                    test=test,
                    value=test.reportable_value,
                    days=pull.timepoint.interval_days,
                    condition=pull.timepoint.condition.label,
                )
            )
    return list(batches.values()), unused


def evaluate(scope, studies):
    """The results of ``studies`` for ``scope`` and the statistics worked out from them."""
    batches, unused = read(scope, studies)
    result = Result(scope=scope, batches=batches, unused=unused)
    fitted = result.fitted
    if not fitted:
        result.problem = (
            f"No study has results at {regression.MIN_TIMES} or more time points yet, so "
            "nothing can be fitted."
        )
        return result
    result.analysis = regression.analyse(
        [[(point.months, point.value) for point in batch.points] for batch in fitted]
    )
    result.estimate = regression.estimate(
        result.analysis, scope.direction, scope.lower_limit, scope.upper_limit
    )
    return result


def of(evaluation):
    """What a draft's studies show now. A concluded evaluation is shown from its content."""
    studies = [link.study for link in evaluation.study_links.select_related("study__lot")]
    studies = (
        Study.objects.filter(pk__in=[study.pk for study in studies])
        .select_related("protocol", "lot")
        .order_by("start_date", "pk")
    )
    return evaluate(Scope.of(evaluation), studies)


# Figures as they are shown and frozen ---------------------------------------------------------


def figure_places(decimals):
    """Decimal places of slopes, intercepts and standard deviations: three more than the
    test's reporting precision (seven when it reports exact values), at most 8."""
    return min((4 if decimals is None else decimals) + 3, 8)


def _fixed(value, places):
    return None if value is None else plain(regression.round_half_up(value, places))


def _test(test):
    if test is None:
        return None
    return {
        "f": _fixed(test.f, 4) if test.f is not None else None,
        "df1": test.df1,
        "df2": test.df2,
        "p": _fixed(test.p, 4),
        "rejected": test.rejected,
    }


def figures(result):
    """The statistics of ``result`` as rounded strings, the way the page shows them and the
    conclusion freezes them; None when nothing was fitted."""
    analysis, estimate = result.analysis, result.estimate
    if analysis is None:
        return None
    places = figure_places(result.scope.decimals)
    fitted = result.fitted
    pooled = len(analysis.fits) == 1
    batches = []
    for number, (batch, line) in enumerate(zip(fitted, analysis.lines, strict=True)):
        fit = analysis.fits[0 if pooled else number]
        crossings = estimate.crossings[0 if pooled else number]
        batches.append(
            {
                "study": batch.study.identifier,
                "lot": batch.study.lot.number,
                "results": line.n,
                "own_slope": _fixed(line.slope, places),
                "own_intercept": _fixed(line.intercept, places),
                "slope": _fixed(fit.slope, places),
                "intercept": _fixed(fit.intercept, places),
                "crossings": {
                    side: _fixed(regression.round_down(months, 1), 1)
                    if months is not None
                    else None
                    for side, months in crossings
                },
            }
        )
    return {
        "model": analysis.model,
        "df": analysis.df,
        "residual_sd": _fixed(analysis.mse.sqrt() if analysis.mse > 0 else Decimal(0), places),
        "slopes": _test(analysis.slopes),
        "intercepts": _test(analysis.intercepts),
        "t": _fixed(estimate.t, 4),
        "confidence": "two-sided 95 %"
        if result.scope.direction == ShelfLifeEvaluation.Direction.EITHER
        else "one-sided 95 %",
        "significance": plain(regression.SIGNIFICANCE),
        "horizon": regression.HORIZON,
        "batches": batches,
        "estimate_months": plain(result.estimate_months)
        if result.estimate_months is not None
        else None,
        "covered_months": _fixed(result.covered_months, 1),
    }


def frozen(evaluation, result):
    """The content a conclusion's signature freezes, with its digest."""
    from catalog.services import digest

    content = {
        "schema": SCHEMA,
        "identifier": evaluation.identifier,
        "protocol_code": evaluation.protocol_code,
        "product": evaluation.product,
        "container_closure": evaluation.container_closure,
        "condition": evaluation.condition,
        "specification": {
            "code": evaluation.specification.code,
            "version": evaluation.specification_version,
        },
        "test": {
            "code": evaluation.test_code,
            "name": evaluation.name,
            "unit": evaluation.unit,
            "decimals": evaluation.decimals,
        },
        "criterion": {
            "lower": plain(evaluation.lower_limit),
            "upper": plain(evaluation.upper_limit),
        },
        "direction": evaluation.direction,
        "purpose": evaluation.purpose,
        "studies": [
            {
                "study": batch.study.identifier,
                "lot": batch.study.lot.number,
                "start_date": batch.study.start_date.isoformat(),
                "fitted": batch.fitted,
                "reason": batch.reason,
            }
            for batch in result.batches
        ],
        **result.data,
        "figures": figures(result),
        "outcome": evaluation.outcome,
        "shelf_life_months": evaluation.shelf_life_months,
        "conclusion": evaluation.conclusion,
    }
    return content, digest(content)


def data_digest(evaluation, result):
    """A digest of what the conclusion rests on: the criterion, direction, studies and results.
    The conclusion page carries it, so a signature is refused when any of it changed since."""
    from catalog.services import digest

    return digest(
        {
            "criterion": [plain(evaluation.lower_limit), plain(evaluation.upper_limit)],
            "direction": evaluation.direction,
            "studies": [batch.study.pk for batch in result.batches],
            **result.data,
        }
    )


# A concluded evaluation, shown from what its signature froze ------------------------------------


@dataclass(frozen=True)
class FrozenLot:
    number: str


@dataclass(frozen=True)
class FrozenStudy:
    pk: str
    identifier: str
    lot: FrozenLot
    start_date: str = ""


@dataclass(frozen=True)
class FrozenTimepoint:
    label: str


@dataclass(frozen=True)
class FrozenPull:
    pk: int
    timepoint: FrozenTimepoint


@dataclass(frozen=True)
class FrozenTest:
    pk: int
    conforms: bool | None


@dataclass
class FrozenPoint:
    """A result as the conclusion froze it, read like a ``Point``."""

    study: FrozenStudy
    pull: FrozenPull
    test: FrozenTest
    value: Decimal
    days: int
    condition: str
    text: str

    @property
    def months(self):
        return regression.months(self.days)

    @property
    def conforms(self):
        return self.test.conforms is not False


def replay(content):
    """The ``Result`` of a concluded evaluation, worked out again from the results its signature
    froze and the studies it fitted then. The page shows the frozen figures; this replay draws
    the chart, and the page says so if the current statistics give other figures."""
    criterion = content["criterion"]
    scope = Scope(
        protocol_code=content["protocol_code"],
        container_closure=content["container_closure"],
        condition=content["condition"],
        test_code=content["test"]["code"],
        unit=content["test"]["unit"],
        lower_limit=Decimal(criterion["lower"]) if criterion["lower"] is not None else None,
        upper_limit=Decimal(criterion["upper"]) if criterion["upper"] is not None else None,
        direction=content["direction"],
        decimals=content["test"]["decimals"],
    )
    studies = {
        item["study"]: FrozenStudy(
            pk=item["study"],
            identifier=item["study"],
            lot=FrozenLot(item["lot"]),
            start_date=item["start_date"],
        )
        for item in content["studies"]
    }
    batches = {
        item["study"]: Batch(
            studies[item["study"]],
            frozen_fitted=item.get("fitted"),
            frozen_reason=item.get("reason", ""),
        )
        for item in content["studies"]
    }
    for row in content["results"]:
        batches[row["study"]].points.append(
            FrozenPoint(
                study=studies[row["study"]],
                pull=FrozenPull(row["pull"], FrozenTimepoint(row["timepoint"])),
                test=FrozenTest(row["test"], row["conforms"]),
                value=Decimal(row["value"]),
                days=row["interval_days"],
                condition=row["condition"],
                text=row["reportable"],
            )
        )
    unused = [
        Unused(studies[item["study"]], FrozenPull(item["pull"], None), None, item["reason"])
        for item in content["unused"]
    ]
    result = Result(scope=scope, batches=list(batches.values()), unused=unused)
    if result.fitted:
        result.analysis = regression.analyse(
            [[(point.months, point.value) for point in batch.points] for batch in result.fitted]
        )
        result.estimate = regression.estimate(
            result.analysis, scope.direction, scope.lower_limit, scope.upper_limit
        )
    return result
