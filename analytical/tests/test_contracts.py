"""Requirement parsing (v1 frozen payloads and v2 shapes) and reading evaluation, no database."""

import copy
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from analytical.contracts import Reading, canonical_hash, parse_requirement
from analytical.fixtures import requirement_payload


def spec(code, **changes):
    payload = requirement_payload(code)
    payload.update(changes)
    return parse_requirement(payload)


def lt(value):
    return Reading(value=Decimal(value), qualifier="<", text=f"<{value}")


def num(value):
    return Reading(value=Decimal(value), text=value)


def outcome(code):
    return Reading(outcome=code)


# v1: frozen payloads keep parsing to the same behaviour --------------------------------------


def test_v1_payload_parses_unchanged():
    payload = requirement_payload("assay")
    frozen = copy.deepcopy(payload)
    parsed = parse_requirement(payload)
    assert payload == frozen  # parsing never rewrites the frozen payload or its hash
    assert canonical_hash(payload) == canonical_hash(frozen)
    assert (parsed.result_type, parsed.lower_inclusive, parsed.upper_inclusive) == (
        "numeric",
        True,
        True,
    )
    assert (parsed.expected_result, parsed.criterion, parsed.outcomes) == ("", "", ())
    assert parsed.acceptance == "95.0 to 105.0 % label claim"
    assert spec("water").acceptance == "at most 0.50 % w/w"
    mean, reportable, text, conforms = parsed.evaluate([Decimal("99.75"), Decimal("99.80")])
    assert (mean, reportable, text, conforms) == (
        Decimal("99.77500000"),
        Decimal("99.8"),
        "99.8",
        True,
    )
    # Inclusive bounds exactly at the limit conform.
    assert parsed.evaluate([Decimal("95.0"), Decimal("95.0")])[3] is True
    assert parsed.evaluate([Decimal("105.0"), Decimal("105.04")])[3] is False  # replicate limit


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"bounds": "exclusive"}, "inclusive"),
        ({"result_type": "qualitative"}, "Only numeric"),
        ({"result_type": "count"}, "Only numeric"),
        ({"lower_inclusive": True}, "keys differ"),
        ({"schema": "oq.test-requirement/3"}, "keys differ"),
        ({"schema": "oq.test-requirement/4"}, "Unsupported"),
    ],
)
def test_v1_unsupported_shapes_still_hold(change, message):
    with pytest.raises(ValidationError, match=message):
        spec("assay", **change)


# v2 acceptance and holds --------------------------------------------------------------------


def test_v2_shapes_parse():
    tamc = spec("tamc")
    assert (tamc.result_type, tamc.unit, tamc.upper, tamc.acceptance) == (
        "count",
        "CFU/g",
        Decimal("1000"),
        "at most 1000 CFU/g",
    )
    impurity = spec("impurity")
    assert (impurity.upper_inclusive, impurity.acceptance) == (False, "less than 0.10 %")
    pathogen = spec("pathogen")
    assert (pathogen.unit, pathogen.lower, pathogen.upper, pathogen.reporting_decimals) == (
        "",
        None,
        None,
        None,
    )
    assert pathogen.acceptance == "Absent in 25 g (expected: Absent)"
    assert pathogen.outcomes == (("absent", "Absent"), ("present", "Present"))
    assert spec("appearance").outcomes == (
        ("conforms", "Conforms"),
        ("does_not_conform", "Does not conform"),
    )
    both = spec("impurity", lower_limit="0.01", lower_inclusive=False, upper_inclusive=True)
    assert both.acceptance == "more than 0.01 and at most 0.10 %"
    equal = spec("tamc", lower_limit="1000")
    assert equal.acceptance == "1000 to 1000 CFU/g"


def without(code, key):
    payload = requirement_payload(code)
    del payload[key]
    return payload


@pytest.mark.parametrize(
    ("code", "change", "message"),
    [
        ("tamc", {"extra": 1}, "keys differ"),
        ("tamc", {"bounds": "inclusive"}, "keys differ"),
        ("tamc", {"result_type": "text"}, "Unsupported result type"),
        ("tamc", {"result_type": ["count"]}, "Unsupported result type"),
        ("tamc", {"unit": ""}, "Unit"),
        ("tamc", {"upper_limit": None}, "at least one limit"),
        ("tamc", {"lower_limit": "2000"}, "exceeds"),
        ("tamc", {"upper_limit": "10.5"}, "whole numbers"),
        ("tamc", {"upper_limit": "-1", "lower_limit": None}, "whole numbers"),
        ("tamc", {"upper_limit": 1000}, "decimal string"),
        ("tamc", {"lower_limit": "1000", "upper_inclusive": False}, "Equal"),
        ("impurity", {"lower_limit": "0.10"}, "Equal"),
        ("impurity", {"expected_result": "absent"}, "no expected result"),
        ("impurity", {"criterion": "Clear"}, "no expected result"),
        ("impurity", {"upper_inclusive": "false"}, "true or false"),
        ("impurity", {"lower_inclusive": None}, "true or false"),
        ("pathogen", {"unit": "CFU"}, "no unit"),
        ("pathogen", {"upper_limit": "0"}, "no numeric limits"),
        ("pathogen", {"lower_inclusive": False}, "no exclusive limits"),
        ("pathogen", {"expected_result": None}, "expected result"),  # legacy qualitative line
        ("pathogen", {"expected_result": "does_not_conform"}, "expected result"),
        ("pathogen", {"expected_result": ["absent"]}, "expected result"),
        ("pathogen", {"reporting_decimals": 0}, "no rounding"),
        ("pathogen", {"replicate_limits": False}, "no rounding"),
        ("pathogen", {"criterion": "  "}, "criterion"),
        ("pathogen", {"criterion": "x" * 161}, "criterion"),
        ("pathogen", {"replicates": 11}, "replicates"),
    ],
)
def test_v2_unsupported_shapes_hold(code, change, message):
    with pytest.raises(ValidationError, match=message):
        spec(code, **change)


def test_v2_missing_key_holds():
    with pytest.raises(ValidationError, match="missing"):
        parse_requirement(without("pathogen", "criterion"))


# Evaluation -----------------------------------------------------------------------------------


def test_exclusive_upper_bound_at_the_limit_with_and_without_rounding():
    impurity = spec("impurity")  # < 0.10 %, rounded to 2 decimals
    assert impurity.evaluate([num("0.10")])[2:] == ("0.10", False)
    assert impurity.evaluate([num("0.09")])[2:] == ("0.09", True)
    # 0.095 rounds half-up to 0.10, which the exclusive limit refuses (raw value is below it).
    assert impurity.evaluate([num("0.095")])[2:] == ("0.10", False)
    assert impurity.evaluate([num("0.0949")])[2:] == ("0.09", True)
    exact = spec("impurity", reporting_decimals=None)
    assert exact.evaluate([num("0.0999")])[2:] == ("0.0999", True)
    assert exact.evaluate([num("0.1")])[2:] == ("0.1", False)


def test_exclusive_lower_bound_at_the_limit_with_rounding():
    loss = spec(
        "impurity",
        lower_limit="5",
        lower_inclusive=False,
        upper_limit="10",
        upper_inclusive=True,
        replicate_limits=False,
    )
    assert loss.acceptance == "more than 5 and at most 10 %"
    assert loss.evaluate([num("5")])[3] is False
    assert loss.evaluate([num("5.004")])[2:] == ("5.00", False)  # rounds onto the bound
    assert loss.evaluate([num("5.005")])[2:] == ("5.01", True)
    assert loss.evaluate([num("10.00")])[3] is True  # inclusive upper


@pytest.mark.parametrize(
    ("code", "reading", "message"),
    [
        ("tamc", num("1.5"), "whole number"),
        ("tamc", num("-1"), "whole number"),
        ("tamc", lt("10.5"), "whole number"),
        ("tamc", lt("0"), "greater than zero"),
        ("impurity", lt("0"), "greater than zero"),
        ("impurity", lt("-0.1"), "greater than zero"),
        ("tamc", Reading(), "Enter the observed value"),
        ("tamc", outcome("absent"), "Enter the observed value"),
        ("tamc", Reading(value=Decimal("1"), qualifier=">"), "qualifier"),
        ("pathogen", Reading(value=Decimal("1"), qualifier="<"), "less than"),
        ("pathogen", outcome("conforms"), "Absent or Present"),
        ("pathogen", Reading(value=Decimal("0")), "Absent or Present"),
        ("pathogen", Reading(value=Decimal("0"), outcome="absent"), "Absent or Present"),
    ],
)
def test_readings_the_requirement_cannot_evaluate_are_refused(code, reading, message):
    requirement = spec(code)
    with pytest.raises(ValidationError, match=message):
        requirement.check_reading(reading)
    with pytest.raises(ValidationError):
        requirement.evaluate([reading] * requirement.replicates)


def test_counts_are_whole_numbers_and_round_like_numeric():
    tamc = spec("tamc")
    assert tamc.evaluate([num("0"), num("1")])[1:] == (Decimal("1"), "1", True)  # 0.5 -> 1
    assert tamc.evaluate([num("1000"), num("1000")])[2:] == ("1000", True)
    assert tamc.evaluate([num("1000"), num("1001")])[2:] == ("1001", False)


def test_less_than_readings_never_become_numbers():
    tamc = spec("tamc")  # at most 1000 CFU/g
    assert tamc.evaluate([lt("10"), lt("10")]) == (None, None, "<10", True)
    assert tamc.evaluate([lt("10"), lt("10.0")]) == (None, None, "<10", True)  # same reading
    # X above the upper limit cannot be shown to conform.
    assert tamc.evaluate([lt("2000"), lt("2000")]) == (None, None, "<2000", False)
    assert tamc.evaluate([lt("1000"), lt("1000")])[3] is True  # X equal to an inclusive limit
    # Mixed replicates: no mean; every replicate judged on its own; readings joined in order.
    assert tamc.evaluate([lt("10"), num("50")]) == (None, None, "<10; 50", True)
    assert tamc.evaluate([num("50"), lt("10")])[2] == "50; <10"
    assert tamc.evaluate([lt("10"), num("2000")]) == (None, None, "<10; 2000", False)
    lenient = spec("tamc", replicate_limits=False)
    assert lenient.evaluate([num("1"), num("1999")])[3] is True  # mean 1000 conforms
    assert lenient.evaluate([lt("10"), num("1999")])[3] is False  # every replicate must conform
    # Equal to an exclusive upper limit: "<0.10" against "< 0.10" conforms.
    assert spec("impurity").evaluate([lt("0.10")]) == (None, None, "<0.10", True)


def test_less_than_against_a_lower_limit_cannot_conform():
    assay = spec("assay")
    assert assay.conforms(lt("10")) is False
    assert assay.evaluate([lt("100"), lt("100")]) == (None, None, "<100", False)
    upper_only = spec("tamc", lower_limit="0")
    assert upper_only.evaluate([lt("10"), lt("10")])[3] is False  # any lower limit


def test_qualitative_replicates():
    pathogen = spec("pathogen")
    absent, present = outcome("absent"), outcome("present")
    assert pathogen.evaluate([absent, absent]) == (None, None, "Absent", True)
    assert pathogen.evaluate([absent, present]) == (None, None, "Present", False)
    assert pathogen.evaluate([present, present]) == (None, None, "Present", False)
    expect_present = spec("pathogen", expected_result="present", criterion="Present (positive)")
    assert expect_present.evaluate([present, present]) == (None, None, "Present", True)
    assert expect_present.evaluate([present, absent]) == (None, None, "Absent", False)
    appearance = spec("appearance")
    assert appearance.evaluate([outcome("conforms")])[2:] == ("Conforms", True)
    assert appearance.evaluate([outcome("does_not_conform")])[2:] == ("Does not conform", False)
    with pytest.raises(ValidationError, match="2 replicate"):
        pathogen.evaluate([absent])
