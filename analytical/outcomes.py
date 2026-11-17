"""What the tests of a stability pull or a reassessment show, once they are decided.

A pull and a reassessment hold tests of their own that name no lot. Each is concluded with a
signature once every test it requires has a reviewed result and no investigation is open, and
that signature freezes the outcome those results give against the acceptance criteria frozen on
them. This module reads the tests and investigations a caller passes and judges them the same
way for both; the caller decides which test codes are required and what else it freezes. A
failing result that an investigation confirmed is an outcome, not an obstacle.
"""

from core.models import ElectronicSignature

from .contracts import reported_source
from .models import AnalyticalTest, Investigation, Observation, RawDataFile

STATE = AnalyticalTest.State
CONFORMS, FAILS = "conforms", "fails"


def signature(object_type, object_id, meaning):
    """The latest signature of a record with this meaning, as frozen evidence, or None."""
    found = (
        ElectronicSignature.objects.filter(
            object_type=object_type, object_id=str(object_id), meaning=meaning
        )
        .order_by("-signed_at", "-pk")
        .first()
    )
    if found is None:
        return None
    return {
        "id": found.pk,
        "signer": found.signer_name,
        "meaning": found.meaning,
        "signed_at": found.signed_at.isoformat(),
        "revision": found.revision,
        "content_hash": found.content_hash,
    }


def code_outcome(lineage, investigations):
    """(outcome, the tests whose results are reported, blockers) for one test code.

    ``lineage`` is the code's original test with its reruns, retests and repeats. The outcome
    is ``conforms`` when a reviewed conforming result stands (its own investigation, if any,
    invalidated the original), ``fails`` when an investigation confirmed an
    out-of-specification result, and "" while that is not decided.
    """
    blockers = []
    for test in lineage:
        if test.state == STATE.OPEN:
            blockers.append(f"{test.label} {test.test_code} is incomplete.")
        elif test.state == STATE.SUBMITTED:
            blockers.append(f"{test.label} {test.test_code} awaits independent review.")
    reviewed = [test for test in lineage if test.state == STATE.REVIEWED]
    related = {
        inv.pk: inv
        for inv in investigations
        if inv.test_id in {test.pk for test in lineage}
        or inv.pk in {test.investigation_id for test in lineage}
    }
    if any(inv.outcome == Investigation.Outcome.CONFIRMED for inv in related.values()):
        # Every reviewed result of the lineage stands with the confirmed failure.
        return FAILS, reviewed, blockers
    standing = [
        test
        for test in reviewed
        if test.conforms
        and (
            test.investigation_id is None
            or related[test.investigation_id].outcome == Investigation.Outcome.INVALIDATED
        )
    ]
    if standing:
        return CONFORMS, standing, blockers
    if not blockers and not any(inv.is_open for inv in related.values()):
        blockers.append(f"{lineage[0].test_code}: no reviewed result.")
    return "", reviewed, blockers


def results(codes, tests, investigations):
    """(blockers, rows, outcome) for the required test ``codes``.

    ``rows`` has one entry for each code: its ``outcome``, the ``tests`` whose results are
    reported and the whole ``lineage``. ``outcome`` is ``conforms`` or ``fails`` once every
    code is decided and nothing blocks, else "".
    """
    blockers = [f"{inv.label} is open: {inv.trigger}." for inv in investigations if inv.is_open]
    rows = []
    for code in codes:
        lineage = [test for test in tests if test.test_code == code]
        if not lineage:
            blockers.append(f"{code}: no test is assigned.")
            rows.append({"test_code": code, "outcome": "", "tests": [], "lineage": []})
            continue
        outcome, reported, reasons = code_outcome(lineage, investigations)
        blockers.extend(reasons)
        rows.append({"test_code": code, "outcome": outcome, "tests": reported, "lineage": lineage})
    outcomes = {row["outcome"] for row in rows}
    if "" in outcomes or blockers:
        overall = ""
    else:
        overall = FAILS if FAILS in outcomes else CONFORMS
    return blockers, rows, overall


def excluded(test):
    """A test of the lineage whose result is not reported. One recorded as not completed
    carries the readings and cause its record froze, so a failure found only there is kept."""
    row = {"test": test.pk, "kind": test.kind, "state": test.state}
    if test.state == STATE.NOT_COMPLETED:
        record = test.not_completed_record
        row["not_completed"] = {
            "cause": record["cause"],
            "recorded": record["recorded"],
            "outside_limits": record["outside_limits"],
            "corrections": record.get("corrections", []),
            "follow_up": record["follow_up"],
            "signature": signature("analytical.analyticaltest", test.pk, "not_completed"),
        }
    return row


def reported(test):
    """A reviewed result as frozen evidence: the reportable value with the criterion, the
    requirement and the method frozen on the test, its review and its contract laboratory."""
    spec = test.spec
    source = reported_source(list(test.current_observations()))
    return {
        "test": test.pk,
        "kind": test.kind,
        "reportable": test.reportable_display,
        "unit": spec.unit,
        "conforms": test.conforms,
        "acceptance": spec.acceptance,
        "requirement_source": spec.source,
        "requirement_hash": test.requirement_hash,
        "method": {"code": spec.method.code, "revision": spec.method.revision},
        "review": signature("analytical.analyticaltest", test.pk, "reviewed"),
        **(
            {
                "contract_laboratory": {
                    "code": source["laboratory"].get("code"),
                    "name": source["laboratory"].get("name"),
                    "report_number": source["report"].get("number"),
                    "report_date": source["report"].get("date"),
                }
            }
            if source
            else {}
        ),
    }


def frozen_rows(rows):
    """The ``rows`` of ``results`` as frozen evidence, one entry for each required code."""
    return [
        {
            "test_code": row["test_code"],
            "name": row["lineage"][0].spec.name if row["lineage"] else "",
            "outcome": row["outcome"],
            "tests": [reported(test) for test in row["tests"]],
            "excluded_tests": [excluded(t) for t in row["lineage"] if t not in row["tests"]],
        }
        for row in rows
    ]


def frozen_investigations(investigations):
    return [
        {
            "investigation": inv.label,
            "test": inv.test_id,
            "trigger": inv.trigger,
            "outcome": inv.outcome,
            "assignable_cause": inv.assignable_cause,
            "closed_at": inv.closed_at.isoformat() if inv.closed_at else None,
            "conclusion": signature("analytical.investigation", inv.pk, "concluded"),
        }
        for inv in investigations
    ]


def work_in_progress(tests, investigations):
    """Why the tests' evidence is still in progress, one reason each, or []: a test awaits
    review, an open one already holds an observation or a raw-data file, or an investigation is
    open. An open test that holds nothing is not work in progress, also when it has a place in
    a QC batch: batch rejection leaves such a test of a closed subject as it is."""
    tests = list(tests.order_by("pk"))
    worked = set(
        Observation.objects.filter(test__in=tests).values_list("test_id", flat=True)
    ) | set(RawDataFile.objects.filter(test__in=tests).values_list("test_id", flat=True))
    reasons = []
    for test in tests:
        if test.state == STATE.SUBMITTED:
            reasons.append(f"{test.label} {test.test_code} awaits independent review.")
        elif test.state == STATE.OPEN and test.pk in worked:
            reasons.append(
                f"{test.label} {test.test_code} holds results or raw data that were not submitted."
            )
    open_investigations = investigations.filter(
        phase__in=[Investigation.Phase.LABORATORY, Investigation.Phase.FULL]
    ).order_by("pk")
    return reasons + [f"{inv.label} is open: {inv.trigger}." for inv in open_investigations]


def failed(rows):
    """Whether a reviewed result of the rows does not conform, or an investigation confirmed a
    failure: such a result is never left unconcluded."""
    return any(
        row["outcome"] == FAILS or any(test.conforms is False for test in row["tests"])
        for row in rows
    )
