"""Each result of a lot judged against every specification that applies to it, and the
certificate of one scope of the lot.

A lot assigned under several scopes is tested against one requirement per test: the statement
its specifications share or, where they state the test differently, the one quality chose with
a signature. A certificate also states how each reportable result compares with the statement
of every other specification of the lot that states the test, and a certificate issued for one
scope (a customer or a market) reports the tests that scope's specification states, with its
limits, and is refused unless each result meets them.

Everything is read from frozen records: the requirement payload the release signed (verified by
the caller), the approved content of each specification version it names (immutable, and
checked here against the hash frozen with it), the current readings of each reviewed test and
the stated result of each accepted supplier result. A result is judged exactly as testing judges
it: ``Requirement.evaluate`` on the readings for the laboratory's results (replicates, rounding
half-up to the statement's reporting precision, inclusive or exclusive limits, less-than and
qualitative readings), and ``Requirement.conforms`` on the stated value, exact and unrounded,
for a supplier's. Nothing is converted: a statement in another unit, of another result type,
with another number of replicates or, for the laboratory's results, of another method is not
judged, and says why.
"""

from functools import partial

from django.apps import apps
from django.core.exceptions import ValidationError

CONFORMS = "conforms"
FAILS = "does_not_conform"
NOT_JUDGED = "not_judged"
INFORMATION = "information"
NOT_TESTED = "not_tested"

OUTCOME_LABELS = {
    CONFORMS: "Conforms",
    FAILS: "Does not conform",
    NOT_JUDGED: "Not judged",
    INFORMATION: "For information",
    NOT_TESTED: "Not tested",
}
OUTCOME_TONES = {
    CONFORMS: "success",
    FAILS: "danger",
    NOT_JUDGED: "warning",
    INFORMATION: "neutral",
    NOT_TESTED: "warning",
}
RESULT_TYPES = {"numeric": "a number", "count": "a count", "qualitative": "an outcome"}
DECISION_RULE = (
    "Each result is compared with the limits of the specification as stated: the mean of the "
    "replicates is rounded half-up to the reporting precision the specification states (and "
    "compared exactly when it states none), each replicate is also compared where the "
    "specification judges replicates, a result recorded as less than a value conforms only to "
    "an upper limit it does not exceed, and a supplier's result is compared exactly as stated. "
    "Measurement uncertainty is not taken into account: the acceptance limit is the "
    "specification's limit (simple acceptance, no guard band)."
)


def _label(spec):
    return f"{spec['code']} version {spec['version']}"


def _approved_lines(specifications):
    """{revision id: {test code: approved line}} for each specification version frozen in the
    payload, or None for a version whose approved content does not digest to the hash frozen
    with it (then nothing is judged against it)."""
    from catalog.services import digest

    revision = apps.get_model("catalog", "SpecificationRevision")
    rows = {
        row["pk"]: row
        for row in revision.objects.filter(
            pk__in=[spec["revision_id"] for spec in specifications]
        ).values("pk", "approved_content", "approved_hash")
    }
    lines = {}
    for spec in specifications:
        row = rows.get(spec["revision_id"])
        content = row and row["approved_content"]
        if (
            not content
            or row["approved_hash"] != spec["approved_hash"]
            or digest(content) != spec["approved_hash"]
        ):
            lines[spec["revision_id"]] = None
            continue
        lines[spec["revision_id"]] = {line["code"]: line for line in content["tests"]}
    return lines


def _requirement(line, frozen, spec, *, any_method=False):
    """(the analytical requirement of a statement, "") or (None, why it cannot be judged).

    The method version is the one frozen for the lot's test: every specification read at the
    same moment named the version then in force of the same method."""
    from analytical.contracts import RequirementHold, parse_requirement
    from catalog.services import LINE_DEFAULTS, test_requirement

    method = frozen["method"]
    if not any_method and line["method"] != method["code"]:
        return None, (
            f"it states method {line['method']}; the result was obtained with method "
            f"{method['code']} version {method['version']}"
        )
    source = f"catalog:{spec['code']}@v{spec['version']}#rev{spec['revision_id']}"
    try:
        payload = test_requirement({**LINE_DEFAULTS, **line, "method": method}, source)
        return parse_requirement(payload), ""
    except KeyError, TypeError, RequirementHold, ValidationError:
        return None, "its statement is in a form that cannot be evaluated"


def _kind_mismatch(line, frozen):
    """Why a statement cannot be compared with a result of the lot's requirement, or ""."""
    if line["result_type"] != frozen["result_type"]:
        return (
            f"it states the result as {RESULT_TYPES.get(line['result_type'], 'another type')}; "
            f"the result is {RESULT_TYPES.get(frozen['result_type'], 'another type')}"
        )
    if line["result_type"] != "qualitative" and (line["unit"] or "") != (frozen["unit"] or ""):
        return (
            f"it states the result in {line['unit'] or 'no unit'}; the result is in "
            f"{frozen['unit'] or 'no unit'}"
        )
    return ""


def _statement(spec, line, applied):
    from catalog.services import LINE_DEFAULTS, describe_limits

    full = {**LINE_DEFAULTS, **line}
    text = describe_limits(full)
    if full["result_type"] != "qualitative" and full["reporting_decimals"] is not None:
        text += f" · rounded to {full['reporting_decimals']} decimals"
    return {
        "scope": spec["scope"],
        "specification": _label(spec),
        "revision_id": spec["revision_id"],
        "applied": applied,
        "required": bool(line.get("required", True)),
        "requirement": text,
    }


def _with_unit(text, unit):
    return f"{text} {unit}" if text and unit else text


def _judge_test(test, frozen, statement, line, spec, applied):
    """A laboratory result judged against one statement."""
    if not statement["required"]:
        result = _with_unit(test.reportable_display, frozen["unit"])
        return {**statement, "result": result, "outcome": INFORMATION, "reason": ""}
    readings = [o.reading for o in test.current_observations()]
    if applied:
        requirement, reason = test.spec, ""
    else:
        requirement, reason = None, _kind_mismatch(line, frozen)
        stated = line.get("replicates", 1)
        if not reason and stated != len(readings):
            reason = (
                f"it states {stated} replicate{'' if stated == 1 else 's'}; "
                f"{len(readings)} {'was' if len(readings) == 1 else 'were'} recorded"
            )
        if not reason:
            requirement, reason = _requirement(line, frozen, spec)
    if requirement is not None:
        try:
            _, _, text, conforms = requirement.evaluate(readings)
        except ValidationError as exc:
            reason = " ".join(exc.messages).rstrip(".")
        else:
            return {
                **statement,
                "result": _with_unit(text, requirement.unit),
                "outcome": CONFORMS if conforms else FAILS,
                "reason": "",
            }
    return {
        **statement,
        "result": _with_unit(test.reportable_display, frozen["unit"]),
        "outcome": NOT_JUDGED,
        "reason": reason,
    }


def _judge_stated(stated, frozen, statement, line, spec, applied):
    """A supplier's stated result judged against one statement, exactly as stated."""
    from analytical.contracts import Reading

    result = _with_unit(stated.value_text, frozen["unit"])
    if not statement["required"]:
        return {**statement, "result": result, "outcome": INFORMATION, "reason": ""}
    if applied:
        # Compared when it was recorded, against the requirement its acceptance relied on.
        return {
            **statement,
            "result": result,
            "outcome": CONFORMS if stated.conforms else FAILS,
            "reason": "",
        }
    reason = _kind_mismatch(line, frozen)
    if not reason:
        requirement, reason = _requirement(line, frozen, spec, any_method=True)
        if requirement is not None:
            reading = Reading(
                value=stated.value, qualifier=stated.qualifier, outcome=stated.outcome
            )
            try:
                requirement.check_reading(reading)
            except ValidationError as exc:
                reason = " ".join(exc.messages).rstrip(".")
            else:
                outcome = CONFORMS if requirement.conforms(reading) else FAILS
                return {**statement, "result": result, "outcome": outcome, "reason": ""}
    return {**statement, "result": result, "outcome": NOT_JUDGED, "reason": reason}


def _untested(statement, line, spec, applied):
    """A statement of a test the lot has no result for."""
    if not statement["required"]:
        return {**statement, "result": "", "outcome": INFORMATION, "reason": ""}
    return {
        **statement,
        "result": "",
        "outcome": NOT_TESTED,
        "reason": "the requirement applied to this lot states it for information only",
    }


def judge(payload, analytical):
    """The conformity of each reportable result with every specification of a lot assigned
    under several of them, from its frozen requirement payload (``oq.requirements/2``) and the
    analytical evidence its release froze. One row per reportable laboratory result and per
    accepted supplier result, and one per test a specification requires that the lot has no
    result for, each with a statement for every specification that states the test."""
    specifications = list(payload["specifications"])
    approved = _approved_lines(specifications)
    frozen = {line["code"]: line for line in payload["tests"]}
    test_model = apps.get_model("analytical", "AnalyticalTest")
    acceptance_model = apps.get_model("quality", "SupplierResultAcceptance")
    results = analytical.get("results") or []
    supplier = analytical.get("supplier_results") or []
    tests = test_model.objects.in_bulk([r["test"] for r in results])
    acceptances = acceptance_model.objects.select_related("result").in_bulk(
        [s["acceptance"] for s in supplier]
    )

    def statements(code, judge_one):
        line_frozen = frozen.get(code)
        sources = set((line_frozen or {}).get("sources") or [])
        found = []
        for spec in specifications:
            lines = approved[spec["revision_id"]]
            if lines is None:
                found.append(
                    {
                        "scope": spec["scope"],
                        "specification": _label(spec),
                        "revision_id": spec["revision_id"],
                        "applied": spec["scope"] in sources,
                        "required": True,
                        "requirement": "",
                        "result": "",
                        "outcome": NOT_JUDGED,
                        "reason": "its approved version could not be verified",
                    }
                )
                continue
            line = lines.get(code)
            if line is None:
                continue  # this specification does not state the test
            applied = spec["scope"] in sources
            found.append(judge_one(_statement(spec, line, applied), line, spec, applied))
        return found

    rows, answered = [], set()
    for result in results:
        code, test = result["test_code"], tests.get(result["test"])
        line_frozen = frozen.get(code)
        if test is None or line_frozen is None:
            continue
        answered.add(code)
        rows.append(
            {
                "origin": "laboratory",
                "test_code": code,
                "name": result.get("name") or code,
                "sample": result["sample"],
                "test": result["test"],
                "statements": statements(code, partial(_judge_test, test, line_frozen)),
            }
        )
    for item in supplier:
        code, acceptance = item["test_code"], acceptances.get(item["acceptance"])
        line_frozen = frozen.get(code)
        if acceptance is None or line_frozen is None:
            continue
        answered.add(code)
        rows.append(
            {
                "origin": "supplier",
                "test_code": code,
                "name": item.get("name") or code,
                "sample": None,
                "acceptance": item["acceptance"],
                "statements": statements(
                    code, partial(_judge_stated, acceptance.result, line_frozen)
                ),
            }
        )
    # A test a specification requires but the lot has no result for: the statement applied to
    # the lot states it for information only.
    stated = {}
    for spec in specifications:
        for code, line in (approved[spec["revision_id"]] or {}).items():
            if code not in answered and line.get("required", True):
                stated.setdefault(code, line)
    for code in sorted(stated):
        rows.append(
            {
                "origin": "none",
                "test_code": code,
                "name": stated[code].get("name") or code,
                "sample": None,
                "statements": statements(code, _untested),
            }
        )
    return rows


# The certificate of one scope ---------------------------------------------------------------


def scopes(evidence):
    """{scope: [its specifications]} a certificate can be issued for: the scopes of a lot
    assigned under more than one specification, each with the specification versions that
    state its requirements."""
    native = (evidence or {}).get("native") or {}
    specifications = native.get("specifications") or []
    if len(specifications) < 2 or "conformity" not in native:
        return {}
    found = {}
    for spec in specifications:
        found.setdefault(spec["scope"], []).append(spec)
    return found


def scope_view(evidence, scope):
    """What a certificate for ``scope`` reports, from the evidence alone: its specifications,
    each laboratory and supplier result of a test they state with the statement it is judged
    against, and the tests they require that have no result. None for a certificate of all
    the lot's requirements, or a scope the lot cannot have a certificate for."""
    if not scope:
        return None
    available = scopes(evidence)
    if scope not in available:
        return None
    native = evidence["native"]
    analytical = native.get("analytical") or {}
    results = {r["test"]: r for r in analytical.get("results") or []}
    supplier = {s["acceptance"]: s for s in analytical.get("supplier_results") or []}
    lab_rows, supplier_rows, untested = [], [], []
    for row in native["conformity"]:
        statement = next((s for s in row["statements"] if s["scope"] == scope), None)
        if statement is None:
            continue
        if row["origin"] == "laboratory" and row["test"] in results:
            lab_rows.append({"result": results[row["test"]], "statement": statement})
        elif row["origin"] == "supplier" and row["acceptance"] in supplier:
            supplier_rows.append({"result": supplier[row["acceptance"]], "statement": statement})
        elif row["origin"] == "none" and statement["outcome"] == NOT_TESTED:
            untested.append({"test_code": row["test_code"], "statement": statement})
    methods = {r["result"]["method"]["code"] for r in lab_rows}
    return {
        "scope": scope,
        "specifications": available[scope],
        "results": lab_rows,
        "supplier_results": supplier_rows,
        "untested": untested,
        "methods": list(
            {
                (m["code"], m.get("version")): m
                for m in evidence.get("methods") or []
                if isinstance(m, dict) and m.get("code") in methods
            }.values()
        ),
        "reviewed_tests": {r["result"]["test"] for r in lab_rows},
        "accepted": {r["result"]["acceptance"] for r in supplier_rows},
    }


def scope_blockers(evidence, scope):
    """Why a certificate for ``scope`` cannot be issued from this evidence (empty when it can):
    the lot has no specification of that scope, a result does not meet or cannot be judged
    against its statement, or a test it requires has no result."""
    if not scope:
        return []
    view = scope_view(evidence, scope)
    if view is None:
        return [
            f"The lot's requirements name no specification for scope {scope}; a certificate for "
            "it cannot be issued."
        ]
    problems = []
    for kind, rows in (
        ("results", view["results"]),
        ("supplier_results", view["supplier_results"]),
    ):
        for row in rows:
            statement, result = row["statement"], row["result"]
            where = (
                f"{result['sample']} {result['test_code']}"
                if kind == "results"
                else f"{result['test_code']} (supplier's result)"
            )
            if statement["outcome"] == FAILS:
                problems.append(
                    f"{where}: the result {statement['result']} does not meet "
                    f"{statement['specification']} ({scope}), {statement['requirement']}."
                )
            elif statement["outcome"] == NOT_JUDGED:
                problems.append(
                    f"{where}: the result cannot be judged against "
                    f"{statement['specification']} ({scope}): {statement['reason']}."
                )
    for row in view["untested"]:
        statement = row["statement"]
        problems.append(
            f"{row['test_code']}: {statement['specification']} ({scope}) requires it and the "
            f"lot has no result for it; {statement['reason']}."
        )
    if not (view["results"] or view["supplier_results"] or view["untested"]):
        problems.append(f"No result of the lot answers a test of the specification of {scope}.")
    return problems
