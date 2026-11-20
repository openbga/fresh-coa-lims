"""The statistics of a shelf-life evaluation, in ``Decimal`` worked to 50 significant digits: the
least-squares line of each batch's results on time, the analysis of covariance that decides
whether batches are pooled, Student's t and F distributions, and the confidence limit of the mean
line with the time at which it meets an acceptance criterion. No database access.

The method is that of ICH Q1E (Evaluation for Stability Data, 2003), Appendix B:

- Each batch's results are fitted by a straight line on time. Batches are pooled when the
  analysis of covariance does not reject equal slopes, and then equal intercepts, at the 0.25
  significance level. Slopes that differ give each batch its own line; equal slopes with
  intercepts that differ give a common slope with each batch's own intercept. Separate lines use
  the mean square error pooled from all batches, as Q1E says; a common slope uses that model's
  own mean square error, an error term Q1E does not name. Equal slopes and intercepts give one
  line for all data.
- The intercept test is made under the common-slope model and uses that model's mean square
  error. Q1E names the tests and their order but not this denominator; it is the product's
  choice, written here so anyone can recompute it.
- The shelf life is the earliest time at which the 95 % confidence limit of the mean line meets
  the acceptance criterion: the one-sided lower limit for an attribute expected to decrease, the
  one-sided upper limit for one expected to increase, and the two-sided limits (97.5 % on each
  side) when the direction is not known. When batches are not pooled, the shortest estimate of
  any batch applies. The search stops at ``HORIZON`` months.

The distributions come from the regularized incomplete beta function (a continued fraction),
with the gamma function of half-integers exact, so no table or floating point is involved.
"""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from functools import cache

PRECISION = 50
SIGNIFICANCE = Decimal("0.25")  # ICH Q1E B.2.2.1: the level of the poolability tests
CONFIDENCE = Decimal("0.95")
HORIZON = 120  # months: the furthest time searched for a crossing
MIN_TIMES = 3  # distinct time points a batch needs to be fitted
_EPS = Decimal("1e-40")
_TINY = Decimal("1e-80")
_MAX_ITER = 20000
_TOLERANCE = Decimal("1e-12")  # months, the bisection's last step


class Model:
    POOLED = "pooled"
    COMMON_SLOPE = "common_slope"
    SEPARATE = "separate"
    SINGLE = "single"

    LABELS = {
        POOLED: "One line for all batches (slopes and intercepts pooled)",
        COMMON_SLOPE: "A common slope with each batch's own intercept",
        SEPARATE: "Each batch's own slope and intercept",
        SINGLE: "One batch",
    }


class Direction:
    DECREASES = "decreases"
    INCREASES = "increases"
    EITHER = "either"


def _context():
    return localcontext(prec=PRECISION)


def months(days):
    """Days on stability as months of 365.25 / 12 days."""
    with _context():
        return Decimal(days) * 48 / 1461


def round_half_up(value, places):
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def round_down(value, places):
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_FLOOR)


# Distributions --------------------------------------------------------------------------------


@cache
def _pi():
    """π to the working precision (the recipe of the ``decimal`` module's documentation)."""
    with _context() as context:
        context.prec += 2
        three = Decimal(3)
        last, t, s, n, na, d, da = 0, three, 3, 1, 0, 0, 24
        while s != last:
            last = s
            n, na = n + na, na + 8
            d, da = d + da, da + 32
            t = (t * n) / d
            s += t
    with _context():
        return +s


@cache
def _gamma_half(twice):
    """Γ(twice / 2) for a positive integer ``twice``, exact up to the working precision."""
    with _context():
        if twice % 2 == 0:
            result = Decimal(1)
            for k in range(2, twice // 2):
                result *= k
            return result
        k = (twice - 1) // 2
        result = _pi().sqrt()
        for j in range(k):  # Γ(k + ½) = (½)(3/2)…(k − ½) √π
            result *= Decimal(2 * j + 1) / 2
        return result


def _continued_fraction(a, b, x):
    """The continued fraction of the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1, a - 1
    c = Decimal(1)
    d = 1 - qab * x / qap
    d = 1 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, _MAX_ITER):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > _TINY else _TINY)
        c = 1 + aa / c
        c = c if abs(c) > _TINY else _TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > _TINY else _TINY)
        c = 1 + aa / c
        c = c if abs(c) > _TINY else _TINY
        delta = d * c
        h *= delta
        if abs(delta - 1) < _EPS:
            return h
    raise ArithmeticError("The incomplete beta function did not converge.")


def incomplete_beta(twice_a, twice_b, x):
    """The regularized incomplete beta function I_x(a, b) for a = twice_a / 2 and
    b = twice_b / 2 (positive integers ``twice_a``, ``twice_b``), 0 <= x <= 1."""
    with _context():
        x = Decimal(x)
        if x <= 0:
            return Decimal(0)
        if x >= 1:
            return Decimal(1)
        a, b = Decimal(twice_a) / 2, Decimal(twice_b) / 2
        front = (
            _gamma_half(twice_a + twice_b)
            / (_gamma_half(twice_a) * _gamma_half(twice_b))
            * x.sqrt() ** twice_a
            * (1 - x).sqrt() ** twice_b
        )
        if x < (a + 1) / (a + b + 2):
            return front * _continued_fraction(a, b, x) / a
        return 1 - front * _continued_fraction(b, a, 1 - x) / b


def t_cdf(t, df):
    """P(T <= t) for Student's t with ``df`` degrees of freedom."""
    with _context():
        t = Decimal(t)
        tail = incomplete_beta(df, 1, df / (df + t * t)) / 2
        return 1 - tail if t >= 0 else tail


@cache
def t_quantile(probability, df):
    """The ``probability`` quantile (above 0.5) of Student's t with ``df`` degrees of freedom."""
    with _context():
        probability = Decimal(probability)
        if not Decimal("0.5") < probability < 1 or df < 1:
            raise ValueError("A quantile above 0.5 with at least one degree of freedom.")
        low, high = Decimal(0), Decimal(1)
        while t_cdf(high, df) < probability:
            low, high = high, high * 2
        while high - low > Decimal("1e-30"):
            middle = (low + high) / 2
            if t_cdf(middle, df) < probability:
                low = middle
            else:
                high = middle
        return (low + high) / 2


def f_survival(f, df1, df2):
    """P(F > f) for the F distribution with ``df1`` and ``df2`` degrees of freedom."""
    with _context():
        f = Decimal(f)
        if f <= 0:
            return Decimal(1)
        return incomplete_beta(df2, df1, df2 / (df2 + df1 * f))


# Least squares --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """The least-squares line of one batch's results ``y`` on time ``x`` (months)."""

    n: int
    mean_x: Decimal
    mean_y: Decimal
    sxx: Decimal
    sxy: Decimal
    syy: Decimal

    @classmethod
    def of(cls, points):
        points = [(Decimal(x), Decimal(y)) for x, y in points]
        with _context():
            n = len(points)
            mean_x = sum(x for x, _ in points) / n
            mean_y = sum(y for _, y in points) / n
            return cls(
                n=n,
                mean_x=mean_x,
                mean_y=mean_y,
                sxx=sum((x - mean_x) ** 2 for x, _ in points),
                sxy=sum((x - mean_x) * (y - mean_y) for x, y in points),
                syy=sum((y - mean_y) ** 2 for _, y in points),
            )

    @property
    def slope(self):
        with _context():
            return self.sxy / self.sxx

    @property
    def intercept(self):
        with _context():
            return self.mean_y - self.slope * self.mean_x

    @property
    def sse(self):
        """The residual sum of squares, never below zero."""
        with _context():
            return max(self.syy - self.sxy * self.sxy / self.sxx, Decimal(0))


@dataclass(frozen=True)
class FTest:
    f: Decimal | None  # None when both sums are zero: no evidence either way
    df1: int
    df2: int
    p: Decimal

    @property
    def rejected(self):
        """Whether the hypothesis of equality is rejected at ``SIGNIFICANCE``."""
        return self.p < SIGNIFICANCE


def _f_test(extra, extra_df, error, error_df):
    with _context():
        if error <= 0:
            if extra <= 0:
                return FTest(f=None, df1=extra_df, df2=error_df, p=Decimal(1))
            return FTest(f=None, df1=extra_df, df2=error_df, p=Decimal(0))
        f = (max(extra, Decimal(0)) / extra_df) / (error / error_df)
        return FTest(f=f, df1=extra_df, df2=error_df, p=f_survival(f, extra_df, error_df))


@dataclass(frozen=True)
class Fit:
    """The mean line of one batch under the model chosen, with what its standard error needs:
    se(x) = s · √(c + (x − center)² / spread)."""

    intercept: Decimal
    slope: Decimal
    c: Decimal
    center: Decimal
    spread: Decimal
    s: Decimal
    df: int

    def mean(self, x):
        with _context():
            return self.intercept + self.slope * x

    def se(self, x):
        with _context():
            return self.s * (self.c + (x - self.center) ** 2 / self.spread).sqrt()


@dataclass(frozen=True)
class Analysis:
    """The model chosen for the batches and each batch's mean line under it."""

    model: str
    lines: tuple  # each batch's own least-squares line, in the order given
    fits: tuple  # each batch's mean line under the model; one for a pooled model
    sse: Decimal
    df: int
    mse: Decimal
    slopes: FTest | None
    intercepts: FTest | None


def analyse(batches):
    """The analysis of the batches, each a list of (months, result) with results at
    ``MIN_TIMES`` or more distinct times."""
    lines = tuple(Line.of(points) for points in batches)
    k = len(lines)
    if k == 0 or any(len({Decimal(x) for x, _ in points}) < MIN_TIMES for points in batches):
        raise ValueError(f"Every batch needs results at {MIN_TIMES} or more times.")
    total = sum(line.n for line in lines)
    with _context():
        sse_full = sum(line.sse for line in lines)
        df_full = total - 2 * k
        if k == 1:
            line = lines[0]
            mse = sse_full / df_full
            fit = Fit(
                intercept=line.intercept,
                slope=line.slope,
                c=Decimal(1) / line.n,
                center=line.mean_x,
                spread=line.sxx,
                s=mse.sqrt(),
                df=df_full,
            )
            return Analysis(Model.SINGLE, lines, (fit,), sse_full, df_full, mse, None, None)
        within_sxx = sum(line.sxx for line in lines)
        within_sxy = sum(line.sxy for line in lines)
        common = within_sxy / within_sxx
        sse_common = max(sum(line.syy for line in lines) - common * within_sxy, Decimal(0))
        df_common = total - k - 1
        slopes = _f_test(sse_common - sse_full, k - 1, sse_full, df_full)
        if slopes.rejected:
            mse = sse_full / df_full
            fits = tuple(
                Fit(
                    intercept=line.intercept,
                    slope=line.slope,
                    c=Decimal(1) / line.n,
                    center=line.mean_x,
                    spread=line.sxx,
                    s=mse.sqrt(),
                    df=df_full,
                )
                for line in lines
            )
            return Analysis(Model.SEPARATE, lines, fits, sse_full, df_full, mse, slopes, None)
        pooled = Line.of([point for points in batches for point in points])
        intercepts = _f_test(pooled.sse - sse_common, k - 1, sse_common, df_common)
        if intercepts.rejected:
            mse = sse_common / df_common
            fits = tuple(
                Fit(
                    intercept=line.mean_y - common * line.mean_x,
                    slope=common,
                    c=Decimal(1) / line.n,
                    center=line.mean_x,
                    spread=within_sxx,
                    s=mse.sqrt(),
                    df=df_common,
                )
                for line in lines
            )
            return Analysis(
                Model.COMMON_SLOPE, lines, fits, sse_common, df_common, mse, slopes, intercepts
            )
        df_pooled = total - 2
        mse = pooled.sse / df_pooled
        fit = Fit(
            intercept=pooled.intercept,
            slope=pooled.slope,
            c=Decimal(1) / pooled.n,
            center=pooled.mean_x,
            spread=pooled.sxx,
            s=mse.sqrt(),
            df=df_pooled,
        )
        return Analysis(Model.POOLED, lines, (fit,), pooled.sse, df_pooled, mse, slopes, intercepts)


# The confidence limit and the shelf life ------------------------------------------------------


def t_factor(direction, df):
    """The t quantile of the confidence limit: one-sided 95 %, or 97.5 % for two-sided limits."""
    probability = CONFIDENCE if direction != Direction.EITHER else (1 + CONFIDENCE) / 2
    return t_quantile(probability, df)


def limits(fit, t, x):
    """(lower, upper) confidence limits of the mean at ``x``."""
    with _context():
        x = Decimal(x)
        mean, half = fit.mean(x), t * fit.se(x)
        return mean - half, mean + half


def _margin(fit, t, criterion, side, x):
    """How far the limit on ``side`` lies inside ``criterion`` at ``x``: concave in ``x``."""
    lower, upper = limits(fit, t, x)
    with _context():
        return lower - criterion if side == "lower" else criterion - upper


def crossing(fit, t, criterion, side, horizon=HORIZON):
    """The earliest time in months, from 0 to ``horizon``, at which the confidence limit on
    ``side`` ("lower" or "upper") meets ``criterion``; 0 when it lies outside at time zero, None
    when it stays inside to the horizon. The margin is concave, so it crosses zero once at most
    after time zero, and bisection finds that time."""
    with _context():
        low, high = Decimal(0), Decimal(horizon)
        if _margin(fit, t, criterion, side, low) <= 0:
            return Decimal(0)
        if _margin(fit, t, criterion, side, high) > 0:
            return None
        while high - low > _TOLERANCE:
            middle = (low + high) / 2
            if _margin(fit, t, criterion, side, middle) > 0:
                low = middle
            else:
                high = middle
        return low


@dataclass(frozen=True)
class Estimate:
    months: Decimal | None  # the earliest crossing of every batch and side; None if none
    crossings: tuple  # per fit: ((side, months or None), ...)
    t: Decimal


def sides(direction, lower, upper):
    """The (side, criterion) pairs the confidence limits are compared with."""
    pairs = []
    if direction in (Direction.DECREASES, Direction.EITHER) and lower is not None:
        pairs.append(("lower", Decimal(lower)))
    if direction in (Direction.INCREASES, Direction.EITHER) and upper is not None:
        pairs.append(("upper", Decimal(upper)))
    return pairs


def estimate(analysis, direction, lower, upper, horizon=HORIZON):
    """The shelf life the analysis supports against the acceptance criterion."""
    pairs = sides(direction, lower, upper)
    if not pairs:
        raise ValueError("The direction chosen has no acceptance criterion to meet.")
    t = t_factor(direction, analysis.df)
    crossings = tuple(
        tuple((side, crossing(fit, t, criterion, side, horizon)) for side, criterion in pairs)
        for fit in analysis.fits
    )
    found = [months for per_fit in crossings for _, months in per_fit if months is not None]
    return Estimate(months=min(found) if found else None, crossings=crossings, t=t)
