"""Seam to the testing/review spine for stability pulls.

A pull tested in the system has its own tests (``pull_results``): it is accepted once every
test of its time point has a reviewed result and no investigation is open, with the outcome
those results give against the acceptance criteria frozen on them. A failing result that an
investigation confirmed is an outcome of the study, not an obstacle to closing the pull.

A pull linked to a sample of its lot (``sample_evidence``) is accepted only when the required
tests on that sample are reviewed, conform and have no open or confirmed investigation, as
published by the analytical module: those are the lot's own tests.

Change this one module if the testing contract moves; nothing else in `stability` reads result
tables. The foundation `quality.Result` rows are not consulted: that path is closed for new
data.
"""

from analytical.contracts import reported_source
from analytical.gates import data_author_ids, investigation_author_ids
from analytical.models import AnalyticalTest, Investigation, Observation, RawDataFile
from core.models import ElectronicSignature

RESULTS_SCHEMA = "stability.pull-results/1"
STATE = AnalyticalTest.State
CONFORMS, FAILS = "conforms", "fails"


def sample_evidence(sample, test_codes, not_before=None):
    """(blockers, evidence) for the required test codes on one sample.

    `not_before` is the start of the pull: tests created earlier cannot be evidence for it."""
    tests = list(AnalyticalTest.objects.filter(sample=sample))
    blockers = []
    if not_before is not None:
        blockers += [
            f"{t.label} was created before the pull and cannot be its evidence."
            for t in tests
            if t.created_at < not_before
        ]
        tests = [t for t in tests if t.created_at >= not_before]
    investigations = {i.pk: i for i in Investigation.objects.filter(test__sample=sample)}
    evidence = []
    for inv in investigations.values():
        if inv.is_open:
            blockers.append(f"{inv.label} is open: {inv.trigger}.")
        elif inv.outcome == Investigation.Outcome.CONFIRMED:
            blockers.append(f"{inv.label} confirmed an out-of-specification result.")
    for code in test_codes:
        good, pending = [], []
        for test in (t for t in tests if t.test_code == code):
            if test.state == AnalyticalTest.State.REVIEWED and test.conforms:
                parent = investigations.get(test.investigation_id)
                if test.investigation_id is None or (
                    parent is not None and parent.outcome == Investigation.Outcome.INVALIDATED
                ):
                    good.append(test)
            elif test.state in (AnalyticalTest.State.OPEN, AnalyticalTest.State.SUBMITTED):
                pending.append(test)
        if good:
            evidence.append({"test_code": code, "tests": [t.pk for t in good]})
        elif pending:
            blockers.extend(f"{code}: {t.label} is not yet reviewed." for t in pending)
        elif not any(code in b for b in blockers):
            blockers.append(f"{code}: no reviewed conforming result.")
    return blockers, evidence


# --- Pulls tested in the system ----------------------------------------------------------------


def _signature(object_type, object_id, meaning):
    signature = (
        ElectronicSignature.objects.filter(
            object_type=object_type, object_id=str(object_id), meaning=meaning
        )
        .order_by("-signed_at", "-pk")
        .first()
    )
    if signature is None:
        return None
    return {
        "id": signature.pk,
        "signer": signature.signer_name,
        "meaning": signature.meaning,
        "signed_at": signature.signed_at.isoformat(),
        "revision": signature.revision,
        "content_hash": signature.content_hash,
    }


def _code_outcome(lineage, investigations):
    """(outcome, the tests whose results are reported, blockers) for one test code of a pull.

    ``lineage`` is the code's original test with its reruns and retests. The outcome is
    ``conforms`` when a reviewed conforming result stands (its own investigation, if any,
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


def _results(pull, tests, investigations):
    blockers = [f"{inv.label} is open: {inv.trigger}." for inv in investigations if inv.is_open]
    rows = []
    for code in pull.timepoint.test_codes:
        lineage = [test for test in tests if test.test_code == code]
        if not lineage:
            blockers.append(f"{code}: no test is assigned.")
            rows.append({"test_code": code, "outcome": "", "tests": [], "lineage": []})
            continue
        outcome, reported, reasons = _code_outcome(lineage, investigations)
        blockers.extend(reasons)
        rows.append({"test_code": code, "outcome": outcome, "tests": reported, "lineage": lineage})
    outcomes = {row["outcome"] for row in rows}
    if "" in outcomes or blockers:
        overall = ""
    else:
        overall = FAILS if FAILS in outcomes else CONFORMS
    return blockers, rows, overall


def pull_results(pull):
    """(blockers, rows, outcome) for a pull tested in the system.

    ``rows`` has one entry for each test of the pull's time point: its ``outcome``, the
    ``tests`` whose results are reported and the whole ``lineage``. ``outcome`` is
    ``conforms`` or ``fails`` once every test is decided and nothing blocks, else "".
    """
    tests = list(AnalyticalTest.objects.filter(pull=pull).order_by("test_code", "pk"))
    investigations = list(Investigation.objects.filter(test__pull=pull).order_by("pk"))
    return _results(pull, tests, investigations)


def study_results(pulls):
    """{pull pk: (blockers, rows, outcome)} for the pulls of a study that have tests of their
    own, read with two queries."""
    by_pull, by_pull_inv = {}, {}
    ids = [pull.pk for pull in pulls]
    for test in AnalyticalTest.objects.filter(pull_id__in=ids).order_by("test_code", "pk"):
        by_pull.setdefault(test.pull_id, []).append(test)
    found = Investigation.objects.filter(test__pull_id__in=ids).select_related("test")
    for inv in found.order_by("pk"):
        by_pull_inv.setdefault(inv.test.pull_id, []).append(inv)
    return {
        pull.pk: _results(pull, by_pull[pull.pk], by_pull_inv.get(pull.pk, []))
        for pull in pulls
        if pull.pk in by_pull
    }


def has_tests(pull):
    return AnalyticalTest.objects.filter(pull=pull).exists()


def test_author_ids(pull):
    """Users who produced data for the pull's own tests or investigated them: none of them
    accepts the pull."""
    ids = set()
    for test in AnalyticalTest.objects.filter(pull=pull):
        ids |= data_author_ids(test)
    return ids | investigation_author_ids(Investigation.objects.filter(test__pull=pull))


def frozen_results(pull, results):
    """Frozen-ready JSON of a pull's results for its acceptance; nothing is recomputed later.
    ``results`` is what ``pull_results`` read for the signature, so the signer's check and the
    frozen record rest on one read. Raises nothing: the caller checks the blockers first."""
    _, rows, outcome = results
    investigations = Investigation.objects.filter(test__pull=pull).order_by("pk")
    timepoint = pull.timepoint
    results = []
    for row in rows:
        reported = []
        for test in row["tests"]:
            spec = test.spec
            source = reported_source(list(test.current_observations()))
            reported.append(
                {
                    "test": test.pk,
                    "kind": test.kind,
                    "reportable": test.reportable_display,
                    "unit": spec.unit,
                    "conforms": test.conforms,
                    "acceptance": spec.acceptance,
                    "requirement_source": spec.source,
                    "requirement_hash": test.requirement_hash,
                    "method": {"code": spec.method.code, "revision": spec.method.revision},
                    "review": _signature("analytical.analyticaltest", test.pk, "reviewed"),
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
            )
        results.append(
            {
                "test_code": row["test_code"],
                "name": row["lineage"][0].spec.name,
                "outcome": row["outcome"],
                "tests": reported,
                "excluded_tests": [
                    {"test": t.pk, "kind": t.kind, "state": t.state}
                    for t in row["lineage"]
                    if t not in row["tests"]
                ],
            }
        )
    return {
        "schema": RESULTS_SCHEMA,
        "study": pull.study.identifier,
        "condition": timepoint.condition.label,
        "timepoint": timepoint.label,
        "interval_days": timepoint.interval_days,
        "pulled_on": pull.pulled_on.isoformat(),
        "outcome": outcome,
        "results": results,
        "investigations": [
            {
                "investigation": inv.label,
                "test": inv.test_id,
                "trigger": inv.trigger,
                "outcome": inv.outcome,
                "assignable_cause": inv.assignable_cause,
                "closed_at": inv.closed_at.isoformat() if inv.closed_at else None,
                "conclusion": _signature("analytical.investigation", inv.pk, "concluded"),
            }
            for inv in investigations
        ],
        "author_ids": sorted(test_author_ids(pull)),
    }


def _work_in_progress(tests, investigations):
    """Why the tests' evidence is still in progress, one reason each, or []: a test awaits
    review, an open one already holds an observation or a raw-data file, or an investigation is
    open. An open test that holds nothing is not work in progress, also when it has a place in
    a QC batch: batch rejection leaves such a test of a closed pull as it is."""
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


def testing_in_progress(study):
    """Why the study cannot be closed yet (see ``_work_in_progress``), or []. Closing would
    leave that work with no way forward, because a closed study's pulls take no more testing.
    An open test that holds nothing does not stop the study: it is left as it is."""
    return _work_in_progress(
        AnalyticalTest.objects.filter(pull__study=study),
        Investigation.objects.filter(test__pull__study=study),
    )


def pull_testing_in_progress(pull):
    """Why a pulled pull cannot be recorded as missed (see ``_work_in_progress``), or []. Its
    reviewed results stay in the record; untouched tests take no more work."""
    return _work_in_progress(
        AnalyticalTest.objects.filter(pull=pull), Investigation.objects.filter(test__pull=pull)
    )
