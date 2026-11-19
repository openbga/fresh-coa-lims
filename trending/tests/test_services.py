"""Trend charts, limits and out-of-trend evaluations through their services, on PostgreSQL:
roles, independence, stale revisions, PINs, the audit trail and the database guards."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature
from planning.reminders import reminders
from quality.services import disposition_notices
from trending import services
from trending.models import Chart, Evaluation, EvaluationAlert, Limits
from trending.series import series_of

from .conftest import BASELINE, PIN, reviewed_lot

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
ALL_RULES = ["beyond", "run", "trend", "two_of_three", "four_of_five"]


def chart_of(data, actor="author"):
    return services.create_chart(
        actor=data["people"][actor], line=data["line"], reason="Follow the assay"
    )


def computed(data, chart, actor="author", **extra):
    today = timezone.localdate()
    values = {
        "basis": "computed",
        "baseline_from": today,
        "baseline_to": today,
        "rules": ALL_RULES,
        "run_length": 8,
        "trend_length": 6,
        "rationale": "The first ten synthetic lots",
        **extra,
    }
    return services.draft_limits(
        actor=data["people"][actor], chart=chart, reason="First limits", **values
    )


def approved(data, limits, actor="approver"):
    limits.refresh_from_db()
    return services.approve_limits(
        actor=data["people"][actor],
        pin=PIN,
        limits=limits,
        expected_revision=limits.revision,
        reason="Independent review of the limits",
    )


@pytest.fixture
def charted(trend):
    """A chart of the assay with ten reviewed baseline results and approved computed limits."""
    for value in BASELINE:
        reviewed_lot(trend, value)
    chart = chart_of(trend)
    limits = approved(trend, computed(trend, chart))
    return {**trend, "chart": chart, "limits": limits}


def sql(statement, *params):
    """A direct statement, past the ORM's own delete collector, as the guards see it."""
    with connection.cursor() as cursor:
        cursor.execute(statement, params)


def fresh(obj):
    return type(obj).objects.get(pk=obj.pk)


# Charts ---------------------------------------------------------------------------------------


def test_quality_creates_a_chart_of_a_numeric_line_once(trend):
    with pytest.raises(PermissionDenied):
        chart_of(trend, actor="analyst")
    chart = chart_of(trend)
    assert (chart.material, chart.stage, chart.test_code, chart.unit, chart.decimals) == (
        trend["material"],
        "incoming",
        "assay",
        "%",
        2,
    )
    assert AuditEvent.objects.filter(action="trend_chart.created", object_id=str(chart.pk))
    with pytest.raises(ValidationError, match="has a chart"):
        chart_of(trend)
    identity = trend["spec"].tests.get(code="identity")
    with pytest.raises(ValidationError, match="numeric or count"):
        services.create_chart(actor=trend["people"]["author"], line=identity, reason="No")
    assert not services.chart_lines(uncharted=True).filter(pk=trend["line"].pk).exists()
    assert not services.chart_lines().filter(pk=identity.pk).exists()


def test_a_chart_is_never_changed_or_deleted(trend):
    chart = chart_of(trend)
    for statement in (
        lambda: Chart.objects.filter(pk=chart.pk).update(unit="mg"),
        lambda: Chart.objects.filter(pk=chart.pk).delete(),
    ):
        with pytest.raises(DatabaseError, match="never changed"), transaction.atomic():
            statement()


def test_points_are_the_reviewed_results_of_the_material_and_stage_in_review_order(trend):
    first = reviewed_lot(trend, "100.4")
    second = reviewed_lot(trend, "99.6")
    chart = chart_of(trend)
    series = series_of(chart)
    assert [p.test.pk for p in series.points] == [first.pk, second.pk]
    assert [p.value for p in series.points] == [D("100.40"), D("99.60")]
    assert series.versions == [] and series.alerts == []


def test_no_limits_are_drafted_from_too_few_results_and_one_draft_at_a_time(trend):
    for value in BASELINE[:5]:
        reviewed_lot(trend, value)
    chart = chart_of(trend)
    with pytest.raises(ValidationError, match="at least 8"):
        computed(trend, chart)
    entered = services.draft_limits(
        actor=trend["people"]["author"],
        chart=chart,
        reason="Alert limits from the procedure",
        basis="entered",
        center=D("100"),
        lower=D("98.5"),
        upper=D("101.5"),
        rules=["beyond", "run"],
        run_length=9,
        trend_length=6,
        rationale="SOP-QC-017 alert limits",
    )
    assert (entered.version, entered.state, entered.rules) == (1, "draft", ["beyond", "run"])
    with pytest.raises(ValidationError, match="has a draft"):
        computed(trend, chart)


def test_entered_limits_are_checked(trend):
    chart = chart_of(trend)
    base = {
        "basis": "entered",
        "rules": ["beyond"],
        "run_length": 8,
        "trend_length": 6,
        "rationale": "Procedure",
    }
    cases = [
        ({}, "lower"),
        ({"lower": D("101"), "upper": D("99")}, "upper"),
        ({"lower": D("99"), "upper": D("101"), "center": D("102")}, "center"),
        ({"lower": D("99"), "rules": ["beyond", "two_of_three"], "center": D("100")}, "sigma"),
        ({"lower": D("99"), "run_length": 20}, "run_length"),
    ]
    for extra, field in cases:
        with pytest.raises(ValidationError) as refused:
            services.draft_limits(
                actor=trend["people"]["author"], chart=chart, reason="Try", **{**base, **extra}
            )
        assert field in refused.value.message_dict


# Approval -------------------------------------------------------------------------------------


def test_computed_limits_are_approved_by_another_quality_person_with_a_signature(trend):
    for value in BASELINE:
        reviewed_lot(trend, value)
    chart = chart_of(trend)
    limits = computed(trend, chart)
    assert len(limits.baseline) == 10
    assert limits.center == D("100")  # 1000.0 / 10, at four places
    assert limits.sigma > 0 and limits.lower == limits.center - 3 * limits.sigma
    assert services.approval_denial(trend["people"]["author"], limits) == (
        services.INDEPENDENT_APPROVAL
    )
    with pytest.raises(PermissionDenied):
        approved(trend, limits, actor="author")
    # A quality person who changed the draft cannot approve it either.
    limits = services.change_limits(
        actor=trend["people"]["quality3"],
        limits=limits,
        expected_revision=limits.revision,
        reason="Shorter run",
        basis="computed",
        baseline_from=limits.baseline_from,
        baseline_to=limits.baseline_to,
        rules=ALL_RULES,
        run_length=9,
        trend_length=6,
        rationale=limits.rationale,
    )
    with pytest.raises(PermissionDenied):
        approved(trend, limits, actor="quality3")
    with pytest.raises(ValidationError, match="Record changed"):
        services.approve_limits(
            actor=trend["people"]["approver"],
            pin=PIN,
            limits=limits,
            expected_revision=limits.revision - 1,
            reason="Stale",
        )
    with pytest.raises(ValidationError):
        services.approve_limits(
            actor=trend["people"]["approver"],
            pin="00000000",
            limits=limits,
            expected_revision=limits.revision,
            reason="Wrong PIN",
        )
    assert AuditEvent.objects.filter(action="signature.denied").exists()
    limits = approved(trend, limits)
    assert limits.state == "approved" and limits.content["schema"] == "oq.trend-limits/1"
    assert limits.content["run_length"] == 9 and len(limits.content["baseline"]) == 10
    signature = ElectronicSignature.objects.get(object_id=str(limits.pk), meaning="approved")
    assert signature.signer == trend["people"]["approver"]


def test_the_baseline_ends_when_it_is_worked_out_and_a_change_to_it_stops_the_approval(trend):
    for value in BASELINE[:8]:
        reviewed_lot(trend, value)
    chart = chart_of(trend)
    limits = computed(trend, chart)
    assert limits.computed_at is not None and len(limits.baseline) == 8
    # A result reviewed later the same day is not part of the baseline.
    reviewed_lot(trend, "100.0")
    assert services.approval_denial(trend["people"]["approver"], fresh(limits)) == ""
    # A baseline result that no longer stands (here: one dropped from the stored list, as an
    # invalidation would) stops the approval until the draft is saved again.
    Limits.objects.filter(pk=limits.pk).update(
        baseline=limits.baseline[1:], revision=limits.revision + 1
    )
    assert "changed since the draft" in services.approval_denial(
        trend["people"]["approver"], fresh(limits)
    )
    with pytest.raises(ValidationError, match="changed since the draft"):
        approved(trend, limits)


def test_a_draft_changes_only_from_the_revision_its_page_showed(trend):
    for value in BASELINE[:8]:
        reviewed_lot(trend, value)
    limits = computed(trend, chart_of(trend))
    for revision in (None, limits.revision + 1):
        with pytest.raises(ValidationError, match="Record changed"):
            services.change_limits(
                actor=trend["people"]["author"],
                limits=limits,
                expected_revision=revision,
                reason="Stale",
                basis="computed",
                baseline_from=limits.baseline_from,
                baseline_to=limits.baseline_to,
                rules=ALL_RULES,
                run_length=9,
                trend_length=6,
                rationale="Changed",
            )


def test_approving_a_later_version_supersedes_the_one_in_force(charted):
    first = charted["limits"]
    later = services.draft_limits(
        actor=charted["people"]["author"],
        chart=charted["chart"],
        reason="Tighter alert limits",
        basis="entered",
        center=D("100"),
        sigma=D("0.2"),
        lower=D("99.4"),
        upper=D("100.6"),
        rules=ALL_RULES,
        run_length=8,
        trend_length=6,
        rationale="Process capability study PCS-7",
    )
    later = approved(charted, later)
    first = fresh(first)
    assert first.superseded_at == later.approved_at
    assert AuditEvent.objects.filter(action="trend_limits.superseded", object_id=str(first.pk))
    assert series_of(charted["chart"]).current == later


def test_the_database_keeps_approved_limits(charted):
    limits = charted["limits"]
    for statement, message in (
        (lambda: Limits.objects.filter(pk=limits.pk).update(upper=D("120")), "keeps what"),
        (lambda: Limits.objects.filter(pk=limits.pk).delete(), "never deleted"),
        (
            lambda: Limits.objects.filter(pk=limits.pk).update(state="draft", content=None),
            "keeps what|trending_limits_states",
        ),
    ):
        with pytest.raises(DatabaseError, match=message), transaction.atomic():
            statement()
    # Supersession is not backdated (beyond the allowance for two clocks), and is set once.
    with pytest.raises(DatabaseError, match="keeps what"), transaction.atomic():
        Limits.objects.filter(pk=limits.pk).update(
            superseded_at=timezone.now() - timezone.timedelta(days=1)
        )
    Limits.objects.filter(pk=limits.pk).update(superseded_at=timezone.now())
    with pytest.raises(DatabaseError, match="keeps what"), transaction.atomic():
        Limits.objects.filter(pk=limits.pk).update(superseded_at=timezone.now())
    # Nothing starts approved or concluded.
    approved_row = {
        "chart": charted["chart"],
        "version": 9,
        "state": "approved",
        "basis": "entered",
        "upper": D("101"),
        "rules": ["beyond"],
        "rationale": "Direct",
        "drafted_by": charted["people"]["author"],
        "approved_at": timezone.now(),
        "content": {},
        "content_hash": "x",
    }
    with pytest.raises(DatabaseError, match="starts as a draft"), transaction.atomic():
        Limits.objects.create(**approved_row)
    with pytest.raises(DatabaseError, match="starts open"), transaction.atomic():
        Evaluation.objects.create(
            chart=charted["chart"],
            opened_by=charted["people"]["author"],
            state="concluded",
            outcome="not_confirmed",
            conclusion="Direct",
            concluded_at=timezone.now(),
            content={},
            content_hash="x",
        )


# Alerts and evaluations -----------------------------------------------------------------------


def test_a_result_reviewed_under_approved_limits_raises_an_alert(charted):
    series = series_of(charted["chart"])
    assert len(series.points) == 10 and series.alerts == []
    inside = reviewed_lot(charted, "100.1")
    outside = reviewed_lot(charted, "103.0")
    series = series_of(charted["chart"])
    flagged = {p.test.pk: p.rules for p in series.points if p.rules}
    assert flagged == {outside.pk: ["beyond"]}
    assert [p.test.pk for p in series.open_alerts] == [outside.pk]
    assert inside.pk not in flagged
    reminder = [r for r in reminders(timezone.localdate(), 7, "trend")]
    assert len(reminder) == 1 and reminder[0].label.endswith(outside.label)
    notices = disposition_notices(outside.lot)
    assert any("raised an out-of-trend alert" in n and "not evaluated" in n for n in notices)
    assert not any("out-of-trend" in n for n in disposition_notices(inside.lot))


def alerting(data, *values):
    return [reviewed_lot(data, value) for value in values]


def test_an_evaluation_covers_open_alerts_and_is_concluded_independently(charted):
    people = charted["people"]
    first, second = alerting(charted, "103.0", "96.0")
    chart = charted["chart"]
    with pytest.raises(PermissionDenied):
        services.open_evaluation(
            actor=people["analyst"], chart=chart, tests=[first.pk], reason="Look into it"
        )
    calm = reviewed_lot(charted, "100.0")
    with pytest.raises(ValidationError, match="No longer open alerts"):
        services.open_evaluation(
            actor=people["author"], chart=chart, tests=[calm.pk], reason="Not an alert"
        )
    evaluation = services.open_evaluation(
        actor=people["author"], chart=chart, tests=[first.pk], reason="Look into it"
    )
    assert [a.test_id for a in evaluation.alerts.all()] == [first.pk]
    assert [p.test.pk for p in series_of(chart).open_alerts] == [second.pk]
    notices = disposition_notices(first.lot)
    assert any(f"under evaluation in {evaluation.identifier}" in n for n in notices)
    with pytest.raises(ValidationError, match="No longer open alerts"):
        services.open_evaluation(
            actor=people["author"], chart=chart, tests=[first.pk], reason="Twice"
        )
    evaluation = services.add_alerts(
        actor=people["author"],
        evaluation=evaluation,
        tests=[second.pk],
        expected_revision=evaluation.revision,
        reason="Same shift",
    )
    assert evaluation.alerts.count() == 2 and series_of(chart).open_alerts == []
    assert "Record the laboratory check." in services.conclusion_denial(
        people["approver"], evaluation
    )
    evaluation = services.record_findings(
        actor=people["quality3"],
        evaluation=evaluation,
        expected_revision=evaluation.revision,
        reason="Investigation notes",
        laboratory_check="Calculations, balance and titrant checked: no error.",
        cause="A new supplier lot of the starting material.",
        effect="Both lots conform; nothing reported is affected.",
        actions="",
        quality_reference="DEV-2026-031",
        impact_assessment=None,
    )
    with pytest.raises(ValidationError, match="Record changed"):
        services.record_findings(
            actor=people["quality3"],
            evaluation=evaluation,
            expected_revision=evaluation.revision - 1,
            reason="Stale",
            laboratory_check="x",
            cause="y",
            effect="z",
            actions="",
            quality_reference="",
            impact_assessment=None,
        )

    def conclude(actor, outcome="confirmed"):
        current = fresh(evaluation)
        return services.conclude_evaluation(
            actor=people[actor],
            pin=PIN,
            evaluation=current,
            expected_revision=current.revision,
            reason="Evaluation reviewed",
            outcome=outcome,
            conclusion="A supplier change shifted the assay; both lots stand.",
        )

    with pytest.raises(PermissionDenied):
        conclude("quality3")  # recorded the findings
    with pytest.raises(ValidationError, match="actions taken"):
        conclude("approver")  # confirmed needs actions
    done = conclude("approver", outcome="not_confirmed")
    assert done.state == "concluded" and done.content["schema"] == "oq.out-of-trend/1"
    assert [a["test"] for a in done.content["alerts"]] == [first.pk, second.pk]
    assert ElectronicSignature.objects.filter(object_id=str(done.pk), meaning="concluded")
    assert not any("out-of-trend" in n for n in disposition_notices(first.lot))
    with pytest.raises(ValidationError, match="concluded"):
        services.record_findings(
            actor=people["quality3"],
            evaluation=done,
            expected_revision=done.revision,
            reason="Too late",
            laboratory_check="x",
            cause="y",
            effect="z",
            actions="",
            quality_reference="",
            impact_assessment=None,
        )


def test_a_data_author_of_a_covered_result_does_not_conclude(charted):
    people = charted["people"]
    authored = reviewed_lot(charted, "103.5", analyst="analyst_quality")
    evaluation = services.open_evaluation(
        actor=people["author"], chart=charted["chart"], tests=[authored.pk], reason="Look"
    )
    evaluation = services.record_findings(
        actor=people["quality3"],
        evaluation=evaluation,
        expected_revision=evaluation.revision,
        reason="Notes",
        laboratory_check="Checked",
        cause="None found",
        effect="None",
        actions="",
        quality_reference="",
        impact_assessment=None,
    )
    assert services.conclusion_denial(people["analyst_quality"], evaluation) == (
        services.INDEPENDENT_CONCLUSION
    )
    assert services.conclusion_denial(people["approver"], evaluation) == ""


def test_the_database_keeps_evaluations_and_their_alerts(charted):
    people = charted["people"]
    (result,) = alerting(charted, "103.0")
    evaluation = services.open_evaluation(
        actor=people["author"], chart=charted["chart"], tests=[result.pk], reason="Look"
    )
    alert = EvaluationAlert.objects.get(evaluation=evaluation)
    for statement, message in (
        (lambda: EvaluationAlert.objects.filter(pk=alert.pk).update(rules=[]), "never changed"),
        (lambda: EvaluationAlert.objects.filter(pk=alert.pk).delete(), "never changed"),
        (
            lambda: sql("DELETE FROM trending_evaluation WHERE id = %s", evaluation.pk),
            "never deleted",
        ),
        (
            lambda: Evaluation.objects.filter(pk=evaluation.pk).update(cause="Quietly"),
            "advances its revision",
        ),
    ):
        with pytest.raises(DatabaseError, match=message), transaction.atomic():
            statement()
    other = reviewed_lot(charted, "100")
    draft = services.draft_limits(
        actor=people["author"],
        chart=charted["chart"],
        reason="Next version",
        basis="entered",
        upper=D("101"),
        rules=["beyond"],
        run_length=8,
        trend_length=6,
        rationale="Next version",
    )
    with pytest.raises(DatabaseError, match="approved limits version"), transaction.atomic():
        EvaluationAlert.objects.create(
            evaluation=evaluation,
            test=other,
            limits=draft,
            value=D("100"),
            reviewed_at=timezone.now(),
            rules=["beyond"],
            added_by=people["author"],
        )
    Evaluation.objects.filter(pk=evaluation.pk).update(
        state="concluded",
        outcome="not_confirmed",
        conclusion="Direct",
        concluded_at=timezone.now(),
        content={},
        content_hash="x",
        revision=evaluation.revision + 1,
    )
    with pytest.raises(DatabaseError, match="never changes"), transaction.atomic():
        Evaluation.objects.filter(pk=evaluation.pk).update(
            conclusion="Changed", revision=evaluation.revision + 2
        )
    with pytest.raises(DatabaseError, match="only while the evaluation is open"):
        with transaction.atomic():
            EvaluationAlert.objects.create(
                evaluation=evaluation,
                test=other,
                limits=charted["limits"],
                value=D("100"),
                reviewed_at=timezone.now(),
                rules=["beyond"],
                added_by=people["author"],
            )
