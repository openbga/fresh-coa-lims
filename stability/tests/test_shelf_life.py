"""Shelf-life evaluations: the results they read, their drafts and the independent signed
conclusion, with the database guards (synthetic data only, PostgreSQL)."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction

from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin
from laboratory.tests.helpers import PASSWORD
from stability import regression, services, shelf_life
from stability.models import ShelfLifeEvaluation, ShelfLifeStudy

from .helpers import (
    FALLING,
    PIN,
    accept,
    approved_protocol,
    assign,
    pulled,
    reviewed,
    started_study,
    studies_with_results,
)

pytestmark = pytest.mark.django_db(transaction=True)
DIRECTION = ShelfLifeEvaluation.Direction
OUTCOME = ShelfLifeEvaluation.Outcome


def draft(people, study, *, actor="quality", direction=DIRECTION.DECREASES, **values):
    return services.draft_shelf_life(
        actor=people[actor],
        study=study,
        condition=values.get("condition", "Long-term"),
        test_code=values.get("test_code", "assay"),
        direction=direction,
        purpose=values.get("purpose", "Synthetic data for a proposed shelf life"),
        reason="Synthetic evaluation",
    )


def conclude(people, evaluation, *, actor="quality2", pin=PIN, data_hash=None, **values):
    evaluation.refresh_from_db()
    if data_hash is None:
        data_hash = shelf_life.data_digest(evaluation, shelf_life.of(evaluation))
    return services.conclude_shelf_life(
        actor=people[actor],
        pin=pin,
        evaluation=evaluation,
        expected_revision=values.get("expected_revision", evaluation.revision),
        data_hash=data_hash,
        reason="Independent statistical review",
        outcome=values.get("outcome", OUTCOME.SUPPORTED),
        shelf_life_months=values.get("months", 12),
        conclusion=values.get("conclusion", "The pooled data support the shelf life recorded."),
    )


def third_quality(django_user_model):
    user = django_user_model.objects.create_user("quality3", password=PASSWORD)
    user.groups.add(Group.objects.get(name="quality"))
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


def test_a_draft_keeps_the_criterion_in_force_and_uses_every_study_of_the_protocol(people):
    studies, config = studies_with_results(people, FALLING)
    evaluation = draft(people, studies[1])
    assert evaluation.state == "draft" and evaluation.revision == 1
    assert (evaluation.protocol_code, evaluation.condition, evaluation.test_code) == (
        "SYN-SL",
        "Long-term",
        "assay",
    )
    assert evaluation.container_closure == "Synthetic marketed container"
    assert (evaluation.lower_limit, evaluation.upper_limit) == (Decimal("95"), Decimal("105"))
    assert (evaluation.unit, evaluation.decimals, evaluation.name) == ("%", 1, "Assay")
    assert evaluation.specification == config["specification"]
    assert evaluation.specification_version == config["revision"].version
    linked = set(evaluation.study_links.values_list("study_id", flat=True))
    assert linked == {study.pk for study in studies}
    event = AuditEvent.objects.get(action="shelf_life.drafted", object_id=str(evaluation.pk))
    assert event.actor == people["quality"] and len(event.after["studies"]) == 3
    assert event.after["specification"]["code"] == "syn-shelf-life"


def test_the_results_of_accepted_pulls_are_fitted_by_their_time_point(people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = draft(people, studies[0])
    result = shelf_life.of(evaluation)
    assert [len(batch.points) for batch in result.batches] == [4, 4, 4]
    assert all(batch.fitted for batch in result.batches) and not result.unused
    first = result.batches[0].points
    assert [point.days for point in first] == [0, 91, 183, 274]
    assert [point.value for point in first] == [Decimal(v) for v in FALLING[0]]
    assert result.covered_months == regression.months(274)
    # The figures are the regression's on the same data, months of 365.25 / 12 days.
    expected = regression.analyse(
        [[(regression.months(d), Decimal(v)) for d, v in zip((0, 91, 183, 274), row, strict=True)]
         for row in FALLING]
    )  # fmt: skip
    assert result.analysis.model == expected.model == regression.Model.POOLED
    assert result.analysis.fits == expected.fits
    estimate = regression.estimate(expected, "decreases", Decimal(95), Decimal(105))
    assert result.estimate.months == estimate.months
    assert result.estimate_months == regression.round_down(estimate.months, 1)
    assert result.longest_supported == int(regression.round_down(estimate.months, 0))
    figures = shelf_life.figures(result)
    assert figures["model"] == "pooled" and figures["confidence"] == "one-sided 95 %"
    assert figures["slopes"]["df1"] == 2 and figures["intercepts"] is not None
    assert figures["estimate_months"] == str(result.estimate_months)


def test_results_not_yet_usable_are_listed_with_the_reason(people):
    studies, _ = studies_with_results(people, [("100.2", "99.8", "99.1", None)])
    (study,) = studies
    last = pulled(people, study, 274)
    (test,) = assign(people, last)
    reviewed(people, test, "98.9")
    evaluation = draft(people, study)
    result = shelf_life.of(evaluation)
    assert [item.reason for item in result.unused] == ["The pull is not yet accepted."]
    assert result.batches[0].fitted and len(result.batches[0].points) == 3
    accept(people, last)
    assert len(shelf_life.of(evaluation).batches[0].points) == 4


def test_a_study_with_fewer_than_three_time_points_is_listed_but_not_fitted(people):
    studies, _ = studies_with_results(people, [FALLING[0], ("100.0", "99.4", None, None)])
    evaluation = draft(people, studies[0])
    result = shelf_life.of(evaluation)
    short = result.batches[1]
    assert not short.fitted and "2 time points" in short.reason
    assert result.analysis.model == regression.Model.SINGLE
    assert len(result.used_points) == 4


def test_a_condition_without_its_own_time_zero_uses_the_study_s_time_zero(people):
    from stability.tests.helpers import draft_protocol, lot_of
    from stability.tests.helpers import shelf_life as specification

    config = specification(people)
    protocol = draft_protocol(
        people,
        code="SYN-SL-ACC",
        intervals=(0, 91, 183),
        specification=config["specification"],
        test_codes=("assay",),
    )
    accelerated = services.add_condition(
        actor=people["analyst"],
        protocol=protocol,
        label="Accelerated",
        setpoint="Synthetic accelerated setpoint",
        temperature_c=Decimal("40.0"),
        humidity_pct=Decimal("75.0"),
        reason="Synthetic condition",
    )
    for days in (91, 183):
        services.add_timepoint(
            actor=people["analyst"],
            protocol=protocol,
            condition=accelerated,
            label=f"{days} days accelerated",
            interval_days=days,
            window_days=5,
            test_codes=["assay"],
            reason="Synthetic timepoint",
        )
    protocol.refresh_from_db()
    protocol = services.approve_protocol(
        actor=people["quality"],
        pin=PIN,
        protocol=protocol,
        expected_revision=protocol.revision,
        reason="Independent approval",
    )
    study = started_study(
        people,
        protocol=protocol,
        lot=lot_of(people, config["material"], "SYN-SL-ACC-1"),
        identifier="STB-ACC-1",
        days_ago=190,
    )
    for condition, days, value in (
        ("Long-term", 0, "100.3"),
        ("Accelerated", 91, "98.9"),
        ("Accelerated", 183, "97.2"),
    ):
        pull = study.pulls.get(timepoint__condition__label=condition, timepoint__interval_days=days)
        pull = pulled(people, study, days) if condition == "Long-term" else pull
        if condition == "Accelerated":
            pull = services.record_pull(
                actor=people["analyst"],
                pull=pull,
                pulled_on=pull.due_date,
                quantity=Decimal("5"),
                quantity_unit="g",
                storage_location="Synthetic chamber",
                reason="Synthetic pull",
            )
        (test,) = assign(people, pull)
        reviewed(people, test, value)
        accept(people, pull)
    evaluation = draft(people, study, condition="Accelerated")
    (batch,) = shelf_life.of(evaluation).batches
    assert [(p.condition, p.days) for p in batch.points] == [
        ("Long-term", 0),
        ("Accelerated", 91),
        ("Accelerated", 183),
    ]


def test_drafting_is_refused_without_role_reason_or_a_test_the_protocol_can_evaluate(people):
    studies, _ = studies_with_results(people, [FALLING[0]])
    (study,) = studies
    with pytest.raises(PermissionDenied):
        draft(people, study, actor="analyst")
    with pytest.raises(PermissionDenied):
        draft(people, study, actor="admin")
    with pytest.raises(ValidationError) as refused:
        draft(people, study, condition="Intermediate", test_code="identity")
    assert set(refused.value.message_dict) == {"condition", "test_code"}
    with pytest.raises(ValidationError, match="State why"):
        draft(people, study, purpose="  ")
    with pytest.raises(ValidationError, match="reason"):
        services.draft_shelf_life(
            actor=people["quality"],
            study=study,
            condition="Long-term",
            test_code="assay",
            direction=DIRECTION.DECREASES,
            purpose="Synthetic",
            reason=" ",
        )
    draft(people, study)
    with pytest.raises(ValidationError, match="draft evaluation of this test"):
        draft(people, study, direction=DIRECTION.EITHER)
    assert ShelfLifeEvaluation.objects.count() == 1


def test_a_protocol_without_a_specification_has_no_test_to_evaluate(people):
    study = started_study(people, protocol=approved_protocol(people, code="SYN-PLAIN"))
    assert services.shelf_life_lines(study.protocol) == (None, [])
    with pytest.raises(ValidationError) as refused:
        draft(people, study)
    assert "test_code" in refused.value.message_dict


def test_a_draft_changes_with_each_revision_and_whoever_changes_it_does_not_conclude(
    people, django_user_model
):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = draft(people, studies[0])
    changed = services.change_shelf_life(
        actor=people["quality2"],
        evaluation=evaluation,
        expected_revision=1,
        reason="The third batch is not a primary batch",
        studies=[studies[0].pk, studies[1].pk],
        direction=DIRECTION.EITHER,
        purpose="Synthetic annual review",
    )
    assert changed.revision == 2 and changed.direction == "either"
    assert set(changed.study_links.values_list("study_id", flat=True)) == {
        studies[0].pk,
        studies[1].pk,
    }
    event = AuditEvent.objects.get(action="shelf_life.changed", object_id=str(evaluation.pk))
    assert len(event.before["studies"]) == 3 and len(event.after["studies"]) == 2
    assert event.actor == people["quality2"]
    with pytest.raises(ValidationError, match="Record changed"):
        services.change_shelf_life(
            actor=people["quality"],
            evaluation=evaluation,
            expected_revision=1,
            reason="Stale",
            studies=[studies[0].pk],
            direction=DIRECTION.DECREASES,
            purpose="Synthetic annual review",
        )
    with pytest.raises(ValidationError, match="Nothing was changed"):
        services.change_shelf_life(
            actor=people["quality"],
            evaluation=evaluation,
            expected_revision=2,
            reason="Same",
            studies=[studies[1].pk, studies[0].pk],
            direction=DIRECTION.EITHER,
            purpose="Synthetic annual review",
        )
    other = started_study(people, protocol=approved_protocol(people, code="SYN-OTHER"))
    with pytest.raises(ValidationError, match="Choose studies of protocol SYN-SL"):
        services.change_shelf_life(
            actor=people["quality"],
            evaluation=evaluation,
            expected_revision=2,
            reason="Wrong study",
            studies=[other.pk],
            direction=DIRECTION.EITHER,
            purpose="Synthetic annual review",
        )
    with pytest.raises(ValidationError, match="at least one study"):
        services.change_shelf_life(
            actor=people["quality"],
            evaluation=evaluation,
            expected_revision=2,
            reason="None",
            studies=[],
            direction=DIRECTION.EITHER,
            purpose="Synthetic annual review",
        )
    # The drafter and the changer are both excluded; a third quality person concludes.
    for name in ("quality", "quality2"):
        with pytest.raises(PermissionDenied, match="another quality person concludes"):
            conclude(people, evaluation, actor=name)
    people["quality3"] = third_quality(django_user_model)
    concluded = conclude(people, evaluation, actor="quality3")
    assert concluded.state == "concluded"


def test_an_independent_conclusion_freezes_the_results_and_the_figures(people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = draft(people, studies[0])
    result = shelf_life.of(evaluation)
    months = result.longest_supported
    assert months >= 12
    concluded = conclude(people, evaluation, months=months)
    assert concluded.state == "concluded" and concluded.revision == 2
    assert concluded.outcome == "supported" and concluded.shelf_life_months == months
    content = concluded.content
    assert (
        content["schema"] == "oq.shelf-life/1" and content["identifier"] == f"SLE-{evaluation.pk}"
    )
    assert content["criterion"] == {"lower": "95", "upper": "105"}
    assert len(content["results"]) == 12 and content["unused"] == []
    assert content["figures"] == shelf_life.figures(result)
    assert content["shelf_life_months"] == months
    signature = ElectronicSignature.objects.get(
        object_type="stability.shelflifeevaluation", object_id=str(evaluation.pk)
    )
    assert signature.meaning == "concluded" and signature.signer == people["quality2"]
    assert signature.revision == 2
    # A result accepted afterwards changes what a draft would show, not the conclusion.
    with pytest.raises(ValidationError, match="no longer changes"):
        services.withdraw_shelf_life(
            actor=people["quality"], evaluation=concluded, expected_revision=2, reason="Late"
        )
    concluded.refresh_from_db()
    assert concluded.content == content


def test_a_conclusion_is_refused_when_the_figures_do_not_support_it(people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = draft(people, studies[0])
    longest = shelf_life.of(evaluation).longest_supported
    with pytest.raises(ValidationError, match=f"at most {longest} months"):
        conclude(people, evaluation, months=longest + 1)
    with pytest.raises(ValidationError, match="whole months"):
        conclude(people, evaluation, months=None)
    with pytest.raises(ValidationError, match="Leave the shelf life empty"):
        conclude(people, evaluation, outcome=OUTCOME.NOT_SUPPORTED, months=6)
    with pytest.raises(ValidationError, match="State the conclusion"):
        conclude(people, evaluation, conclusion=" ")
    with pytest.raises(ValidationError, match="Choose the outcome"):
        conclude(people, evaluation, outcome="maybe")
    with pytest.raises(ValidationError, match="changed since this page was opened"):
        conclude(people, evaluation, data_hash="0" * 64)
    with pytest.raises(ValidationError, match="Reload and review"):
        conclude(people, evaluation, expected_revision=7)
    evaluation.refresh_from_db()
    assert evaluation.state == "draft" and evaluation.revision == 1
    assert not ElectronicSignature.objects.filter(
        object_type="stability.shelflifeevaluation"
    ).exists()
    not_supported = conclude(
        people,
        evaluation,
        outcome=OUTCOME.NOT_SUPPORTED,
        months=None,
        conclusion="Synthetic: the proposal waits for 12 months of data.",
    )
    assert not_supported.shelf_life_months is None and not_supported.outcome == "not_supported"


def test_a_wrong_pin_is_recorded_and_the_evaluation_stays_a_draft(people):
    studies, _ = studies_with_results(people, [FALLING[0]])
    evaluation = draft(people, studies[0])
    with pytest.raises(ValidationError):
        conclude(people, evaluation, pin="000000")
    assert AuditEvent.objects.filter(action="signature.denied", actor=people["quality2"]).exists()
    evaluation.refresh_from_db()
    assert evaluation.state == "draft"


def test_a_change_of_the_results_after_the_page_was_read_refuses_the_signature(people):
    studies, _ = studies_with_results(people, [("100.2", "99.8", "99.1", None)])
    evaluation = draft(people, studies[0])
    last = pulled(people, studies[0], 274)
    (test,) = assign(people, last)
    reviewed(people, test, "98.7")
    shown = shelf_life.data_digest(evaluation, shelf_life.of(evaluation))
    accept(people, last)
    assert shelf_life.data_digest(evaluation, shelf_life.of(evaluation)) != shown
    with pytest.raises(ValidationError, match="changed since this page was opened"):
        conclude(people, evaluation, data_hash=shown)


def test_whoever_produced_a_result_used_does_not_conclude(people):
    studies, _ = studies_with_results(people, [FALLING[0]])
    evaluation = draft(people, studies[0])
    analyst = people["analyst2"]
    analyst.groups.add(Group.objects.get(name="quality"))
    result = shelf_life.of(evaluation)
    assert analyst.pk in services.shelf_life_authors(evaluation, result)
    assert services.shelf_life_denial(analyst, evaluation, result) == (
        services.INDEPENDENT_SHELF_LIFE
    )
    with pytest.raises(PermissionDenied, match="another quality person concludes"):
        conclude(people, evaluation, actor="analyst2")
    # Reviewing a result or accepting a pull is not authorship.
    assert people["reviewer2"].pk not in services.shelf_life_authors(evaluation, result)


def test_nothing_fitted_cannot_be_concluded(people):
    studies, _ = studies_with_results(people, [("100.0", "99.6", None, None)])
    evaluation = draft(people, studies[0])
    result = shelf_life.of(evaluation)
    assert result.analysis is None and "3 or more time points" in result.problem
    assert services.shelf_life_denial(people["quality2"], evaluation, result).startswith(
        "Not ready to conclude."
    )
    with pytest.raises(ValidationError, match="nothing can be fitted"):
        conclude(people, evaluation)


def test_a_withdrawn_draft_frees_its_scope_and_never_changes(people):
    studies, _ = studies_with_results(people, [FALLING[0]])
    evaluation = draft(people, studies[0])
    with pytest.raises(PermissionDenied):
        services.withdraw_shelf_life(
            actor=people["reviewer"], evaluation=evaluation, expected_revision=1, reason="No"
        )
    withdrawn = services.withdraw_shelf_life(
        actor=people["quality"], evaluation=evaluation, expected_revision=1, reason="Wrong test"
    )
    assert withdrawn.state == "withdrawn" and withdrawn.withdrawn_at and withdrawn.revision == 2
    assert AuditEvent.objects.filter(
        action="shelf_life.withdrawn", object_id=str(evaluation.pk)
    ).exists()
    with pytest.raises(ValidationError, match="withdrawn"):
        conclude(people, withdrawn)
    again = draft(people, studies[0])
    assert again.pk != evaluation.pk and again.state == "draft"


def test_the_database_keeps_evaluations_and_their_studies(people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = draft(people, studies[0])
    with pytest.raises(DatabaseError, match="never deleted"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM stability_shelflifeevaluation WHERE id = %s", [evaluation.pk]
            )
    with pytest.raises(DatabaseError, match="drafted from is fixed"), transaction.atomic():
        ShelfLifeEvaluation.objects.filter(pk=evaluation.pk).update(
            lower_limit=Decimal("90"), revision=5
        )
    with pytest.raises(DatabaseError, match="advances its revision"), transaction.atomic():
        ShelfLifeEvaluation.objects.filter(pk=evaluation.pk).update(purpose="Quietly")
    other = started_study(people, protocol=approved_protocol(people, code="SYN-OTHER"))
    with pytest.raises(DatabaseError, match="its protocol and container closure"):
        with transaction.atomic():
            ShelfLifeStudy.objects.create(evaluation=evaluation, study=other)
    with pytest.raises(DatabaseError, match="linked or unlinked"), transaction.atomic():
        ShelfLifeStudy.objects.filter(evaluation=evaluation).update(study=studies[1])
    with pytest.raises(IntegrityError), transaction.atomic():
        ShelfLifeStudy.objects.create(evaluation=evaluation, study=studies[0])
    concluded = conclude(people, evaluation, months=6)
    with pytest.raises(DatabaseError, match="never changes"), transaction.atomic():
        ShelfLifeEvaluation.objects.filter(pk=concluded.pk).update(shelf_life_months=60, revision=9)
    with pytest.raises(DatabaseError, match="only while it is a draft"):
        with transaction.atomic():
            ShelfLifeStudy.objects.filter(evaluation=concluded).delete()
    with pytest.raises(DatabaseError, match="starts as a draft"), transaction.atomic():
        ShelfLifeEvaluation.objects.create(
            protocol_code="SYN-SL",
            product="Synthetic",
            container_closure="Synthetic marketed container",
            condition="Long-term",
            specification=evaluation.specification,
            specification_version=1,
            test_code="assay",
            name="Assay",
            unit="%",
            lower_limit=Decimal("95"),
            direction="decreases",
            purpose="Synthetic",
            drafted_by=people["quality"],
            state="withdrawn",
            withdrawn_at=concluded.concluded_at,
        )


def test_time_zero_of_another_condition_prefers_an_accepted_pull():
    from types import SimpleNamespace as N

    def pull(pk, study, label, days, state):
        timepoint = N(condition=N(label=label), interval_days=days)
        return N(pk=pk, study_id=study, timepoint=timepoint, state=state)

    missed = pull(1, 7, "Long-term", 0, "missed")
    accepted = pull(2, 7, "Intermediate", 0, "accepted")
    later = pull(3, 7, "Accelerated", 91, "accepted")
    own = pull(4, 8, "Accelerated", 0, "accepted")
    other = pull(5, 8, "Long-term", 0, "accepted")
    chosen = shelf_life.choose([missed, accepted, later, own, other], "Accelerated")
    assert chosen == [accepted, later, own]
    # Without an accepted one, the first recorded stands in.
    assert shelf_life.choose([missed, later], "Accelerated") == [missed, later]


def test_an_estimate_under_one_month_supports_no_whole_month():
    from types import SimpleNamespace as N

    def result(months):
        return N(
            analysis=object(),
            problem="",
            estimate=N(months=Decimal(months)),
            longest_supported=int(Decimal(months)),
        )

    assert services.shelf_life_problems(result("0.7"), OUTCOME.SUPPORTED, 1) == [
        "The estimate is under one month, so the data support no whole month of shelf life."
    ]
    assert "at time zero" in services.shelf_life_problems(result("0"), OUTCOME.SUPPORTED, 1)[0]
    assert services.shelf_life_problems(result("0.7"), OUTCOME.NOT_SUPPORTED, None) == []
