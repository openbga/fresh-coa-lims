"""Trend charts, their limits and out-of-trend evaluations: every change, with its locks.

Quality creates a chart from a numeric or count test line of a specification in force, drafts
its limits (computed from a baseline of reviewed results, or entered) and the rules that apply,
and another quality person approves them with a signature. Quality opens an out-of-trend
evaluation for open alerts of one chart, records what was found and done, and a quality person
who recorded none of the findings and none of the results' data concludes it with a signature.

Locks, in order: the actor's account (``lock_account``, or the signer's in ``sign_transition``),
the chart, then the limits version or the evaluation. Opening an evaluation and approving limits
both hold the chart, so the alerts an evaluation names are read against the versions that stand.
Which charts to keep, the rules and limits, and what follows an alert are the laboratory's
decisions: nothing here holds a lot or a test.
"""

from datetime import datetime, time, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.db.models.functions import Now
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from catalog.models import Material, RevisionStatus, SpecificationTest, Stage
from catalog.units import plain
from core.audit import record_event, snapshot
from core.models import AuditEvent
from core.services import require_role, sign_transition
from laboratory.services import lock_account

from . import rules as arithmetic
from .models import Chart, Evaluation, EvaluationAlert, Limits, Rule
from .series import CHARTED_TYPES, series_of

QUALITY = "quality"
READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
MAX_ALERTS = 50
LIMIT_FIELDS = (
    "basis",
    "baseline_from",
    "baseline_to",
    "center",
    "sigma",
    "lower",
    "upper",
    "rules",
    "run_length",
    "trend_length",
    "rationale",
)
FINDING_FIELDS = (
    "laboratory_check",
    "cause",
    "effect",
    "actions",
    "quality_reference",
    "impact_assessment",
)
DRAFT_ACTIONS = ("trend_limits.drafted", "trend_limits.changed")
FINDINGS_ACTION = "evaluation.findings_recorded"
BASIS = Limits.Basis
OUTCOME = Evaluation.Outcome

INDEPENDENT_APPROVAL = "You drafted or changed these limits; another quality person approves them."
INDEPENDENT_CONCLUSION = (
    "You recorded findings of this evaluation, or data of a result it covers; another quality "
    "person concludes it."
)


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _lock_chart(chart):
    """The chart row, locked: it is never updated, so the lock only serializes the writers that
    read the chart's series (opening an evaluation, adding alerts, approving limits)."""
    return Chart.objects.select_for_update(no_key=True).select_related("material").get(pk=chart.pk)


def _actors(obj, actions):
    return set(
        AuditEvent.objects.filter(
            object_type=obj._meta.label_lower, object_id=str(obj.pk), action__in=actions
        ).values_list("actor_id", flat=True)
    )


# Charts ---------------------------------------------------------------------------------------


def chart_lines(uncharted=False):
    """The test lines a chart can be created from: numeric and count lines of the approved
    specification versions in force now, at any stage but stability; with ``uncharted``, only
    those whose test has no chart yet for its material and stage."""
    # The database's clock, so that the form's queryset and the lookup's are the same query.
    now = Now()
    lines = (
        SpecificationTest.objects.filter(
            specification_revision__status=RevisionStatus.APPROVED,
            specification_revision__effective_from__lte=now,
            specification_revision__effective_until__gt=now,
            result_type__in=CHARTED_TYPES,
        )
        .exclude(specification_revision__superseded_from__lte=now)
        .exclude(specification_revision__specification__stage=Stage.STABILITY)
        .select_related(
            "specification_revision__specification__material", "method", "specification_revision"
        )
    )
    if uncharted:
        spec = "specification_revision__specification__"
        lines = lines.exclude(
            Exists(
                Chart.objects.filter(
                    material=OuterRef(spec + "material"),
                    stage=OuterRef(spec + "stage"),
                    test_code=OuterRef("code"),
                )
            )
        )
    return lines


def line_label(line):
    spec = line.specification_revision.specification
    return (
        f"{spec.material.code} · {spec.get_stage_display()} · {line.code} ({line.unit}) · "
        f"{spec.code} v{line.specification_revision.version}"
    )


@transaction.atomic
def create_chart(*, actor, line, reason):
    """Create the chart of ``line``'s test for its specification's material and stage."""
    require_role(actor, QUALITY)
    _require_reason(reason)
    lock_account(actor)
    line = chart_lines().filter(pk=line.pk).first()
    if line is None:
        raise ValidationError(
            {"line": "Choose a numeric or count test of a specification version in force."}
        )
    spec = line.specification_revision.specification
    # Charts of one material are created one at a time, so the same test is never charted
    # twice by two requests at once.
    Material.objects.select_for_update(no_key=True).get(pk=spec.material_id)
    if Chart.objects.filter(
        material_id=spec.material_id, stage=spec.stage, test_code=line.code
    ).exists():
        raise ValidationError({"line": "This test of this material and stage has a chart."})
    chart = Chart(
        material_id=spec.material_id,
        stage=spec.stage,
        test_code=line.code,
        name=line.name,
        unit=line.unit,
        decimals=line.reporting_decimals,
        created_by=actor,
    )
    chart.full_clean()
    chart.save()
    record_event(
        actor=actor,
        action="trend_chart.created",
        obj=chart,
        after={
            **snapshot(chart),
            "line": {"specification": spec.code, "version": line.specification_revision.version},
        },
        reason=reason,
    )
    return chart


# Limits ---------------------------------------------------------------------------------------


def period_bounds(start, end):
    """The aware datetimes of the local days ``start`` to ``end`` inclusive: [from, until)."""
    zone = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start, time.min), zone),
        timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), zone),
    )


def baseline_points(chart, start, end, cutoff, series=None):
    """The plotted results of ``chart`` reviewed on the local days ``start`` to ``end`` and
    before ``cutoff`` (the moment the figures were worked out), in review order, leaving out
    those that fail their specification: an out-of-specification result has a cause of its own
    and would widen the limits."""
    since, until = period_bounds(start, end)
    until = min(until, cutoff)
    series = series or series_of(chart)
    return [
        point for point in series.points if since <= point.reviewed_at < until and point.conforms
    ]


def frozen_baseline(points):
    return [
        {
            "test": point.test.pk,
            "lot": point.test.lot.number,
            "value": plain(point.value),
            "reviewed_at": point.reviewed_at.isoformat(),
        }
        for point in points
    ]


def _limit_values(chart, values, series=None):
    """The fields of a draft from ``values``, checked; computed figures worked out."""
    unknown = set(values) - set(LIMIT_FIELDS)
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}.")
    data = {name: _strip(values.get(name)) for name in LIMIT_FIELDS}
    data["rationale"] = data["rationale"] or ""
    chosen = {str(rule) for rule in (data["rules"] or [])}
    if unknown := chosen - set(Rule.values):
        raise ValidationError({"rules": f"Unknown rules: {', '.join(sorted(unknown))}."})
    # A result outside the limits is always a rule; the others keep the order of ``Rule``.
    data["rules"] = [rule for rule in Rule.values if rule in chosen | {Rule.BEYOND.value}]
    errors = {}
    if data["basis"] not in BASIS.values:
        raise ValidationError({"basis": "Choose how the limits are set."})
    if data["basis"] == BASIS.COMPUTED:
        start, end = data["baseline_from"], data["baseline_to"]
        if not start:
            errors["baseline_from"] = "State the first day of the baseline."
        if not end:
            errors["baseline_to"] = "State the last day of the baseline."
        elif end > timezone.localdate():
            errors["baseline_to"] = "The baseline cannot end after today."
        if start and end and start > end:
            errors["baseline_to"] = "The baseline cannot end before it starts."
        if errors:
            raise ValidationError(errors)
        cutoff = timezone.now()
        points = baseline_points(chart, start, end, cutoff, series)
        figures = arithmetic.baseline([point.value for point in points], chart.decimals)
        data.update(
            computed_at=cutoff,
            center=figures.center,
            sigma=figures.sigma,
            lower=figures.lower,
            upper=figures.upper,
            baseline=frozen_baseline(points),
        )
    else:
        data.update(baseline_from=None, baseline_to=None, baseline=[], computed_at=None)
        lower, upper, center, sigma = (data[n] for n in ("lower", "upper", "center", "sigma"))
        if lower is None and upper is None:
            errors["lower"] = "Enter a lower limit, an upper limit or both."
        if lower is not None and upper is not None and lower >= upper:
            errors["upper"] = "The upper limit must be above the lower limit."
        if sigma is not None and sigma <= 0:
            errors["sigma"] = "σ must be above zero."
        if center is not None and (
            (lower is not None and center <= lower) or (upper is not None and center >= upper)
        ):
            errors["center"] = "The center line must lie between the limits."
    errors.update(
        arithmetic.rule_problems(data["rules"], center=data["center"], sigma=data["sigma"])
    )
    if not data["rationale"]:
        errors["rationale"] = "State the basis of these limits."
    for name, low, high in (("run_length", 6, 12), ("trend_length", 5, 10)):
        if data[name] is None or not low <= data[name] <= high:
            errors[name] = f"Choose between {low} and {high}."
    if errors:
        raise ValidationError(errors)
    return data


@transaction.atomic
def draft_limits(*, actor, chart, reason, **values):
    """Draft the next version of ``chart``'s limits. One draft at a time."""
    require_role(actor, QUALITY)
    _require_reason(reason)
    lock_account(actor)
    chart = _lock_chart(chart)
    if Limits.objects.filter(chart=chart, state=Limits.State.DRAFT).exists():
        raise ValidationError(
            f"{chart.identifier} has a draft of its limits: change that draft instead."
        )
    data = _limit_values(chart, values)
    last = Limits.objects.filter(chart=chart).order_by("-version").first()
    limits = Limits(
        chart=chart, version=(last.version + 1 if last else 1), drafted_by=actor, **data
    )
    limits.full_clean()
    limits.save()
    record_event(
        actor=actor,
        action="trend_limits.drafted",
        obj=limits,
        after=snapshot(limits),
        reason=reason,
    )
    return limits


def _check_revision(locked, expected_revision):
    """Every change names the revision its page showed."""
    if expected_revision is None or locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before saving.")


def _locked_draft(limits, expected_revision):
    locked = Limits.objects.select_for_update().select_related("chart").get(pk=limits.pk)
    if locked.state != Limits.State.DRAFT:
        raise ValidationError(f"{locked.identifier} is approved: draft a new version instead.")
    _check_revision(locked, expected_revision)
    return locked


@transaction.atomic
def change_limits(*, actor, limits, expected_revision, reason, **values):
    """Change a draft. A computed draft is worked out again from the baseline as it now
    stands. Whoever changes a draft cannot approve it."""
    require_role(actor, QUALITY)
    _require_reason(reason)
    lock_account(actor)
    chart = _lock_chart(limits.chart)
    locked = _locked_draft(limits, expected_revision)
    data = _limit_values(chart, values)
    unchanged = (
        getattr(locked, name) == value for name, value in data.items() if name != "computed_at"
    )
    if all(unchanged):
        raise ValidationError("Nothing was changed.")
    before = snapshot(locked)
    for name, value in data.items():
        setattr(locked, name, value)
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="trend_limits.changed",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


def drafters(limits):
    return _actors(limits, DRAFT_ACTIONS) | {limits.drafted_by_id}


def baseline_change(limits, series=None):
    """Why a computed draft no longer matches its baseline (a result reviewed in the period
    since, or invalidated), or ""."""
    if limits.basis != BASIS.COMPUTED:
        return ""
    points = baseline_points(
        limits.chart, limits.baseline_from, limits.baseline_to, limits.computed_at, series
    )
    if frozen_baseline(points) != limits.baseline:
        return (
            "The results of the baseline changed since the draft was saved (a result was "
            "invalidated or its lot assigned again). Save the draft again to work out its limits "
            "from them."
        )
    return ""


def approval_denial(actor, limits):
    """Why ``actor`` cannot approve ``limits`` now, or "". Signing checks it again under lock."""
    if limits.state != Limits.State.DRAFT:
        return f"{limits.identifier} is already approved."
    if actor.pk in drafters(limits):
        return INDEPENDENT_APPROVAL
    return baseline_change(limits)


def frozen_limits(limits):
    from catalog.services import digest

    chart = limits.chart
    content = {
        "schema": "oq.trend-limits/1",
        "chart": {
            "id": chart.pk,
            "material": chart.material.code,
            "stage": chart.stage,
            "test_code": chart.test_code,
            "unit": chart.unit,
        },
        "version": limits.version,
        "basis": limits.basis,
        "baseline_from": limits.baseline_from.isoformat() if limits.baseline_from else None,
        "baseline_to": limits.baseline_to.isoformat() if limits.baseline_to else None,
        "baseline": limits.baseline,
        "computed_at": limits.computed_at.isoformat() if limits.computed_at else None,
        "center": plain(limits.center),
        "sigma": plain(limits.sigma),
        "lower": plain(limits.lower),
        "upper": plain(limits.upper),
        "rules": limits.rules,
        "run_length": limits.run_length,
        "trend_length": limits.trend_length,
        "rationale": limits.rationale,
    }
    return content, digest(content)


@sensitive_variables("pin")
def approve_limits(*, actor, pin, limits, expected_revision, reason):
    """Approve a draft with a signature: from the signing moment results are judged by it, and
    the version it follows stops applying."""
    chart = limits.chart

    def lock():
        _lock_chart(chart)

    def apply(locked):
        if locked.state != Limits.State.DRAFT:
            raise ValidationError(f"{locked.identifier} is already approved.")
        if actor.pk in drafters(locked):
            raise PermissionDenied(INDEPENDENT_APPROVAL)
        if change := baseline_change(locked):
            raise ValidationError(change)
        problems = arithmetic.rule_problems(locked.rules, center=locked.center, sigma=locked.sigma)
        if problems:
            raise ValidationError(list(problems.values()))
        moment = locked._signing_timestamp
        for previous in Limits.objects.select_for_update().filter(
            chart_id=locked.chart_id, state=Limits.State.APPROVED, superseded_at__isnull=True
        ):
            before = snapshot(previous)
            previous.superseded_at = moment
            previous.save(update_fields=["superseded_at"])
            record_event(
                actor=actor,
                action="trend_limits.superseded",
                obj=previous,
                before=before,
                after=snapshot(previous),
                reason=f"Superseded by version {locked.version}: {reason}",
            )
        locked.content, locked.content_hash = frozen_limits(locked)
        locked.state = Limits.State.APPROVED
        locked.approved_at = moment

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=limits,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission=QUALITY,
        apply=apply,
        prepare=lock,
    )


# Evaluations ----------------------------------------------------------------------------------


def _alert_rows(series, test_ids, evaluation, actor):
    """The alert rows for ``test_ids``, each an open alert of ``series``."""
    wanted = set(test_ids)
    if not wanted:
        raise ValidationError({"alerts": "Choose at least one alert."})
    open_alerts = {point.test.pk: point for point in series.open_alerts}
    missing = sorted(wanted - set(open_alerts))
    if missing:
        raise ValidationError(
            {
                "alerts": "No longer open alerts of this chart: "
                + ", ".join(f"T-{pk}" for pk in missing)
                + ". Reload the chart."
            }
        )
    return [
        EvaluationAlert(
            evaluation=evaluation,
            test=open_alerts[pk].test,
            limits=open_alerts[pk].limits,
            value=open_alerts[pk].value,
            reviewed_at=open_alerts[pk].reviewed_at,
            rules=open_alerts[pk].rules,
            added_by=actor,
        )
        for pk in sorted(wanted)
    ]


def alert_content(alert):
    return {
        "test": alert.test_id,
        "lot": alert.test.lot.number,
        "value": plain(alert.value),
        "reviewed_at": alert.reviewed_at.isoformat(),
        "limits": alert.limits.version,
        "rules": alert.rules,
    }


@transaction.atomic
def open_evaluation(*, actor, chart, tests, reason):
    """Open an out-of-trend evaluation of ``tests`` (ids), each an open alert of ``chart``."""
    require_role(actor, QUALITY)
    _require_reason(reason)
    lock_account(actor)
    chart = _lock_chart(chart)
    if len(set(tests)) > MAX_ALERTS:
        raise ValidationError({"alerts": f"An evaluation covers at most {MAX_ALERTS} alerts."})
    series = series_of(chart)
    evaluation = Evaluation(chart=chart, opened_by=actor)
    rows = _alert_rows(series, tests, evaluation, actor)
    evaluation.full_clean()
    evaluation.save()
    EvaluationAlert.objects.bulk_create(rows)
    record_event(
        actor=actor,
        action="evaluation.opened",
        obj=evaluation,
        after={"chart": chart.pk, "alerts": [alert_content(row) for row in rows]},
        reason=reason,
    )
    return evaluation


def _locked_open(evaluation, expected_revision):
    locked = Evaluation.objects.select_for_update().get(pk=evaluation.pk)
    if locked.state != Evaluation.State.OPEN:
        raise ValidationError(f"{locked.identifier} is concluded: it no longer changes.")
    _check_revision(locked, expected_revision)
    return locked


@transaction.atomic
def add_alerts(*, actor, evaluation, tests, expected_revision, reason):
    """Add further open alerts of the same chart to an open evaluation."""
    require_role(actor, QUALITY)
    _require_reason(reason)
    lock_account(actor)
    chart = _lock_chart(evaluation.chart)
    locked = _locked_open(evaluation, expected_revision)
    if locked.alerts.count() + len(set(tests)) > MAX_ALERTS:
        raise ValidationError({"alerts": f"An evaluation covers at most {MAX_ALERTS} alerts."})
    rows = _alert_rows(series_of(chart), tests, locked, actor)
    EvaluationAlert.objects.bulk_create(rows)
    locked.revision += 1
    locked.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="evaluation.alerts_added",
        obj=locked,
        after={"alerts": [alert_content(row) for row in rows]},
        reason=reason,
    )
    return locked


@transaction.atomic
def record_findings(*, actor, evaluation, expected_revision, reason, **values):
    """Record or change what an open evaluation found and did. Whoever does cannot conclude it."""
    require_role(actor, QUALITY)
    _require_reason(reason)
    lock_account(actor)
    locked = _locked_open(evaluation, expected_revision)
    unknown = set(values) - set(FINDING_FIELDS)
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}.")
    data = {name: _strip(values.get(name)) for name in FINDING_FIELDS}
    for name in FINDING_FIELDS:
        if data[name] is None and name != "impact_assessment":
            data[name] = ""
    assessment = data["impact_assessment"]
    if assessment is not None and assessment.state == "withdrawn":
        raise ValidationError({"impact_assessment": f"{assessment.label} was withdrawn."})
    if all(getattr(locked, name) == value for name, value in data.items()):
        raise ValidationError("Nothing was changed.")
    before = snapshot(locked)
    for name, value in data.items():
        setattr(locked, name, value)
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action=FINDINGS_ACTION,
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


def covered_tests(evaluation):
    from analytical.models import AnalyticalTest

    return AnalyticalTest.objects.filter(pk__in=evaluation.alerts.values_list("test_id", flat=True))


def conclusion_authors(evaluation):
    """Who recorded the evaluation's findings, or data of a result it covers: they do not
    conclude it. Opening it or adding alerts is not authorship."""
    from analytical.gates import tests_author_ids

    return _actors(evaluation, (FINDINGS_ACTION,)) | tests_author_ids(covered_tests(evaluation))


def assessment_refusal(assessment):
    if assessment is None:
        return None
    if assessment.state == "withdrawn":
        return f"{assessment.label} was withdrawn: name another impact assessment or none."
    if assessment.state != "concluded":
        return f"{assessment.label} is still open: conclude it before this evaluation."
    return None


def conclusion_problems(evaluation, outcome=None):
    """What keeps an open evaluation from being concluded, in the words of the page."""
    problems = []
    for name, text in (
        ("laboratory_check", "Record the laboratory check."),
        ("cause", "Record the cause found, or that none was found."),
        ("effect", "Record whether the lots and results already reported are affected."),
    ):
        if not getattr(evaluation, name).strip():
            problems.append(text)
    if outcome == OUTCOME.CONFIRMED and not evaluation.actions.strip():
        problems.append("Record the actions taken on a confirmed out-of-trend result.")
    if refusal := assessment_refusal(evaluation.impact_assessment):
        problems.append(refusal)
    return problems


def conclusion_denial(actor, evaluation):
    if evaluation.state != Evaluation.State.OPEN:
        return f"{evaluation.identifier} is already concluded."
    if actor.pk in conclusion_authors(evaluation):
        return INDEPENDENT_CONCLUSION
    if problems := conclusion_problems(evaluation):
        return "Not ready to conclude. " + " ".join(problems)
    return ""


def frozen_evaluation(evaluation):
    from catalog.services import digest

    chart = evaluation.chart
    assessment = evaluation.impact_assessment
    alerts = evaluation.alerts.select_related("test__lot", "limits").order_by("reviewed_at", "pk")
    content = {
        "schema": "oq.out-of-trend/1",
        "identifier": evaluation.identifier,
        "chart": {
            "id": chart.pk,
            "material": chart.material.code,
            "stage": chart.stage,
            "test_code": chart.test_code,
            "unit": chart.unit,
        },
        "alerts": [alert_content(alert) for alert in alerts],
        "laboratory_check": evaluation.laboratory_check,
        "cause": evaluation.cause,
        "effect": evaluation.effect,
        "actions": evaluation.actions,
        "quality_reference": evaluation.quality_reference,
        "impact_assessment": {"id": assessment.pk, "label": assessment.label}
        if assessment
        else None,
        "outcome": evaluation.outcome,
        "conclusion": evaluation.conclusion,
    }
    return content, digest(content)


@sensitive_variables("pin")
def conclude_evaluation(*, actor, pin, evaluation, expected_revision, reason, outcome, conclusion):
    """Conclude an evaluation with a signature that freezes it: out of trend confirmed, or
    not confirmed."""
    from impact.models import Assessment

    chart = evaluation.chart

    def lock():
        _lock_chart(chart)
        # The impact assessment named is read under lock, so a withdrawal signed meanwhile
        # waits for the conclusion or the conclusion for it.
        named = Evaluation.objects.filter(pk=evaluation.pk).values_list(
            "impact_assessment", flat=True
        )
        list(Assessment.objects.select_for_update(no_key=True).filter(pk__in=named))

    def apply(locked):
        if locked.state != Evaluation.State.OPEN:
            raise ValidationError(f"{locked.identifier} is already concluded.")
        if actor.pk in conclusion_authors(locked):
            raise PermissionDenied(INDEPENDENT_CONCLUSION)
        if outcome not in OUTCOME.values:
            raise ValidationError({"outcome": "Choose the outcome."})
        if not (conclusion or "").strip():
            raise ValidationError({"conclusion": "State the conclusion."})
        if problems := conclusion_problems(locked, outcome):
            raise ValidationError(problems)
        locked.outcome = outcome
        locked.conclusion = conclusion.strip()
        locked.content, locked.content_hash = frozen_evaluation(locked)
        locked.state = Evaluation.State.CONCLUDED
        locked.concluded_at = locked._signing_timestamp

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=evaluation,
        expected_revision=expected_revision,
        meaning="concluded",
        reason=reason,
        permission=QUALITY,
        apply=apply,
        prepare=lock,
    )


def assessment_choices():
    from impact.models import Assessment

    return Assessment.objects.exclude(state="withdrawn")
