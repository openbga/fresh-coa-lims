"""Controlled unit vocabulary and exact Decimal helpers.

Units are stored as the exact symbol shown to users. Adding a unit is a code change reviewed with
its consumers; a free-text unit would let two spellings of one unit defeat comparison.
"""

from decimal import ROUND_HALF_UP, Decimal

RESULT_UNITS = [
    ("%", "% (percent)"),
    ("% w/w", "% w/w"),
    ("% w/v", "% w/v"),
    ("% v/v", "% v/v"),
    ("% of label claim", "% of label claim"),
    ("mg/g", "mg/g"),
    ("mg/kg", "mg/kg"),
    ("µg/g", "µg/g"),
    ("µg/kg", "µg/kg"),
    ("ppm", "ppm"),
    ("ppb", "ppb"),
    ("mg/mL", "mg/mL"),
    ("g/mL", "g/mL"),
    ("CFU/g", "CFU/g"),
    ("CFU/mL", "CFU/mL"),
    ("MPN/g", "MPN/g"),
    ("EU/mL", "EU/mL"),
    ("pH", "pH"),
    ("°C", "°C"),
    ("mPa·s", "mPa·s"),
    ("mm", "mm"),
    ("µm", "µm"),
    ("N", "N (newton)"),
    ("min", "min"),
    ("count", "count"),
]

QUANTITY_UNITS = [
    ("mg", "mg"),
    ("g", "g"),
    ("kg", "kg"),
    ("mL", "mL"),
    ("L", "L"),
    ("units", "units (items)"),
]


def plain(value):
    """Exact Decimal as a plain string without exponent or padded scale; None stays None."""
    if value is None:
        return None
    text = format(Decimal(value).normalize(), "f")
    return "0" if text in {"-0", ""} else text


def rounded(value, decimals):
    """Round half up to the stated number of decimals, used only when a test specifies it."""
    if decimals is None:
        return Decimal(value)
    return Decimal(value).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
