"""Read-only lot gate and evidence snapshot published for QC disposition and certificates.

Call these inside the disposition/report transaction after locking the lot row: every analytical
evidence change locks and bumps the same lot revision, so the result is consistent under that lock.
"""

from django.core.exceptions import ValidationError

from core.models import ElectronicSignature
from quality.models import Sample

from .contracts import (
    bench,
    canonical_hash,
    content_hash,
    reported_source,
    resolve,
    supplier_results,
)
from .models import (
    AnalyticalTest,
    Investigation,
    InvestigationEntry,
    Observation,
    QCResult,
    RawDataFile,
)

EVIDENCE_SCHEMA = "analytical.lot-evidence/1"
STATE = AnalyticalTest.State
# Tests that answer nothing and block nothing by themselves: their lineage decides.
EXCLUDED = (STATE.INVALIDATED, STATE.SUPERSEDED, STATE.NOT_COMPLETED)


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


def tested_here(lot, test_code):
    """Why a supplier's result cannot stand in for this requirement of the lot, or "": the
    laboratory has started testing it. A test that is still open, in no QC batch, without any
    observation (corrected ones included) and without a raw-data file has not started; nor has
    one that was superseded in that condition when the lot's requirements were replaced, or
    recorded in that condition as not completed.
    Laboratory work on a superseded test still counts: replacing a requirement does not make
    room for a supplier's result where the laboratory already has its own."""
    tests = AnalyticalTest.objects.filter(lot_id=lot.pk, test_code=test_code).order_by("pk")
    for test in tests:
        if (
            test.state not in (STATE.OPEN, STATE.SUPERSEDED, STATE.NOT_COMPLETED)
            or test.evaluated_at is not None
            or test.batch_id is not None
            or Observation.objects.filter(test=test).exists()
            or RawDataFile.objects.filter(test=test).exists()
        ):
            return (
                f"{test.label} {test_code} already holds laboratory work (a result, a raw-data "
                "file, a QC batch or a decision). A supplier's result cannot stand in for a "
                "requirement the laboratory has started testing."
            )
    return ""


def lot_status(lot):
    """Return (blockers, reportable tests by (sample, code), tests, investigations) for a lot.

    Every sample that carries original tests, or no tests at all, must have each required code
    assigned and answered by a reportable result in that sample's own lineage. One sample never
    covers another; samples holding only authorized resample/rerun tests answer for the original
    sample they replace. A requirement for which a supplier's certificate result was accepted is
    answered for the whole lot by that acceptance and needs no test.

    A test answers a requirement by content (``content_hash``), so a test carries over when
    the lot's requirements are replaced by identical ones. A superseded test is closed: it
    blocks nothing and answers nothing, and its sample then needs a test of the kind
    ``revised`` under the current requirement. A test recorded as not completed is closed too:
    its repeat, or the investigation it belongs to or opened, answers for its sample.
    """
    return _status(lot)[:4]


def _status(lot):
    """``lot_status`` plus the supplier results accepted in place of tests, by test code."""
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
    content = {code: content_hash(payload) for code, payload in required.items()}
    stale = set()
    blockers = []
    for inv in investigations.values():
        if inv.is_open:
            blockers.append(f"{inv.label} is open: {inv.trigger}.")
        elif inv.outcome == Investigation.Outcome.CONFIRMED:
            blockers.append(f"{inv.label} confirmed an out-of-specification result.")
    relied = supplier_results(lot)
    blockers.extend(relied["blockers"])
    accepted = {}
    for code, entry in relied["accepted"].items():
        # The source already withholds an acceptance whose requirement changed; the gate does
        # not take its word for the hash or the signature.
        if current.get(code) == entry["requirement_hash"] and entry["signature"]:
            accepted[code] = entry
        else:
            blockers.append(
                f"{entry['label']}: the accepted supplier result for {code} does not match "
                "the lot's current requirement or is not signed."
            )
    worked = set(
        Observation.objects.filter(test__lot_id=lot.pk).values_list("test_id", flat=True)
    ) | set(RawDataFile.objects.filter(test__lot_id=lot.pk).values_list("test_id", flat=True))
    reportable, roots, replaced = {}, {}, set()
    for test in tests:
        if test.state == STATE.SUPERSEDED:
            root = _root(test, by_pk)
            replaced.add((root.sample_id, root.test_code))
            continue
        if test.state == STATE.OPEN:
            # An untouched test of a requirement the supplier's result answers is not work
            # left undone; it stays open and takes no result while the acceptance stands.
            untouched = test.batch_id is None and test.pk not in worked
            if not (test.test_code in accepted and untouched):
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
            if (
                test.test_code in content
                and content_hash(test.requirement) != content[test.test_code]
            ):
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
            if code in accepted:
                continue  # answered for the whole lot by the accepted supplier result
            if (sample.pk, code) not in roots and (sample.pk, code) in replaced:
                blockers.append(
                    f"Sample {sample.reference} has no {code} test under the lot's current "
                    "requirements: the earlier test was superseded when they were replaced. "
                    "Assign the required tests."
                )
            elif (sample.pk, code) not in roots:
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
    for code in accepted:
        if any(key[1] == code for key in reportable):
            blockers.append(
                f"{code} has both a laboratory result and an accepted supplier result "
                f"({accepted[code]['label']}); withdraw the acceptance."
            )
    return blockers, reportable, tests, investigations, accepted, relied["author_ids"]


def _authors(tests):
    ids = set(Observation.objects.filter(test__in=tests).values_list("recorded_by_id", flat=True))
    ids.update(t.submitted_by_id for t in tests if t.submitted_by_id)
    batch_ids = {t.batch_id for t in tests if t.batch_id}
    ids.update(
        QCResult.objects.filter(batch_id__in=batch_ids).values_list("recorded_by_id", flat=True)
    )
    ids.update(RawDataFile.objects.filter(test__in=tests).values_list("uploaded_by_id", flat=True))
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


def _reported_by(observations):
    """{"contract_laboratory": {...}} when a contract laboratory reported every current
    replicate, else {}. A test never mixes the two origins."""
    source = reported_source(observations)
    if source is None:
        return {}
    laboratory, report, approval = source["laboratory"], source["report"], source["approval"]
    return {
        "contract_laboratory": {
            "code": laboratory.get("code"),
            "name": laboratory.get("name"),
            "location": laboratory.get("location"),
            "report_number": report.get("number"),
            "report_date": report.get("date"),
            "approval": approval.get("id"),
            "approval_evidence": approval.get("evidence_ref"),
        }
    }


def lot_notices(lot):
    """What a disposition signer should know about the lot's results; never a blocker.

    A result reported by a contract laboratory says so when the approval it relied on has been
    revoked since: the result stands as recorded and the decision is taken knowing it.
    """
    try:
        desk = bench()
    except ValidationError:
        return []
    notices = []
    tests = AnalyticalTest.objects.filter(lot_id=lot.pk).exclude(state__in=EXCLUDED)
    for test in tests.order_by("pk"):
        source = test.contract_source()
        notice = desk.contract_notice(source) if source else ""
        if notice:
            notices.append(
                f"{test.label} {test.test_code} was reported by a contract laboratory. {notice} "
                "This does not block the disposition."
            )
    return notices


def _excluded(test):
    """A test that answers nothing, for the evidence. One recorded as not completed carries
    that record and its signature, so the certificate's evidence says why."""
    row = {"test": test.pk, "test_code": test.test_code, "kind": test.kind, "state": test.state}
    if test.state == STATE.NOT_COMPLETED:
        record = test.not_completed_record
        row["not_completed"] = {
            "cause": record["cause"],
            "recorded": record["recorded"],
            "outside_limits": record["outside_limits"],
            "corrections": record.get("corrections", []),
            "follow_up": record["follow_up"],
            "signature": _signature("analytical.analyticaltest", test.pk, "not_completed"),
        }
    return row


def lot_evidence(lot):
    """Frozen-ready JSON evidence for reports. Values are strings; nothing is recomputed later.

    Replicate values are the text as recorded ("99.80", "<10", "Absent"); ``mean`` is null when
    the result has none (qualitative, or a replicate reported as less than a value). A result
    reported by a contract laboratory names it under ``contract_laboratory``. Supplier
    certificate results accepted in place of a test are listed apart, under
    ``supplier_results``: they are the supplier's results, not tests of this laboratory.
    """
    blockers, reportable, tests, investigations, accepted, supplier_authors = _status(lot)
    results = []
    references = {t.sample_id: t.sample.reference for t in tests}
    for sample_id, code in sorted(reportable, key=lambda k: (references[k[0]], k[1])):
        for test in reportable[(sample_id, code)]:
            spec = test.spec
            observations = list(test.current_observations())
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
                    "result_type": spec.result_type,
                    "unit": spec.unit,
                    "lower_limit": None if spec.lower is None else str(spec.lower),
                    "upper_limit": None if spec.upper is None else str(spec.upper),
                    "lower_inclusive": spec.lower_inclusive,
                    "upper_inclusive": spec.upper_inclusive,
                    "expected_result": spec.expected_result or None,
                    "criterion": spec.criterion,
                    "acceptance": spec.acceptance,
                    "replicates": [
                        {
                            "replicate": o.replicate,
                            "value": o.value_text,
                            "observed": o.observed_text,
                            "raw_reference": o.raw_reference,
                            "eligibility": o.eligibility,
                            "recorded_by": o.recorded_by.get_username(),
                            "recorded_at": o.recorded_at.isoformat(),
                        }
                        for o in observations
                    ],
                    "mean": None if test.mean_value is None else str(test.mean_value),
                    "reportable": test.reportable_display,
                    "reporting_decimals": spec.reporting_decimals,
                    "batch": test.batch.number if test.batch else None,
                    "review": _signature("analytical.analyticaltest", test.pk, "reviewed"),
                    # Present only for a result a contract laboratory reported, so evidence
                    # of results made at this bench keeps the shape it always had.
                    **_reported_by(observations),
                }
            )
    return {
        "schema": EVIDENCE_SCHEMA,
        "lot": lot.number,
        "lot_revision": lot.revision,
        "complete": not blockers,
        "blockers": blockers,
        "author_ids": sorted(lot_author_ids(lot) | set(supplier_authors)),
        "results": results,
        # Present only when a supplier's result was accepted in place of a test, so evidence
        # of lots tested in full keeps the shape it always had.
        **({"supplier_results": [accepted[code] for code in sorted(accepted)]} if accepted else {}),
        "excluded_tests": [_excluded(t) for t in tests if t.state in EXCLUDED],
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
