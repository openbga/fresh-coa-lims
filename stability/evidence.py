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

from analytical import outcomes
from analytical.gates import data_author_ids, investigation_author_ids, tests_author_ids
from analytical.models import AnalyticalTest, Investigation

RESULTS_SCHEMA = "stability.pull-results/1"
CONFORMS, FAILS = outcomes.CONFORMS, outcomes.FAILS


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


def _results(pull, tests, investigations):
    return outcomes.results(pull.timepoint.test_codes, tests, investigations)


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
    return {
        "schema": RESULTS_SCHEMA,
        "study": pull.study.identifier,
        "condition": timepoint.condition.label,
        "timepoint": timepoint.label,
        "interval_days": timepoint.interval_days,
        "pulled_on": pull.pulled_on.isoformat(),
        "outcome": outcome,
        "results": outcomes.frozen_rows(rows),
        "investigations": outcomes.frozen_investigations(investigations),
        "author_ids": sorted(test_author_ids(pull)),
    }


_work_in_progress = outcomes.work_in_progress


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


def results_author_ids(tests):
    """Users who produced data of any of ``tests`` (a shelf-life evaluation's results): none of
    them concludes the evaluation. Reviewing a result or accepting a pull is not authorship."""
    return tests_author_ids(tests)
