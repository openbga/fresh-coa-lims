"""Expiry and retest dates of a lot: recording and corrections, the database guards, the
release gates, what the release, a rejection and the certificate freeze, and the status of a
released lot (synthetic data only)."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature, RuleSet
from core.services import validate_policy
from quality import dates, rejection
from quality import services as quality
from quality.models import Lot, LotDates
from reporting import evidence as ev
from reporting import services as reporting
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import PIN, dispose
from tests.test_lot_receipt import PIN as STAFF_PIN
from tests.test_lot_receipt import approved_rules, receive, release, staff
from tests.test_result_types_journey import build_world, review, run

pytestmark = pytest.mark.django_db(transaction=True)

BASIS = (
    "Supplier certificate SYN-COA-001 states the expiry date; retest period 12 months "
    "(SOP-SYN-QC-012)"
)


def today():
    return timezone.localdate()


def dated_rules(people, rule="expiry_or_retest", code="synthetic-dated"):
    """An approved rule set that requires dates (created directly: synthetic configuration)."""
    return RuleSet.objects.create(
        code=code,
        segment="chemical",
        author=people["quality"],
        status="approved",
        effective_from=timezone.now() - timedelta(days=1),
        effective_until=timezone.now() + timedelta(days=365),
        policy={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
            "material_dates": rule,
        },
    )


@pytest.fixture
def people(django_user_model):
    return staff(django_user_model)


@pytest.fixture
def lot(people):
    return receive(people, approved_rules(people), on_site_receipt())


def put(people, lot, who="analyst", expected=None, reason="Synthetic dates", **values):
    values = {"expiry_on": None, "retest_on": None, "basis": BASIS} | values
    return dates.record_dates(
        actor=people[who], lot=lot, expected=expected, reason=reason, **values
    )


def fresh(lot):
    return Lot.objects.get(pk=lot.pk)


# The rule set's requirement ---------------------------------------------------------------


def policy(**extra):
    return {
        "required_tests": ["identity"],
        "review_meaning": "reviewed",
        "disposition_meaning": "approved",
        **extra,
    }


@pytest.mark.parametrize("rule", ["expiry", "retest", "expiry_or_retest", "expiry_and_retest"])
def test_a_rule_set_may_require_dates(rule):
    validate_policy(policy(material_dates=rule))


@pytest.mark.parametrize("rule", ["sometimes", "", None, ["expiry"], {"expiry": True}])
def test_a_rule_set_states_its_dates_rule_exactly(rule):
    with pytest.raises(ValidationError, match="material_dates must be one of"):
        validate_policy(policy(material_dates=rule))


# Recording and correcting --------------------------------------------------------------------


def test_dates_are_recorded_and_corrected_keeping_the_record_replaced(people, lot):
    expiry, retest = today() + timedelta(days=400), today() + timedelta(days=200)
    first = put(people, lot, expiry_on=expiry, retest_on=retest)
    assert fresh(lot).revision == lot.revision + 1
    assert dates.current_dates(lot) == first and first.replaces is None
    event = AuditEvent.objects.get(action="lot.dates_recorded")
    assert event.actor == people["analyst"] and event.reason == "Synthetic dates"
    assert event.after["expiry_on"] == expiry.isoformat()
    assert event.after["retest_on"] == retest.isoformat() and not event.before

    corrected = put(
        people,
        lot,
        who="quality",
        expected=first.pk,
        reason="Retest period is 6 months",
        expiry_on=expiry,
        retest_on=today() + timedelta(days=150),
    )
    assert dates.current_dates(lot) == corrected and corrected.replaces == first
    assert LotDates.objects.filter(lot=lot).count() == 2
    first.refresh_from_db()
    assert first.retest_on == retest  # the original is kept as recorded
    event = AuditEvent.objects.get(action="lot.dates_corrected")
    assert event.before["retest_on"] == retest.isoformat()
    assert event.after["replaces"] == first.pk
    assert fresh(lot).revision == lot.revision + 2
    history = dates.history(lot)
    assert [entry["title"] for entry in history] == ["Dates recorded", "Dates corrected"]
    assert history[1]["changes"] == [
        ("Retest date", retest.isoformat(), (today() + timedelta(days=150)).isoformat())
    ]


def test_a_correction_may_leave_the_lot_without_dates(people, lot):
    first = put(people, lot, retest_on=today() + timedelta(days=30))
    none = put(people, lot, expected=first.pk, basis="", reason="Dates recorded on the wrong lot")
    assert not none.stated and dates.current_dates(lot) == none
    # A lot without dates freezes none, as one that never had any.
    assert dates.frozen(lot) is None
    assert dates.disposition_notices(lot) == []


@pytest.mark.parametrize(
    ("values", "field"),
    [
        ({}, "expiry_on"),
        ({"retest_on": date(2030, 6, 1), "expiry_on": date(2030, 5, 31)}, "retest_on"),
        ({"retest_on": date(2030, 6, 1), "basis": "  "}, "basis"),
        ({"retest_on": date(2030, 6, 1), "reason": " "}, "reason"),
    ],
)
def test_incomplete_or_inconsistent_dates_are_refused(people, lot, values, field):
    with pytest.raises(ValidationError) as refused:
        put(people, lot, **values)
    assert field in refused.value.message_dict
    assert not LotDates.objects.exists() and fresh(lot).revision == lot.revision


def test_a_correction_must_change_something_and_follow_the_record_shown(people, lot):
    first = put(people, lot, expiry_on=date(2030, 1, 31))
    with pytest.raises(ValidationError, match="changes nothing"):
        put(people, lot, expected=first.pk, expiry_on=date(2030, 1, 31))
    # A page that showed no dates, or an older record, does not replace dates it never showed.
    with pytest.raises(ValidationError, match="changed after this page was opened"):
        put(people, lot, expiry_on=date(2030, 2, 28))
    second = put(people, lot, expected=first.pk, expiry_on=date(2030, 2, 28))
    with pytest.raises(ValidationError, match="changed after this page was opened"):
        put(people, lot, expected=first.pk, expiry_on=date(2030, 3, 31))
    assert dates.current_dates(lot) == second


@pytest.mark.parametrize("who", ["reviewer", "auditor", "admin"])
def test_only_analysts_and_quality_record_dates(people, lot, who):
    with pytest.raises(PermissionDenied):
        put(people, lot, who=who, expiry_on=date(2030, 1, 31))
    assert not LotDates.objects.exists()


def test_a_lot_out_of_quarantine_takes_no_dates(people, lot, settings):
    release(people, lot, settings)
    with pytest.raises(ValidationError, match="Only lots in quarantine"):
        put(people, lot, expiry_on=date(2030, 1, 31))


def test_the_database_keeps_dates_append_only_and_on_their_lot(people, lot, settings):
    first = put(people, lot, expiry_on=date(2030, 1, 31))
    other = receive(people, lot.rules, on_site_receipt(), number="SYN-R-002")
    for statement in (
        f"UPDATE quality_lotdates SET expiry_on = '2031-01-31' WHERE id = {first.pk}",
        f"DELETE FROM quality_lotdates WHERE id = {first.pk}",
    ):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement)
    # A correction belongs to the lot of the record it replaces.
    with pytest.raises(DatabaseError, match="belongs to the lot"), transaction.atomic():
        LotDates.objects.create(
            lot=other,
            expiry_on=date(2030, 2, 28),
            basis=BASIS,
            reason="Synthetic",
            recorded_by=people["analyst"],
            replaces=first,
        )
    # One original per lot, and a retest date never after the expiry date.
    with pytest.raises(IntegrityError), transaction.atomic():
        LotDates.objects.create(
            lot=lot,
            expiry_on=date(2030, 2, 28),
            basis=BASIS,
            reason="Synthetic",
            recorded_by=people["analyst"],
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        LotDates.objects.create(
            lot=other,
            expiry_on=date(2030, 2, 28),
            retest_on=date(2030, 3, 1),
            basis=BASIS,
            reason="Synthetic",
            recorded_by=people["analyst"],
        )
    # Released: no record is added beside the release.
    release(people, other, settings)
    with pytest.raises(DatabaseError, match="only while the lot is in quarantine"):
        with transaction.atomic():
            LotDates.objects.create(
                lot=other,
                expiry_on=date(2030, 2, 28),
                basis=BASIS,
                reason="Synthetic",
                recorded_by=people["analyst"],
            )


# Release gates ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "values", "missing"),
    [
        ("expiry", {"retest_on": date(2030, 1, 31)}, "an expiry date"),
        ("retest", {"expiry_on": date(2030, 1, 31)}, "a retest date"),
        ("expiry_and_retest", {"expiry_on": date(2030, 1, 31)}, "an expiry date and a retest date"),
        ("expiry_or_retest", None, "an expiry date or a retest date"),
    ],
)
def test_the_release_needs_the_dates_its_rule_set_requires(people, settings, rule, values, missing):
    lot = receive(people, dated_rules(people, rule), on_site_receipt())
    if values:
        put(people, lot, **values)
    expected = f"Rule set synthetic-dated v1 requires {missing} for the lot. Record its dates."
    assert dates.lot_blockers(fresh(lot)) == [expected]
    # The lot record lists exactly what signing checks; the dates come last.
    assert quality.disposition_blockers(fresh(lot))[-1] == expected
    with pytest.raises(ValidationError, match="requires"):
        release(people, lot, settings)
    assert fresh(lot).state == "quarantine"


def test_a_rule_set_without_material_dates_requires_none(people, lot):
    assert dates.required_dates(lot) == []
    assert dates.lot_blockers(lot) == []


def test_the_release_is_refused_after_the_expiry_date_and_from_the_retest_date(
    people, lot, settings
):
    first = put(people, lot, expiry_on=today() - timedelta(days=1))
    assert dates.lot_blockers(fresh(lot)) == [
        f"The lot expired after {(today() - timedelta(days=1)).isoformat()}. An expired lot is "
        "not released."
    ]
    # The expiry date itself is still a day of use; the retest date itself is due.
    second = put(people, lot, expected=first.pk, expiry_on=today(), retest_on=today())
    assert "has been reached" in dates.lot_blockers(fresh(lot))[0]
    with pytest.raises(ValidationError, match="retest date"):
        release(people, lot, settings)
    put(
        people,
        lot,
        expected=second.pk,
        expiry_on=today() + timedelta(days=1),
        retest_on=today() + timedelta(days=1),
    )
    assert dates.lot_blockers(fresh(lot)) == []


def test_status_of_a_lots_dates():
    on = date(2030, 6, 15)
    assert dates.status(None, None, on) == ""
    assert dates.status(date(2030, 6, 15), None, on) == ""  # the expiry date is still usable
    assert dates.status(date(2030, 6, 14), None, on) == dates.EXPIRED
    assert dates.status(None, date(2030, 6, 15), on) == dates.RETEST_DUE
    assert dates.status(date(2030, 6, 14), date(2030, 6, 1), on) == dates.EXPIRED
    assert dates.status_label("rejected", date(2030, 6, 14), None, on) is None
    assert dates.status_label("released", None, date(2030, 6, 1), on) == ("Retest due", "warning")


@pytest.mark.parametrize("days", [-2, -1, 0, 1, 2])
@pytest.mark.parametrize("which", ["expiry_on", "retest_on"])
def test_the_certificate_and_the_lot_agree_on_the_boundary_days(which, days):
    on = date(2030, 6, 15)
    stated = {"expiry_on": None, "retest_on": None, which: on + timedelta(days=days)}
    reached = bool(dates.status(stated["expiry_on"], stated["retest_on"], on))
    shown = {k: v.isoformat() if v else None for k, v in stated.items()}
    assert bool(ev.date_blockers(shown | {"frozen_at_release": True}, on)) == reached


def test_certificate_date_gates():
    frozen = {"frozen_at_release": True, "expiry_on": "2030-06-14", "retest_on": None}
    assert ev.date_blockers(None, date(2030, 6, 15)) == []
    assert ev.date_blockers(frozen, date(2030, 6, 14)) == []
    assert ev.date_blockers(frozen, date(2030, 6, 15)) == [
        "The lot expired after 2030-06-14; no certificate is issued for it."
    ]
    due = {"frozen_at_release": True, "expiry_on": None, "retest_on": "2030-06-15"}
    assert "has been reached" in ev.date_blockers(due, date(2030, 6, 15))[0]
    assert ev.date_blockers(due | {"frozen_at_release": False}, date(2030, 6, 1)) == [
        "The lot's expiry and retest dates are not those its release froze."
    ]


# Native release, rejection and certificate -----------------------------------------------


@pytest.fixture
def world(django_user_model):
    return build_world(django_user_model)


def ready_for_release(world):
    for test, _ in run(world).values():
        review(world, test)
    world["lot"].refresh_from_db()
    return world["lot"]


def test_whoever_recorded_the_dates_cannot_release_the_lot(world):
    people = world["people"]
    put(people, world["lot"], who="author", retest_on=today() + timedelta(days=90))
    ready_for_release(world)
    assert quality.disposition_blockers(fresh(world["lot"])) == []
    assert quality.disposition_denial(people["author"], world["lot"]) == quality.SELF_DISPOSITION
    with pytest.raises(ValidationError, match="dates"):
        dispose(world, people["author"])
    assert dispose(world, people["approver"]).state == "released"


def test_the_release_freezes_the_dates_and_the_certificate_prints_them(world, monkeypatch):
    people = world["people"]
    expiry, retest = today() + timedelta(days=365), today() + timedelta(days=180)
    record = put(people, world["lot"], expiry_on=expiry, retest_on=retest)
    lot = ready_for_release(world)
    notices = quality.disposition_notices(lot)
    assert notices[0].startswith(
        f"The release freezes the lot's expiry date {expiry.isoformat()}, retest date "
        f"{retest.isoformat()} (basis: {BASIS})."
    )
    released = dispose(world, people["approver"])
    frozen = released.disposition_evidence["dates"]
    assert frozen["id"] == record.pk and frozen["recorded_by"] == people["analyst"].pk
    assert (frozen["expiry_on"], frozen["retest_on"]) == (expiry.isoformat(), retest.isoformat())
    signature = ElectronicSignature.objects.get(object_type="quality.lot", meaning="approved")
    assert signature.content["disposition_evidence"]["dates"] == frozen

    evidence, evidence_hash, blockers = reporting.preview(released)
    assert blockers == []
    assert evidence["dates"] == {
        "id": record.pk,
        "expiry_on": expiry.isoformat(),
        "retest_on": retest.isoformat(),
        "basis": BASIS,
        "frozen_at_release": True,
    }
    report = reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=released,
        recipient="Synthetic recipient",
        evidence_hash=evidence_hash,
        reason="Synthetic certificate",
    )
    version = report.versions.get(number=1)
    assert version.snapshot["dates"]["retest_on"] == retest.isoformat()
    html = " ".join(
        render_to_string("reporting/_certificate.html", {"snapshot": version.snapshot}).split()
    )
    assert f'<dt>Expiry date</dt><dd><time datetime="{expiry.isoformat()}">' in html
    assert f'<dt>Retest date</dt><dd><time datetime="{retest.isoformat()}">' in html
    from reporting.tests.test_services import normalized, pdf_text

    spoken = normalized(pdf_text(reporting.read_pdf(actor=people["reviewer"], version=version)))
    # The PDF prints labels in capitals (text-transform).
    assert "EXPIRY DATE" in spoken.upper() and expiry.isoformat() in spoken
    assert "RETEST DATE" in spoken.upper() and retest.isoformat() in spoken

    # From the retest date on, the released lot is due and takes no new certificate.
    later = retest
    monkeypatch.setattr(dates, "today", lambda: later)
    assert dates.status_label("released", expiry, retest) == ("Retest due", "warning")
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: later)
    _, later_hash, blockers = reporting.preview(released)
    assert blockers == [
        f"The lot's retest date, {retest.isoformat()}, has been reached; no certificate is "
        "issued for a lot due for retest."
    ]
    with pytest.raises(ValidationError, match="retest date"):
        reporting.amend_report(
            actor=people["approver"],
            pin=PIN,
            report=report,
            expected_version=1,
            evidence_hash=later_hash,
            reason="Synthetic amendment",
        )


def test_a_lot_without_dates_keeps_the_evidence_it_always_had(world):
    ready_for_release(world)
    released = dispose(world, world["people"]["approver"])
    assert set(released.disposition_evidence) == {"assignment_id", "assignment_hash", "analytical"}
    evidence, _, blockers = reporting.preview(released)
    assert "dates" not in evidence and blockers == []


def test_a_rejection_freezes_the_dates_and_a_cancellation_too(people, settings):
    rules = approved_rules(people)
    first = receive(people, rules, on_site_receipt(), number="SYN-R-REJ")
    record = put(people, first, expiry_on=today() + timedelta(days=60))
    preview = rejection.rejection_preview(fresh(first))
    assert preview.evidence["dates"]["id"] == record.pk
    rejected = rejection.reject_lot(
        actor=people["quality"],
        pin=STAFF_PIN,
        lot=fresh(first),
        expected_revision=fresh(first).revision,
        grounds="other",
        reason="Synthetic rejection",
        basis=preview.basis,
    )
    assert rejected.disposition_evidence["dates"]["expiry_on"] == record.expiry_on.isoformat()
    assert dates.status_label(rejected.state, date(2000, 1, 1), None) is None

    second = receive(people, rules, on_site_receipt(), number="SYN-R-CAN")
    assert "dates" not in rejection.cancellation_preview(second).evidence


# Races, stale pages and independence ------------------------------------------------------


def test_recording_dates_and_releasing_cannot_both_apply(people, settings, monkeypatch):
    """Whichever takes the lot first wins; the other is refused, never applied on top."""
    import core.services as signing
    from laboratory.tests.helpers import run_interleaved
    from tests.test_lot_receipt import with_reviewed_result

    rules = approved_rules(people)

    def release_of(target):
        return lambda: quality.dispose_lot(
            actor=people["quality"],
            pin=STAFF_PIN,
            lot=target,
            expected_revision=target.revision,
            reason="Synthetic disposition",
        )

    def dates_of(target):
        return lambda: put(people, target, retest_on=today() + timedelta(days=30))

    # The dates hold the lot first: the release signs a revision that has moved on.
    lot = with_reviewed_result(people, receive(people, rules, on_site_receipt()), settings)
    shown = lot.revision
    outcome = run_interleaved(monkeypatch, dates, "record_event", dates_of(lot), release_of(lot))
    assert isinstance(outcome["first"], LotDates)
    assert "Record changed" in outcome["second"].messages[0]
    assert (fresh(lot).state, fresh(lot).revision) == ("quarantine", shown + 1)
    assert not ElectronicSignature.objects.filter(object_type="quality.lot").exists()

    # The release holds the lot first: the dates find it released.
    other = with_reviewed_result(
        people, receive(people, rules, on_site_receipt(), number="SYN-R-002"), settings
    )
    outcome = run_interleaved(
        monkeypatch, signing, "record_event", release_of(other), dates_of(other)
    )
    assert outcome["first"].state == "released"
    assert dates.NOT_QUARANTINED in outcome["second"].messages[0]
    assert not LotDates.objects.filter(lot=other).exists()


def test_a_rejection_page_opened_before_the_dates_changed_signs_nothing(people):
    lot = receive(people, approved_rules(people), on_site_receipt())
    preview = rejection.rejection_preview(fresh(lot))
    shown = fresh(lot).revision
    put(people, lot, expiry_on=today() + timedelta(days=60))
    with pytest.raises(ValidationError, match="Record changed"):
        rejection.reject_lot(
            actor=people["quality"],
            pin=STAFF_PIN,
            lot=fresh(lot),
            expected_revision=shown,
            grounds="other",
            reason="Synthetic rejection",
            basis=preview.basis,
        )
    # The page's revision alone is not enough: what it showed must be what is signed.
    with pytest.raises(ValidationError, match="changed after this page was opened"):
        rejection.reject_lot(
            actor=people["quality"],
            pin=STAFF_PIN,
            lot=fresh(lot),
            expected_revision=fresh(lot).revision,
            grounds="other",
            reason="Synthetic rejection",
            basis=preview.basis,
        )
    assert fresh(lot).state == "quarantine"


def test_whoever_recorded_the_dates_cannot_reject_or_cancel_the_lot(people):
    lot = receive(people, approved_rules(people), on_site_receipt())
    put(people, lot, who="quality", expiry_on=today() + timedelta(days=60))
    assert rejection.rejection_denial(people["quality"], fresh(lot)) == rejection.SELF_REJECTION
    assert (
        rejection.cancellation_denial(people["quality"], fresh(lot)) == rejection.SELF_CANCELLATION
    )
    with pytest.raises(ValidationError, match="expiry and retest dates you recorded"):
        rejection.reject_lot(
            actor=people["quality"],
            pin=STAFF_PIN,
            lot=fresh(lot),
            expected_revision=fresh(lot).revision,
            grounds="other",
            reason="Synthetic rejection",
            basis=rejection.rejection_preview(fresh(lot)).basis,
        )


def test_whoever_recorded_the_dates_cannot_issue_the_certificate(world):
    from django.core.exceptions import PermissionDenied as Denied

    people = world["people"]
    put(people, world["lot"], who="author", retest_on=today() + timedelta(days=90))
    ready_for_release(world)
    released = dispose(world, people["approver"])
    evidence, evidence_hash, blockers = reporting.preview(released)
    assert blockers == [] and people["author"].pk in evidence["authors"]
    with pytest.raises(Denied, match="records you authored"):
        reporting.issue_report(
            actor=people["author"],
            pin=PIN,
            lot=released,
            recipient="Synthetic recipient",
            evidence_hash=evidence_hash,
            reason="Synthetic certificate",
        )


def test_a_lot_released_on_the_manual_path_keeps_its_dates_on_the_certificate(people, settings):
    lot = receive(people, approved_rules(people), on_site_receipt())
    put(people, lot, retest_on=today() + timedelta(days=90))
    released = release(people, lot, settings)
    assert released.disposition_evidence == {}  # the manual path freezes no native evidence
    evidence, _, blockers = reporting.preview(released)
    assert evidence["dates"]["frozen_at_release"] is None
    assert blockers == []


def test_the_lot_record_export_holds_every_dates_record(people):
    import json

    from reporting import lot_record
    from tests.test_lot_record_export import section, unpack

    lot = receive(people, approved_rules(people), on_site_receipt())
    first = put(people, lot, expiry_on=today() + timedelta(days=60))
    second = put(people, lot, expected=first.pk, expiry_on=today() + timedelta(days=90))
    package = lot_record.export_lot_record(
        actor=people["auditor"], lot_pk=lot.pk, purpose="Synthetic inspection request"
    )
    _, _, members = unpack(package)
    records = section(json.loads(members["record.json"]), "dates")["records"]
    assert [r["id"] for r in records] == [first.pk, second.pk]
    assert records[1]["fields"]["replaces"] == first.pk
    assert records[0]["fields"]["expiry_on"] == (today() + timedelta(days=60)).isoformat()


def test_whoever_recorded_the_dates_cannot_cancel_the_lot_or_decide_its_requirements(people):
    from sampling import services as sampling

    lot = receive(people, approved_rules(people), on_site_receipt())
    put(people, lot, who="quality", expiry_on=today() + timedelta(days=60))
    assert sampling.decision_denial(people["quality"], fresh(lot)) == sampling.SELF_DECISION
    assert sampling.replacement_denial(people["quality"], fresh(lot)) == sampling.SELF_REPLACEMENT
    with pytest.raises(ValidationError, match="Another quality person must sign"):
        rejection.cancel_receipt(
            actor=people["quality"],
            pin=STAFF_PIN,
            lot=fresh(lot),
            expected_revision=fresh(lot).revision,
            reason="Synthetic: recorded twice",
            basis=rejection.cancellation_preview(fresh(lot)).basis,
        )
    assert fresh(lot).state == "quarantine"
