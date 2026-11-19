"""Pages for participations in proficiency testing and interlaboratory comparisons (HTTP only;
the rules are in ``catalog.proficiency``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.people import person
from core.services import require_role
from laboratory.forms import SigningForm
from laboratory.ui import (
    action,
    cell,
    critical,
    day,
    external_link,
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

from . import proficiency as services
from .forms import (
    FollowUpForm,
    ParticipationForm,
    ParticipationPlanForm,
    ParticipationReportForm,
    ProficiencyResultForm,
    ReasonForm,
    ReviewForm,
)
from .models import Method, ProficiencyParticipation, ProficiencyResult
from .views import crumbs_for, form_page, tabs
from .web import can, read_access, run

LIST = "Proficiency testing"
STATE = ProficiencyParticipation.State
OTHERS_SHOWN = 10
WHAT_IT_IS = (
    "Each participation compares the laboratory's results for one method with those of other "
    "laboratories: a round of a proficiency testing scheme or another interlaboratory comparison."
)
STATUS_FILTER = [
    ("planned", "Planned"),
    ("overdue", "Results overdue"),
    ("reported", "Results reported"),
    ("follow_up", "Follow-up open"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
]


def _crumbs(*trail):
    return crumbs_for((LIST, reverse("catalog:proficiency_list")), *trail)


def detail_url(item):
    return reverse("catalog:proficiency_detail", args=[item.pk])


def state_cell(item, today=None):
    return status(*services.display_state(item, today))


def outcome_cell(item, *, fact=False):
    if not item.outcome:
        return ""
    tone = services.OUTCOME_TONES[item.outcome]
    if fact:
        return critical(item.get_outcome_display(), tone)
    return status(item.get_outcome_display(), tone)


def score_text(result):
    if result.score_kind == ProficiencyResult.ScoreKind.NONE:
        return "No score"
    label = {"z": "z", "z_prime": "z′", "zeta": "ζ", "en": "En"}[result.score_kind]
    return f"{label} = {result.score.normalize():f}"


# List -----------------------------------------------------------------------------------


@login_required
def proficiency_list(request):
    read_access(request)
    form, data = make_filter(
        request,
        STATUS_FILTER,
        extra={
            "kind": ("Kind", ProficiencyParticipation.Kind.choices),
            "outcome": ("Outcome", ProficiencyParticipation._meta.get_field("outcome").choices),
        },
    )
    today = timezone.localdate()
    queryset = ProficiencyParticipation.objects.select_related("method")
    if q := data.get("q"):
        queryset = queryset.filter(
            Q(method__code__icontains=q)
            | Q(method__title__icontains=q)
            | Q(provider__icontains=q)
            | Q(scheme__icontains=q)
            | Q(round_ref__icontains=q)
            | Q(test_item__icontains=q)
        )
    # Opened from a method's page: that method only, matched exactly.
    if (method_id := request.GET.get("method", "")).isdigit():
        queryset = queryset.filter(method_id=int(method_id))
    open_ = Q(state=STATE.OPEN)
    match data.get("status"):
        case "planned":
            queryset = queryset.filter(open_, reported_on__isnull=True, results_due__gte=today)
        case "overdue":
            queryset = queryset.filter(open_, reported_on__isnull=True, results_due__lt=today)
        case "reported":
            queryset = queryset.filter(open_, reported_on__isnull=False)
        case "follow_up" | "closed" | "cancelled" as state:
            queryset = queryset.filter(state=state)
    for name in ("kind", "outcome"):
        if data.get(name):
            queryset = queryset.filter(**{name: data[name]})
    page, sort, descending = paginate(
        request,
        queryset,
        {"due": ["results_due"], "method": ["method__code", "results_due"]},
        "-due",
    )
    rows = [
        [
            cell(item.identifier, detail_url(item), sub=item.round_ref),
            cell(
                item.method.code,
                reverse("catalog:method", args=[item.method_id]),
                sub=item.method.title,
            ),
            cell(item.provider, sub=item.scheme),
            item.get_kind_display(),
            day(item.results_due),
            outcome_cell(item),
            state_cell(item, today),
        ]
        for item in page
    ]
    return list_page(
        request,
        title=LIST,
        intro=WHAT_IT_IS + " Quality plans each one, the laboratory records its results with the "
        "provider's scores, and an independent quality person reviews the outcome.",
        noun="participations",
        columns=[
            ("Participation", None, False),
            ("Method", "method", False),
            ("Provider", None, False),
            ("Kind", None, False, "low"),
            ("Results due", "due", False),
            ("Outcome", None, False),
            ("State", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "participation", "href": reverse("catalog:proficiency_new")}
        if can(request.user, services.PLANNER)
        else None,
        empty_body="Quality plans the rounds the laboratory takes part in, method by method.",
        extra={"page_title": LIST, "tabs": tabs(request, LIST)},
    )


# Planning -------------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_new(request):
    require_role(request.user, services.PLANNER)
    initial = {}
    if (method_id := request.GET.get("method", "")).isdigit():
        if method := Method.objects.filter(pk=method_id).first():
            initial["method"] = method
    form = ParticipationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = run(
            form,
            lambda: services.plan_participation(
                actor=request.user,
                method=form.cleaned_data["method"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if item:
            messages.success(request, f"{item.identifier} planned.")
            return redirect(detail_url(item))
    return form_page(
        request,
        form,
        title="New participation",
        crumbs=_crumbs(("New participation", None)),
        cancel_url=reverse("catalog:proficiency_list"),
        submit_label="Plan participation",
        intro=WHAT_IT_IS + " The day results are due puts it on the reminders.",
    )


def _participation(pk):
    return get_object_or_404(
        ProficiencyParticipation.objects.select_related(
            "method", "planned_by", "method_version", "impact_assessment"
        ),
        pk=pk,
    )


def _changing(request, pk, roles, *states):
    """(participation, detail url, redirect) for a page that changes it in ``states``."""
    require_role(request.user, *roles)
    item = _participation(pk)
    detail = detail_url(item)
    if item.state not in states:
        messages.error(request, services._state_refusal(item, states))
        return item, detail, redirect(detail)
    return item, detail, None


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_edit(request, pk):
    item, detail, refused_page = _changing(request, pk, (services.PLANNER,), STATE.OPEN)
    if refused_page:
        return refused_page
    initial = {name: getattr(item, name) for name in services.PLAN_FIELDS}
    initial["expected_revision"] = item.revision
    form = ParticipationPlanForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.change_plan(
                actor=request.user,
                participation=item,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if done:
            messages.success(request, f"Plan of {item.identifier} changed.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Change plan · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Change plan", None)),
        cancel_url=detail,
        submit_label="Save plan",
        intro="Before results or the report are recorded, changing the plan does not stop you "
        "from reviewing the outcome. Once they are, the change corrects what the review will "
        "freeze, and whoever makes it cannot review the outcome.",
        facts=[("Method", str(item.method))],
    )


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_cancel(request, pk):
    item, detail, refused_page = _changing(request, pk, (services.PLANNER,), STATE.OPEN)
    if refused_page:
        return refused_page
    if item.results.exists():
        messages.error(
            request,
            "Results are recorded: review the participation instead. A round the provider did "
            "not evaluate is recorded as not evaluated.",
        )
        return redirect(detail)
    form = ReasonForm(request.POST or None, initial={"expected_revision": item.revision})
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.cancel_participation(
                actor=request.user,
                participation=item,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
            ),
        )
        if done:
            messages.success(request, f"{item.identifier} cancelled.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Cancel participation · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Cancel participation", None)),
        cancel_url=detail,
        submit_label="Cancel participation",
        intro="For a round that will not take place or that the laboratory will not take part "
        "in. The participation stays in the list with your reason and no longer changes.",
        facts=[("Participation", str(item)), ("Method", str(item.method))],
    )


# The laboratory's report and results ----------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_report(request, pk):
    item, detail, refused_page = _changing(request, pk, services.RECORDERS, STATE.OPEN)
    if refused_page:
        return refused_page
    initial = {name: getattr(item, name) for name in services.REPORT_FIELDS}
    initial["expected_revision"] = item.revision
    form = ParticipationReportForm(request.POST or None, initial=initial, method=item.method)
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.record_report(
                actor=request.user,
                participation=item,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if done:
            messages.success(request, f"Report of {item.identifier} recorded.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Record report · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Record report", None)),
        cancel_url=detail,
        submit_label="Save report",
        intro="What the laboratory did and what the provider's report says. Whoever records "
        "the report cannot review the outcome.",
        facts=[("Participation", str(item)), ("Method", str(item.method))],
    )


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_result_new(request, pk):
    item, detail, refused_page = _changing(request, pk, services.RECORDERS, STATE.OPEN)
    if refused_page:
        return refused_page
    form = ProficiencyResultForm(request.POST or None, initial={"expected_revision": item.revision})
    if request.method == "POST" and form.is_valid():
        added = run(
            form,
            lambda: services.add_result(
                actor=request.user, participation=item, **form.cleaned_data
            ),
        )
        if added:
            messages.success(
                request,
                f"{added.measurand} added to {item.identifier}: "
                f"{added.get_outcome_display().lower()}.",
            )
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Record result · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Record result", None)),
        cancel_url=detail,
        submit_label="Record result",
        intro="One measurand: the laboratory's result as reported to the provider, and the "
        "score the provider's report gives it. Whoever records a result, and the analyst who "
        "performed it, cannot review the outcome.",
        facts=[("Participation", str(item)), ("Method", str(item.method))],
    )


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_result_remove(request, pk, result_pk):
    item, detail, refused_page = _changing(request, pk, services.RECORDERS, STATE.OPEN)
    if refused_page:
        return refused_page
    result = get_object_or_404(ProficiencyResult, pk=result_pk, participation=item)
    form = ReasonForm(request.POST or None, initial={"expected_revision": item.revision})
    if request.method == "POST" and form.is_valid():
        if run(
            form,
            lambda: services.remove_result(
                actor=request.user,
                item=result,
                reason=form.cleaned_data["reason"],
                expected_revision=form.cleaned_data["expected_revision"],
            ),
        ):
            messages.success(request, f"{result.measurand} removed from {item.identifier}.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Remove result · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Remove result", None)),
        cancel_url=detail,
        submit_label="Remove result",
        intro="Removal is recorded in the participation's history with your reason.",
        facts=[
            ("Measurand", result.measurand),
            ("Laboratory's result", f"{result.reported_value} {result.unit}".strip()),
            ("Score", score_text(result)),
            ("Outcome", result.get_outcome_display()),
        ],
    )


# Record ---------------------------------------------------------------------------------


def result_rows(item, *, removable=False):
    rows = []
    for result in item.results.select_related("performed_by"):
        row = [
            cell(result.measurand, sub=result.unit, wrap=True),
            cell(result.reported_value, numeric=True),
            cell(result.assigned_value, numeric=True),
            score_text(result),
            status(result.get_outcome_display(), services.OUTCOME_TONES[result.outcome]),
            person(result.performed_by),
            cell(result.note, wrap=True),
        ]
        if removable:
            row.append(
                cell(
                    "Remove",
                    reverse("catalog:proficiency_result_remove", args=[item.pk, result.pk]),
                )
            )
        rows.append(row)
    return rows


RESULT_COLUMNS = [
    ("Measurand", False),
    ("Laboratory's result", True),
    ("Assigned value", True),
    ("Score", False),
    ("Outcome", False),
    ("Analyst", False),
    ("Note", False, "low"),
]


def plan_facts(item, today=None):
    today = today or timezone.localdate()
    due = cell(day(item.results_due))
    if item.state == STATE.OPEN and not item.reported_on and item.results_due < today:
        due = cell(day(item.results_due), pill=("Overdue", "danger"))
    return [
        ("Method", cell(str(item.method), reverse("catalog:method", args=[item.method_id]))),
        ("Kind", item.get_kind_display()),
        ("Provider or organizer", item.provider),
        ("Provider's accreditation", item.provider_accreditation),
        ("Scheme", item.scheme),
        ("Round", item.round_ref),
        ("Test item", cell(item.test_item, wrap=True)),
        ("Results due", due),
    ]


def report_facts(item):
    version = item.method_version
    return [
        (
            "Method version used",
            cell(f"v{version.version}", reverse("catalog:method", args=[item.method_id]))
            if version
            else "",
        ),
        ("Item received", day(item.received_on)),
        ("Results reported", day(item.reported_on)),
        ("Laboratory records", cell(item.data_ref, code=True) if item.data_ref else ""),
        ("Provider's report", cell(item.report_ref, code=True) if item.report_ref else ""),
        ("Report dated", day(item.report_on)),
        ("Report link", external_link(item.report_url)),
    ]


def follow_up_facts(item):
    assessment = item.impact_assessment
    return [
        ("Cause", cell(item.cause, wrap=True)),
        ("Corrective actions", cell(item.actions, wrap=True)),
        ("Results already reported", cell(item.reported_results, wrap=True)),
        (
            "Impact assessment",
            cell(
                f"{assessment.label} · {assessment.get_state_display()}",
                reverse("impact:detail", args=[assessment.pk]),
            )
            if assessment
            else "",
        ),
        ("Quality-system reference", item.quality_reference),
        ("Effectiveness check", cell(item.effectiveness, wrap=True)),
    ]


def _others(item):
    others = (
        ProficiencyParticipation.objects.filter(method=item.method)
        .exclude(pk=item.pk)
        .order_by("-results_due", "-pk")
    )
    rows = [
        [
            cell(other.identifier, detail_url(other), sub=other.round_ref),
            other.provider,
            day(other.results_due),
            outcome_cell(other),
            state_cell(other),
        ]
        for other in others[:OTHERS_SHOWN]
    ]
    total = others.count()
    note = "Newest first, to compare this outcome with the method's earlier rounds."
    if total > len(rows):
        note += f" Showing the latest {len(rows)} of {total}."
    return section(
        f"Other participations for {item.method.code}",
        [
            ("Participation", False),
            ("Provider", False),
            ("Results due", False),
            ("Outcome", False),
            ("State", False),
        ],
        rows,
        "No other participation for this method.",
        note=note,
    )


def _actions(user, item):
    recorder = can(user, *services.RECORDERS)
    quality = can(user, services.REVIEWER)
    actions = []
    if item.state == STATE.OPEN:
        if recorder:
            actions += [
                action("Record result", reverse("catalog:proficiency_result_new", args=[item.pk])),
                action("Record report", reverse("catalog:proficiency_report", args=[item.pk])),
            ]
        if quality:
            actions.append(
                action("Change plan", reverse("catalog:proficiency_edit", args=[item.pk]))
            )
            if not item.results.exists():
                actions.append(
                    action(
                        "Cancel participation",
                        reverse("catalog:proficiency_cancel", args=[item.pk]),
                        danger=True,
                        more=True,
                    )
                )
            if user.pk in services.data_authors(item):
                actions.insert(0, refused(services.INDEPENDENT))
            elif not services.review_problems(item):
                actions.append(
                    action(
                        "Review outcome",
                        reverse("catalog:proficiency_review", args=[item.pk]),
                        True,
                    )
                )
    elif item.state == STATE.FOLLOW_UP and quality:
        actions.append(
            action("Record follow-up", reverse("catalog:proficiency_follow_up", args=[item.pk]))
        )
        actions.append(action("Assess impact", reverse("impact:new"), more=True))
        if user.pk in services.data_authors(item) | services.follow_up_authors(item):
            actions.insert(0, refused(services.INDEPENDENT_CLOSE))
        elif not services.close_problems(item):
            actions.append(
                action(
                    "Close follow-up", reverse("catalog:proficiency_close", args=[item.pk]), True
                )
            )
    return actions


def _notice(item, today):
    if item.state == STATE.OPEN:
        if not item.reported_on and item.results_due < today:
            return {
                "tone": "danger",
                "label": "Results overdue",
                "text": f"Results were due on {day(item.results_due)} and none are reported. "
                "Record the report, change the plan, or cancel a round that will not take place.",
            }
        if problems := services.review_problems(item):
            return {"tone": "info", "label": "Before review", "text": " ".join(problems)}
    if item.state == STATE.FOLLOW_UP:
        problems = services.close_problems(item)
        return {
            "tone": "warning",
            "label": "Corrective follow-up open",
            "text": "The review asked for corrective follow-up. "
            + (" ".join(problems) if problems else "It is ready to be closed."),
        }
    if item.state == STATE.CANCELLED:
        return {
            "tone": "neutral",
            "label": "Cancelled",
            "text": "This participation did not take place. The reason is in its history.",
        }
    return None


@login_required
def proficiency_detail(request, pk):
    read_access(request)
    item = _participation(pk)
    today = timezone.localdate()
    open_ = item.state == STATE.OPEN
    removable = open_ and can(request.user, *services.RECORDERS)
    facts = []
    if item.outcome:
        facts.append(("Outcome", outcome_cell(item, fact=True)))
    facts += plan_facts(item, today) + report_facts(item)
    facts.append(("Planned by", person(item.planned_by)))
    if item.reviewed_at:
        facts += [
            ("Review", cell(item.review_conclusion, wrap=True)),
            ("Corrective follow-up", "Required" if item.follow_up_required else "Not required"),
        ]
    if item.follow_up_required:
        facts += follow_up_facts(item)
    moments = [
        ("Planned", item.planned_at),
        ("Reviewed", item.reviewed_at),
        ("Closed", item.closed_at),
        ("Cancelled", item.cancelled_at),
    ]
    facts += [(label, stamp(moment)) for label, moment in moments if moment]
    return record_page(
        request,
        identifier=item.identifier,
        title=item.title,
        crumbs=_crumbs((item.identifier, None)),
        state=state_cell(item, today),
        facts=facts,
        meta=[("Revision", item.revision)],
        actions=_actions(request.user, item),
        notice=_notice(item, today),
        sections=[
            section(
                "Results",
                RESULT_COLUMNS + ([("Action", False)] if removable else []),
                result_rows(item, removable=removable),
                "No result recorded yet.",
                note="A z, z′ or ζ score is satisfactory up to 2 in absolute value, questionable "
                "above 2 and below 3, and unsatisfactory from 3; an En number is satisfactory up "
                "to 1. A result without a score carries the provider's evaluation.",
            ),
            _others(item),
        ],
        related=[item],
    )


# Review ---------------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_review(request, pk):
    require_role(request.user, services.REVIEWER)
    item = _participation(pk)
    detail = detail_url(item)
    denial = services.review_denial(request.user, item)
    outcome = services.overall_outcome(item.results.all())
    form = ReviewForm(
        request.POST or None,
        initial={
            "expected_revision": item.revision,
            "follow_up": outcome == services.OUTCOME.UNSATISFACTORY,
        },
    )
    results = list(item.results.select_related("performed_by"))
    facts = [
        ("Outcome", critical(outcome.label, services.OUTCOME_TONES[outcome])),
        *plan_facts(item),
        *report_facts(item),
        (
            "Results",
            "; ".join(
                f"{r.measurand}: {r.reported_value} ({score_text(r)}, "
                f"{r.get_outcome_display().lower()})"
                for r in results
            ),
        ),
    ]
    return sign_page(
        request,
        form,
        title=f"Review outcome · {item.identifier}",
        identifier=item.identifier,
        meaning="reviewed",
        meaning_text="You review the outcome of this participation and its results as shown. "
        "Your signature freezes them with your review; with corrective follow-up the "
        "participation stays open until another quality person closes it.",
        button="Sign review",
        facts=facts,
        revision=item.revision,
        cancel_url=detail,
        run=lambda d: services.review_participation(
            actor=request.user,
            pin=d["pin"],
            participation=item,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
            conclusion=d["conclusion"],
            follow_up=d["follow_up"],
        ),
        success=f"{item.identifier} reviewed.",
        success_url=detail,
        denial=denial,
        crumbs=_crumbs((item.identifier, detail), ("Review outcome", None)),
    )


# Corrective follow-up -------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_follow_up(request, pk):
    item, detail, refused_page = _changing(request, pk, (services.REVIEWER,), STATE.FOLLOW_UP)
    if refused_page:
        return refused_page
    initial = {name: getattr(item, name) for name in services.FOLLOW_UP_FIELDS}
    initial["expected_revision"] = item.revision
    form = FollowUpForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.record_follow_up(
                actor=request.user,
                participation=item,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if done:
            messages.success(request, f"Follow-up of {item.identifier} recorded.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Record follow-up · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Record follow-up", None)),
        cancel_url=detail,
        submit_label="Save follow-up",
        intro="Record the investigation, the actions and how they were shown to work, as they "
        "progress. Whoever records the follow-up cannot close it.",
        facts=[
            ("Participation", str(item)),
            ("Outcome", item.get_outcome_display()),
            ("Review", item.review_conclusion),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def proficiency_close(request, pk):
    require_role(request.user, services.REVIEWER)
    item = _participation(pk)
    detail = detail_url(item)
    form = SigningForm(request.POST or None, initial={"expected_revision": item.revision})
    return sign_page(
        request,
        form,
        title=f"Close follow-up · {item.identifier}",
        identifier=item.identifier,
        meaning="closed",
        meaning_text="You confirm that the corrective follow-up of this participation is "
        "complete and was shown to work. Your signature freezes it and closes the "
        "participation.",
        button="Sign and close",
        facts=[
            ("Participation", str(item)),
            ("Outcome", outcome_cell(item, fact=True)),
            ("Review", cell(item.review_conclusion, wrap=True)),
            *follow_up_facts(item),
        ],
        revision=item.revision,
        cancel_url=detail,
        run=lambda d: services.close_follow_up(
            actor=request.user,
            pin=d["pin"],
            participation=item,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"Follow-up of {item.identifier} closed.",
        success_url=detail,
        denial=services.close_denial(request.user, item),
        crumbs=_crumbs((item.identifier, detail), ("Close follow-up", None)),
    )
