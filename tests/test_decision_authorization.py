"""Qualifications for authorizing the decisions a rule set reserves (OQ-004): the release of a
lot, the conclusion that reassessed material stays in use, and the issue and amendment of its
certificates. The qualification relied on is frozen with the signed decision; a signer without
one is refused before the PIN is checked and again under the locks; a revocation serializes with
the decision; rejection, cancellation, the end of use and withdrawal are not reserved
(synthetic data only)."""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import ElectronicSignature, PINCredential
from core.services import approve_rule, save_rule, validate_policy
from laboratory import eligibility
from laboratory import services as laboratory
from laboratory.models import Qualification
from laboratory.tests.helpers import run_interleaved
from quality import authority, dates, reassessment
from quality import services as quality
from quality.models import Lot, Reassessment
from reporting import services as reporting
from reporting.models import Report
from tests.test_integrated_journey import PIN, dispose
from tests.test_reassessment import BASIS, assign, begin, fresh
from tests.test_reassessment import conclude as conclude_reassessment
from tests.test_result_types_journey import build_world, record, review, run, submit

pytestmark = pytest.mark.django_db(transaction=True)

RELEASE_ACTIVITY = "Synthetic-QC-Release"
COA_ACTIVITY = "synthetic-coa-signing"
SITE_ACTIVITY = "synthetic-site-release"
SITE_COA = "synthetic-site-coa"
RESERVED = {"authorization": {"release": RELEASE_ACTIVITY, "certificate": COA_ACTIVITY}}
WRONG_PIN = "00000000"
READINGS = {"identity": "conforms", "salmonella": "absent", "tamc": "<10", "impurity": "4.20"}


def today():
    return timezone.localdate()


def ready(world):
    """Every test reviewed: the lot awaits its release."""
    for test, _ in run(world).values():
        review(world, test)
    world["lot"].refresh_from_db()
    return world


@pytest.fixture
def world(django_user_model):
    return ready(build_world(django_user_model, extra_policy=RESERVED))


@pytest.fixture
def plain_world(django_user_model):
    return ready(build_world(django_user_model))


def qualify(world, who, activity, work, *, recorder="author", approver="analyst", **dates):
    people = world["people"]
    recorded = laboratory.record_qualification(
        actor=people[recorder],
        user=people[who],
        activity=activity,
        work=work,
        evidence_ref="AUTH-SYN-001 rev 1",
        valid_from=dates.get("valid_from", today() - timedelta(days=1)),
        valid_until=dates.get("valid_until", today() + timedelta(days=365)),
        reason="Synthetic authorization",
    )
    return laboratory.approve_qualification(
        actor=people[approver],
        pin=PIN,
        qualification=recorded,
        expected_revision=recorded.revision,
        reason="Independent review of the authorization",
    )


def revoke(world, held, who="author"):
    held.refresh_from_db()
    return laboratory.revoke_qualification(
        actor=world["people"][who],
        pin=PIN,
        qualification=held,
        expected_revision=held.revision,
        reason="Authorization withdrawn",
    )


def release(world, who="approver", pin=PIN):
    lot = Lot.objects.get(pk=world["lot"].pk)
    return quality.dispose_lot(
        actor=world["people"][who],
        pin=pin,
        lot=lot,
        expected_revision=lot.revision,
        reason="Synthetic independent QC disposition",
    )


def failures(person):
    return PINCredential.objects.get(user=person).failures


def issue(world, who="approver", pin=PIN):
    lot = Lot.objects.get(pk=world["lot"].pk)
    _, evidence_hash, blockers = reporting.preview(lot)
    assert blockers == [], blockers
    return reporting.issue_report(
        actor=world["people"][who],
        pin=pin,
        lot=lot,
        recipient="Synthetic recipient",
        evidence_hash=evidence_hash,
        reason="Certificate for the synthetic lot",
    )


def amend(world, report, who="approver", pin=PIN):
    report = Report.objects.get(pk=report.pk)
    _, evidence_hash, _ = reporting.preview(report.lot)
    return reporting.amend_report(
        actor=world["people"][who],
        pin=pin,
        report=report,
        expected_version=report.version_count,
        evidence_hash=evidence_hash,
        reason="Corrected remarks",
        remarks="Synthetic amended remarks",
    )


# The rule set's reservation ------------------------------------------------------------------


def base_policy(**extra):
    return {
        "required_tests": ["identity"],
        "review_meaning": "reviewed",
        "disposition_meaning": "approved",
        **extra,
    }


@pytest.mark.parametrize(
    "reserved",
    [
        {"release": "qc-release"},
        {"certificate": "coa"},
        {"release": "qc-release", "certificate": "coa"},
    ],
)
def test_a_rule_set_may_reserve_release_and_certificates(reserved):
    validate_policy(base_policy(authorization=reserved))


@pytest.mark.parametrize(
    "reserved",
    [
        {},
        [],
        "qc-release",
        {"rejection": "qc"},
        {"release": ""},
        {"release": " qc-release"},
        {"release": 7},
        {"release": "x" * 121},
    ],
)
def test_a_malformed_reservation_is_refused(reserved):
    with pytest.raises(ValidationError, match="authorization must name"):
        validate_policy(base_policy(authorization=reserved))


def test_a_rule_set_without_it_reserves_nothing(plain_world):
    lot = plain_world["lot"]
    assert authority.reserved(lot, authority.RELEASE) == []
    assert authority.reserved(lot, authority.CERTIFICATE) == []
    assert authority.refusal(plain_world["people"]["approver"], lot, authority.RELEASE) == ""


def test_reservations_name_the_activity_and_the_rule_set(world):
    rules = world["lot"].rules
    assert authority.reserved(world["lot"], authority.RELEASE) == [
        {
            "activity": RELEASE_ACTIVITY,
            "rule_sets": [{"id": rules.pk, "code": rules.code, "version": rules.version}],
        }
    ]
    text = authority.requirement_text(
        authority.reserved(world["lot"], authority.CERTIFICATE)[0], authority.CERTIFICATE
    )
    assert text == (
        f"Rule set {rules.code} v{rules.version} reserves issuing certificates for people "
        f"qualified for “{COA_ACTIVITY}”."
    )


# Qualifications for authorizing a decision ----------------------------------------------------


def test_a_qualification_for_release_is_recorded_only_for_a_quality_person(world):
    people = world["people"]
    with pytest.raises(ValidationError, match="signed with the quality role"):
        laboratory.record_qualification(
            actor=people["author"],
            user=people["reviewer"],
            activity=RELEASE_ACTIVITY,
            work=Qualification.Work.RELEASE,
            evidence_ref="AUTH-SYN-002",
            valid_from=today(),
            valid_until=today() + timedelta(days=30),
            reason="Synthetic",
        )
    with pytest.raises(ValidationError, match="issued with the quality role"):
        laboratory.record_qualification(
            actor=people["author"],
            user=people["reviewer"],
            activity=COA_ACTIVITY,
            work=Qualification.Work.CERTIFY,
            evidence_ref="AUTH-SYN-002",
            valid_from=today(),
            valid_until=today() + timedelta(days=30),
            reason="Synthetic",
        )
    # A qualification to review is still recorded for a reviewer.
    laboratory.record_qualification(
        actor=people["author"],
        user=people["reviewer"],
        activity=RELEASE_ACTIVITY,
        work=Qualification.Work.REVIEW,
        evidence_ref="AUTH-SYN-002",
        valid_from=today(),
        valid_until=today() + timedelta(days=30),
        reason="Synthetic",
    )


def test_an_instrument_is_never_qualified_to_authorize(world):
    from laboratory.models import Equipment

    equipment = Equipment.objects.create(
        asset_id="SYN-AUTH-EQ",
        description="Synthetic balance",
        category="balance",
        created_by=world["people"]["author"],
    )
    with pytest.raises(ValidationError, match="reviews nothing"):
        laboratory.record_qualification(
            actor=world["people"]["author"],
            equipment=equipment,
            activity=RELEASE_ACTIVITY,
            work=Qualification.Work.RELEASE,
            evidence_ref="AUTH-SYN-003",
            valid_from=today(),
            valid_until=today() + timedelta(days=30),
            reason="Synthetic",
        )


def test_one_kind_of_qualification_never_stands_for_another(world):
    people = world["people"]
    for work in ("perform", "review", "certify"):
        qualify(world, "approver", RELEASE_ACTIVITY, work)
    approver = people["approver"]
    assert authority.refusal(approver, world["lot"], authority.RELEASE).startswith(
        f"Rule set {world['lot'].rules.code} v1 reserves release decisions"
    )
    finding = laboratory.authority_finding(
        actor=approver, activity=RELEASE_ACTIVITY, work=Qualification.Work.RELEASE
    )
    assert not finding.ok
    assert finding.reasons == (
        f"No approved, current qualification for release decisions in “{RELEASE_ACTIVITY}”.",
    )
    with pytest.raises(ValueError):
        laboratory.authority_finding(actor=approver, activity=RELEASE_ACTIVITY, work="review")


# The release ---------------------------------------------------------------------------------


def test_the_release_is_refused_without_the_qualification_it_is_reserved_for(world):
    with pytest.raises(ValidationError, match="You hold no approved, current qualification"):
        release(world, pin=WRONG_PIN)
    # Refused before the PIN was checked: a wrong PIN counts nothing against the signer.
    assert failures(world["people"]["approver"]) == 0
    lot = Lot.objects.get(pk=world["lot"].pk)
    assert lot.state == "quarantine" and lot.disposition_evidence == {}
    assert not ElectronicSignature.objects.filter(
        object_type="quality.lot", object_id=str(lot.pk), meaning="approved"
    ).exists()


def test_the_release_freezes_the_qualification_it_relies_on(world):
    # Matched without regard to case, as every qualification is.
    held = qualify(world, "approver", RELEASE_ACTIVITY.lower(), "release")
    lot = release(world)
    rules = lot.rules
    expected = [
        {
            "activity": RELEASE_ACTIVITY,
            "rule_sets": [{"id": rules.pk, "code": rules.code, "version": rules.version}],
            "qualification": held.pk,
        }
    ]
    assert lot.state == "released"
    assert lot.disposition_evidence["authorization"] == expected
    signature = ElectronicSignature.objects.get(
        object_type="quality.lot", object_id=str(lot.pk), meaning="approved"
    )
    assert signature.content["disposition_evidence"]["authorization"] == expected
    assert authority.relied_on(held) == [
        ("Release", lot.number, f"/lots/{lot.pk}/"),
    ]


def test_a_lot_whose_rule_sets_reserve_nothing_keeps_its_evidence_shape(plain_world):
    lot = dispose(plain_world, plain_world["people"]["approver"])
    assert lot.state == "released"
    assert "authorization" not in lot.disposition_evidence


@pytest.mark.parametrize("state", ["recorded", "revoked", "expired", "later"])
def test_a_qualification_not_in_force_does_not_authorize(world, state, monkeypatch):
    people = world["people"]
    if state == "recorded":
        laboratory.record_qualification(
            actor=people["author"],
            user=people["approver"],
            activity=RELEASE_ACTIVITY,
            work="release",
            evidence_ref="AUTH-SYN-004",
            valid_from=today(),
            valid_until=today() + timedelta(days=30),
            reason="Synthetic",
        )
    elif state == "revoked":
        revoke(world, qualify(world, "approver", RELEASE_ACTIVITY, "release"))
    elif state == "expired":
        qualify(world, "approver", RELEASE_ACTIVITY, "release")
    else:
        qualify(
            world,
            "approver",
            RELEASE_ACTIVITY,
            "release",
            valid_from=today() + timedelta(days=5),
            valid_until=today() + timedelta(days=30),
        )
    if state == "expired":
        # Validity is frozen with the record: the release is signed after its last valid day.
        real = timezone

        class Later:
            @staticmethod
            def now():
                return real.now() + timedelta(days=400)

            localdate = staticmethod(real.localdate)

        monkeypatch.setattr(eligibility, "timezone", Later)
    with pytest.raises(ValidationError, match="You hold no approved, current qualification"):
        release(world)


def test_the_preflight_and_the_lock_agree_on_a_wrong_activity(world):
    qualify(world, "approver", "synthetic-other-release", "release")
    approver = world["people"]["approver"]
    reason = authority.refusal(approver, world["lot"], authority.RELEASE)
    assert RELEASE_ACTIVITY in reason
    with pytest.raises(ValidationError) as refused:
        release(world)
    assert refused.value.messages == [reason]


def test_every_rule_set_of_the_lot_asks_for_its_own_activity(django_user_model):
    world = build_world(django_user_model, extra_policy=RESERVED)
    people = world["people"]
    start, end = timezone.now() - timedelta(days=1), timezone.now() + timedelta(days=365)
    site = save_rule(
        actor=people["author"],
        code="synthetic-site-rules",
        segment="chemical",
        policy=base_policy(
            applies_to={"materials": ["synthetic-rt-material"]},
            authorization={"release": SITE_ACTIVITY, "certificate": SITE_COA},
        ),
        effective_from=start,
        effective_until=end,
        reason="Synthetic site rule set",
    )
    site = approve_rule(
        actor=people["approver"],
        pin=PIN,
        rule=site,
        expected_revision=site.revision,
        reason="Independent synthetic policy review",
    )
    ready(world)
    first = qualify(world, "approver", RELEASE_ACTIVITY, "release")
    reason = authority.refusal(people["approver"], world["lot"], authority.RELEASE)
    assert reason == (
        "Rule set synthetic-site-rules v1 reserves release decisions for people qualified for "
        f"“{SITE_ACTIVITY}”. You hold no approved, current qualification for it."
    )
    with pytest.raises(ValidationError, match=SITE_ACTIVITY):
        release(world)
    second = qualify(world, "approver", SITE_ACTIVITY, "release")
    lot = release(world)
    assert [item["qualification"] for item in lot.disposition_evidence["authorization"]] == [
        first.pk,
        second.pk,
    ]
    assert lot.disposition_evidence["authorization"][1]["rule_sets"] == [
        {"id": site.pk, "code": "synthetic-site-rules", "version": 1}
    ]
    # Certificates likewise: the lot's own activity and the additional rule set's.
    world["lot"] = lot
    qualify(world, "approver", COA_ACTIVITY, "certify")
    with pytest.raises(PermissionDenied, match=SITE_COA):
        issue(world)
    qualify(world, "approver", SITE_COA, "certify")
    report = issue(world)
    frozen = report.versions.get(number=1).snapshot["report"]["authorization"]
    assert [item["activity"] for item in frozen] == [COA_ACTIVITY, SITE_COA]


def test_rejection_is_not_reserved(world):
    from quality import rejection

    lot = Lot.objects.get(pk=world["lot"].pk)
    rejected = rejection.reject_lot(
        actor=world["people"]["approver"],
        pin=PIN,
        lot=lot,
        expected_revision=lot.revision,
        grounds="results",
        reason="Synthetic rejection by a quality person without a release qualification",
        reference="NCR-SYN-AUTH",
        basis=rejection.rejection_preview(lot).basis,
    )
    assert rejected.state == "rejected"


def test_the_release_locks_the_qualifications_it_relies_on(world):
    qualify(world, "approver", RELEASE_ACTIVITY, "release")
    with CaptureQueriesContext(connection) as queries:
        release(world)
    assert any(
        "laboratory_qualification" in q["sql"] and "FOR UPDATE" in q["sql"]
        for q in queries.captured_queries
    ), "the release must lock the signer's qualifications before reading them"
    with pytest.raises(RuntimeError):
        laboratory.authority_finding(
            actor=world["people"]["approver"],
            activity=RELEASE_ACTIVITY,
            work=Qualification.Work.RELEASE,
            lock=True,
        )


def test_a_revocation_after_the_page_was_shown_is_seen_under_the_lock(world, monkeypatch):
    held = qualify(world, "approver", RELEASE_ACTIVITY, "release")
    monkeypatch.setattr(authority, "refusal", lambda *args, **kwargs: "")
    revoke(world, held)
    with pytest.raises(ValidationError, match="You hold no approved, current qualification"):
        release(world)
    assert Lot.objects.get(pk=world["lot"].pk).state == "quarantine"


def test_a_revocation_signed_during_the_release_waits_for_it(world, monkeypatch):
    held = qualify(world, "approver", RELEASE_ACTIVITY, "release")
    # The unlocked check before the PIN is passed by; the interleaving starts at the locked one.
    monkeypatch.setattr(authority, "refusal", lambda *args, **kwargs: "")
    outcome = run_interleaved(
        monkeypatch,
        laboratory,
        "authority_eligibility",
        lambda: release(world),
        lambda: revoke(world, held),
    )
    released, revoked = outcome["first"], outcome["second"]
    assert not isinstance(released, Exception), released
    assert not isinstance(revoked, Exception), revoked
    assert released.disposition_evidence["authorization"][0]["qualification"] == held.pk
    signed = ElectronicSignature.objects.get(
        object_type="quality.lot", object_id=str(released.pk), meaning="approved"
    )
    assert revoked.state == "revoked" and revoked.revoked_at > signed.signed_at


# Certificates ----------------------------------------------------------------------------------


@pytest.fixture
def released(world):
    qualify(world, "approver", RELEASE_ACTIVITY, "release")
    world["lot"] = release(world)
    return world


def test_a_release_qualification_does_not_issue_certificates(released):
    approver = released["people"]["approver"]
    with pytest.raises(PermissionDenied, match="reserves issuing certificates"):
        issue(released, pin=WRONG_PIN)
    # Refused before the PIN was checked and before a certificate record was opened.
    assert failures(approver) == 0
    assert not Report.objects.exists()


def test_the_certificate_freezes_the_qualification_it_relies_on(released):
    # Matched without regard to case.
    held = qualify(released, "approver", COA_ACTIVITY.upper(), "certify")
    with CaptureQueriesContext(connection) as queries:
        report = issue(released)
    assert any(
        "laboratory_qualification" in q["sql"] and "FOR UPDATE" in q["sql"]
        for q in queries.captured_queries
    ), "issuing must lock the signer's qualifications before reading them"
    version = report.versions.get(number=1)
    frozen = version.snapshot["report"]["authorization"]
    assert [item["qualification"] for item in frozen] == [held.pk]
    assert frozen[0]["activity"] == COA_ACTIVITY
    # The signature binds the snapshot; the certificate's data and PDF state nothing about it.
    assert report.current_snapshot_hash == version.snapshot_hash
    assert b"authorization" not in bytes(version.data)
    assert authority.relied_on(held) == [
        ("Certificate issued", f"{report.number} version 1", f"/reports/{report.pk}/versions/1/")
    ]


def test_an_amendment_needs_the_qualification_too(released):
    people = released["people"]
    held = qualify(released, "approver", COA_ACTIVITY, "certify")
    report = issue(released)
    # Another quality person without it is refused before the PIN is checked.
    with pytest.raises(PermissionDenied, match="reserves issuing certificates"):
        amend(released, report, who="author", pin=WRONG_PIN)
    assert failures(people["author"]) == 0
    revoke(released, held, who="author")
    with pytest.raises(PermissionDenied, match="reserves issuing certificates"):
        amend(released, report)
    renewed = qualify(released, "approver", COA_ACTIVITY, "certify")
    amended = amend(released, report)
    version = amended.versions.get(number=2)
    assert version.snapshot["report"]["authorization"][0]["qualification"] == renewed.pk


def test_withdrawal_is_not_reserved(released):
    people = released["people"]
    held = qualify(released, "approver", COA_ACTIVITY, "certify")
    report = issue(released)
    revoke(released, held, who="author")
    report = Report.objects.get(pk=report.pk)
    withdrawn = reporting.withdraw_report(
        actor=people["approver"],
        pin=PIN,
        report=report,
        expected_revision=report.revision,
        reason="Synthetic withdrawal",
    )
    assert withdrawn.state == "withdrawn"


# Reassessment ----------------------------------------------------------------------------------


@pytest.fixture
def reassessed(django_user_model):
    """A lot released with a retest date under a reserving rule set, and its reassessment with
    every test reviewed."""
    world = build_world(django_user_model, extra_policy=RESERVED)
    people = world["people"]
    dates.record_dates(
        actor=people["analyst"],
        lot=world["lot"],
        expected=None,
        reason="Synthetic dates",
        expiry_on=today() + timedelta(days=400),
        retest_on=today() + timedelta(days=10),
        basis=BASIS,
    )
    ready(world)
    qualify(world, "approver", RELEASE_ACTIVITY, "release")
    world["lot"] = release(world)
    item = begin(world)
    for code, test in assign(world, item).items():
        record(world, test, READINGS[code])
        _, investigation = submit(world, test)
        assert investigation is None
        review(world, test)
    world["item"] = fresh(item)
    return world


def test_concluding_that_the_material_stays_in_use_is_reserved(reassessed):
    people = reassessed["people"]
    item = reassessed["item"]
    new_date = today() + timedelta(days=180)
    with pytest.raises(ValidationError, match="reserves release decisions"):
        reassessment.conclude(
            actor=people["author"],
            pin=WRONG_PIN,
            reassessment=item,
            expected_revision=item.revision,
            outcome=Reassessment.Outcome.SUITABLE,
            retest_on=new_date,
            reason="Synthetic conclusion",
        )
    assert failures(people["author"]) == 0
    held = qualify(reassessed, "author", RELEASE_ACTIVITY, "release", recorder="approver")
    done = conclude_reassessment(reassessed, item, Reassessment.Outcome.SUITABLE, new_date)
    assert done.state == "concluded" and done.retest_on == new_date
    assert done.result_evidence["authorization"][0]["qualification"] == held.pk
    assert ("Reassessment concluded suitable", f"{done.label} · {done.lot.number}") in [
        row[:2] for row in authority.relied_on(held)
    ]


def test_a_reassessment_asks_what_the_rule_set_version_in_force_reserves(reassessed):
    """The lot was released under version 1; version 2, approved since, names another
    activity, and the reassessment is judged under it as its requirements are."""
    people = reassessed["people"]
    old = reassessed["lot"].rules
    start, end = timezone.now() - timedelta(minutes=1), timezone.now() + timedelta(days=365)
    newer = save_rule(
        actor=people["author"],
        code=old.code,
        segment=old.segment,
        policy={**old.policy, "authorization": {"release": SITE_ACTIVITY}},
        effective_from=start,
        effective_until=end,
        reason="Synthetic version 2",
    )
    newer = approve_rule(
        actor=people["approver"],
        pin=PIN,
        rule=newer,
        expected_revision=newer.revision,
        reason="Independent synthetic policy review",
    )
    item, new_date = reassessed["item"], today() + timedelta(days=180)
    # The approver holds the qualification version 1 named, not the one version 2 names.
    with pytest.raises(ValidationError, match=SITE_ACTIVITY):
        conclude_reassessment(
            reassessed, item, Reassessment.Outcome.SUITABLE, new_date, who="approver"
        )
    held = qualify(reassessed, "approver", SITE_ACTIVITY, "release")
    with CaptureQueriesContext(connection) as queries:
        done = conclude_reassessment(
            reassessed, item, Reassessment.Outcome.SUITABLE, new_date, who="approver"
        )
    assert any(
        "laboratory_qualification" in q["sql"] and "FOR UPDATE" in q["sql"]
        for q in queries.captured_queries
    )
    frozen = done.result_evidence["authorization"]
    assert frozen == [
        {
            "activity": SITE_ACTIVITY,
            "rule_sets": [{"id": newer.pk, "code": old.code, "version": 2}],
            "qualification": held.pk,
        }
    ]


def test_ending_the_use_of_material_is_not_reserved(reassessed):
    done = conclude_reassessment(
        reassessed, reassessed["item"], Reassessment.Outcome.NOT_SUITABLE, None
    )
    assert done.state == "concluded"
    assert "authorization" not in done.result_evidence
