"""The statistics of a shelf-life evaluation (stability.regression), checked against published
reference values and independent formulas. No database."""

from decimal import Decimal, localcontext
from fractions import Fraction
from math import comb

import pytest

from stability import regression as r

D = Decimal

# NIST Statistical Reference Datasets, linear least squares, "Norris" (x, y), with the certified
# values (https://www.itl.nist.gov/div898/strd/lls/data/LINKS/DATA/Norris.dat, read 2026-11-19).
NORRIS = [
    ("0.2", "0.1"), ("337.4", "338.8"), ("118.2", "118.1"), ("884.6", "888.0"),
    ("10.1", "9.2"), ("226.5", "228.1"), ("666.3", "668.5"), ("996.3", "998.5"),
    ("448.6", "449.1"), ("777.0", "778.9"), ("558.2", "559.2"), ("0.4", "0.3"),
    ("0.6", "0.1"), ("775.5", "778.1"), ("666.9", "668.8"), ("338.0", "339.3"),
    ("447.5", "448.9"), ("11.6", "10.8"), ("556.0", "557.7"), ("228.1", "228.3"),
    ("995.8", "998.0"), ("887.6", "888.8"), ("120.2", "119.6"), ("0.3", "0.3"),
    ("0.3", "0.6"), ("556.8", "557.6"), ("339.1", "339.3"), ("887.2", "888.0"),
    ("999.0", "998.5"), ("779.0", "778.9"), ("11.1", "10.2"), ("118.3", "117.6"),
    ("229.2", "228.9"), ("669.1", "668.4"), ("448.9", "449.2"), ("0.5", "0.2"),
]  # fmt: skip

# NIST/SEMATECH e-Handbook of Statistical Methods, 1.3.6.7.2 (critical values of Student's t).
T_TABLE = {
    1: ("6.314", "12.706"),
    2: ("2.920", "4.303"),
    3: ("2.353", "3.182"),
    5: ("2.015", "2.571"),
    10: ("1.812", "2.228"),
    20: ("1.725", "2.086"),
    30: ("1.697", "2.042"),
    100: ("1.660", "1.984"),
}

MONTHS = ("0", "3", "6", "9", "12", "18")


def batch(intercept, slope, noise):
    """A synthetic batch: intercept + slope * month + noise, at ``MONTHS``."""
    return [
        (D(m), D(intercept) + D(slope) * D(m) + D(e)) for m, e in zip(MONTHS, noise, strict=True)
    ]


NOISE = (
    ("0.12", "-0.08", "0.05", "-0.10", "0.07", "-0.04"),
    ("-0.05", "0.09", "-0.11", "0.06", "-0.03", "0.08"),
    ("0.02", "-0.06", "0.10", "-0.07", "0.04", "-0.02"),
)


def close(a, b, places=12):
    return abs(D(a) - D(b)) < D(1).scaleb(-places)


def test_least_squares_matches_the_certified_norris_values():
    line = r.Line.of(NORRIS)
    assert close(line.intercept, "-0.262323073774029", 14)
    assert close(line.slope, "1.00211681802045", 13)
    assert close(line.sse, "26.6173985294224", 12)
    (fit,) = r.analyse([NORRIS]).fits
    assert close(fit.s, "0.884796396144373", 14)
    assert close(fit.se(0), "0.232818234301152", 14)  # the standard deviation of B0
    assert close(fit.s / fit.spread.sqrt(), "0.429796848199937E-03", 16)


@pytest.mark.parametrize("df", sorted(T_TABLE))
def test_t_quantiles_match_the_published_table(df):
    one_sided, two_sided = T_TABLE[df]
    assert r.round_half_up(r.t_quantile(D("0.95"), df), 3) == D(one_sided)
    assert r.round_half_up(r.t_quantile(D("0.975"), df), 3) == D(two_sided)
    # A quantile is the inverse of the distribution function.
    assert close(r.t_cdf(r.t_quantile(D("0.95"), df), df), "0.95", 25)


def test_t_approaches_the_normal_quantile():
    # Φ⁻¹(0.95) = 1.6448536...; t with 100000 degrees of freedom is within 1e-5 of it.
    assert abs(r.t_quantile(D("0.95"), 100000) - D("1.6448536269514722")) < D("0.00002")


@pytest.mark.parametrize("a,b", [(1, 1), (2, 3), (5, 4), (1, 7), (6, 6), (12, 3)])
@pytest.mark.parametrize("x", ["0.05", "0.3", "0.5", "0.81", "0.97"])
def test_incomplete_beta_matches_the_binomial_identity(a, b, x):
    """For whole a and b, I_x(a, b) is the binomial tail sum, an exact fraction."""
    fx = Fraction(x)
    n = a + b - 1
    exact = sum(comb(n, j) * fx**j * (1 - fx) ** (n - j) for j in range(a, n + 1))
    with localcontext(prec=60):
        expected = D(exact.numerator) / D(exact.denominator)
    assert close(r.incomplete_beta(2 * a, 2 * b, D(x)), expected, 35)


@pytest.mark.parametrize("n", [1, 3, 8, 30])
@pytest.mark.parametrize("f", ["0.25", "1.4", "6.5"])
def test_f_distribution_matches_closed_forms(n, f):
    f = D(f)
    with localcontext(prec=50):
        # F(2, n) has P(F > f) = (1 + 2f / n)^(-n / 2).
        expected = (1 + 2 * f / n) ** (D(-n) / 2)
        # F(1, n) is the square of t with n degrees of freedom.
        root = f.sqrt()
        two_tailed = 2 * (1 - r.t_cdf(root, n))
    assert close(r.f_survival(f, 2, n), expected, 35)
    assert close(r.f_survival(f, 1, n), two_tailed, 35)


def test_months_are_of_365_25_over_12_days():
    assert r.months(0) == 0
    assert close(r.months(365), "11.99178644763860369609856262833675564681724845996", 40)
    assert close(r.months(1461), 48, 45)


def test_one_batch_is_fitted_with_its_own_error():
    data = batch("100.1", "-0.25", NOISE[0])
    analysis = r.analyse([data])
    assert analysis.model == r.Model.SINGLE
    assert analysis.df == 4 and analysis.slopes is None and analysis.intercepts is None
    line = r.Line.of(data)
    with localcontext(prec=50):
        assert analysis.mse == line.sse / 4


def test_similar_batches_are_pooled():
    batches = [batch("100.0", "-0.25", noise) for noise in NOISE]
    analysis = r.analyse(batches)
    assert analysis.model == r.Model.POOLED
    assert not analysis.slopes.rejected and not analysis.intercepts.rejected
    assert analysis.df == 18 - 2 and len(analysis.fits) == 1
    pooled = r.Line.of([point for points in batches for point in points])
    assert analysis.fits[0].slope == pooled.slope


def test_two_batch_tests_equal_the_square_of_the_t_statistics():
    """With two batches the analysis of covariance tests are t tests squared: of the slopes'
    difference with the full model's error, and of the intercepts' with the common-slope
    model's error."""
    one, two = batch("100.0", "-0.25", NOISE[0]), batch("100.6", "-0.26", NOISE[1])
    analysis = r.analyse([one, two])
    a, b = r.Line.of(one), r.Line.of(two)
    with localcontext(prec=50):
        mse_full = (a.sse + b.sse) / (a.n + b.n - 4)
        t_slopes = (a.slope - b.slope) / (mse_full * (1 / a.sxx + 1 / b.sxx)).sqrt()
        common = (a.sxy + b.sxy) / (a.sxx + b.sxx)
        sse_common = a.syy + b.syy - common * (a.sxy + b.sxy)
        mse_common = sse_common / (a.n + b.n - 3)
        gap = a.mean_y - b.mean_y - common * (a.mean_x - b.mean_x)
        spread = 1 / D(a.n) + 1 / D(b.n) + (a.mean_x - b.mean_x) ** 2 / (a.sxx + b.sxx)
        t_intercepts = gap / (mse_common * spread).sqrt()
        slopes_f, intercepts_f = t_slopes**2, t_intercepts**2
        slopes_p = 2 * (1 - r.t_cdf(abs(t_slopes), 8))
    assert not analysis.slopes.rejected and analysis.intercepts is not None
    assert close(analysis.slopes.f, slopes_f, 30)
    assert (analysis.slopes.df1, analysis.slopes.df2) == (1, 8)
    assert close(analysis.slopes.p, slopes_p, 30)
    assert close(analysis.intercepts.f, intercepts_f, 30)
    assert (analysis.intercepts.df1, analysis.intercepts.df2) == (1, 9)


def test_slopes_that_differ_give_each_batch_its_own_line_with_the_pooled_error():
    batches = [
        batch("100.0", "-0.10", NOISE[0]),
        batch("100.0", "-0.50", NOISE[1]),
        batch("100.0", "-0.30", NOISE[2]),
    ]
    analysis = r.analyse(batches)
    assert analysis.model == r.Model.SEPARATE and analysis.slopes.rejected
    assert analysis.intercepts is None
    lines = [r.Line.of(points) for points in batches]
    with localcontext(prec=50):
        assert analysis.mse == sum(line.sse for line in lines) / (18 - 6)
    for fit, line in zip(analysis.fits, lines, strict=True):
        assert fit.slope == line.slope and fit.spread == line.sxx and fit.df == 12


def test_equal_slopes_and_different_intercepts_give_a_common_slope():
    batches = [
        batch("101.0", "-0.25", NOISE[0]),
        batch("99.0", "-0.25", NOISE[1]),
        batch("100.0", "-0.25", NOISE[2]),
    ]
    analysis = r.analyse(batches)
    assert analysis.model == r.Model.COMMON_SLOPE
    assert not analysis.slopes.rejected and analysis.intercepts.rejected
    assert len({fit.slope for fit in analysis.fits}) == 1
    assert len({fit.intercept for fit in analysis.fits}) == 3
    assert analysis.df == 18 - 3 - 1


def test_a_batch_needs_three_time_points():
    with pytest.raises(ValueError, match="3 or more times"):
        r.analyse([[(D(0), D(100)), (D(3), D(99)), (D(3), D(99.1))]])


def _closed_form(fit, t, criterion):
    """The time at which mean - t·se meets ``criterion``, solving the quadratic for the lower
    limit: an independent check of the bisection."""
    with localcontext(prec=50):
        a, b = fit.intercept + fit.slope * fit.center - criterion, fit.slope
        q = t * t * fit.s * fit.s
        qa = b * b - q / fit.spread
        qb = 2 * a * b
        qc = a * a - q * fit.c
        root = (qb * qb - 4 * qa * qc).sqrt()
        roots = [(-qb - root) / (2 * qa), (-qb + root) / (2 * qa)]
        valid = [u + fit.center for u in roots if a + b * u >= 0 and u + fit.center > 0]
        return min(valid)


def test_the_shelf_life_is_where_the_lower_limit_meets_the_criterion():
    batches = [batch("100.0", "-0.25", noise) for noise in NOISE]
    analysis = r.analyse(batches)
    result = r.estimate(analysis, r.Direction.DECREASES, D("95"), D("105"))
    t = r.t_quantile(D("0.95"), analysis.df)
    assert result.t == t
    (fit,) = analysis.fits
    assert close(result.months, _closed_form(fit, t, D(95)), 9)
    lower, _ = r.limits(fit, t, result.months)
    assert close(lower, 95, 9)
    before, _ = r.limits(fit, t, result.months - D("0.01"))
    assert before > 95
    # The mean line itself meets 95 later than its confidence limit does.
    assert (95 - fit.intercept) / fit.slope > result.months
    assert result.crossings == ((("lower", result.months),),)


def test_an_attribute_that_increases_is_judged_by_its_upper_limit():
    batches = [[(m, 200 - y) for m, y in batch("100.0", "-0.25", noise)] for noise in NOISE]
    rising = r.analyse(batches)
    falling = r.analyse([batch("100.0", "-0.25", noise) for noise in NOISE])
    up = r.estimate(rising, r.Direction.INCREASES, None, D("105"))
    down = r.estimate(falling, r.Direction.DECREASES, D("95"), None)
    assert close(up.months, down.months, 9)
    with pytest.raises(ValueError, match="no acceptance criterion"):
        r.estimate(rising, r.Direction.INCREASES, D("95"), None)


def test_two_sided_limits_use_97_5_percent_and_the_earlier_crossing():
    batches = [batch("100.0", "-0.25", noise) for noise in NOISE]
    analysis = r.analyse(batches)
    either = r.estimate(analysis, r.Direction.EITHER, D("95"), D("105"))
    one_sided = r.estimate(analysis, r.Direction.DECREASES, D("95"), D("105"))
    assert either.t == r.t_quantile(D("0.975"), analysis.df)
    assert either.months < one_sided.months  # a wider limit meets the criterion sooner
    sides = dict(either.crossings[0])
    assert sides["upper"] is None and sides["lower"] == either.months


def test_the_shortest_batch_estimate_applies_when_batches_are_not_pooled():
    batches = [
        batch("100.0", "-0.10", NOISE[0]),
        batch("100.0", "-0.50", NOISE[1]),
        batch("100.0", "-0.30", NOISE[2]),
    ]
    analysis = r.analyse(batches)
    result = r.estimate(analysis, r.Direction.DECREASES, D("95"), None)
    per_batch = [crossings[0][1] for crossings in result.crossings]
    assert result.months == min(per_batch) == per_batch[1]


def test_a_limit_outside_at_time_zero_or_never_reaching_the_criterion():
    analysis = r.analyse([batch("100.0", "-0.25", noise) for noise in NOISE])
    assert r.estimate(analysis, r.Direction.DECREASES, D("100.5"), None).months == 0
    flat = r.analyse([batch("100.0", "0", noise) for noise in NOISE])
    result = r.estimate(flat, r.Direction.DECREASES, D("90"), None)
    assert result.months is None and result.crossings == ((("lower", None),),)
    # Within a shorter horizon the falling batches never meet 95 either.
    assert r.estimate(analysis, r.Direction.DECREASES, D("95"), None, horizon=6).months is None


def test_a_perfect_fit_is_not_divided_by_zero():
    exact = [(D(m), D(100) - D("0.5") * D(m)) for m in MONTHS]
    analysis = r.analyse([exact, exact])
    assert analysis.model == r.Model.POOLED and analysis.mse == 0
    assert analysis.slopes.f is None and analysis.slopes.p == 1
    result = r.estimate(analysis, r.Direction.DECREASES, D("95"), None)
    assert close(result.months, 10, 9)  # the mean line itself: 100 - 0.5 m = 95
