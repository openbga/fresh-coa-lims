"""The reassessment of a released lot: starting it, testing it apart from the lot's record,
concluding it with a later retest date or with the end of the lot's use, withdrawal, the
database guards and what the certificate says afterwards (synthetic data only)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from analytical import services as analytical
from analytical.contracts import resolve_reassessment
from analytical.models import AnalyticalTest, Investigation
from core.models import AuditEvent, ElectronicSignature
from quality import dates, reassessment
from quality.models import Lot, LotDates, Reassessment
from reporting import services as reporting
from tests.test_integrated_journey import PIN, dispose
from tests.test_result_types_journey import build_world, record, review, run, submit

pytestmark = pytest.mark.django_db(transaction=True)

BASIS = "Retest period 12 months (SOP-SYN-QC-012); shelf life 24 months"
SUITABLE, NOT_SUITABLE = Reassessment.Outcome.SUITABLE, Reassessment.Outcome.NOT_SUITABLE
READINGS = {"identity": "conforms", "salmonella": "absent", "tamc": "<10", "impurity": "4.20"}


def today():
    return timezone.localdate()


def released_world(django_user_model, retest_in=10, expiry_in=400):
    """A lot released with a retest date and an expiry date (synthetic)."""
    world = build_world(django_user_model)
    people = world["people"]
    dates.record_dates(
        actor=people["analyst"],
        lot=world["lot"],
        expected=None,
        reason="Synthetic dates",
        expiry_on=today() + timedelta(days=expiry_in) if expiry_in is not None else None,
        retest_on=today() + timedelta(days=retest_in) if retest_in is not None else None,
        basis=BASIS,
    )
    for test, _ in run(world).values():
        review(world, test)
    world["lot"] = dispose(world, people["approver"])
    return world


@pytest.fixture
def world(django_user_model):
    return released_world(django_user_model)


def fresh(item):
    return type(item).objects.get(pk=item.pk)


def begin(world, who="analyst", reference="SYN-RA-S001", **values):
    return reassessment.start(
        actor=world["people"][who],
        lot=world["lot"],
        reason=values.pop("reason", "Retest date in ten days"),
        sample_reference=reference,
        sampled_on=values.pop("sampled_on", today()),
        quantity=values.pop("quantity", "25"),
        quantity_unit="g",
        containers=values.pop("containers", "SYN-C001; warehouse bay B2"),
    )


def assign(world, item):
    accepted, holds = resolve_reassessment(item)
    assert holds == [], holds
    return {
        test.test_code: test
        for test in analytical.assign_reassessment_tests(
            actor=world["people"]["analyst"],
            reassessment=item,
            reason="Assign the reassessment's tests",
            criteria_hash=analytical.pull_criteria_hash(accepted),
        )
    }


def submit_all(world, item, **readings):
    """Assign, record and submit every test; return {code: (test, investigation)}."""
    out = {}
    for code, test in assign(world, item).items():
        record(world, test, {**READINGS, **readings}[code])
        out[code] = submit(world, test)
    return out


def reviewed(world, item, **readings):
    for test, investigation in submit_all(world, item, **readings).values():
        if investigation is None:
            review(world, test)
    return fresh(item)


def assess(world, investigation):
    analytical.add_entry(
        actor=world["people"]["analyst"],
        investigation=investigation,
        kind="assessment",
        text="Laboratory assessment: no assignable laboratory error found",
    )


def conclude(world, item, outcome, retest_on=None, who="author", reason="Synthetic conclusion"):
    item = fresh(item)
    return reassessment.conclude(
        actor=world["people"][who],
        pin=PIN,
        reassessment=item,
        expected_revision=item.revision,
        outcome=outcome,
        retest_on=retest_on,
        reason=reason,
    )


def lot_record(lot):
    """The released lot's own record, as every reader of the lot sees it."""
    lot = Lot.objects.get(pk=lot.pk)
    return {
        "lot": (lot.state, lot.revision, lot.disposition_evidence),
        "dates": list(LotDates.objects.filter(lot=lot).values()),
        "tests": sorted(AnalyticalTest.objects.filter(lot=lot).values_list("pk", "state")),
        "investigations": Investigation.objects.filter(lot=lot).count(),
        "lot_events": AuditEvent.objects.filter(
            object_type="quality.lot", object_id=str(lot.pk)
        ).count(),
    }


# Starting ---------------------------------------------------------------------------------------


def test_a_released_lot_with_a_retest_date_is_reassessed_on_a_sample_taken_for_it(world):
    item = begin(world)
    assert item.state == "open" and item.label == f"RA-{item.pk}"
    assert item.quantity == Decimal("25") and item.sampled_on == today()
    assert item.dates_basis["retest_on"] == (today() + timedelta(days=10)).isoformat()
    assert item.dates_basis["expiry_on"] == (today() + timedelta(days=400)).isoformat()
    event = AuditEvent.objects.get(action="lot.reassessment_started")
    assert event.actor == world["people"]["analyst"] and event.after["sample_reference"]
    # One open at a time.
    assert reassessment.start_refusal(world["lot"]) == f"{item.label} of this lot is open."
    with pytest.raises(ValidationError, match="is open"):
        begin(world, reference="SYN-RA-S002")


def test_only_analysts_and_quality_start_a_reassessment(world):
    with pytest.raises(PermissionDenied):
        begin(world, who="reviewer")


@pytest.mark.parametrize(
    "values, field",
    [
        ({"reason": " "}, "reason"),
        ({"containers": ""}, "containers"),
        ({"quantity": "0"}, "quantity"),
        ({"quantity": "lots"}, "quantity"),
        ({"sampled_on": None}, "sampled_on"),
    ],
)
def test_starting_states_the_sample(world, values, field):
    with pytest.raises(ValidationError) as caught:
        begin(world, **values)
    assert field in caught.value.message_dict


def test_a_sample_is_not_taken_in_the_future(world):
    with pytest.raises(ValidationError, match="future"):
        begin(world, sampled_on=today() + timedelta(days=1))


def test_a_lot_in_quarantine_is_not_reassessed(django_user_model):
    world = build_world(django_user_model)
    assert reassessment.start_refusal(world["lot"]) == "Only a released lot is reassessed."
    with pytest.raises(ValidationError, match="released"):
        begin(world)
    # Nor does the database accept one.
    with pytest.raises(DatabaseError, match="Only a released lot"), transaction.atomic():
        Reassessment.objects.create(
            lot=world["lot"],
            reason="Direct write",
            sample_reference="SYN-RA-DIRECT",
            sampled_on=today(),
            quantity=1,
            quantity_unit="g",
            containers="SYN-C001",
            dates_basis={},
            started_by=world["people"]["analyst"],
        )


def test_a_lot_without_a_retest_date_or_expired_is_not_reassessed(django_user_model, monkeypatch):
    world = released_world(django_user_model, retest_in=None, expiry_in=30)
    assert "no retest date" in reassessment.start_refusal(world["lot"])
    later = today() + timedelta(days=31)
    monkeypatch.setattr(dates, "today", lambda: later)
    assert "no retest date" in reassessment.start_refusal(world["lot"])


def test_an_expired_lot_is_not_reassessed(django_user_model, monkeypatch):
    world = released_world(django_user_model, retest_in=10, expiry_in=20)
    later = today() + timedelta(days=21)
    monkeypatch.setattr(dates, "today", lambda: later)
    assert "expired after" in reassessment.start_refusal(world["lot"])


# Testing apart from the lot's record ------------------------------------------------------------


def test_the_tests_belong_to_the_reassessment_and_the_lot_record_is_unchanged(world):
    before = lot_record(world["lot"])
    item = begin(world)
    reviewed(world, item)
    tests = AnalyticalTest.objects.filter(reassessment=item, kind="original")
    assert {test.test_code for test in tests} == set(READINGS)
    for test in tests:
        assert test.lot_id is None and test.sample_id is None and test.state == "reviewed"
        assert "/reassess:" in test.spec.source and "synthetic-rt-spec@v1" in test.spec.source
    assigned = AuditEvent.objects.filter(action="test.assigned", after__reassessment=item.pk)
    assert assigned.count() == len(READINGS)
    conclude(world, item, SUITABLE, today() + timedelta(days=180))
    assert lot_record(world["lot"]) == before


def test_a_page_opened_before_the_criteria_changed_assigns_nothing(world):
    item = begin(world)
    with pytest.raises(ValidationError, match="changed since this page was opened"):
        analytical.assign_reassessment_tests(
            actor=world["people"]["analyst"],
            reassessment=item,
            reason="Stale criteria",
            criteria_hash="0" * 64,
        )
    assert not AnalyticalTest.objects.filter(reassessment=item).exists()


def test_a_failing_result_opens_an_investigation_that_holds_no_lot(world):
    item = begin(world)
    submitted = submit_all(world, item, impurity="5.50")
    test, investigation = submitted["impurity"]
    assert investigation is not None and investigation.lot_id is None
    assert fresh(item).revision > item.revision
    assert "is open" in " ".join(reassessment.review(fresh(item)).blockers)


def test_a_test_not_completed_is_repeated_on_the_sample_taken_never_another(world):
    item = begin(world)
    test = assign(world, item)["identity"]

    def not_completed(repeat):
        test.refresh_from_db()
        return analytical.record_not_completed(
            actor=world["people"]["author"],
            pin=PIN,
            test=test,
            expected_revision=test.revision,
            cause="sample",
            reason="Sample container broken",
            repeat=repeat,
        )

    with pytest.raises(ValidationError, match="sample taken for it"):
        not_completed("sample")
    not_completed("same")
    repeat = AnalyticalTest.objects.get(parent=test)
    assert repeat.kind == "repeat" and repeat.reassessment_id == item.pk and repeat.lot_id is None


# Concluding --------------------------------------------------------------------------------------


def test_a_suitable_outcome_gives_the_lot_a_later_retest_date_in_force(world):
    item = begin(world)
    item = reviewed(world, item)
    new_date = today() + timedelta(days=180)
    shown = reassessment.review(item)
    assert shown.outcome == "conforms" and shown.suitable_refusal == ""
    done = conclude(world, item, SUITABLE, new_date)
    assert (done.state, done.outcome, done.retest_on) == ("concluded", SUITABLE, new_date)
    evidence = done.result_evidence
    assert evidence["schema"] == "oq.reassessment-results/1" and evidence["outcome"] == "conforms"
    assert {row["test_code"] for row in evidence["results"]} == set(READINGS)
    assert world["people"]["analyst"].pk in evidence["author_ids"]
    signature = ElectronicSignature.objects.get(
        object_type="quality.reassessment", meaning="reassessed"
    )
    assert signature.signer == world["people"]["author"]
    assert signature.content["retest_on"] == new_date.isoformat()
    found = dates.in_force(world["lot"])
    assert found.retest_on == new_date and found.reassessment == done
    assert found.record.retest_on == today() + timedelta(days=10)  # the release's record stays
    # The lot can be reassessed again later.
    assert reassessment.start_refusal(world["lot"]) is None


def test_whoever_started_tested_or_lacks_quality_cannot_conclude(world):
    item = reviewed(world, begin(world, who="author"))
    new_date = today() + timedelta(days=180)
    for who, error in (("author", PermissionDenied), ("analyst", PermissionDenied)):
        with pytest.raises(error):
            conclude(world, item, SUITABLE, new_date, who=who)
    with pytest.raises(PermissionDenied):
        conclude(world, item, SUITABLE, new_date, who="reviewer")
    assert conclude(world, item, SUITABLE, new_date, who="approver").state == "concluded"


@pytest.mark.parametrize("days, match", [(0, "after today"), (401, "expiry date"), (None, "Enter")])
def test_the_new_retest_date_is_after_today_and_never_after_the_expiry_date(world, days, match):
    item = reviewed(world, begin(world))
    retest_on = None if days is None else today() + timedelta(days=days)
    with pytest.raises(ValidationError, match=match):
        conclude(world, item, SUITABLE, retest_on)
    assert fresh(item).state == "open"
    assert conclude(world, item, SUITABLE, today() + timedelta(days=400)).state == "concluded"


def test_a_conclusion_waits_for_the_results_and_a_stale_page_is_refused(world):
    item = begin(world)
    tests = assign(world, item)
    with pytest.raises(ValidationError, match="Testing is not complete"):
        conclude(world, item, SUITABLE, today() + timedelta(days=90))
    shown = fresh(item)
    record(world, tests["identity"], "conforms")  # advances the reassessment's revision
    with pytest.raises(ValidationError, match="Record changed"):
        reassessment.conclude(
            actor=world["people"]["author"],
            pin=PIN,
            reassessment=shown,
            expected_revision=shown.revision,
            outcome=NOT_SUITABLE,
            retest_on=None,
            reason="Stale page",
        )
    # A result recorded and not submitted is work in progress: its use cannot end over it.
    with pytest.raises(ValidationError, match="Testing is in progress"):
        conclude(world, item, NOT_SUITABLE)


def test_a_confirmed_failure_ends_the_lot_s_use(world):
    item = begin(world)
    submitted = submit_all(world, item, impurity="5.50")
    for code, (test, _) in submitted.items():
        if code != "impurity":
            review(world, test)
    test, investigation = submitted["impurity"]
    review(world, test)
    with pytest.raises(ValidationError, match="is open"):
        conclude(world, item, NOT_SUITABLE)
    assess(world, investigation)
    investigation.refresh_from_db()
    analytical.conclude(
        actor=world["people"]["author"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome=Investigation.Outcome.CONFIRMED,
        assignable_cause="",
        reason="Confirmed out-of-specification impurity",
    )
    shown = reassessment.review(fresh(item))
    assert shown.outcome == "fails" and shown.failed
    with pytest.raises(ValidationError, match="does not meet"):
        conclude(world, item, SUITABLE, today() + timedelta(days=90))
    with pytest.raises(ValidationError, match="not suitable instead"):
        reassessment.withdraw(
            actor=world["people"]["author"],
            pin=PIN,
            reassessment=fresh(item),
            expected_revision=fresh(item).revision,
            reason="Hiding a failure",
        )
    with pytest.raises(ValidationError, match="sets no date"):
        conclude(world, item, NOT_SUITABLE, today() + timedelta(days=90), who="approver")
    done = conclude(world, item, NOT_SUITABLE, who="approver")
    assert done.outcome == NOT_SUITABLE and done.retest_on is None
    assert done.result_evidence["outcome"] == "fails"
    found = dates.in_force(world["lot"])
    assert found.use_ended == done
    assert dates.status_label("released", found.expiry_on, found.retest_on, use_ended=True) == (
        "Use ended",
        "danger",
    )
    assert "ended with" in reassessment.start_refusal(world["lot"])
    # The lot stays released as it was signed, and takes no certificate.
    assert Lot.objects.get(pk=world["lot"].pk).state == "released"
    _, _, blockers = reporting.preview(world["lot"])
    assert any("use ended" in blocker for blocker in blockers)
    # Its tests take no more work.
    with pytest.raises(ValidationError, match="concluded"):
        analytical.record_observation(
            actor=world["people"]["analyst"],
            test=test,
            value=Decimal("1"),
            raw_reference="RAW-SYN",
            reason="Too late",
        )


def test_withdrawal_of_a_reassessment_started_in_error(world):
    item = begin(world)
    assign(world, item)
    with pytest.raises(PermissionDenied):
        reassessment.withdraw(
            actor=world["people"]["reviewer"],
            pin=PIN,
            reassessment=fresh(item),
            expected_revision=fresh(item).revision,
            reason="Started on the wrong lot",
        )
    done = reassessment.withdraw(
        actor=world["people"]["author"],
        pin=PIN,
        reassessment=fresh(item),
        expected_revision=fresh(item).revision,
        reason="Started on the wrong lot",
    )
    assert done.state == "withdrawn" and done.decision_reason == "Started on the wrong lot"
    assert dates.in_force(world["lot"]).reassessment is None
    assert reassessment.start_refusal(world["lot"]) is None
    assert begin(world, reference="SYN-RA-S002").state == "open"


# The database keeps a reassessment as it was concluded ------------------------------------------


def test_the_database_guards_a_reassessment(world):
    item = begin(world)
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        Reassessment.objects.filter(pk=item.pk).update(sample_reference="SYN-OTHER")
    with pytest.raises(DatabaseError, match="cannot be deleted"), transaction.atomic():
        Reassessment.objects.filter(pk=item.pk).delete()
    with pytest.raises(IntegrityError, match="reassessment_steps"), transaction.atomic():
        Reassessment.objects.filter(pk=item.pk).update(state="concluded")
    beyond = today() + timedelta(days=401)
    with pytest.raises(DatabaseError, match="never after the expiry date"), transaction.atomic():
        Reassessment.objects.filter(pk=item.pk).update(
            state="concluded",
            outcome="suitable",
            retest_on=beyond,
            result_evidence={"schema": "x"},
            decided_at=timezone.now(),
            decision_reason="Direct write",
        )
    with pytest.raises(IntegrityError, match="reassessment_one_open"), transaction.atomic():
        Reassessment.objects.create(
            lot=world["lot"],
            reason="Second open",
            sample_reference="SYN-RA-SECOND",
            sampled_on=today(),
            quantity=1,
            quantity_unit="g",
            containers="SYN-C001",
            dates_basis={},
            started_by=world["people"]["analyst"],
        )
    done = conclude(world, reviewed(world, item), SUITABLE, today() + timedelta(days=90))
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        Reassessment.objects.filter(pk=done.pk).update(retest_on=today() + timedelta(days=95))
    # A reassessment's test stays with it: a linked test cannot move to the lot.
    test = AnalyticalTest.objects.filter(reassessment=done).first()
    with pytest.raises(DatabaseError, match="reassessment of the test it follows"):
        with transaction.atomic():
            AnalyticalTest.objects.create(
                pull=None,
                reassessment=None,
                lot=world["lot"],
                sample=world["lot"].samples.first(),
                test_code=test.test_code,
                requirement=test.requirement,
                requirement_hash=test.requirement_hash,
                kind="rerun",
                parent=test,
                created_by=world["people"]["analyst"],
            )


# The certificate after a reassessment -----------------------------------------------------------


def test_the_certificate_prints_the_new_retest_date_and_names_the_reassessment(world, monkeypatch):
    retest = today() + timedelta(days=10)
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: retest)
    monkeypatch.setattr(dates, "today", lambda: retest)
    _, _, blockers = reporting.preview(world["lot"])
    assert any("has been reached" in blocker for blocker in blockers)
    monkeypatch.undo()
    item = reviewed(world, begin(world))
    new_date = today() + timedelta(days=180)
    done = conclude(world, item, SUITABLE, new_date)
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: retest)
    evidence, evidence_hash, blockers = reporting.preview(world["lot"])
    assert blockers == []
    assert evidence["dates"]["retest_on"] == new_date.isoformat()
    assert evidence["dates"]["reassessment"]["label"] == done.label
    assert evidence["dates"]["frozen_at_release"] is True
    # Whoever tested the reassessment is an author of the date the certificate asserts.
    assert world["people"]["analyst"].pk in evidence["authors"]
    report = reporting.issue_report(
        actor=world["people"]["approver"],
        pin=PIN,
        lot=world["lot"],
        recipient="Synthetic recipient",
        evidence_hash=evidence_hash,
        reason="Certificate after reassessment",
    )
    assert report.versions.get(number=1).snapshot["dates"]["reassessment"]["id"] == done.pk


# The lot's record export ------------------------------------------------------------------------


def test_the_lot_record_export_includes_reassessments_and_their_tests(world):
    import json

    from reporting import lot_record
    from tests.test_lot_record_export import section, unpack

    item = conclude(world, reviewed(world, begin(world)), SUITABLE, today() + timedelta(days=120))
    package = lot_record.export_lot_record(
        actor=world["people"]["approver"], lot_pk=world["lot"].pk, purpose="Synthetic review"
    )
    _, _, members = unpack(package)
    record = json.loads(members["record.json"])
    assert [r["id"] for r in section(record, "reassessments")["records"]] == [item.pk]
    tests = AnalyticalTest.objects.filter(reassessment=item).values_list("pk", flat=True)
    assert {r["id"] for r in section(record, "reassessment_tests")["records"]} == set(tests)
    own = {r["id"] for r in section(record, "tests")["records"]}
    assert own.isdisjoint(tests)  # the lot's release testing lists only its own tests
    observed = {r["fields"]["test"] for r in section(record, "observations")["records"]}
    assert set(tests) <= observed
    events = {(e["fields"]["object_type"], e["fields"]["object_id"]) for e in record["audit_trail"]}
    assert ("quality.reassessment", str(item.pk)) in events
    assert all(c["outcome"] == "intact" for c in record["checks"])
