"""What replacing a lot's requirements during testing does to the lot's tests.

Published for the requirement replacement (``settings.REQUIREMENT_REPLACEMENT_TESTING``, the
adapter ``config.integrations.TestingUnderReplacement``); the sampling module, which owns the
lot's requirements, never imports this one.

A test answers a requirement by its content (``contracts.content_hash``), whatever document
states it. When the requirements are replaced:

- a test whose requirement is unchanged carries over as it is;
- a test whose requirement changed, or is no longer required, is closed as ``superseded``: it
  and everything recorded on it are kept, it takes no more work and it never counts. Assigning
  the lot's tests afterwards adds a linked test of the kind ``revised`` under the new
  requirement.

Nothing recorded is set aside unevaluated: the replacement is refused while an investigation is
open on the lot, and while a test that would be superseded holds results or raw-data files
that were not submitted. A failing result therefore always meets the requirement it was
tested under first.

Lock order: the lot's tests (by pk) are locked before the lot, as everywhere in testing
(``lock`` runs before the signed lot is locked, ``apply`` under both locks).
"""

from django.core.exceptions import ValidationError

from core.audit import record_event

from .contracts import content_hash, parse_requirement
from .models import AnalyticalTest, Investigation, Observation, RawDataFile

STATE = AnalyticalTest.State
CLOSED = (STATE.INVALIDATED, STATE.SUPERSEDED, STATE.NOT_COMPLETED)
CARRIED, SUPERSEDED = "carried", "superseded"
CHANGED, DROPPED = "changed", "not_required"
STALE = "The lot's tests changed after the replacement was prepared. Reload and review it again."


def held(requirements):
    """Why testing could not execute the new requirements ({code: payload}); empty when it can."""
    reasons = []
    for code, payload in requirements.items():
        try:
            spec = parse_requirement(payload)
        except ValidationError as exc:
            reasons.append(f"Requirement for {code} is held: {' '.join(exc.messages)}")
            continue
        if spec.test_code != code:
            reasons.append(f"Requirement for {code} is held: test code mismatch.")
    if not requirements:
        reasons.append("No required tests in the new requirements.")
    return reasons


def effects(lot, requirements, tests=None):
    """One row per test of the lot that is still open, awaiting review or reviewed: whether it
    carries over or is superseded under ``requirements`` ({code: payload}), and why.

    Tests already invalidated, superseded or recorded as not completed are closed and are not
    listed.
    """
    current = {code: content_hash(payload) for code, payload in requirements.items()}
    if tests is None:
        tests = AnalyticalTest.objects.filter(lot_id=lot.pk).select_related("sample")
        tests = list(tests.order_by("pk"))
    ids = [t.pk for t in tests]
    # Laboratory work that was recorded on a test: current observations and raw-data files.
    recorded = set(
        Observation.objects.filter(test__in=ids, correction__isnull=True).values_list(
            "test_id", flat=True
        )
    ) | set(RawDataFile.objects.filter(test__in=ids).values_list("test_id", flat=True))
    rows = []
    for test in tests:
        if test.state in CLOSED:
            continue
        if test.test_code not in current:
            effect, why = SUPERSEDED, DROPPED
        elif content_hash(test.requirement) == current[test.test_code]:
            effect, why = CARRIED, ""
        else:
            effect, why = SUPERSEDED, CHANGED
        rows.append(
            {
                "test": test.pk,
                "label": test.label,
                "test_code": test.test_code,
                "sample": test.sample.reference,
                "kind": test.kind,
                "state": test.state,
                "result": test.reportable_display,
                "conforms": test.conforms,
                "has_results": test.pk in recorded,
                "effect": effect,
                "why": why,
            }
        )
    return rows


def refusals(lot, rows):
    """Why the lot's requirements cannot be replaced now, from the testing side; empty when
    they can. Read-only: pages show it and ``apply`` repeats it under the locks."""
    reasons = [
        f"{inv.label} is open on this lot ({inv.trigger}). Conclude it first: a result is "
        "investigated against the requirement it was tested under."
        for inv in Investigation.objects.filter(lot_id=lot.pk)
        .exclude(phase=Investigation.Phase.CLOSED)
        .order_by("pk")
    ]
    reasons.extend(
        f"{row['label']} {row['test_code']} holds results or raw-data files that were not "
        "submitted, and its requirement would change. Complete and submit it first, or have "
        "quality record that it cannot be completed, so that what was recorded is evaluated "
        "against the requirement it was tested under."
        for row in rows
        if row["effect"] == SUPERSEDED and row["state"] == STATE.OPEN and row["has_results"]
    )
    return reasons


def lock(lot):
    """Lock every test of the lot, by pk, and return their ids. Call before the lot is locked."""
    tests = AnalyticalTest.objects.select_for_update().filter(lot_id=lot.pk).order_by("pk")
    return [test.pk for test in tests]


def apply(*, actor, lot, requirements, reason, locked):
    """Supersede the lot's tests that the new requirements no longer ask for; return the rows.

    The caller holds the locks taken by ``lock`` (``locked``) and then the lot, signs the
    replacement and advances the lot revision. A test created since ``lock`` ran was not
    locked, so the replacement is refused as stale instead of locking out of order.
    """
    tests = list(
        AnalyticalTest.objects.filter(lot_id=lot.pk).select_related("sample").order_by("pk")
    )
    if [test.pk for test in tests] != list(locked):
        raise ValidationError(STALE)
    rows = effects(lot, requirements, tests)
    if reasons := refusals(lot, rows):
        raise ValidationError(reasons)
    by_pk = {test.pk: test for test in tests}
    for row in rows:
        if row["effect"] != SUPERSEDED:
            continue
        test = by_pk[row["test"]]
        test.state = STATE.SUPERSEDED
        test.revision += 1
        test.save(update_fields=["state", "revision"])
        record_event(
            actor=actor,
            action="test.superseded",
            obj=test,
            before={"state": row["state"]},
            after={
                "state": STATE.SUPERSEDED.value,
                "why": row["why"],
                "result": row["result"],
                "requirement_hash": test.requirement_hash,
            },
            reason=reason,
        )
    return rows
