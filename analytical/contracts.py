"""Test-requirement contract consumed from approved specification/method revisions.

settings.ANALYTICAL_REQUIREMENT_PROVIDER names a class with ``requirements(lot)`` returning
``{test_code: payload | None}`` (or raising RequirementHold) and ``methods()`` returning approved
batch-method payloads. There is deliberately no default: without a provider every lot is held.
``analytical.fixtures.FixtureProvider`` is synthetic and only for explicit test overrides.
Tests freeze the validated payload and its hash; later specification revisions never change them.
Anything this contract cannot represent exactly (qualitative results, exclusive bounds, unknown
keys) is a hold, never coerced.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string

SCHEMA = "oq.test-requirement/1"
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
METHOD_KEYS = {"code", "revision", "requires_batch", "qc_checks"}
QC_KEYS = {"code", "name", "unit", "lower_limit", "upper_limit"}


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


def within(value, lower, upper):
    return (lower is None or value >= lower) and (upper is None or value <= upper)


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

    def conforms(self, value):
        return within(value, self.lower, self.upper)

    def evaluate(self, values):
        """Exact mean, reportable value and conformance.

        With an approved reporting precision the mean is rounded half-up to it before comparison.
        Without one (null) the exact mean is compared; a mean that cannot be represented exactly
        in 8 decimal places is refused rather than silently rounded.
        """
        if len(values) != self.replicates:
            raise ValidationError(f"{self.replicates} replicate value(s) are required.")
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
        return stored_mean, reportable, conforms


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


def parse_requirement(data):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValidationError("Unsupported test-requirement payload.")
    _exact_keys(data, REQUIREMENT_KEYS, "Requirement")
    if data["result_type"] != "numeric":
        raise ValidationError("Only numeric results are supported by this testing contract.")
    if data["bounds"] != "inclusive":
        raise ValidationError("Only inclusive specification limits are supported.")
    lower, upper = _limits(data, "Specification")
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
    if not isinstance(data.get("replicate_limits"), bool):
        raise ValidationError("replicate_limits must be true or false.")
    return Requirement(
        source=_text(data, "source", "Specification source", 160),
        test_code=_text(data, "test_code", "Test code", 80),
        name=_text(data, "name", "Test name"),
        unit=_text(data, "unit", "Unit", 40),
        lower=lower,
        upper=upper,
        replicate_limits=data["replicate_limits"],
        method=parse_method(data.get("method")),
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
