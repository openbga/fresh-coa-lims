"""The arithmetic of trend charts, in exact ``Decimal``: limits computed from a baseline, and the
rules a result is judged by. No database access.

Computed limits follow the individuals chart: the center line is the mean of the baseline
results, σ is estimated from the average moving range (the mean absolute difference between
consecutive results) divided by 1.128, the d2 constant for ranges of two, and the limits are the
center line ± 3σ. The center line and σ are rounded half-up to two decimals more than the test's
reporting precision (six when the test reports exact values); the limits are worked out from
those rounded figures exactly, so anyone can recompute them from what the page shows.

The rules are the run rules of the Western Electric handbook as the NIST/SEMATECH e-Handbook
lists them, with a steady trend; a laboratory chooses which apply. A result is judged with the
results before it; a rule is broken at the result that completes the pattern, and that result
is the one flagged.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from itertools import pairwise

from django.core.exceptions import ValidationError

from .models import Rule

D2 = Decimal("1.128")
MIN_BASELINE = 8  # the fewest results computed limits are worked out from
ADVISED_BASELINE = 20  # fewer results give limits that are shown as uncertain
MAX_DECIMALS = 8  # the precision of the stored figures
EXACT_DECIMALS = 6  # computed figures of a test that reports exact values

NEEDS_CENTER = {Rule.RUN, Rule.TWO_OF_THREE, Rule.FOUR_OF_FIVE}
NEEDS_SIGMA = {Rule.TWO_OF_THREE, Rule.FOUR_OF_FIVE}


def figure_places(decimals):
    """Decimal places of computed figures for a test reported to ``decimals`` places."""
    if decimals is None:
        return EXACT_DECIMALS
    return min(decimals + 2, MAX_DECIMALS)


def _rounded(value, places):
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Baseline:
    count: int
    center: Decimal
    sigma: Decimal
    lower: Decimal
    upper: Decimal
    moving_range: Decimal


def baseline(values, decimals):
    """The computed limits of ``values`` (in the order they were reviewed)."""
    values = [Decimal(value) for value in values]
    if len(values) < MIN_BASELINE:
        raise ValidationError(
            f"The baseline holds {len(values)} result{'s' if len(values) != 1 else ''}; computed "
            f"limits need at least {MIN_BASELINE}. Choose a longer period or enter the limits."
        )
    places = figure_places(decimals)
    with localcontext() as context:
        context.prec = 50
        mean = sum(values) / len(values)
        moving = sum(abs(b - a) for a, b in pairwise(values)) / (len(values) - 1)
        sigma = moving / D2
    center, sigma = _rounded(mean, places), _rounded(sigma, places)
    if sigma <= 0:
        raise ValidationError(
            "The baseline results do not vary, so no limits can be computed from them. Enter "
            "the limits instead."
        )
    return Baseline(
        count=len(values),
        center=center,
        sigma=sigma,
        lower=center - 3 * sigma,
        upper=center + 3 * sigma,
        moving_range=_rounded(moving, places),
    )


@dataclass(frozen=True)
class Judge:
    """What a limits version judges a result by."""

    rules: frozenset
    lower: Decimal | None = None
    upper: Decimal | None = None
    center: Decimal | None = None
    sigma: Decimal | None = None
    run_length: int = 8
    trend_length: int = 6

    @classmethod
    def of(cls, limits):
        return cls(
            rules=frozenset(limits.rules),
            lower=limits.lower,
            upper=limits.upper,
            center=limits.center,
            sigma=limits.sigma,
            run_length=limits.run_length,
            trend_length=limits.trend_length,
        )


def rule_problems(rules, *, center, sigma):
    """Why the chosen rules cannot apply to these figures, as {field: message}; empty when they
    can."""
    problems = {}
    rules = set(rules)
    if Rule.BEYOND not in rules:
        problems["rules"] = "A result outside the limits is always a rule."
    unknown = rules - set(Rule.values)
    if unknown:
        problems["rules"] = f"Unknown rules: {', '.join(sorted(unknown))}."
    if center is None and rules & NEEDS_CENTER:
        problems["center"] = "The rules chosen need a center line."
    if sigma is None and rules & NEEDS_SIGMA:
        problems["sigma"] = "The 2 of 3 and 4 of 5 rules need σ."
    return problems


def _side(value, center, distance):
    """+1 above center + distance, -1 below center - distance, 0 otherwise."""
    if value > center + distance:
        return 1
    if value < center - distance:
        return -1
    return 0


def _zone(values, index, judge, *, multiple, needed, window):
    side = _side(values[index], judge.center, multiple * judge.sigma)
    if side == 0:
        return False
    recent = values[max(0, index - window + 1) : index + 1]
    count = sum(1 for value in recent if _side(value, judge.center, multiple * judge.sigma) == side)
    return count >= needed


def broken(values, index, judge):
    """The rules the result at ``index`` breaks, judged with the results before it, in the order
    of ``Rule``."""
    value = values[index]
    found = []
    rules = judge.rules
    if Rule.BEYOND in rules and (
        (judge.lower is not None and value < judge.lower)
        or (judge.upper is not None and value > judge.upper)
    ):
        found.append(Rule.BEYOND)
    if Rule.RUN in rules and judge.center is not None and index + 1 >= judge.run_length:
        run = values[index - judge.run_length + 1 : index + 1]
        if all(v > judge.center for v in run) or all(v < judge.center for v in run):
            found.append(Rule.RUN)
    if Rule.TREND in rules and index + 1 >= judge.trend_length:
        trend = values[index - judge.trend_length + 1 : index + 1]
        steps = list(pairwise(trend))
        if all(b > a for a, b in steps) or all(b < a for a, b in steps):
            found.append(Rule.TREND)
    if judge.center is not None and judge.sigma is not None:
        if Rule.TWO_OF_THREE in rules and _zone(
            values, index, judge, multiple=2, needed=2, window=3
        ):
            found.append(Rule.TWO_OF_THREE)
        if Rule.FOUR_OF_FIVE in rules and _zone(
            values, index, judge, multiple=1, needed=4, window=5
        ):
            found.append(Rule.FOUR_OF_FIVE)
    return [str(rule) for rule in found]


def describe(rule, *, run_length=8, trend_length=6):
    """A rule in words, with the lengths of the version it belongs to."""
    match rule:
        case Rule.RUN:
            return f"{run_length} results in a row on the same side of the center line"
        case Rule.TREND:
            return (
                f"{trend_length} results in a row each higher, or each lower, than the one before"
            )
    return Rule(rule).label
