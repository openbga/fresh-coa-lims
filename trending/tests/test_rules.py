"""The arithmetic of trend charts: computed limits and the trend rules, in exact Decimal."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from trending.models import Rule
from trending.rules import Judge, baseline, broken, describe, figure_places, rule_problems

D = Decimal
ALL = frozenset(Rule.values)


def values(*items):
    return [D(item) for item in items]


def test_computed_limits_are_mean_and_three_moving_range_sigmas():
    data = values("10.0", "10.2", "9.9", "10.1", "10.0", "9.8", "10.1", "10.3")
    figures = baseline(data, decimals=1)
    # Mean 80.4 / 8 = 10.05; moving ranges 0.2 0.3 0.2 0.1 0.2 0.3 0.2 = 1.5 / 7 = 0.214285...
    # sigma = 0.214285... / 1.128 = 0.189969..., rounded half-up to 3 places.
    assert figures.count == 8
    assert figures.center == D("10.050")
    assert figures.sigma == D("0.190")
    assert figures.lower == D("9.480")
    assert figures.upper == D("10.620")
    assert figures.moving_range == D("0.214")


def test_rounding_is_half_up_to_two_more_places_than_reported():
    assert figure_places(2) == 4
    assert figure_places(7) == 8
    assert figure_places(None) == 6
    figures = baseline(values(*["1.00"] * 7, "1.0004"), decimals=2)
    # Mean 8.0004 / 8 = 1.00005: half-up gives 1.0001 where half-even would give 1.0000.
    assert figures.center == D("1.0001")
    assert figures.sigma == D("0.0001")


def test_too_few_or_unvarying_results_give_no_limits():
    with pytest.raises(ValidationError, match="at least 8"):
        baseline(values("1", "2", "3"), decimals=0)
    with pytest.raises(ValidationError, match="do not vary"):
        baseline(values(*["5.00"] * 9), decimals=2)


JUDGE = Judge(
    rules=ALL,
    lower=D("97"),
    upper=D("103"),
    center=D("100"),
    sigma=D("1"),
    run_length=8,
    trend_length=6,
)


def test_a_result_outside_the_limits_breaks_the_first_rule_and_one_on_the_limit_does_not():
    assert broken(values("103.01"), 0, JUDGE) == ["beyond"]
    assert broken(values("96.9"), 0, JUDGE) == ["beyond"]
    assert broken(values("103"), 0, JUDGE) == []


def test_a_run_counts_results_strictly_on_one_side():
    run = values(*["100.1"] * 8)
    assert "run" in broken(run, 7, JUDGE)
    assert "run" not in broken(run, 6, JUDGE)  # only seven so far
    broken_run = values(*["100.1"] * 3, "100", *["100.1"] * 4)
    assert "run" not in broken(broken_run, 7, JUDGE)  # a result on the center line ends it
    assert "run" in broken(values(*["99.5"] * 9), 8, JUDGE)  # and goes on being flagged


def test_a_trend_needs_each_result_higher_or_each_lower():
    rising = values("99.0", "99.2", "99.4", "99.6", "99.8", "100.0")
    assert broken(rising, 5, JUDGE) == ["trend"]
    flat_step = values("99.0", "99.2", "99.2", "99.6", "99.8", "100.0")
    assert broken(flat_step, 5, JUDGE) == []
    falling = values("100.5", "100.4", "100.3", "100.2", "100.1", "99.95")
    assert "trend" in broken(falling, 5, JUDGE)


def test_two_of_three_beyond_two_sigma_on_the_same_side():
    assert "two_of_three" in broken(values("102.5", "100", "102.2"), 2, JUDGE)
    # On opposite sides it is not a signal.
    assert "two_of_three" not in broken(values("97.5", "100", "102.2"), 2, JUDGE)
    # The result completing the pattern must itself be beyond 2 sigma.
    assert "two_of_three" not in broken(values("102.5", "102.2", "100"), 2, JUDGE)


def test_four_of_five_beyond_one_sigma_on_the_same_side():
    data = values("101.5", "101.2", "100.5", "101.1", "101.3")
    assert "four_of_five" in broken(data, 4, JUDGE)
    assert "four_of_five" not in broken(
        values("101.5", "100.2", "100.5", "101.1", "101.3"), 4, JUDGE
    )


def test_only_the_chosen_rules_are_applied():
    judge = Judge(rules=frozenset({"beyond"}), lower=D("97"), upper=D("103"), center=D("100"))
    assert broken(values(*["100.1"] * 9), 8, judge) == []


def test_rules_that_need_a_center_line_or_sigma_say_so():
    problems = rule_problems(["beyond", "run", "two_of_three"], center=None, sigma=None)
    assert set(problems) == {"center", "sigma"}
    assert rule_problems(["run"], center=D("1"), sigma=None) == {
        "rules": "A result outside the limits is always a rule."
    }
    assert rule_problems(["beyond", "trend"], center=None, sigma=None) == {}


def test_rules_are_described_with_their_lengths():
    assert describe("run", run_length=9) == "9 results in a row on the same side of the center line"
    assert describe("trend", trend_length=7).startswith("7 results in a row each higher")
    assert describe("beyond") == "A result outside the limits"
