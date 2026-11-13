"""The shared formula contract: exact Decimal arithmetic over named inputs, nothing else."""

from decimal import Decimal

import pytest

from core.formulas import MAX_LENGTH, Formula, FormulaError, calculate, is_name, parse

D = Decimal


def test_parse_reports_the_names_used_and_keeps_the_text_as_approved():
    formula = parse("  (titre - blank) * factor / sample_mass * 100 ")
    assert isinstance(formula, Formula)
    assert formula.expression == "(titre - blank) * factor / sample_mass * 100"
    assert formula.names == {"titre", "blank", "factor", "sample_mass"}


def test_precedence_parentheses_and_unary_signs():
    assert parse("2 + 3 * 4").evaluate({}) == D(14)
    assert parse("(2 + 3) * 4").evaluate({}) == D(20)
    assert parse("10 - 4 - 3").evaluate({}) == D(3)  # left associative
    assert parse("24 / 4 / 2").evaluate({}) == D(3)
    assert parse("-a + 5").evaluate({"a": D(2)}) == D(3)
    assert parse("--a").evaluate({"a": D(2)}) == D(2)
    assert parse("+a * -b").evaluate({"a": D(2), "b": D(3)}) == D(-6)


def test_arithmetic_is_exact_decimal_not_binary_floating_point():
    assert parse("a + b").evaluate({"a": D("0.1"), "b": D("0.2")}) == D("0.3")
    assert parse("0.1 + 0.2").evaluate({}) == D("0.3")
    assert parse("a * 1.10").evaluate({"a": D("3")}) == D("3.30")


def test_calculate_rounds_half_up_to_the_approved_decimals():
    values = {"a": D(2), "b": D(3)}
    assert calculate("a / b", values, 4) == D("0.6667")
    assert str(calculate("a / b", values, 0)) == "1"
    assert calculate("x", {"x": D("2.345")}, 2) == D("2.35")  # half up, not half even
    assert calculate("x", {"x": D("2.335")}, 2) == D("2.34")
    assert calculate("x", {"x": D("-2.345")}, 2) == D("-2.35")
    assert str(calculate("x", {"x": D("5")}, 2)) == "5.00"  # scale is the approved precision


def test_a_worked_assay_calculation():
    # (10.05 - 0.05) mL * 12.21 mg/mL / 250.4 mg * 100 = 48.76198...
    values = {
        "titre": D("10.05"),
        "blank": D("0.05"),
        "factor": D("12.21"),
        "sample_mass": D("250.4"),
    }
    assert calculate("(titre - blank) * factor / sample_mass * 100", values, 2) == D("48.76")


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "a +",
        "* a",
        "a b",
        "(a + b",
        "a + b)",
        "a ** b",
        "a // b",
        "a % b",
        "a ^ 2",
        "1e5",
        "1.",
        ".5",
        "a = 1",
        "a == b",
        "a > b",
        "abs(a)",
        "a.real",
        "a[0]",
        "__import__",
        "A + b",
        "Titre",
        "1,5",
        "a; b",
        "'a'",
        "a\nb",
        "µ",
        "x" * 41,
        "a + " * 200 + "a",
        "(" * 30 + "a" + ")" * 30,
        None,
        5,
    ],
)
def test_anything_outside_the_grammar_is_refused(expression):
    with pytest.raises(FormulaError):
        parse(expression)


def test_length_limit_is_inclusive():
    expression = "a" + " + a" * ((MAX_LENGTH - 1) // 4)
    assert len(expression) <= MAX_LENGTH
    assert parse(expression).names == {"a"}


def test_evaluation_needs_exactly_the_named_inputs():
    formula = parse("a / b")
    with pytest.raises(FormulaError, match="No value for b"):
        formula.evaluate({"a": D(1)})
    with pytest.raises(FormulaError, match="does not use c"):
        formula.evaluate({"a": D(1), "b": D(2), "c": D(3)})


@pytest.mark.parametrize("value", [1, 1.5, "1", None, D("NaN"), D("Infinity")])
def test_values_must_be_finite_decimals(value):
    with pytest.raises(FormulaError, match="finite decimal"):
        parse("a + 1").evaluate({"a": value})


def test_division_by_zero_and_overflow_are_errors_not_results():
    with pytest.raises(FormulaError, match="divides by zero"):
        parse("a / (b - b)").evaluate({"a": D(1), "b": D(2)})
    with pytest.raises(FormulaError, match="divides by zero"):
        parse("a / b").evaluate({"a": D(0), "b": D(0)})
    with pytest.raises(FormulaError, match="no finite result"):
        parse("a * a").evaluate({"a": D("1e999999")})


@pytest.mark.parametrize("decimals", [-1, 9, 2.0, "2", None, True])
def test_decimals_must_be_a_whole_number_from_0_to_8(decimals):
    with pytest.raises(FormulaError, match="decimals"):
        calculate("a", {"a": D(1)}, decimals)


def test_input_names():
    assert is_name("sample_mass") and is_name("v1") and is_name("a")
    for bad in ["", "1a", "_a", "A", "sample-mass", "sample mass", "a" * 41, None, 5]:
        assert not is_name(bad)
