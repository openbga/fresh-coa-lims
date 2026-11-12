"""Test-requirement contract consumed from approved specification/method revisions.

settings.ANALYTICAL_REQUIREMENT_PROVIDER names a class with ``requirements(lot)`` returning
``{test_code: payload | None}`` (or raising RequirementHold) and ``methods()`` returning approved
batch-method payloads. There is deliberately no default: without a provider every lot is held.
``analytical.fixtures.FixtureProvider`` is synthetic and only for explicit test overrides.
Tests freeze the validated payload and its hash; later specification revisions never change them.

``oq.test-requirement/1`` (numeric, inclusive limits) is accepted forever because tests froze it.
``oq.test-requirement/2`` adds counts, qualitative results from a controlled outcome pair and
limits that exclude their boundary. Anything this contract cannot represent exactly (unknown or
missing keys, unsupported result types, inconsistent limits or a qualitative line without an
expected result) is a hold, never coerced. Batch QC checks stay numeric with inclusive limits.
"""

import hashlib
import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string

SCHEMA = "oq.test-requirement/1"
SCHEMA_V2 = "oq.test-requirement/2"
REQUIREMENT_KEYS = {
    "schema",
    "source",
    "test_code",
    "name",
    "result_type",
    "bounds",
    "unit",
    "lower_limit",
    "upper_limit",
    "replicates",
    "reporting_decimals",
    "replicate_limits",
    "max_retests",
    "method",
}
REQUIREMENT_KEYS_V2 = (REQUIREMENT_KEYS - {"bounds"}) | {
    "lower_inclusive",
    "upper_inclusive",
    "expected_result",
    "criterion",
}
METHOD_KEYS = {"code", "revision", "requires_batch", "qc_checks"}
QC_KEYS = {"code", "name", "unit", "lower_limit", "upper_limit"}

NUMERIC, COUNT, QUALITATIVE = "numeric", "count", "qualitative"
LESS_THAN = "<"
# Qualitative outcomes: code -> label. Each expected result admits exactly one deviating outcome.
OUTCOMES = {
    "conforms": "Conforms",
    "does_not_conform": "Does not conform",
    "absent": "Absent",
    "present": "Present",
}
OUTCOME_PAIRS = {
    "conforms": ("conforms", "does_not_conform"),
    "absent": ("absent", "present"),
    "present": ("absent", "present"),
}


class RequirementHold(Exception):
    """Raised by a provider when the lot's requirements cannot be resolved."""

    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


MAX_DIGITS = 20
DECIMAL_PLACES = 8


def canonical_hash(payload):
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


def _decimal(value, label, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a decimal string.")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError(f"{label} is not a decimal.") from exc
    if not number.is_finite():
        raise ValidationError(f"{label} must be finite.")
    if -number.as_tuple().exponent > DECIMAL_PLACES or len(number.as_tuple().digits) > MAX_DIGITS:
        raise ValidationError(f"{label} exceeds the supported precision.")
    return number


def _text(data, key, label, max_length=160):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValidationError(f"{label} is required.")
    return value


def _limits(data, label):
    lower = _decimal(data.get("lower_limit"), f"{label} lower limit")
    upper = _decimal(data.get("upper_limit"), f"{label} upper limit")
    if lower is None and upper is None:
        raise ValidationError(f"{label} needs at least one limit.")
    if lower is not None and upper is not None and lower > upper:
        raise ValidationError(f"{label} lower limit exceeds its upper limit.")
    return lower, upper


def within(value, lower, upper, lower_inclusive=True, upper_inclusive=True):
    """True when value lies within the limits, honouring each bound's inclusivity."""
    if lower is not None and (value < lower if lower_inclusive else value <= lower):
        return False
    return upper is None or (value <= upper if upper_inclusive else value < upper)


def plain(value):
    """Exact decimal text without padded scale or exponent, e.g. 99.8 not 99.80000000."""
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", ""} else text


def _whole(value):
    return value >= 0 and value == value.to_integral_value()


@dataclass(frozen=True)
class Reading:
    """One replicate as recorded: a number, a number reported as less than it, or an outcome.

    ``text`` is the reading exactly as recorded ("99.80", "<10", "Conforms"); it never takes part
    in comparisons, so "<10" and "<10.0" are the same reading.
    """

    value: Decimal | None = None
    qualifier: str = ""
    outcome: str = ""
    text: str = field(default="", compare=False)

    def __str__(self):
        if self.text:
            return self.text
        if self.outcome:
            return OUTCOMES.get(self.outcome, self.outcome)
        return f"{self.qualifier}{self.value}"


def _as_reading(value):
    return value if isinstance(value, Reading) else Reading(value=value)


@dataclass(frozen=True)
class QCCheck:
    code: str
    name: str
    unit: str
    lower: Decimal | None
    upper: Decimal | None

    def conforms(self, value):
        return within(value, self.lower, self.upper)


@dataclass(frozen=True)
class Method:
    code: str
    revision: int
    requires_batch: bool
    qc_checks: tuple

    def check(self, code):
        for check in self.qc_checks:
            if check.code == code:
                return check
        raise ValidationError("This QC check is not defined by the batch method revision.")


@dataclass(frozen=True)
class Requirement:
    source: str
    test_code: str
    name: str
    unit: str
    lower: Decimal | None
    upper: Decimal | None
    replicates: int
    reporting_decimals: int | None
    replicate_limits: bool
    max_retests: int
    method: Method
    result_type: str = NUMERIC
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    expected_result: str = ""  # qualitative only: conforms, absent or present
    criterion: str = ""  # qualitative only: the approved criterion wording

    @property
    def is_qualitative(self):
        return self.result_type == QUALITATIVE

    @property
    def outcomes(self):
        """The controlled (code, label) pair a qualitative reading is chosen from."""
        pair = OUTCOME_PAIRS.get(self.expected_result, ()) if self.is_qualitative else ()
        return tuple((code, OUTCOMES[code]) for code in pair)

    @property
    def expected_label(self):
        return OUTCOMES.get(self.expected_result, "")

    @property
    def acceptance(self):
        """Human-readable acceptance criterion, e.g. "95.0 to 105.0 %" or "less than 10 CFU/g"."""
        if self.is_qualitative:
            return f"{self.criterion} (expected: {self.expected_label})"
        lower, upper = self.lower, self.upper
        inclusive = self.lower_inclusive and self.upper_inclusive
        if lower is not None and upper is not None and inclusive:
            return f"{lower} to {upper} {self.unit}"
        parts = []
        if lower is not None:
            parts.append(f"{'at least' if self.lower_inclusive else 'more than'} {lower}")
        if upper is not None:
            parts.append(f"{'at most' if self.upper_inclusive else 'less than'} {upper}")
        return f"{' and '.join(parts)} {self.unit}"

    def format_value(self, value):
        """A reportable value at the approved reporting precision (exact when there is none)."""
        if self.reporting_decimals is None:
            return plain(value)
        return str(value.quantize(Decimal(1).scaleb(-self.reporting_decimals)))

    def check_reading(self, reading):
        """Refuse a reading this requirement cannot evaluate exactly."""
        reading = _as_reading(reading)
        if self.is_qualitative:
            if reading.qualifier:
                raise ValidationError(
                    "A qualitative result cannot be reported as less than a value."
                )
            if reading.value is not None or reading.outcome not in dict(self.outcomes):
                choices = " or ".join(label for _, label in self.outcomes)
                raise ValidationError(f"Choose the observed result: {choices}.")
            return
        if reading.outcome or reading.value is None:
            raise ValidationError("Enter the observed value.")
        if reading.qualifier not in {"", LESS_THAN}:
            raise ValidationError("Unsupported result qualifier.")
        if not reading.value.is_finite():
            raise ValidationError("The observed value must be finite.")
        if reading.qualifier == LESS_THAN and reading.value <= 0:
            raise ValidationError("A less-than result needs a value greater than zero.")
        if self.result_type == COUNT and not _whole(reading.value):
            raise ValidationError("A count must be a whole number of zero or more.")

    def conforms(self, reading):
        """Whether one reading meets the acceptance criterion on its own.

        A less-than reading "<X" conforms only when there is no lower limit and X is within the
        upper limit; otherwise it cannot be shown to conform and is treated as not conforming.
        """
        reading = _as_reading(reading)
        if self.is_qualitative:
            return reading.outcome == self.expected_result
        if reading.qualifier == LESS_THAN:
            return self.lower is None and self.upper is not None and reading.value <= self.upper
        return within(
            reading.value, self.lower, self.upper, self.lower_inclusive, self.upper_inclusive
        )

    def evaluate(self, readings):
        """Return (mean, reportable value, reportable text, conforms) for the current replicates.

        Numeric and count: with an approved reporting precision the mean is rounded half-up to it
        before comparison. Without one (null) the exact mean is compared; a mean that cannot be
        represented exactly in 8 decimal places is refused rather than silently rounded.
        If any replicate is a less-than reading there is no mean and no reportable value: the test
        conforms only if every replicate conforms on its own. Qualitative: no mean; conforms only
        if every replicate shows the expected outcome.
        """
        readings = [_as_reading(r) for r in readings]
        if len(readings) != self.replicates:
            raise ValidationError(f"{self.replicates} replicate value(s) are required.")
        for reading in readings:
            self.check_reading(reading)
        if self.is_qualitative:
            conforms = all(r.outcome == self.expected_result for r in readings)
            if conforms:
                return None, None, self.expected_label, True
            deviating = next(code for code, _ in self.outcomes if code != self.expected_result)
            return None, None, OUTCOMES[deviating], False
        if any(r.qualifier == LESS_THAN for r in readings):
            conforms = all(self.conforms(r) for r in readings)
            first = readings[0]
            if all(r == first for r in readings):
                text = str(first)
            else:
                text = "; ".join(str(r) for r in readings)
            return None, None, text, conforms
        values = [r.value for r in readings]
        total = sum(values, Decimal(0))
        mean = total / len(values)
        if self.reporting_decimals is None:
            if mean * len(values) != total or -mean.as_tuple().exponent > DECIMAL_PLACES:
                raise ValidationError(
                    "The mean is not exact; an approved reporting precision is required."
                )
            reportable = mean
        else:
            reportable = mean.quantize(Decimal(1).scaleb(-self.reporting_decimals), ROUND_HALF_UP)
        conforms = self.conforms(reportable) and (
            not self.replicate_limits or all(self.conforms(v) for v in values)
        )
        stored_mean = mean.quantize(Decimal(1).scaleb(-DECIMAL_PLACES), ROUND_HALF_UP)
        return stored_mean, reportable, self.format_value(reportable), conforms


def _exact_keys(data, keys, label):
    if set(data) != keys:
        unknown = sorted(set(data) - keys)
        missing = sorted(keys - set(data))
        raise ValidationError(f"{label} keys differ (unknown {unknown}, missing {missing}).")


def parse_method(data):
    if not isinstance(data, dict):
        raise ValidationError("Method snapshot is missing.")
    _exact_keys(data, METHOD_KEYS, "Method")
    revision = data.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValidationError("Method revision must be a positive integer.")
    checks = data.get("qc_checks", [])
    if not isinstance(checks, list) or not isinstance(data.get("requires_batch"), bool):
        raise ValidationError("Method QC definition is invalid.")
    parsed = []
    for item in checks:
        if not isinstance(item, dict):
            raise ValidationError("QC check definition is invalid.")
        _exact_keys(item, QC_KEYS, "QC check")
        code = _text(item, "code", "QC check code", 40)
        lower, upper = _limits(item, f"QC check {code}")
        parsed.append(
            QCCheck(
                code,
                _text(item, "name", "QC check name"),
                _text(item, "unit", "Unit", 40),
                lower,
                upper,
            )
        )
    if len({c.code for c in parsed}) != len(parsed):
        raise ValidationError("QC check codes must be unique.")
    if data["requires_batch"] and not parsed:
        raise ValidationError("A batch method needs at least one QC check.")
    return Method(
        _text(data, "code", "Method code", 80), revision, data["requires_batch"], tuple(parsed)
    )


def _bool(data, key):
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValidationError(f"{key} must be true or false.")
    return value


def _shape_v1(data):
    _exact_keys(data, REQUIREMENT_KEYS, "Requirement")
    if data["result_type"] != NUMERIC:
        raise ValidationError("Only numeric results are supported by this testing contract.")
    if data["bounds"] != "inclusive":
        raise ValidationError("Only inclusive specification limits are supported.")
    lower, upper = _limits(data, "Specification")
    return {"result_type": NUMERIC, "lower": lower, "upper": upper}


def _shape_v2(data):
    _exact_keys(data, REQUIREMENT_KEYS_V2, "Requirement")
    result_type = data["result_type"]
    lower_inclusive = _bool(data, "lower_inclusive")
    upper_inclusive = _bool(data, "upper_inclusive")
    expected, criterion = data["expected_result"], data["criterion"]
    if result_type in (NUMERIC, COUNT):
        lower, upper = _limits(data, "Specification")
        if lower is not None and lower == upper and not (lower_inclusive and upper_inclusive):
            raise ValidationError("Equal specification limits must both be inclusive.")
        if result_type == COUNT and any(
            limit is not None and not _whole(limit) for limit in (lower, upper)
        ):
            raise ValidationError("Count limits must be whole numbers of zero or more.")
        if expected is not None or criterion != "":
            raise ValidationError(
                "A numeric or count requirement has no expected result or criterion."
            )
    elif result_type == QUALITATIVE:
        if data["unit"] != "":
            raise ValidationError("A qualitative requirement has no unit.")
        if data["lower_limit"] is not None or data["upper_limit"] is not None:
            raise ValidationError("A qualitative requirement has no numeric limits.")
        if not (lower_inclusive and upper_inclusive):
            raise ValidationError("A qualitative requirement has no exclusive limits.")
        if not isinstance(expected, str) or expected not in OUTCOME_PAIRS:
            raise ValidationError("A qualitative requirement needs an approved expected result.")
        if data["reporting_decimals"] is not None or data["replicate_limits"] is not True:
            raise ValidationError(
                "A qualitative requirement has no rounding and judges every replicate."
            )
        lower = upper = None
        criterion = _text(data, "criterion", "Acceptance criterion")
    else:
        raise ValidationError("Unsupported result type.")
    return {
        "result_type": result_type,
        "lower": lower,
        "upper": upper,
        "lower_inclusive": lower_inclusive,
        "upper_inclusive": upper_inclusive,
        "expected_result": expected or "",
        "criterion": criterion,
    }


def parse_requirement(data):
    schema = data.get("schema") if isinstance(data, dict) else None
    if schema == SCHEMA:
        shape = _shape_v1(data)
    elif schema == SCHEMA_V2:
        shape = _shape_v2(data)
    else:
        raise ValidationError("Unsupported test-requirement payload.")
    integers = {}
    for key, low, high in [
        ("replicates", 1, 10),
        ("reporting_decimals", 0, 8),
        ("max_retests", 0, 3),
    ]:
        value = data.get(key)
        if key == "reporting_decimals" and value is None:
            integers[key] = None  # approved "no rounding": compare the exact value
            continue
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise ValidationError(f"{key} must be an integer from {low} to {high}.")
        integers[key] = value
    replicate_limits = _bool(data, "replicate_limits")
    unit = "" if shape["result_type"] == QUALITATIVE else _text(data, "unit", "Unit", 40)
    return Requirement(
        source=_text(data, "source", "Specification source", 160),
        test_code=_text(data, "test_code", "Test code", 80),
        name=_text(data, "name", "Test name"),
        unit=unit,
        replicate_limits=replicate_limits,
        method=parse_method(data.get("method")),
        **shape,
        **integers,
    )


def provider():
    path = getattr(settings, "ANALYTICAL_REQUIREMENT_PROVIDER", "")
    if not path:
        raise ImproperlyConfigured("No approved test-requirement provider is configured.")
    return import_string(path)()


def resolve(lot):
    """Return ({test_code: payload}, hold reasons). Missing or unsupported requirements hold."""
    try:
        raw = provider().requirements(lot)
    except ImproperlyConfigured as exc:
        return {}, [str(exc)]
    except RequirementHold as hold:
        return {}, hold.reasons
    accepted, reasons = {}, []
    for code, payload in raw.items():
        if payload is None:
            reasons.append(f"No approved specification is available for {code}.")
            continue
        try:
            spec = parse_requirement(payload)
        except ValidationError as exc:
            reasons.append(f"Requirement for {code} is held: {' '.join(exc.messages)}")
            continue
        if spec.test_code != code:
            reasons.append(f"Requirement for {code} is held: test code mismatch.")
            continue
        accepted[code] = payload
    return accepted, reasons


def batch_methods():
    """Approved batch-method payloads by code; invalid or unavailable methods are omitted."""
    try:
        methods = provider().methods()
    except ImproperlyConfigured:
        return {}
    accepted = {}
    for payload in methods:
        try:
            method = parse_method(payload)
        except ValidationError:
            continue
        if method.requires_batch:
            accepted[method.code] = payload
    return accepted


def check_eligibility(*, actor, test):
    """Return JSON evidence that the actor may record observations for the test's method.

    settings.ANALYTICAL_ELIGIBILITY_CHECK names a callable(*, actor, test) that returns evidence or
    raises ValidationError. There is no default: without a configured check, observations hold.
    """
    path = getattr(settings, "ANALYTICAL_ELIGIBILITY_CHECK", "")
    if not path:
        raise ValidationError("No analyst eligibility check is configured; observations are held.")
    evidence = import_string(path)(actor=actor, test=test)
    if not isinstance(evidence, dict):
        raise ValidationError("Analyst eligibility evidence is missing.")
    json.dumps(evidence)  # must be storable as frozen evidence
    return evidence
