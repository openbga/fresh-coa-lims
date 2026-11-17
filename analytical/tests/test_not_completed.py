"""The record that a test cannot be completed, against what the independent review proved:
rounding never hides a failure, its lock order meets batch rejection without a deadlock, the
people an investigation excludes are excluded, and a routine sample is never taken as a
stand-in. Uses the synthetic fixture provider and bench (see conftest)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from analytical import gates, services
from analytical.models import AnalyticalTest, Investigation, QCBatch
from laboratory.tests.helpers import run_interleaved
from quality.models import Lot
from quality.services import add_sample

from .conftest import PIN, fresh, pass_qc, record, review, submit

pytestmark = pytest.mark.django_db(transaction=True)


def not_completed(people, test, who="quality2", **changes):
    test = fresh(test)
    kwargs = {
        "actor": people[who],
        "pin": PIN,
        "test": test,
        "expected_revision": test.revision,
        "cause": "equipment",
        "reason": "Synthetic: the balance failed its daily check",
    }
    kwargs.update(changes)
    return services.record_not_completed(**kwargs)


def test_a_reading_that_fails_once_rounded_opens_an_investigation(people, make_lot):
    _, sample = make_lot(number="SYN-RND", tests=("impurity",))
    (test,), _ = services.assign_tests(actor=people["analyst"], sample=sample, reason="Assign")
    record(people, test, "0.095")  # below "< 0.10" as recorded, 0.10 once rounded to 2 places
    spec = fresh(test).spec
    assert spec.conforms(Decimal("0.095")) and spec.fails_alone(Decimal("0.095"))
    assert spec.evaluate([Decimal("0.095")])[3] is False
    with pytest.raises(ValidationError, match="investigation decides"):
        not_completed(people, test, repeat="same")
    closed = not_completed(people, test)
    assert closed.not_completed_record["outside_limits"] == ["0.095"]
    assert Investigation.objects.filter(test=closed).exists()
    assert not AnalyticalTest.objects.filter(parent=closed).exists()


def _retest_in_failed_batch(people, assigned):
    _, _, tests = assigned
    first = services.create_batch(
        actor=people["analyst2"], number="SYN-B1", method_code="SYN-HPLC", reason="Run"
    )
    services.assign_to_batch(
        actor=people["analyst"], test=tests["assay"], batch=first, reason="Run"
    )
    pass_qc(people, first)
    record(people, tests["assay"], "106.0", "106.2")
    _, investigation = submit(people, tests["assay"])
    review(people, tests["assay"])
    services.add_entry(
        actor=people["reviewer"], investigation=investigation, kind="assessment", text="Checked"
    )
    investigation.refresh_from_db()
    services.authorize_retest(
        actor=people["quality"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        kind="retest",
        reason="Plan",
    )
    retest = investigation.tests.get()
    second = services.create_batch(
        actor=people["analyst2"], number="SYN-B2", method_code="SYN-HPLC", reason="Run"
    )
    services.assign_to_batch(actor=people["analyst"], test=retest, batch=second, reason="Run")
    pass_qc(people, second, control="90.0")  # the control fails
    assert fresh(second).qc_status()[0] == "failed"
    return investigation, retest, second


def _reject(people, batch):
    batch = QCBatch.objects.get(pk=batch.pk)
    return services.reject_batch(
        actor=people["reviewer2"],
        pin=PIN,
        batch=batch,
        expected_revision=batch.revision,
        reason="Control failed",
    )


@pytest.mark.parametrize("other", ["not_completed", "conclude"])
def test_batch_rejection_and_the_investigation_s_transitions_do_not_deadlock(
    people, assigned, monkeypatch, other
):
    investigation, retest, batch = _retest_in_failed_batch(people, assigned)
    shown_test = fresh(retest).revision
    shown_investigation = Investigation.objects.get(pk=investigation.pk).revision

    def second():
        if other == "not_completed":
            return not_completed(people, retest, expected_revision=shown_test)
        return services.conclude(
            actor=people["quality2"],
            pin=PIN,
            investigation=Investigation.objects.get(pk=investigation.pk),
            expected_revision=shown_investigation,
            outcome="confirmed",
            assignable_cause="",
            reason="Confirmed",
        )

    # Batch rejection holds the batch, the investigation and the retest when it reaches the
    # lots; the other transition queues on the investigation and finds the work changed.
    outcome = run_interleaved(
        monkeypatch, services, "_lock_lots", lambda: _reject(people, batch), second, pause=1.0
    )
    assert not any("deadlock" in str(value) for value in outcome.values()), outcome
    assert fresh(retest).state == AnalyticalTest.State.INVALIDATED
    assert isinstance(outcome["second"], ValidationError)


def test_who_may_not_conclude_an_investigation_may_not_close_its_retest(people, assigned):
    _, _, tests = assigned
    batch = services.create_batch(
        actor=people["analyst2"], number="SYN-B1", method_code="SYN-HPLC", reason="Run"
    )
    services.assign_to_batch(
        actor=people["analyst"], test=tests["assay"], batch=batch, reason="Run"
    )
    pass_qc(people, batch)
    record(people, tests["assay"], "106.0", "106.2", who="multi")
    _, investigation = submit(people, tests["assay"], who="multi")
    review(people, tests["assay"])
    services.add_entry(
        actor=people["quality2"], investigation=investigation, kind="assessment", text="Checked"
    )
    investigation.refresh_from_db()
    services.authorize_retest(
        actor=people["quality"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        kind="retest",
        reason="Plan",
    )
    retest = investigation.tests.get()
    # The author of the result investigated, and the author of its assessment.
    for who in ("multi", "quality2"):
        with pytest.raises(ValidationError, match="Another quality person"):
            not_completed(people, retest, who=who)
    assert not_completed(people, retest, who="quality").state == "not_completed"


def test_a_sample_recorded_before_the_test_is_not_a_stand_in(people, make_lot):
    lot, first = make_lot(number="SYN-ROUTINE")
    routine = add_sample(
        actor=people["analyst"],
        lot=lot,
        reference="SYN-ROUTINE-S2",
        collected_at=timezone.now(),
        reason="Second container, routine",
    )
    created, _ = services.assign_tests(actor=people["analyst"], sample=first, reason="Assign")
    identity = next(test for test in created if test.test_code == "identity")
    assert list(services.repeat_samples(fresh(identity))) == []
    with pytest.raises(ValidationError, match="recorded after this test was assigned"):
        not_completed(people, identity, repeat="sample", sample=routine)
    blockers = gates.lot_blockers(Lot.objects.get(pk=lot.pk))
    assert any("SYN-ROUTINE-S2 has no assay" in item for item in blockers)
    # A sample recorded afterwards qualifies, whatever sampling time was entered for it.
    later = add_sample(
        actor=people["analyst"],
        lot=lot,
        reference="SYN-ROUTINE-S3",
        collected_at=fresh(identity).created_at - timedelta(hours=2),
        reason="Taken after the first sample was lost",
    )
    assert list(services.repeat_samples(fresh(identity))) == [later]


def test_a_long_trigger_is_shortened_to_fit():
    limit = Investigation._meta.get_field("trigger").max_length
    shortened = services.investigation_trigger("Out-of-limit " + "9" * 400)
    assert len(shortened) == limit and shortened.endswith("…")
    assert services.investigation_trigger("short") == "short"
