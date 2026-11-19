"""A method version that asks for qualified reviewers, through the production adapters: the
reviewer needs an approved, current qualification to review the method to review or return a
result of it, the qualification relied on is frozen on the test and bound by the review
signature, and a revocation serializes with the review (synthetic data)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from analytical import services as analytical
from analytical.models import AnalyticalTest
from catalog import services as catalog
from catalog.models import MethodRevision
from core.models import ElectronicSignature
from core.services import approve_rule, save_rule, set_pin
from laboratory import services as laboratory
from laboratory.tests.helpers import run_interleaved
from quality import services as quality
from sampling import services as sampling
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import PASSWORD, PIN, approve

pytestmark = pytest.mark.django_db(transaction=True)

QUALIFIED_REVIEW = "synthetic-rq-assay"
ANY_REVIEW = "synthetic-rq-loss"


def method(author, approver, code, window, *, qualified_reviewers):
    _, revision = catalog.create_method(
        actor=author,
        code=code,
        title=f"Synthetic {code}",
        technique="Gravimetry",
        document_ref=f"SOP-{code} rev 1",
        suitability_kind="validation",
        suitability_ref=f"VAL-{code} rev 1",
        requires_batch=False,
        requires_review_qualification=qualified_reviewers,
        reason="Synthetic method",
        **window,
    )
    return approve(revision, approver)


@pytest.fixture
def world(django_user_model, settings):
    assert settings.ANALYTICAL_REVIEWERS == "config.integrations.LaboratoryReviewers"
    people = {}
    for name, roles in {
        "author": ["quality"],
        "approver": ["quality"],
        "analyst": ["analyst"],
        "reviewer": ["reviewer"],
        "qualified": ["reviewer"],
    }.items():
        person = django_user_model.objects.create_user(
            username=f"rq_{name}", password=PASSWORD, first_name="Synthetic", last_name=name
        )
        person.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        set_pin(actor=person, pin=PIN, password=PASSWORD)
        people[name] = person
    author, approver = people["author"], people["approver"]
    window = {
        "effective_from": timezone.now() - timedelta(days=1),
        "effective_until": timezone.now() + timedelta(days=365),
    }
    rules = save_rule(
        actor=author,
        code="synthetic-review-qualification",
        segment="chemical",
        policy={
            "required_tests": ["assay", "loss"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        reason="Synthetic policy",
        **window,
    )
    rules = approve_rule(
        actor=approver,
        pin=PIN,
        rule=rules,
        expected_revision=rules.revision,
        reason="Independent synthetic policy review",
    )
    material = catalog.create_material(
        actor=author,
        code="synthetic-rq-material",
        name="Synthetic reviewed material",
        kind="raw_material",
        reason="Synthetic master data",
    )
    methods = {
        QUALIFIED_REVIEW: method(
            author, approver, QUALIFIED_REVIEW, window, qualified_reviewers=True
        ),
        ANY_REVIEW: method(author, approver, ANY_REVIEW, window, qualified_reviewers=False),
    }
    _, spec = catalog.create_specification(
        actor=author,
        code="synthetic-rq-spec",
        title="Synthetic specification",
        material=material,
        stage="incoming",
        scope="general",
        basis="Synthetic limits",
        reason="Synthetic specification",
        **window,
    )
    for code, method_code in (("assay", QUALIFIED_REVIEW), ("loss", ANY_REVIEW)):
        catalog.add_test_line(
            actor=author,
            revision=spec,
            reason="Synthetic line",
            method=methods[method_code].method,
            required=True,
            replicates=1,
            max_retests=0,
            code=code,
            name=code.title(),
            result_type="numeric",
            unit="%",
            lower_limit=Decimal("0"),
            upper_limit=Decimal("100"),
            lower_inclusive=True,
            upper_inclusive=True,
            reporting_decimals=1,
        )
    approve(spec, approver)
    _, plan = sampling.create_plan(
        actor=author,
        code="synthetic-rq-plan",
        title="Synthetic sampling plan",
        material=material,
        stage="incoming",
        basis="all",
        minimum_quantity=Decimal("10"),
        quantity_unit="g",
        instructions="Take one identified sample.",
        rationale="Synthetic single-container lot only",
        reason="Synthetic sampling plan",
        **window,
    )
    approve(plan, approver)
    for code in methods:
        qualify(people, people["analyst"], code)
    lot = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-RQ-001",
        material=material.name,
        rules=rules,
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    sampling.assign_requirements(
        actor=people["analyst"],
        lot=lot,
        material=material,
        stage="incoming",
        reason="Assign approved synthetic policy",
    )
    sample = sampling.record_sampling(
        actor=people["analyst"],
        lot=lot,
        reference="SYN-RQ-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic sampling",
    ).sample
    tests, holds = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign frozen required tests"
    )
    assert holds == []
    submitted = {}
    for test in tests:
        analytical.record_observation(
            actor=people["analyst"],
            test=test,
            value=Decimal("50.0"),
            raw_reference="RAW-SYN-RQ",
            reason="Synthetic observation",
        )
        test.refresh_from_db()
        submitted[test.test_code], _ = analytical.submit_test(
            actor=people["analyst"],
            test=test,
            expected_revision=test.revision,
            reason="Results complete",
        )
    return {"people": people, "tests": submitted}


def qualify(people, user, activity, work="perform"):
    record = laboratory.record_qualification(
        actor=people["author"],
        user=user,
        activity=activity,
        work=work,
        evidence_ref=f"QUAL-{activity}",
        valid_from=timezone.localdate() - timedelta(days=1),
        valid_until=timezone.localdate() + timedelta(days=365),
        reason="Synthetic evidence",
    )
    return laboratory.approve_qualification(
        actor=people["approver"],
        pin=PIN,
        qualification=record,
        expected_revision=record.revision,
        reason="Independent approval",
    )


def review(world, who, code="assay"):
    test = AnalyticalTest.objects.get(pk=world["tests"][code].pk)
    return analytical.review_test(
        actor=world["people"][who],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Reviewed source data",
    )


def test_the_method_version_carries_the_flag_into_its_approved_content(world):
    flagged = MethodRevision.objects.get(method__code=QUALIFIED_REVIEW)
    assert flagged.approved_content["requires_review_qualification"] is True
    plain = MethodRevision.objects.get(method__code=ANY_REVIEW)
    assert plain.approved_content["requires_review_qualification"] is False
    # A new version keeps the flag unless it is given.
    draft = catalog.new_method_revision(
        actor=world["people"]["author"],
        method=flagged.method,
        technique="Gravimetry",
        document_ref="SOP rev 2",
        suitability_kind="validation",
        suitability_ref="VAL rev 2",
        effective_from=timezone.now() + timedelta(days=30),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Revised procedure",
    )
    assert draft.requires_review_qualification is True


def test_a_reviewer_without_a_qualification_to_review_the_method_is_refused(world, client):
    people, test = world["people"], world["tests"]["assay"]
    # A qualification to perform the method is not one to review it.
    qualify(people, people["reviewer"], QUALIFIED_REVIEW)
    message = f"No approved, current qualification to review “{QUALIFIED_REVIEW}”."
    with pytest.raises(ValidationError, match=message):
        review(world, "reviewer")
    with pytest.raises(ValidationError, match=message):
        analytical.return_test(
            actor=people["reviewer"], test=test, expected_revision=test.revision, reason="Fix"
        )
    test.refresh_from_db()
    assert test.state == "submitted" and test.review_evidence == {}
    assert not ElectronicSignature.objects.filter(
        object_type="analytical.analyticaltest", object_id=str(test.pk)
    ).exists()
    client.force_login(people["reviewer"])
    page = client.get(reverse("analytical:test_detail", args=[test.pk]))
    assert page.context["review_note"] == message
    html = page.content.decode()
    assert reverse("analytical:test_review", args=[test.pk]) not in html
    assert reverse("analytical:test_return", args=[test.pk]) not in html
    assert "By a reviewer qualified to review" in html
    detail = reverse("analytical:test_detail", args=[test.pk])
    for name in ("analytical:test_review", "analytical:test_return"):
        refused = client.get(reverse(name, args=[test.pk]))
        assert refused.status_code == 302 and refused.url == detail


def test_a_qualified_reviewer_reviews_and_the_qualification_is_frozen_and_signed(world, client):
    people = world["people"]
    held = qualify(people, people["qualified"], QUALIFIED_REVIEW, work="review")
    reviewed = review(world, "qualified")
    expected = {
        "activity": QUALIFIED_REVIEW,
        "method_revision": 1,
        "qualification": held.pk,
    }
    assert reviewed.state == "reviewed" and reviewed.review_evidence == expected
    signature = ElectronicSignature.objects.get(
        object_type="analytical.analyticaltest", object_id=str(reviewed.pk), meaning="reviewed"
    )
    assert signature.content["review_evidence"] == expected
    client.force_login(people["approver"])
    html = client.get(reverse("analytical:test_detail", args=[reviewed.pk])).content.decode()
    assert "Reviewer&#x27;s qualification" in html or "Reviewer's qualification" in html
    assert reverse("laboratory:qualification_detail", args=[held.pk]) in html


def test_a_method_that_asks_for_no_qualified_reviewer_takes_any_reviewer(world, client):
    reviewed = review(world, "reviewer", code="loss")
    assert reviewed.state == "reviewed" and reviewed.review_evidence == {}
    client.force_login(world["people"]["reviewer"])
    html = client.get(reverse("analytical:test_detail", args=[reviewed.pk])).content.decode()
    assert "By a reviewer qualified to review" not in html
    assert "Reviewer&#x27;s qualification" not in html


def test_a_revoked_or_expired_review_qualification_refuses_the_review(world):
    people = world["people"]
    held = qualify(people, people["qualified"], QUALIFIED_REVIEW, work="review")
    laboratory.revoke_qualification(
        actor=people["approver"],
        pin=PIN,
        qualification=held,
        expected_revision=held.revision,
        reason="No longer authorized",
    )
    with pytest.raises(ValidationError, match="qualification to review"):
        review(world, "qualified")
    # The author may not review whatever they hold.
    qualify(people, people["analyst"], QUALIFIED_REVIEW, work="review")
    test = world["tests"]["assay"]
    assert analytical.review_refusal(people["analyst"], test) == "You cannot review your own test."


def test_the_database_freezes_the_review_evidence(world):
    people = world["people"]
    qualify(people, people["qualified"], QUALIFIED_REVIEW, work="review")
    submitted = world["tests"]["loss"]
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalyticalTest.objects.filter(pk=submitted.pk).update(review_evidence={"qualification": 1})
    reviewed = review(world, "qualified")
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalyticalTest.objects.filter(pk=reviewed.pk).update(review_evidence={})


def test_the_review_locks_the_qualifications_it_relies_on(world):
    people = world["people"]
    qualify(people, people["qualified"], QUALIFIED_REVIEW, work="review")
    with CaptureQueriesContext(connection) as queries:
        review(world, "qualified")
    locks = [
        q["sql"]
        for q in queries.captured_queries
        if "laboratory_qualification" in q["sql"] and "FOR UPDATE" in q["sql"]
    ]
    assert locks, "the review must lock the reviewer's qualifications before reading them"
    with pytest.raises(RuntimeError):
        laboratory.review_finding(actor=people["qualified"], activity=QUALIFIED_REVIEW, lock=True)


def test_a_revocation_signed_during_the_review_waits_for_it(world, monkeypatch):
    people = world["people"]
    held = qualify(people, people["qualified"], QUALIFIED_REVIEW, work="review")

    def revoke():
        return laboratory.revoke_qualification(
            actor=people["approver"],
            pin=PIN,
            qualification=held,
            expected_revision=held.revision,
            reason="Withdrawn",
        )

    outcome = run_interleaved(
        monkeypatch,
        laboratory,
        "reviewer_eligibility",
        lambda: review(world, "qualified"),
        revoke,
    )
    assert outcome["first"].state == "reviewed"
    assert outcome["first"].review_evidence["qualification"] == held.pk
    assert outcome["second"].state == "revoked"
    revoked = outcome["second"]
    # The revocation committed after the review, which relied on the qualification while current.
    signed = ElectronicSignature.objects.get(
        object_type="analytical.analyticaltest", object_id=str(outcome["first"].pk)
    )
    assert revoked.revoked_at > signed.signed_at


def test_a_return_records_the_qualification_it_relied_on(world):
    from core.models import AuditEvent

    people = world["people"]
    held = qualify(people, people["qualified"], QUALIFIED_REVIEW, work="review")
    test = world["tests"]["assay"]
    analytical.return_test(
        actor=people["qualified"], test=test, expected_revision=test.revision, reason="Fix units"
    )
    event = AuditEvent.objects.get(action="test.returned", object_id=str(test.pk))
    assert event.after == {
        "reviewer": {
            "activity": QUALIFIED_REVIEW,
            "method_revision": 1,
            "qualification": held.pk,
        }
    }
    test.refresh_from_db()
    assert test.state == "open" and test.review_evidence == {}


def test_only_a_reviewed_test_holds_review_evidence(world):
    test = AnalyticalTest.objects.get(pk=world["tests"]["assay"].pk)
    test.review_evidence = {"qualification": 1}
    with pytest.raises(ValidationError):
        test.validate_constraints()
    test.state = "reviewed"
    test.validate_constraints()


def test_a_deployment_without_the_reviewer_check_fails_the_system_check(settings):
    from analytical.apps import reviewer_check_configured

    assert reviewer_check_configured(None) == []
    settings.ANALYTICAL_REVIEWERS = ""
    (error,) = reviewer_check_configured(None)
    assert error.id == "analytical.E001"
