"""Read-only lot gate and evidence snapshot published for disposition (integrator) and CoA (D).

Call these inside the disposition/report transaction after locking the lot row: every analytical
evidence change locks and bumps the same lot revision, so the result is consistent under that lock.
"""

from core.models import ElectronicSignature
from quality.models import Sample

from .contracts import canonical_hash, resolve
from .models import AnalyticalTest, Investigation, InvestigationEntry, Observation, QCResult

EVIDENCE_SCHEMA = "analytical.lot-evidence/1"
STATE = AnalyticalTest.State


def _reportable(test, investigations):
    """A reviewed conforming result counts unless its own lineage is still under investigation."""
    if test.state != STATE.REVIEWED or not test.conforms:
        return False
    if test.investigation_id:
        parent = investigations[test.investigation_id]
        return parent.outcome == Investigation.Outcome.INVALIDATED
    return True


def _root(test, by_pk):
    """The original test whose sample/code a rerun, retest or resample answers for."""
    while test.kind != AnalyticalTest.Kind.ORIGINAL:
        test = by_pk[test.parent_id]
    return test


def lot_status(lot):
    """Return (blockers, reportable tests by (sample, code), tests, investigations) for a lot.

    Every sample that carries original tests, or no tests at all, must have each required code
    assigned and answered by a reportable result in that sample's own lineage. One sample never
    covers another; samples holding only authorized resample/rerun tests answer for the original
    sample they replace.
    """
    tests = list(
        AnalyticalTest.objects.filter(lot_id=lot.pk)
        .select_related("sample", "batch")
        .order_by("test_code", "pk")
    )
    by_pk = {t.pk: t for t in tests}
    investigations = {i.pk: i for i in Investigation.objects.filter(lot_id=lot.pk)}
    by_test = {i.test_id: i for i in investigations.values()}
    required, holds = resolve(lot)
    current = {code: canonical_hash(payload) for code, payload in required.items()}
    stale = set()
    blockers = []
    for inv in investigations.values():
        if inv.is_open:
            blockers.append(f"{inv.label} is open: {inv.trigger}.")
        elif inv.outcome == Investigation.Outcome.CONFIRMED:
            blockers.append(f"{inv.label} confirmed an out-of-specification result.")
    reportable, roots = {}, {}
    for test in tests:
        if test.state == STATE.OPEN:
            blockers.append(f"{test.label} {test.test_code} is incomplete.")
        elif test.state == STATE.SUBMITTED:
            blockers.append(f"{test.label} {test.test_code} awaits independent review.")
        elif test.state == STATE.REVIEWED and not test.conforms:
            # Open/confirmed investigations already block; anything else must not slip through.
            inv = by_test.get(test.pk) or investigations.get(test.investigation_id)
            if inv is None or inv.outcome == Investigation.Outcome.INVALIDATED:
                blockers.append(f"{test.label} {test.test_code} does not conform.")
        root = _root(test, by_pk)
        key = (root.sample_id, root.test_code)
        roots[key] = root
        if _reportable(test, investigations):
            if test.test_code in current and test.requirement_hash != current[test.test_code]:
                stale.add(key)  # tested against a superseded requirement: never counts
            else:
                reportable.setdefault(key, []).append(test)
    blockers.extend(holds)
    sampled = {t.sample_id for t in tests}
    originals = {t.sample_id for t in tests if t.kind == AnalyticalTest.Kind.ORIGINAL}
    for sample in Sample.objects.filter(lot_id=lot.pk).order_by("pk"):
        if sample.pk in sampled and sample.pk not in originals:
            continue  # holds only tests answering for another sample
        for code in required:
            if (sample.pk, code) not in roots:
                blockers.append(f"Sample {sample.reference} has no {code} test assigned.")
            elif (sample.pk, code) not in reportable and (sample.pk, code) in stale:
                blockers.append(
                    f"Sample {sample.reference} {code} was tested against a superseded "
                    "requirement; the current approved requirement has no reviewed result."
                )
            elif (sample.pk, code) not in reportable:
                blockers.append(
                    f"Sample {sample.reference} has no reviewed conforming {code} result."
                )
    return blockers, reportable, tests, investigations


def _authors(tests):
    ids = set(Observation.objects.filter(test__in=tests).values_list("recorded_by_id", flat=True))
    ids.update(t.submitted_by_id for t in tests if t.submitted_by_id)
    batch_ids = {t.batch_id for t in tests if t.batch_id}
    ids.update(
        QCResult.objects.filter(batch_id__in=batch_ids).values_list("recorded_by_id", flat=True)
    )
    return ids


def data_author_ids(test):
    """Users who generated or submitted the test's data, including superseded entries and the
    QC of its batch. Assigning, reviewing or authorizing a test is not authorship."""
    return _authors([test])


def investigation_author_ids(investigations):
    """Openers and authors of investigative entries (not escalation or plan records)."""
    ids = set(investigations.values_list("opened_by_id", flat=True))
    ids.update(
        InvestigationEntry.objects.filter(investigation__in=investigations)
        .exclude(kind__in=["escalation", "plan"])
        .values_list("author_id", flat=True)
    )
    return ids


def lot_author_ids(lot):
    """Users who must not sign the lot's QC disposition: every analytical data author
    (observations including corrected originals, submitters, batch QC recorders), everyone who
    opened an investigation and every author of investigative entries. Signers of reviews,
    retest authorizations and conclusions are not included."""
    tests = list(AnalyticalTest.objects.filter(lot_id=lot.pk))
    return _authors(tests) | investigation_author_ids(Investigation.objects.filter(lot_id=lot.pk))


def lot_blockers(lot):
    """Messages that must block QC disposition approval; empty means analytical evidence passes."""
    return lot_status(lot)[0]


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


def lot_evidence(lot):
    """Frozen-ready JSON evidence for reports. Values are strings; nothing is recomputed later."""
    blockers, reportable, tests, investigations = lot_status(lot)
    results = []
    references = {t.sample_id: t.sample.reference for t in tests}
    for sample_id, code in sorted(reportable, key=lambda k: (references[k[0]], k[1])):
        for test in reportable[(sample_id, code)]:
            spec = test.spec
            results.append(
                {
                    "test": test.pk,
                    "test_code": code,
                    "for_sample": references[sample_id],
                    "name": spec.name,
                    "kind": test.kind,
                    "sample": test.sample.reference,
                    "requirement_source": spec.source,
                    "requirement_hash": test.requirement_hash,
                    "method": {"code": spec.method.code, "revision": spec.method.revision},
                    "unit": spec.unit,
                    "lower_limit": None if spec.lower is None else str(spec.lower),
                    "upper_limit": None if spec.upper is None else str(spec.upper),
                    "replicates": [
                        {
                            "replicate": o.replicate,
                            "value": o.value_text,
                            "raw_reference": o.raw_reference,
                            "eligibility": o.eligibility,
                            "recorded_by": o.recorded_by.get_username(),
                            "recorded_at": o.recorded_at.isoformat(),
                        }
                        for o in test.current_observations()
                    ],
                    "mean": str(test.mean_value),
                    "reportable": test.reportable_display,
                    "reporting_decimals": spec.reporting_decimals,
                    "batch": test.batch.number if test.batch else None,
                    "review": _signature("analytical.analyticaltest", test.pk, "reviewed"),
                }
            )
    return {
        "schema": EVIDENCE_SCHEMA,
        "lot": lot.number,
        "lot_revision": lot.revision,
        "complete": not blockers,
        "blockers": blockers,
        "author_ids": sorted(lot_author_ids(lot)),
        "results": results,
        "excluded_tests": [
            {"test": t.pk, "test_code": t.test_code, "kind": t.kind, "state": t.state}
            for t in tests
            if t.state == STATE.INVALIDATED
        ],
        "investigations": [
            {
                "investigation": inv.label,
                "test": inv.test_id,
                "trigger": inv.trigger,
                "phase": inv.phase,
                "outcome": inv.outcome,
                "assignable_cause": inv.assignable_cause,
                "closed_at": inv.closed_at.isoformat() if inv.closed_at else None,
                "conclusion": _signature("analytical.investigation", inv.pk, "concluded"),
            }
            for inv in sorted(investigations.values(), key=lambda i: i.pk)
        ],
    }
