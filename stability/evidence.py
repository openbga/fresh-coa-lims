"""Seam to the testing/review spine for stability pulls.

A pull is accepted only when the required tests on its linked sample are reviewed, conform and
have no open or confirmed investigation, as published by the analytical module. Change this one
module if the testing contract moves; nothing else in `stability` reads result tables. The
foundation `quality.Result` rows are not consulted: the integrator closed that path for new data.
"""

from analytical.models import AnalyticalTest, Investigation


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
