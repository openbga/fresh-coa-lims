"""Arithmetic formulas for calculated results: one approved expression over named inputs.

Shared by the catalog, which validates a formula before a method version is approved, and by
testing, which evaluates the frozen formula for each observation and again at review.

Grammar (no functions, exponents, comparisons or assignments; nothing is ever passed to
``eval``)::

    expression := term (("+" | "-") term)*
    term       := factor (("*" | "/") factor)*
    factor     := ("-" | "+") factor | number | name | "(" expression ")"
    number     := digits ["." digits]
    name       := a lower-case letter, then lower-case letters, digits or underscores (40 at most)

Values are exact ``Decimal`` numbers. Arithmetic carries 50 significant digits, so a division that
does not terminate is carried to 50 digits before ``calculate`` rounds the result half-up to the
approved number of decimals. Any input the formula does not name, any missing input, a division
by zero and a non-finite value are errors, never a guessed result.
"""

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Context, Decimal, DivisionByZero, InvalidOperation, Overflow

MAX_LENGTH = 500
MAX_DEPTH = 20
MAX_DECIMALS = 8
PRECISION = 50
NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")
_TOKEN = re.compile(r"\s*(?:(?P<number>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>.))")
_OPERATORS = {"+", "-", "*", "/"}


class FormulaError(ValueError):
    """The expression cannot be parsed, or cannot be evaluated with the values given."""


def is_name(text):
    """Whether ``text`` is a valid input name (the code an approved input is referred to by)."""
    return isinstance(text, str) and NAME.fullmatch(text) is not None


def _tokens(expression):
    tokens, position = [], 0
    text = expression.rstrip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        position = match.end()
        if match["number"] is not None:
            if len(match["number"]) > 40:
                raise FormulaError("A number in the formula is too long.")
            tokens.append(("number", Decimal(match["number"])))
        elif match["name"] is not None:
            if not is_name(match["name"]):
                raise FormulaError(
                    f"“{match['name']}” is not a valid input name: use a lower-case letter "
                    "followed by lower-case letters, digits or underscores (40 at most)."
                )
            tokens.append(("name", match["name"]))
        elif match["op"] in _OPERATORS or match["op"] in "()":
            tokens.append(("op", match["op"]))
        else:
            raise FormulaError(f"“{match['op']}” is not allowed in a formula.")
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0
        self.names = set()

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.position += 1
        return token

    def expression(self, depth):
        node = self.term(depth)
        while self.peek() in (("op", "+"), ("op", "-")):
            operator = self.take()[1]
            node = (operator, node, self.term(depth))
        return node

    def term(self, depth):
        node = self.factor(depth)
        while self.peek() in (("op", "*"), ("op", "/")):
            operator = self.take()[1]
            node = (operator, node, self.factor(depth))
        return node

    def factor(self, depth):
        if depth > MAX_DEPTH:
            raise FormulaError("The formula is nested too deeply.")
        kind, value = self.take()
        if kind == "number":
            return ("number", value)
        if kind == "name":
            self.names.add(value)
            return ("name", value)
        if (kind, value) in (("op", "-"), ("op", "+")):
            operand = self.factor(depth + 1)
            return ("negate", operand) if value == "-" else operand
        if (kind, value) == ("op", "("):
            node = self.expression(depth + 1)
            if self.take() != ("op", ")"):
                raise FormulaError("A closing parenthesis is missing.")
            return node
        if kind is None:
            raise FormulaError("The formula is incomplete.")
        raise FormulaError(f"Unexpected “{value}” in the formula.")


def _context():
    return Context(prec=PRECISION, traps=[InvalidOperation, DivisionByZero, Overflow])


def _evaluate(node, values, context):
    kind = node[0]
    if kind == "number":
        return node[1]
    if kind == "name":
        return values[node[1]]
    if kind == "negate":
        return context.minus(_evaluate(node[1], values, context))
    left = _evaluate(node[1], values, context)
    right = _evaluate(node[2], values, context)
    if kind == "+":
        return context.add(left, right)
    if kind == "-":
        return context.subtract(left, right)
    if kind == "*":
        return context.multiply(left, right)
    if right == 0:  # 0 / 0 is otherwise reported as an invalid operation, not a division by zero
        raise DivisionByZero
    return context.divide(left, right)


@dataclass(frozen=True)
class Formula:
    """A parsed formula: its text as approved and the input names it uses."""

    expression: str
    names: frozenset
    tree: tuple = field(repr=False, compare=False)

    def evaluate(self, values):
        """The exact result for ``values`` (name -> Decimal), carried to 50 significant digits.

        ``values`` must hold exactly the names the formula uses, each a finite Decimal.
        """
        given = set(values)
        if missing := sorted(self.names - given):
            raise FormulaError(f"No value for {', '.join(missing)}.")
        if unknown := sorted(given - self.names):
            raise FormulaError(f"The formula does not use {', '.join(unknown)}.")
        for name, value in values.items():
            if not isinstance(value, Decimal) or not value.is_finite():
                raise FormulaError(f"The value for {name} must be a finite decimal number.")
        try:
            result = _evaluate(self.tree, values, _context())
        except DivisionByZero as exc:
            raise FormulaError("The formula divides by zero for these values.") from exc
        except (InvalidOperation, Overflow) as exc:
            raise FormulaError("The formula has no finite result for these values.") from exc
        if not result.is_finite():
            raise FormulaError("The formula has no finite result for these values.")
        return result


def parse(expression):
    """Parse an expression; raise FormulaError when it is not a formula of this grammar."""
    if not isinstance(expression, str) or not expression.strip():
        raise FormulaError("Enter a formula.")
    expression = expression.strip()
    if len(expression) > MAX_LENGTH:
        raise FormulaError(f"A formula has at most {MAX_LENGTH} characters.")
    parser = _Parser(_tokens(expression))
    tree = parser.expression(0)
    kind, value = parser.peek()
    if kind is not None:
        raise FormulaError(f"Unexpected “{value}” in the formula.")
    return Formula(expression=expression, names=frozenset(parser.names), tree=tree)


def calculate(expression, values, decimals):
    """Evaluate ``expression`` and round the result half-up to ``decimals`` (0 to 8) places."""
    if not isinstance(decimals, int) or isinstance(decimals, bool):
        raise FormulaError("The number of decimals must be a whole number from 0 to 8.")
    if not 0 <= decimals <= MAX_DECIMALS:
        raise FormulaError("The number of decimals must be a whole number from 0 to 8.")
    result = parse(expression).evaluate(values)
    try:
        return result.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise FormulaError("The calculated result is too large to record.") from exc
