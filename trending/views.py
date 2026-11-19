"""Pages of trend charts, their limits and out-of-trend evaluations (HTTP only; the rules are in
``trending.services``, the reading of results in ``trending.series``)."""

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.units import plain
from catalog.views import form_page
from catalog.web import can, run
from core.people import person
from core.services import require_role
from laboratory.forms import SigningForm
from laboratory.ui import (
    action,
    cell,
    critical,
    day,
    list_page,
    make_filter,
    paginate,
    record_page,
    refused,
    section,
    sign_page,
    status,
)
from laboratory.ui import when as stamp

from . import plot, services
from .forms import AlertsForm, ChartForm, ConcludeForm, FindingsForm, LimitsForm
from .models import Chart, Evaluation, Limits
from .rules import ADVISED_BASELINE, describe
from .series import all_series, series_of

SECTION = "Trends"
SHOWN = 100  # the latest results drawn and listed on a chart's page
QUALITY = services.QUALITY
WHAT_IT_IS = (
    "A trend chart follows one test of one material at one stage: the reviewed results of its "
    "lots in the order their reviews were signed, judged by the limits and rules quality "
    "approved."
)
CHART_FILTER = [
    ("alerts", "Open alerts"),
    ("no_limits", "No approved limits"),
    ("draft", "Limits drafted"),
]
EVALUATION_FILTER = [("open", "Open"), ("concluded", "Concluded")]


def _read(request):
    require_role(request.user, *services.READ_ROLES)


def _crumbs(*trail):
    return [(SECTION, reverse("trending:chart_list")), *trail]


def chart_url(chart):
    return reverse("trending:chart_detail", args=[chart.pk])


def limits_url(limits):
    return reverse("trending:limits_detail", args=[limits.pk])


def evaluation_url(evaluation):
    return reverse("trending:evaluation_detail", args=[evaluation.pk])


def _count(number, noun):
    return f"{number} {noun}{'' if number == 1 else 's'}"


def chart_state(series):
    alerts = len(series.open_alerts)
    if alerts:
        return status(_count(alerts, "open alert"), "danger")
    if series.current is None:
        return status("No approved limits", "neutral")
    return status("No open alert", "success")


def limits_state(limits):
    if limits.state == Limits.State.DRAFT:
        return status("Draft", "progress")
    if limits.superseded_at:
        return status("Superseded", "neutral")
    return status("In force", "success")


def evaluation_state(evaluation):
    if evaluation.state == Evaluation.State.OPEN:
        return status("Open", "warning")
    tone = "danger" if evaluation.outcome == Evaluation.Outcome.CONFIRMED else "success"
    return status(evaluation.get_outcome_display(), tone)


def rules_text(limits):
    return "; ".join(
        describe(rule, run_length=limits.run_length, trend_length=limits.trend_length)
        for rule in limits.rules
    )


def value_text(value, unit):
    return f"{plain(value)} {unit}" if value is not None else ""


# Charts ---------------------------------------------------------------------------------------


@login_required
def chart_list(request):
    _read(request)
    form, data = make_filter(
        request, CHART_FILTER, extra={"stage": ("Stage", Chart._meta.get_field("stage").choices)}
    )
    queryset = Chart.objects.select_related("material")
    if q := data.get("q"):
        queryset = queryset.filter(
            Q(test_code__icontains=q)
            | Q(name__icontains=q)
            | Q(material__code__icontains=q)
            | Q(material__name__icontains=q)
        )
    if data.get("stage"):
        queryset = queryset.filter(stage=data["stage"])
    match data.get("status"):
        case "alerts":
            alerting = [s.chart.pk for s in all_series(queryset) if s.open_alerts]
            queryset = queryset.filter(pk__in=alerting)
        case "no_limits":
            queryset = queryset.exclude(versions__state=Limits.State.APPROVED)
        case "draft":
            queryset = queryset.filter(versions__state=Limits.State.DRAFT)
    page, sort, descending = paginate(
        request,
        queryset.distinct(),
        {"chart": ["id"], "material": ["material__code", "test_code"], "test": ["test_code"]},
        "material",
    )
    series = {s.chart.pk: s for s in all_series(list(page))}
    rows = []
    for chart in page:
        current = series[chart.pk].current
        points = series[chart.pk].points
        rows.append(
            [
                cell(chart.identifier, chart_url(chart), sub=chart.name),
                cell(chart.material.code, sub=chart.material.name),
                chart.test_code,
                chart.get_stage_display(),
                cell(f"v{current.version}", limits_url(current)) if current else "",
                cell(str(len(points)), numeric=True),
                stamp(points[-1].reviewed_at) if points else "",
                chart_state(series[chart.pk]),
            ]
        )
    return list_page(
        request,
        title="Trend charts",
        intro=WHAT_IT_IS + " A result that breaks a rule raises an out-of-trend alert for quality "
        "to evaluate.",
        noun="trend charts",
        columns=[
            ("Chart", "chart", False),
            ("Material", "material", False),
            ("Test", "test", False),
            ("Stage", None, False, "low"),
            ("Limits", None, False),
            ("Results", None, True, "low"),
            ("Last reviewed", None, False, "low"),
            ("State", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "trend chart", "href": reverse("trending:chart_new")}
        if can(request.user, QUALITY)
        else None,
        empty_body="Quality creates a chart for each test whose results it wants to follow, from "
        "a numeric or count test of a specification in force.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def chart_new(request):
    require_role(request.user, QUALITY)
    form = ChartForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        chart = run(
            form,
            lambda: services.create_chart(
                actor=request.user,
                line=form.cleaned_data["line"],
                reason=form.cleaned_data["reason"],
            ),
        )
        if chart:
            messages.success(request, f"{chart.identifier} created. Draft its limits next.")
            return redirect(chart_url(chart))
    return form_page(
        request,
        form,
        title="New trend chart",
        crumbs=_crumbs(("New trend chart", None)),
        cancel_url=reverse("trending:chart_list"),
        submit_label="Create chart",
        intro=WHAT_IT_IS + " Results are plotted at once; alerts start when limits are approved.",
    )


def _point_flag(point):
    if not point.conforms:
        return status("Out of specification", "danger")
    if point.raised:
        if point.covered:
            return cell(
                point.covered.evaluation.identifier,
                evaluation_url(point.covered.evaluation),
                pill=("Alert", "warning"),
            )
        return status("Alert, not evaluated", "danger")
    return ""


def _broken_text(point):
    if not point.raised:
        return ""
    return "; ".join(
        describe(r, run_length=point.limits.run_length, trend_length=point.limits.trend_length)
        for r in point.rules
    )


def _test_cell(test):
    return cell(test.label, reverse("analytical:test_detail", args=[test.pk]), sub=test.kind)


def _lot_cell(test):
    return cell(test.lot.number, reverse("quality:lot_detail", args=[test.lot_id]))


def point_rows(points, unit):
    return [
        [
            _test_cell(point.test),
            _lot_cell(point.test),
            cell(f"{point.text} {unit}", numeric=True),
            stamp(point.reviewed_at),
            cell(f"v{point.limits.version}", limits_url(point.limits)) if point.limits else "",
            _point_flag(point),
            cell(_broken_text(point), wrap=True),
        ]
        for point in points
    ]


POINT_COLUMNS = [
    ("Test", False),
    ("Lot", False),
    ("Result", True),
    ("Review signed", False),
    ("Limits", False, "low"),
    ("Flag", False),
    ("Rules broken", False, "medium"),
]


def _chart(pk):
    return get_object_or_404(Chart.objects.select_related("material", "created_by"), pk=pk)


def _chart_actions(user, chart, series):
    if not can(user, QUALITY):
        return []
    actions = []
    draft = chart.versions.filter(state=Limits.State.DRAFT).first()
    if draft:
        actions.append(action(f"Open draft v{draft.version}", limits_url(draft)))
    else:
        actions.append(
            action(
                "Draft limits",
                reverse("trending:limits_new", args=[chart.pk]),
                not series.open_alerts,
            )
        )
    if series.open_alerts:
        actions.append(
            action("Evaluate alerts", reverse("trending:evaluation_new", args=[chart.pk]), True)
        )
    return actions


def _chart_notice(series):
    if series.open_alerts:
        return {
            "tone": "danger",
            "label": "Out-of-trend alerts",
            "text": f"{_count(len(series.open_alerts), 'result')} broke a rule of the limits in "
            "force and no evaluation covers them yet. Quality evaluates them.",
        }
    if series.current is None:
        return {
            "tone": "info",
            "label": "No approved limits",
            "text": "Results are plotted, but no alert is raised until a version of the limits "
            "is approved.",
        }
    return None


@login_required
def chart_detail(request, pk):
    _read(request)
    chart = _chart(pk)
    series = series_of(chart)
    shown = series.points[-SHOWN:]
    current = series.current
    note = ""
    if len(series.points) > len(shown):
        note = f"The latest {len(shown)} of {len(series.points)} results are drawn and listed."
    drawing = plot.geometry(chart, shown, caption=note)
    facts = [
        ("Material", f"{chart.material.code} · {chart.material.name}"),
        ("Stage", chart.get_stage_display()),
        ("Test", f"{chart.test_code} · {chart.name}"),
        ("Unit", chart.unit),
        (
            "Limits in force",
            cell(f"v{current.version}", limits_url(current)) if current else "None",
        ),
    ]
    if current:
        facts += [
            ("Center line", value_text(current.center, chart.unit)),
            (
                "Limits",
                " to ".join(
                    value_text(v, chart.unit)
                    for v in (current.lower, current.upper)
                    if v is not None
                ),
            ),
            ("Rules", cell(rules_text(current), wrap=True)),
        ]
    facts += [
        ("Results plotted", str(len(series.points))),
        ("Created by", person(chart.created_by)),
    ]
    versions = list(chart.versions.order_by("-version"))
    evaluations = list(chart.evaluations.annotate(covered=Count("alerts")).order_by("-pk"))
    sections = [
        section(
            "Open alerts",
            POINT_COLUMNS,
            point_rows(reversed(series.open_alerts), chart.unit),
            "No open alert.",
            note="Results that conform to their specification and broke a rule of the limits in "
            "force when their review was signed, not yet covered by an evaluation.",
        ),
        section(
            "Results",
            POINT_COLUMNS,
            point_rows(reversed(shown), chart.unit),
            "No reviewed result of this test yet.",
            note="Newest first. "
            + (note or "")
            + " A result that fails its specification is left to its out-of-specification "
            "investigation and raises no alert here.",
        ),
    ]
    if series.unplotted:
        sections.append(
            section(
                "Not plotted",
                [("Test", False), ("Lot", False), ("Review signed", False), ("Why", False)],
                [
                    [
                        _test_cell(item.test),
                        _lot_cell(item.test),
                        stamp(item.reviewed_at),
                        item.reason,
                    ]
                    for item in reversed(series.unplotted)
                ],
                "",
                note="Reviewed results of this test without a value in the chart's unit.",
            )
        )
    sections += [
        section(
            "Limits versions",
            [
                ("Version", False),
                ("State", False),
                ("Basis", False),
                ("Center line", True),
                ("Lower limit", True),
                ("Upper limit", True),
                ("Approved", False, "low"),
            ],
            [
                [
                    cell(f"v{v.version}", limits_url(v)),
                    limits_state(v),
                    v.get_basis_display(),
                    cell(value_text(v.center, chart.unit), numeric=True),
                    cell(value_text(v.lower, chart.unit), numeric=True),
                    cell(value_text(v.upper, chart.unit), numeric=True),
                    stamp(v.approved_at),
                ]
                for v in versions
            ],
            "No limits drafted yet.",
        ),
        section(
            "Evaluations",
            [("Evaluation", False), ("State", False), ("Alerts", True), ("Opened", False)],
            [
                [
                    cell(e.identifier, evaluation_url(e)),
                    evaluation_state(e),
                    cell(str(e.covered), numeric=True),
                    stamp(e.opened_at),
                ]
                for e in evaluations
            ],
            "No evaluation yet.",
        ),
    ]
    return record_page(
        request,
        identifier=chart.identifier,
        title=chart.title,
        crumbs=_crumbs((chart.identifier, None)),
        state=chart_state(series),
        facts=facts,
        actions=_chart_actions(request.user, chart, series),
        notice=_chart_notice(series),
        sections=sections,
        related=[chart],
        template="trending/chart_detail.html",
        extra={
            "drawing": drawing,
            "drawing_note": "Results appear here once a review of this test is signed for a lot "
            "of this material and stage.",
        },
    )


# Limits ---------------------------------------------------------------------------------------


def _limits(pk):
    return get_object_or_404(Limits.objects.select_related("chart__material", "drafted_by"), pk=pk)


def limits_facts(limits):
    chart = limits.chart
    unit = chart.unit
    facts = [
        ("Chart", cell(chart.identifier, chart_url(chart), sub=chart.title)),
        ("Basis", limits.get_basis_display()),
    ]
    if limits.basis == Limits.Basis.COMPUTED:
        facts += [
            ("Baseline", f"{day(limits.baseline_from)} to {day(limits.baseline_to)}"),
            ("Baseline results", str(len(limits.baseline))),
            ("Worked out", stamp(limits.computed_at)),
        ]
    facts += [
        ("Center line", value_text(limits.center, unit)),
        # Fact labels are set in capitals, which would turn σ into Σ.
        ("Standard deviation", value_text(limits.sigma, unit)),
        ("Lower limit", value_text(limits.lower, unit)),
        ("Upper limit", value_text(limits.upper, unit)),
        ("Rules", cell(rules_text(limits), wrap=True)),
        ("Basis of the limits", cell(limits.rationale, wrap=True)),
    ]
    return facts


def _limits_notice(limits):
    if limits.state == Limits.State.DRAFT:
        if change := services.baseline_change(limits):
            return {"tone": "warning", "label": "Baseline changed", "text": change}
        if limits.basis == Limits.Basis.COMPUTED and len(limits.baseline) < ADVISED_BASELINE:
            return {
                "tone": "info",
                "label": "Short baseline",
                "text": f"These limits come from {len(limits.baseline)} results. Limits from fewer "
                f"than {ADVISED_BASELINE} are uncertain; review them when more results are "
                "available.",
            }
    elif limits.superseded_at:
        return {
            "tone": "neutral",
            "label": "Superseded",
            "text": "A later version applies to results reviewed from "
            f"{stamp(limits.superseded_at)}.",
        }
    return None


@login_required
def limits_detail(request, pk):
    _read(request)
    limits = _limits(pk)
    chart = limits.chart
    actions = []
    if limits.state == Limits.State.DRAFT and can(request.user, QUALITY):
        actions.append(action("Change draft", reverse("trending:limits_edit", args=[limits.pk])))
        if denial := services.approval_denial(request.user, limits):
            actions.insert(0, refused(denial))
        else:
            actions.append(
                action("Approve limits", reverse("trending:limits_approve", args=[limits.pk]), True)
            )
    facts = limits_facts(limits) + [
        ("Drafted by", person(limits.drafted_by)),
        ("Drafted", stamp(limits.drafted_at)),
    ]
    if limits.approved_at:
        facts.append(("Approved", stamp(limits.approved_at)))
    if limits.superseded_at:
        facts.append(("Superseded", stamp(limits.superseded_at)))
    sections = []
    if limits.basis == Limits.Basis.COMPUTED:
        sections.append(
            section(
                "Baseline results",
                [("Test", False), ("Lot", False), ("Result", True), ("Review signed", False)],
                [
                    [
                        cell(
                            f"T-{row['test']}",
                            reverse("analytical:test_detail", args=[row["test"]]),
                        ),
                        row["lot"],
                        cell(f"{row['value']} {chart.unit}", numeric=True),
                        stamp(datetime.fromisoformat(row["reviewed_at"])),
                    ]
                    for row in limits.baseline
                ],
                "No baseline result.",
                note="The reviewed results of the period in review order, leaving out results "
                "that failed their specification.",
            )
        )
    return record_page(
        request,
        identifier=limits.identifier,
        title=f"Limits v{limits.version} · {chart.title}",
        crumbs=_crumbs((chart.identifier, chart_url(chart)), (f"Limits v{limits.version}", None)),
        state=limits_state(limits),
        facts=facts,
        meta=[("Revision", limits.revision)],
        actions=actions,
        notice=_limits_notice(limits),
        sections=sections,
        related=[limits],
    )


def _limits_page(request, form, chart, *, title, crumbs, cancel_url, submit_label):
    return form_page(
        request,
        form,
        title=title,
        crumbs=crumbs,
        cancel_url=cancel_url,
        submit_label=submit_label,
        intro="Computed limits are worked out when you save, from the results reviewed in the "
        "baseline period, leaving out results that failed their specification; at least 8 are "
        f"needed and {ADVISED_BASELINE} or more are advised. Another quality person approves the "
        "draft with a signature, and results reviewed from then on are judged by it.",
        facts=[("Chart", chart.title), ("Unit", chart.unit)],
    )


@login_required
@require_http_methods(["GET", "POST"])
def limits_new(request, pk):
    require_role(request.user, QUALITY)
    chart = _chart(pk)
    detail = chart_url(chart)
    draft = chart.versions.filter(state=Limits.State.DRAFT).first()
    if draft:
        messages.error(request, f"{chart.identifier} has a draft of its limits: change that draft.")
        return redirect(limits_url(draft))
    form = LimitsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        limits = run(
            form,
            lambda: services.draft_limits(
                actor=request.user, chart=chart, reason=form.cleaned_data["reason"], **form.values()
            ),
        )
        if limits:
            messages.success(request, f"Limits v{limits.version} drafted.")
            return redirect(limits_url(limits))
    return _limits_page(
        request,
        form,
        chart,
        title=f"Draft limits · {chart.identifier}",
        crumbs=_crumbs((chart.identifier, detail), ("Draft limits", None)),
        cancel_url=detail,
        submit_label="Save draft",
    )


@login_required
@require_http_methods(["GET", "POST"])
def limits_edit(request, pk):
    require_role(request.user, QUALITY)
    limits = _limits(pk)
    detail = limits_url(limits)
    if limits.state != Limits.State.DRAFT:
        messages.error(request, f"{limits.identifier} is approved: draft a new version instead.")
        return redirect(detail)
    initial = {name: getattr(limits, name) for name in services.LIMIT_FIELDS}
    initial["expected_revision"] = limits.revision
    form = LimitsForm(request.POST or None, initial=initial)
    form.fields["expected_revision"].required = True
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.change_limits(
                actor=request.user,
                limits=limits,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if done:
            messages.success(request, f"Draft {limits.identifier} saved.")
            return redirect(detail)
    return _limits_page(
        request,
        form,
        limits.chart,
        title=f"Change draft · {limits.identifier}",
        crumbs=_crumbs(
            (limits.chart.identifier, chart_url(limits.chart)),
            (f"Limits v{limits.version}", detail),
            ("Change draft", None),
        ),
        cancel_url=detail,
        submit_label="Save draft",
    )


@login_required
@require_http_methods(["GET", "POST"])
def limits_approve(request, pk):
    require_role(request.user, QUALITY)
    limits = _limits(pk)
    detail = limits_url(limits)
    form = SigningForm(request.POST or None, initial={"expected_revision": limits.revision})
    return sign_page(
        request,
        form,
        title=f"Approve limits · {limits.identifier}",
        identifier=limits.identifier,
        meaning="approved",
        meaning_text="You approve these limits and rules for this chart. From the moment you sign, "
        "every result whose review is signed is judged by them, and the version in force before "
        "stops applying.",
        button="Sign and approve",
        facts=limits_facts(limits),
        revision=limits.revision,
        cancel_url=detail,
        run=lambda d: services.approve_limits(
            actor=request.user,
            pin=d["pin"],
            limits=limits,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"{limits.identifier} approved.",
        success_url=detail,
        denial=services.approval_denial(request.user, limits),
        crumbs=_crumbs(
            (limits.chart.identifier, chart_url(limits.chart)),
            (f"Limits v{limits.version}", detail),
            ("Approve limits", None),
        ),
    )


# Evaluations ----------------------------------------------------------------------------------


def _alert_label(point, unit):
    return (
        f"{point.test.label} · lot {point.test.lot.number} · {point.text} {unit} · "
        f"{stamp(point.reviewed_at)} · {_broken_text(point)}"
    )


def _alert_choices(series):
    return [(p.test.pk, _alert_label(p, series.chart.unit)) for p in series.open_alerts]


@login_required
def evaluation_list(request):
    _read(request)
    form, data = make_filter(
        request,
        EVALUATION_FILTER,
        extra={"outcome": ("Outcome", Evaluation.Outcome.choices)},
    )
    queryset = Evaluation.objects.select_related("chart__material", "opened_by").annotate(
        covered=Count("alerts")
    )
    if q := data.get("q"):
        queryset = queryset.filter(
            Q(chart__test_code__icontains=q)
            | Q(chart__material__code__icontains=q)
            | Q(quality_reference__icontains=q)
        )
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    if data.get("outcome"):
        queryset = queryset.filter(outcome=data["outcome"])
    page, sort, descending = paginate(
        request, queryset, {"opened": ["opened_at"], "chart": ["chart__test_code"]}, "-opened"
    )
    rows = [
        [
            cell(e.identifier, evaluation_url(e)),
            cell(e.chart.identifier, chart_url(e.chart), sub=e.chart.title),
            cell(str(e.covered), numeric=True),
            stamp(e.opened_at),
            person(e.opened_by),
            e.quality_reference,
            evaluation_state(e),
        ]
        for e in page
    ]
    return list_page(
        request,
        title="Out-of-trend evaluations",
        intro="Each evaluation looks into out-of-trend alerts of one chart: what the laboratory "
        "check found, the cause, the lots and results affected and the actions, concluded with "
        "a signature by a quality person who recorded none of it.",
        noun="evaluations",
        columns=[
            ("Evaluation", None, False),
            ("Chart", "chart", False),
            ("Alerts", None, True, "low"),
            ("Opened", "opened", False),
            ("Opened by", None, False, "low"),
            ("Quality-system reference", None, False, "low"),
            ("State", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        empty_body="Quality opens an evaluation from a chart's open alerts.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def evaluation_new(request, pk):
    require_role(request.user, QUALITY)
    chart = _chart(pk)
    detail = chart_url(chart)
    series = series_of(chart)
    choices = _alert_choices(series)
    if not choices:
        messages.error(request, f"{chart.identifier} has no open alert.")
        return redirect(detail)
    # Every open alert is offered and, up to the most an evaluation covers, ticked: the oldest.
    ticked = [pk for pk, _ in choices[: services.MAX_ALERTS]]
    form = AlertsForm(request.POST or None, choices=choices, initial={"alerts": ticked})
    if request.method == "POST" and form.is_valid():
        evaluation = run(
            form,
            lambda: services.open_evaluation(
                actor=request.user,
                chart=chart,
                tests=form.cleaned_data["alerts"],
                reason=form.cleaned_data["reason"],
            ),
        )
        if evaluation:
            messages.success(request, f"{evaluation.identifier} opened.")
            return redirect(evaluation_url(evaluation))
    return form_page(
        request,
        form,
        title=f"Evaluate alerts · {chart.identifier}",
        crumbs=_crumbs((chart.identifier, detail), ("Evaluate alerts", None)),
        cancel_url=detail,
        submit_label="Open evaluation",
        intro="Choose the alerts to look into together, typically the results of one run or one "
        "shift. Further alerts of this chart can be added while the evaluation is open.",
        facts=[("Chart", chart.title)],
    )


def _evaluation(pk):
    return get_object_or_404(
        Evaluation.objects.select_related("chart__material", "opened_by", "impact_assessment"),
        pk=pk,
    )


def findings_facts(evaluation):
    assessment = evaluation.impact_assessment
    return [
        ("Laboratory check", cell(evaluation.laboratory_check, wrap=True)),
        ("Cause", cell(evaluation.cause, wrap=True)),
        ("Lots and results affected", cell(evaluation.effect, wrap=True)),
        ("Actions", cell(evaluation.actions, wrap=True)),
        ("Quality-system reference", evaluation.quality_reference),
        (
            "Impact assessment",
            cell(
                f"{assessment.label} · {assessment.get_state_display()}",
                reverse("impact:detail", args=[assessment.pk]),
            )
            if assessment
            else "",
        ),
    ]


def alert_rows(evaluation):
    unit = evaluation.chart.unit
    rows = []
    for alert in evaluation.alerts.select_related("test__lot", "limits").order_by("reviewed_at"):
        limits = alert.limits
        rows.append(
            [
                _test_cell(alert.test),
                _lot_cell(alert.test),
                cell(value_text(alert.value, unit), numeric=True),
                stamp(alert.reviewed_at),
                cell(f"v{limits.version}", limits_url(limits)),
                cell(
                    "; ".join(
                        describe(r, run_length=limits.run_length, trend_length=limits.trend_length)
                        for r in alert.rules
                    ),
                    wrap=True,
                ),
            ]
        )
    return rows


ALERT_COLUMNS = [
    ("Test", False),
    ("Lot", False),
    ("Result", True),
    ("Review signed", False),
    ("Limits", False, "low"),
    ("Rules broken", False),
]


def _evaluation_actions(user, evaluation):
    if evaluation.state != Evaluation.State.OPEN or not can(user, QUALITY):
        return []
    actions = [
        action("Record findings", reverse("trending:evaluation_findings", args=[evaluation.pk])),
        action("Add alerts", reverse("trending:evaluation_alerts", args=[evaluation.pk])),
        action("Assess impact", reverse("impact:new"), more=True),
    ]
    if user.pk in services.conclusion_authors(evaluation):
        actions.insert(0, refused(services.INDEPENDENT_CONCLUSION))
    elif not services.conclusion_problems(evaluation):
        actions.append(
            action(
                "Conclude evaluation",
                reverse("trending:evaluation_conclude", args=[evaluation.pk]),
                True,
            )
        )
    return actions


def _evaluation_notice(evaluation):
    if evaluation.state != Evaluation.State.OPEN:
        return None
    problems = services.conclusion_problems(evaluation)
    return {
        "tone": "warning",
        "label": "Evaluation open",
        "text": " ".join(problems)
        if problems
        else "The findings are recorded. A quality person who recorded none of them, and none "
        "of the results' data, concludes the evaluation.",
    }


@login_required
def evaluation_detail(request, pk):
    _read(request)
    evaluation = _evaluation(pk)
    chart = evaluation.chart
    facts = []
    if evaluation.outcome:
        tone = "danger" if evaluation.outcome == Evaluation.Outcome.CONFIRMED else "success"
        facts.append(("Outcome", critical(evaluation.get_outcome_display(), tone)))
        facts.append(("Conclusion", cell(evaluation.conclusion, wrap=True)))
    facts += [
        ("Chart", cell(chart.identifier, chart_url(chart), sub=chart.title)),
        *findings_facts(evaluation),
        ("Opened by", person(evaluation.opened_by)),
        ("Opened", stamp(evaluation.opened_at)),
    ]
    if evaluation.concluded_at:
        facts.append(("Concluded", stamp(evaluation.concluded_at)))
    return record_page(
        request,
        identifier=evaluation.identifier,
        title=f"Out-of-trend evaluation · {chart.title}",
        crumbs=[
            (SECTION, reverse("trending:chart_list")),
            ("Evaluations", reverse("trending:evaluation_list")),
            (evaluation.identifier, None),
        ],
        state=evaluation_state(evaluation),
        facts=facts,
        meta=[("Revision", evaluation.revision)],
        actions=_evaluation_actions(request.user, evaluation),
        notice=_evaluation_notice(evaluation),
        sections=[section("Alerts covered", ALERT_COLUMNS, alert_rows(evaluation), "No alert.")],
        related=[evaluation],
    )


def _open_evaluation(request, pk):
    """(evaluation, detail url, redirect) for a page that changes an open evaluation."""
    require_role(request.user, QUALITY)
    evaluation = _evaluation(pk)
    detail = evaluation_url(evaluation)
    if evaluation.state != Evaluation.State.OPEN:
        messages.error(request, f"{evaluation.identifier} is concluded: it no longer changes.")
        return evaluation, detail, redirect(detail)
    return evaluation, detail, None


def _evaluation_crumbs(evaluation, detail, last):
    return [
        (SECTION, reverse("trending:chart_list")),
        ("Evaluations", reverse("trending:evaluation_list")),
        (evaluation.identifier, detail),
        (last, None),
    ]


@login_required
@require_http_methods(["GET", "POST"])
def evaluation_alerts(request, pk):
    evaluation, detail, refused_page = _open_evaluation(request, pk)
    if refused_page:
        return refused_page
    choices = _alert_choices(series_of(evaluation.chart))
    if not choices:
        messages.error(request, f"{evaluation.chart.identifier} has no further open alert.")
        return redirect(detail)
    form = AlertsForm(
        request.POST or None,
        choices=choices,
        initial={"expected_revision": evaluation.revision},
    )
    form.fields["expected_revision"].required = True
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.add_alerts(
                actor=request.user,
                evaluation=evaluation,
                tests=form.cleaned_data["alerts"],
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
            ),
        )
        if done:
            messages.success(request, f"Alerts added to {evaluation.identifier}.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Add alerts · {evaluation.identifier}",
        crumbs=_evaluation_crumbs(evaluation, detail, "Add alerts"),
        cancel_url=detail,
        submit_label="Add alerts",
        intro="Open alerts of the same chart, raised since the evaluation was opened or left out "
        "of it.",
        facts=[("Evaluation", str(evaluation))],
    )


@login_required
@require_http_methods(["GET", "POST"])
def evaluation_findings(request, pk):
    evaluation, detail, refused_page = _open_evaluation(request, pk)
    if refused_page:
        return refused_page
    initial = {name: getattr(evaluation, name) for name in services.FINDING_FIELDS}
    initial["expected_revision"] = evaluation.revision
    form = FindingsForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.record_findings(
                actor=request.user,
                evaluation=evaluation,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if done:
            messages.success(request, f"Findings of {evaluation.identifier} recorded.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Record findings · {evaluation.identifier}",
        crumbs=_evaluation_crumbs(evaluation, detail, "Record findings"),
        cancel_url=detail,
        submit_label="Save findings",
        intro="Record what the evaluation found and did as it progresses. Whoever records "
        "findings cannot conclude the evaluation.",
        facts=[("Evaluation", str(evaluation)), ("Chart", evaluation.chart.title)],
    )


@login_required
@require_http_methods(["GET", "POST"])
def evaluation_conclude(request, pk):
    require_role(request.user, QUALITY)
    evaluation = _evaluation(pk)
    detail = evaluation_url(evaluation)
    form = ConcludeForm(request.POST or None, initial={"expected_revision": evaluation.revision})
    alerts = alert_rows(evaluation)
    return sign_page(
        request,
        form,
        title=f"Conclude evaluation · {evaluation.identifier}",
        identifier=evaluation.identifier,
        meaning="concluded",
        meaning_text="You conclude this out-of-trend evaluation with the outcome you choose. "
        "Your signature freezes the alerts it covers, the findings and your conclusion.",
        button="Sign and conclude",
        facts=[
            ("Chart", cell(evaluation.chart.identifier, sub=evaluation.chart.title)),
            ("Alerts covered", str(len(alerts))),
            *findings_facts(evaluation),
        ],
        revision=evaluation.revision,
        cancel_url=detail,
        run=lambda d: services.conclude_evaluation(
            actor=request.user,
            pin=d["pin"],
            evaluation=evaluation,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
            outcome=d["outcome"],
            conclusion=d["conclusion"],
        ),
        success=f"{evaluation.identifier} concluded.",
        success_url=detail,
        denial=services.conclusion_denial(request.user, evaluation),
        crumbs=_evaluation_crumbs(evaluation, detail, "Conclude evaluation"),
    )
