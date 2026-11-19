"""Participations in proficiency testing and interlaboratory comparisons: who plans, records,
reviews and closes them, the outcome of each score, what the signatures freeze, the
independence of the review and of the closure, and the database guards. Synthetic data."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from catalog import proficiency
from catalog.models import ProficiencyParticipation, ProficiencyResult
from catalog.services import digest
from core.models import AuditEvent, ElectronicSignature, PINCredential
from impact import services as impact

from .factories import PIN, approve, method_revision, person

pytestmark = pytest.mark.django_db(transaction=True)

PLAN = {
    "kind": "proficiency_test",
    "provider": "Synthetic PT Provider",
    "provider_accreditation": "ISO/IEC 17043, synthetic certificate 0001",
    "scheme": "Synthetic assay scheme",
    "round_ref": "Round 2026-4",
    "test_item": "Synthetic tablet powder, assay",
}


def plan_values(**overrides):
    data = {**PLAN, "results_due": timezone.localdate() + timedelta(days=20)}
    data.update(overrides)
    return data


def plan(actor, method, **overrides):
    return proficiency.plan_participation(
        actor=actor, method=method, reason="Annual plan", **plan_values(**overrides)
    )


def report_values(item, **overrides):
    today = timezone.localdate()
    data = {
        "method_version": None,
        "received_on": today - timedelta(days=10),
        "reported_on": today - timedelta(days=5),
        "data_ref": "WS-SYN-PT-01",
        "report_ref": "SYN-PT-2026-4 final report",
        "report_on": today - timedelta(days=1),
        "report_url": "",
    }
    data.update(overrides)
    return data


def report(actor, item, **overrides):
    item.refresh_from_db()
    return proficiency.record_report(
        actor=actor,
        participation=item,
        expected_revision=item.revision,
        reason="Report received",
        **report_values(item, **overrides),
    )


def result(actor, item, performer, score_kind="z", score="0.8", outcome="", **overrides):
    data = {
        "measurand": "Synthetic API assay",
        "unit": "%",
        "reported_value": "99.1",
        "assigned_value": "98.6",
        "score_kind": score_kind,
        "score": None if score is None else Decimal(score),
        "outcome": outcome,
        "performed_by": performer,
        "note": "",
    }
    data.update(overrides)
    item.refresh_from_db()
    return proficiency.add_result(
        actor=actor,
        participation=item,
        reason="From the report",
        expected_revision=item.revision,
        **data,
    )


def review(actor, item, follow_up=False, conclusion="Within the expected range.", **overrides):
    item.refresh_from_db()
    kwargs = {
        "actor": actor,
        "pin": PIN,
        "participation": item,
        "expected_revision": item.revision,
        "reason": "Outcome reviewed",
        "conclusion": conclusion,
        "follow_up": follow_up,
    }
    kwargs.update(overrides)
    return proficiency.review_participation(**kwargs)


def ready(people, method, score="0.8", score_kind="z", outcome=""):
    """A participation with its report and one result, recorded by the analyst."""
    item = plan(people["author"], method)
    result(people["analyst"], item, people["analyst"], score_kind, score, outcome)
    report(people["analyst"], item)
    item.refresh_from_db()
    return item


def follow_up(actor, item, **overrides):
    item.refresh_from_db()
    data = {
        "cause": "Integration of a shoulder peak.",
        "actions": "Integration parameters revised; analysts retrained.",
        "reported_results": "Results since the last round re-checked; none affected.",
        "impact_assessment": None,
        "quality_reference": "CAPA-SYN-014",
        "effectiveness": "Remaining item re-analysed: z = 0.4.",
    }
    data.update(overrides)
    return proficiency.record_follow_up(
        actor=actor,
        participation=item,
        expected_revision=item.revision,
        reason="Follow-up recorded",
        **data,
    )


def close(actor, item, **overrides):
    item.refresh_from_db()
    kwargs = {
        "actor": actor,
        "pin": PIN,
        "participation": item,
        "expected_revision": item.revision,
        "reason": "Follow-up complete",
    }
    kwargs.update(overrides)
    return proficiency.close_follow_up(**kwargs)


@pytest.fixture
def method(people):
    return method_revision(people["author"]).method


@pytest.fixture
def closer(db):
    return person("qa-closer", "quality")


# Outcomes -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, score, outcome",
    [
        ("z", "2", "satisfactory"),
        ("z", "-2.0000", "satisfactory"),
        ("z", "2.0001", "questionable"),
        ("z_prime", "-2.9999", "questionable"),
        ("zeta", "3", "unsatisfactory"),
        ("z", "-3.5", "unsatisfactory"),
        ("en", "1", "satisfactory"),
        ("en", "-1.0001", "unsatisfactory"),
    ],
)
def test_the_outcome_follows_from_the_score(kind, score, outcome):
    assert proficiency.outcome_of(kind, Decimal(score)) == outcome


@pytest.mark.parametrize(
    "kind, score, outcome",
    [
        ("z", "2", "satisfactory"),
        ("z", "-2", "satisfactory"),
        ("z_prime", "2.0001", "questionable"),
        ("zeta", "-3", "unsatisfactory"),
        ("z", "3", "unsatisfactory"),
        ("en", "-1", "satisfactory"),
        ("en", "1.0001", "unsatisfactory"),
    ],
)
def test_the_database_accepts_each_derived_outcome(people, method, kind, score, outcome):
    item = plan(people["author"], method)
    line = result(people["analyst"], item, people["analyst"], kind, score)
    line.refresh_from_db()
    assert line.outcome == outcome


def test_the_participation_takes_the_worst_outcome(people, method):
    item = plan(people["author"], method)
    analyst = people["analyst"]
    assert proficiency.overall_outcome(item.results.all()) == "not_evaluated"
    result(analyst, item, analyst, "none", None, "not_evaluated")
    assert proficiency.overall_outcome(item.results.all()) == "not_evaluated"
    result(analyst, item, analyst, "z", "1.1", measurand="Impurity A")
    assert proficiency.overall_outcome(item.results.all()) == "satisfactory"
    result(analyst, item, analyst, "z", "2.4", measurand="Impurity B")
    assert proficiency.overall_outcome(item.results.all()) == "questionable"
    result(analyst, item, analyst, "en", "1.3", measurand="Water")
    assert proficiency.overall_outcome(item.results.all()) == "unsatisfactory"


def test_a_result_without_a_score_carries_the_providers_evaluation(people, method):
    item = plan(people["author"], method)
    analyst = people["analyst"]
    with pytest.raises(ValidationError) as caught:
        result(analyst, item, analyst, "none", None, "")
    assert "outcome" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        result(analyst, item, analyst, "none", "1.2", "satisfactory")
    assert "score" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        result(analyst, item, analyst, "z", None)
    assert "score" in caught.value.message_dict
    with pytest.raises(ValidationError, match="questionable"):
        result(analyst, item, analyst, "z", "2.5", "satisfactory")
    done = result(analyst, item, analyst, "none", None, "unsatisfactory", reported_value="Absent")
    assert done.outcome == "unsatisfactory" and done.score is None


def test_the_database_refuses_an_outcome_that_contradicts_the_score(people, method):
    item = plan(people["author"], method)
    analyst = people["analyst"]
    with pytest.raises(DatabaseError), transaction.atomic():
        ProficiencyResult.objects.create(
            participation=item,
            measurand="Tampered",
            reported_value="1",
            score_kind="z",
            score=Decimal("3.2"),
            outcome="satisfactory",
            performed_by=analyst,
            created_by=analyst,
        )


# Planning and recording ---------------------------------------------------------------


def test_quality_plans_a_participation_with_an_audit_event(people, method):
    item = plan(people["author"], method)
    assert item.state == "open" and item.identifier == f"PT-{item.pk}"
    event = AuditEvent.objects.get(action="participation.planned")
    assert event.actor == people["author"] and event.reason == "Annual plan"
    assert proficiency.display_state(item) == ("Planned", "neutral")


@pytest.mark.parametrize("role", ["analyst", "reviewer", "admin", "auditor"])
def test_only_quality_plans(people, method, role):
    with pytest.raises(PermissionDenied):
        plan(people[role], method)
    assert not ProficiencyParticipation.objects.exists()


@pytest.mark.parametrize("role", ["admin", "auditor"])
def test_admin_and_auditor_record_no_results(people, method, role):
    item = plan(people["author"], method)
    with pytest.raises(PermissionDenied):
        result(people[role], item, people["analyst"])
    with pytest.raises(PermissionDenied):
        report(people[role], item)


def test_a_reason_and_a_due_day_are_required(people, method):
    with pytest.raises(ValidationError, match="reason"):
        proficiency.plan_participation(
            actor=people["author"], method=method, reason=" ", **plan_values()
        )
    with pytest.raises(ValidationError) as caught:
        plan(people["author"], method, results_due=None)
    assert "results_due" in caught.value.message_dict


def test_the_report_dates_are_checked(people, method):
    item = plan(people["author"], method)
    today = timezone.localdate()
    with pytest.raises(ValidationError) as caught:
        report(people["analyst"], item, reported_on=today + timedelta(days=1))
    assert "reported_on" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        report(people["analyst"], item, received_on=today, reported_on=today - timedelta(days=2))
    assert "reported_on" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        report(people["analyst"], item, reported_on=None)
    assert "reported_on" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        report(people["analyst"], item, reported_on=today, report_on=today - timedelta(days=1))
    assert "report_on" in caught.value.message_dict


def test_the_method_version_must_be_an_approved_version_of_the_method(people, method):
    item = plan(people["author"], method)
    draft = method.revisions.get()
    with pytest.raises(ValidationError) as caught:
        report(people["analyst"], item, method_version=draft)
    assert "method_version" in caught.value.message_dict
    approve(draft, people["approver"])
    done = report(people["analyst"], item, method_version=draft)
    assert done.method_version == draft and done.revision == 2


def test_a_stale_revision_is_refused(people, method):
    item = plan(people["author"], method)
    report(people["analyst"], item)
    with pytest.raises(ValidationError, match="Reload"):
        proficiency.change_plan(
            actor=people["author"],
            participation=item,
            expected_revision=1,
            reason="Later round",
            **plan_values(round_ref="Round 2027-1"),
        )


def test_the_analyst_must_be_an_active_analyst(people, method):
    item = plan(people["author"], method)
    with pytest.raises(ValidationError) as caught:
        result(people["reviewer"], item, people["reviewer"])
    assert "performed_by" in caught.value.message_dict


def test_at_most_thirty_results(people, method, monkeypatch):
    monkeypatch.setattr(proficiency, "MAX_RESULTS", 2)
    item = plan(people["author"], method)
    analyst = people["analyst"]
    result(analyst, item, analyst, measurand="One")
    result(analyst, item, analyst, measurand="Two")
    with pytest.raises(ValidationError, match="at most 2"):
        result(analyst, item, analyst, measurand="Three")


def test_a_result_is_removed_with_a_reason_and_audited(people, method):
    item = plan(people["author"], method)
    line = result(people["analyst"], item, people["analyst"])
    for role in ("admin", "auditor"):
        with pytest.raises(PermissionDenied):
            proficiency.remove_result(
                actor=people[role], item=line, reason="Not mine", expected_revision=2
            )
    with pytest.raises(ValidationError, match="Reload"):
        proficiency.remove_result(
            actor=people["reviewer"], item=line, reason="Typed twice", expected_revision=1
        )
    proficiency.remove_result(
        actor=people["reviewer"], item=line, reason="Typed twice", expected_revision=2
    )
    assert not item.results.exists()
    event = AuditEvent.objects.get(action="participation.result_removed")
    assert event.before["measurand"] == "Synthetic API assay"


def test_a_participation_without_results_is_cancelled_by_quality(people, method):
    item = plan(people["author"], method)
    with pytest.raises(PermissionDenied):
        proficiency.cancel_participation(
            actor=people["analyst"], participation=item, expected_revision=1, reason="No round"
        )
    done = proficiency.cancel_participation(
        actor=people["approver"], participation=item, expected_revision=1, reason="No round"
    )
    assert done.state == "cancelled" and done.cancelled_at
    with_results = plan(people["author"], method)
    result(people["analyst"], with_results, people["analyst"])
    with_results.refresh_from_db()
    with pytest.raises(ValidationError, match="review the participation"):
        proficiency.cancel_participation(
            actor=people["author"],
            participation=with_results,
            expected_revision=with_results.revision,
            reason="Changed our mind",
        )


def test_an_overdue_participation_shows_as_overdue(people, method):
    item = plan(people["author"], method, results_due=timezone.localdate() - timedelta(days=1))
    assert proficiency.display_state(item) == ("Results overdue", "danger")
    report(people["analyst"], item)
    item.refresh_from_db()
    assert proficiency.display_state(item) == ("Results reported", "progress")


# Review -------------------------------------------------------------------------------


def test_review_needs_the_report_and_results(people, method):
    item = plan(people["author"], method)
    problems = proficiency.review_problems(item)
    assert len(problems) == 4
    with pytest.raises(ValidationError, match="Record the laboratory's results"):
        review(people["approver"], item)
    assert not ElectronicSignature.objects.exists()


def test_an_independent_quality_person_reviews_and_closes_a_satisfactory_outcome(people, method):
    item = ready(people, method)
    done = review(people["approver"], item)
    assert done.state == "closed" and done.outcome == "satisfactory"
    assert done.closed_at == done.reviewed_at and not done.follow_up_required
    assert done.review_hash == digest(done.review_content)
    assert done.review_content["schema"] == "oq.proficiency/1"
    assert done.review_content["results"][0]["score"] == "0.8"
    signature = ElectronicSignature.objects.get(object_id=str(item.pk))
    assert signature.meaning == "reviewed" and signature.signer == people["approver"]
    assert AuditEvent.objects.filter(action="signed.reviewed", object_id=str(item.pk)).exists()


@pytest.mark.parametrize("who", ["analyst_dual", "recorder", "performer"])
def test_review_is_independent_of_the_report_and_results(people, method, who):
    dual = people["dual"]
    item = plan(people["author"], method)
    if who == "analyst_dual":
        result(dual, item, dual)
        report(people["analyst"], item)
    elif who == "recorder":
        result(people["analyst"], item, people["analyst"])
        report(dual, item)
    else:
        result(people["analyst"], item, dual)
        report(people["analyst"], item)
    item.refresh_from_db()
    assert proficiency.review_denial(dual, item) == proficiency.INDEPENDENT
    with pytest.raises(PermissionDenied):
        review(dual, item)
    item.refresh_from_db()
    assert item.state == "open" and not ElectronicSignature.objects.exists()


def test_planning_is_not_authorship_until_results_are_recorded(people, method):
    item = plan(people["author"], method)
    proficiency.change_plan(
        actor=people["author"],
        participation=item,
        expected_revision=item.revision,
        reason="Round renumbered",
        **plan_values(round_ref="Round 2026-4b"),
    )
    result(people["analyst"], item, people["analyst"])
    report(people["analyst"], item)
    assert review(people["author"], item).state == "closed"


def test_a_plan_corrected_after_results_makes_its_author_a_data_author(people, method):
    item = ready(people, method)
    proficiency.change_plan(
        actor=people["approver"],
        participation=item,
        expected_revision=item.revision,
        reason="Provider renamed the round",
        **plan_values(round_ref="Round 2026-4 bis"),
    )
    assert AuditEvent.objects.filter(action="participation.plan_corrected").exists()
    item.refresh_from_db()
    assert proficiency.review_denial(people["approver"], item) == proficiency.INDEPENDENT
    with pytest.raises(PermissionDenied):
        review(people["approver"], item)
    assert review(people["author"], item).review_content["round_ref"] == "Round 2026-4 bis"


def test_whoever_removed_a_result_does_not_review(people, method):
    item = ready(people, method)
    extra = result(people["analyst"], item, people["analyst"], measurand="Typo")
    item.refresh_from_db()
    proficiency.remove_result(
        actor=people["approver"], item=extra, reason="Typed twice", expected_revision=item.revision
    )
    item.refresh_from_db()
    with pytest.raises(PermissionDenied):
        review(people["approver"], item)


def test_an_unsatisfactory_outcome_needs_follow_up(people, method):
    item = ready(people, method, score="-3.4")
    with pytest.raises(ValidationError, match="corrective follow-up"):
        review(people["approver"], item)
    done = review(people["approver"], item, follow_up=True, conclusion="Bias found.")
    assert done.state == "follow_up" and done.outcome == "unsatisfactory"
    assert done.closed_at is None


def test_a_questionable_outcome_is_the_reviewers_decision(people, method):
    item = ready(people, method, score="2.4")
    done = review(
        people["approver"], item, conclusion="Second warning in a row: investigate.", follow_up=True
    )
    assert done.outcome == "questionable" and done.state == "follow_up"
    other = ready(people, method, score="2.1")
    assert review(people["approver"], other).state == "closed"


def test_review_needs_a_conclusion_and_a_correct_pin(people, method):
    item = ready(people, method)
    with pytest.raises(ValidationError) as caught:
        review(people["approver"], item, conclusion=" ")
    assert "conclusion" in caught.value.message_dict
    with pytest.raises(ValidationError):
        review(people["approver"], item, pin="00000000")
    credential = PINCredential.objects.get(user=people["approver"])
    assert credential.failures == 1
    assert AuditEvent.objects.filter(action="signature.denied").exists()
    item.refresh_from_db()
    assert item.state == "open"


def test_review_refuses_a_stale_revision(people, method):
    item = ready(people, method)
    stale = item.revision
    result(people["analyst"], item, people["analyst"], measurand="Late result")
    with pytest.raises(ValidationError, match="Reload"):
        review(people["approver"], item, expected_revision=stale)


# Follow-up ----------------------------------------------------------------------------


def test_follow_up_is_recorded_and_closed_by_another_quality_person(people, method, closer):
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    assert proficiency.close_problems(item)
    follow_up(people["approver"], item)
    item.refresh_from_db()
    assert proficiency.close_denial(people["approver"], item) == proficiency.INDEPENDENT_CLOSE
    with pytest.raises(PermissionDenied):
        close(people["approver"], item)
    done = close(closer, item)
    assert done.state == "closed" and done.closed_at
    assert done.close_hash == digest(done.close_content)
    assert done.close_content["review_hash"] == done.review_hash
    assert done.close_content["quality_reference"] == "CAPA-SYN-014"
    assert ElectronicSignature.objects.filter(meaning="closed", signer=closer).exists()


def test_closing_refuses_a_stale_revision_and_a_wrong_pin(people, method, closer):
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    follow_up(people["approver"], item)
    item.refresh_from_db()
    stale = item.revision
    follow_up(people["approver"], item, quality_reference="CAPA-SYN-015")
    with pytest.raises(ValidationError, match="Reload"):
        close(closer, item, expected_revision=stale)
    with pytest.raises(ValidationError):
        close(closer, item, pin="00000000")
    assert PINCredential.objects.get(user=closer).failures == 1
    item.refresh_from_db()
    assert item.state == "follow_up" and not item.close_hash


def test_a_reviewed_participation_takes_no_more_results(people, method):
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    with pytest.raises(ValidationError, match="corrective follow-up is open"):
        result(people["analyst"], item, people["analyst"], measurand="Late")


def test_closing_needs_every_part_of_the_follow_up(people, method, closer):
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    follow_up(people["approver"], item, effectiveness="")
    with pytest.raises(ValidationError, match="shown to work"):
        close(closer, item)


def test_data_authors_do_not_close_the_follow_up(people, method):
    item = plan(people["author"], method)
    result(people["dual"], item, people["analyst"], score="3.3")
    report(people["analyst"], item)
    review(people["approver"], item, follow_up=True)
    follow_up(people["approver"], item)
    item.refresh_from_db()
    with pytest.raises(PermissionDenied):
        close(people["dual"], item)


def test_follow_up_changes_only_while_open_and_by_quality(people, method, closer):
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    with pytest.raises(PermissionDenied):
        follow_up(people["analyst"], item)
    follow_up(people["approver"], item)
    close(closer, item)
    with pytest.raises(ValidationError, match="no corrective follow-up open"):
        follow_up(people["approver"], item, cause="Changed afterwards")


def _assessment(people):
    today = timezone.localdate()
    return impact.start(
        actor=people["author"],
        cause="other",
        title="Bias in the synthetic assay",
        description="Unsatisfactory proficiency result.",
        found_on=today,
        period_from=today - timedelta(days=90),
        period_until=today,
    )


def test_a_linked_impact_assessment_must_be_concluded(people, method, closer):
    assessment = _assessment(people)
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    follow_up(people["approver"], item, impact_assessment=assessment)
    item.refresh_from_db()
    with pytest.raises(ValidationError, match="still open"):
        close(closer, item)
    assessment.refresh_from_db()
    impact.conclude(
        actor=closer,
        pin=PIN,
        assessment=assessment,
        expected_revision=assessment.revision,
        reason="Nothing affected",
    )
    done = close(closer, item)
    assert done.close_content["impact_assessment"] == {
        "id": assessment.pk,
        "label": assessment.label,
    }


def test_a_withdrawn_impact_assessment_is_not_linked(people, method, closer):
    assessment = _assessment(people)
    impact.withdraw(
        actor=closer,
        pin=PIN,
        assessment=assessment,
        expected_revision=assessment.revision,
        reason="Started in error",
    )
    assessment.refresh_from_db()
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    with pytest.raises(ValidationError) as caught:
        follow_up(people["approver"], item, impact_assessment=assessment)
    assert "impact_assessment" in caught.value.message_dict
    assert not proficiency.assessment_choices().filter(pk=assessment.pk).exists()


# Database guards ----------------------------------------------------------------------


def test_reviewed_and_closed_records_are_guarded(people, method, closer):
    item = review(people["approver"], ready(people, method))
    line = item.results.get()
    for operation in (
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).update(provider="Tampered"),
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).update(cause="Afterwards"),
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).delete(),
        lambda: ProficiencyResult.objects.filter(pk=line.pk).update(reported_value="100.0"),
        lambda: ProficiencyResult.objects.filter(pk=line.pk).delete(),
        lambda: ProficiencyResult.objects.create(
            participation=item,
            measurand="Added later",
            reported_value="1",
            score_kind="none",
            outcome="satisfactory",
            performed_by=people["analyst"],
            created_by=people["analyst"],
        ),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()


def test_a_follow_up_keeps_its_review(people, method):
    item = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    for operation in (
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).update(
            review_conclusion="Rewritten"
        ),
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).update(outcome="satisfactory"),
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).update(state="open"),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()
    # The follow-up itself changes while it is open.
    ProficiencyParticipation.objects.filter(pk=item.pk).update(cause="Found")


def test_an_open_participation_keeps_its_method_and_planner(people, method):
    item = plan(people["author"], method)
    other = method_revision(people["author"], code="kf-water").method
    for operation in (
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).update(method=other),
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).update(
            planned_by=people["approver"]
        ),
        lambda: ProficiencyParticipation.objects.filter(pk=item.pk).delete(),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()
    with pytest.raises(DatabaseError), transaction.atomic():
        ProficiencyParticipation.objects.filter(pk=item.pk).update(
            state="cancelled", cancelled_at=timezone.now(), review_hash="0" * 64
        )
    cancelled = proficiency.cancel_participation(
        actor=people["author"], participation=item, expected_revision=1, reason="No round"
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        ProficiencyParticipation.objects.filter(pk=cancelled.pk).update(round_ref="Revived")
