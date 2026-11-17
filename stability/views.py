from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import DateField, DurationField, ExpressionWrapper, F, Q, Value
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from analytical import services as analytical
from analytical.contracts import parse_requirement, resolve_pull
from core.services import require_role
from laboratory.ui import (
    access,
    action,
    cell,
    critical,
    day,
    external_link,
    form_page,
    list_page,
    make_filter,
    paginate,
    record_page,
    roles_of,
    run_form,
    section,
    section_tabs,
    sign_page,
    status,
    when,
)

from . import gates, services, testing
from .evidence import (
    CONFORMS,
    FAILS,
    has_tests,
    pull_results,
    sample_evidence,
    study_results,
    testing_in_progress,
)
from .forms import (
    AnchorForm,
    CloseStudyForm,
    ConditionForm,
    EvidenceForm,
    HoldForm,
    ObligationForm,
    ProtocolForm,
    PullForm,
    PullTestsForm,
    ReasonForm,
    ReserveForm,
    SigningForm,
    StudyForm,
    TimepointForm,
    WithdrawProtocolForm,
)
from .models import (
    Hold,
    Protocol,
    Pull,
    ReserveSample,
    RetentionObligation,
    Study,
)

HOME = "Stability and retention"


def crumbs(*pairs):
    return [(HOME, reverse("stability:overview")), *pairs]


def can(user, *roles):
    return bool(roles_of(user) & set(roles))


# The pull list's filter labels (PULL_STATUS), so a pill reads like the filter that finds it.
PULL_LABELS = {"due": "Due now", "pulled": "Awaiting acceptance"}


def _pull_tone(pull, today):
    timing, label = pull.timing(today)
    tone = {"overdue": "danger", "due": "warning", "upcoming": "neutral"}.get(timing)
    if tone is None:
        tone = {"pulled": "progress", "accepted": "success", "missed": "danger"}[pull.state]
    label = PULL_LABELS.get(timing, PULL_LABELS.get(pull.state, label))
    if pull.outcome == FAILS:
        # Accepted means the pull and its results were reviewed, not that the results conform.
        return "Accepted · acceptance criteria not met", "danger"
    if pull.outcome == CONFORMS:
        return "Accepted · meets acceptance criteria", "success"
    return label, tone


def _with_windows(queryset):
    day_length = Value(timedelta(days=1), output_field=DurationField())
    span = ExpressionWrapper(F("timepoint__window_days") * day_length, output_field=DurationField())
    return queryset.annotate(
        opens=ExpressionWrapper(F("due_date") - span, output_field=DateField()),
        closes=ExpressionWrapper(F("due_date") + span, output_field=DateField()),
    )


def _pull_filter(queryset, key, today):
    queryset = _with_windows(queryset)
    scheduled = Q(state=Pull.State.SCHEDULED)
    match key:
        case "overdue":
            return queryset.filter(scheduled, closes__lt=today)
        case "due":
            return queryset.filter(scheduled, opens__lte=today, closes__gte=today)
        case "upcoming":
            return queryset.filter(scheduled, opens__gt=today)
        case "pulled" | "accepted" | "missed":
            return queryset.filter(state=key)
        case "fails":
            return queryset.filter(state=Pull.State.ACCEPTED, outcome=FAILS)
    return queryset


# --- Overview --------------------------------------------------------------------------------


@login_required
def overview(request):
    access(request.user)
    today = timezone.localdate()
    pulls = Pull.objects.filter(study__state=Study.State.ACTIVE)
    link = reverse("stability:pull_list")
    queues = [
        (
            "Pulls overdue",
            _pull_filter(pulls, "overdue", today).count(),
            "danger",
            f"{link}?status=overdue",
        ),
        (
            "Pulls due now",
            _pull_filter(pulls, "due", today).count(),
            "warning",
            f"{link}?status=due",
        ),
        (
            "Pulls awaiting acceptance",
            pulls.filter(state="pulled").count(),
            "info",
            f"{link}?status=pulled",
        ),
        (
            "Pulls outside acceptance criteria",
            pulls.filter(state="accepted", outcome=FAILS).count(),
            "danger",
            f"{link}?status=fails",
        ),
        (
            "Active studies",
            Study.objects.filter(state="active").count(),
            "neutral",
            reverse("stability:study_list") + "?status=active",
        ),
        (
            "Protocols awaiting approval",
            Protocol.objects.filter(state="draft").count(),
            "info",
            reverse("stability:protocol_list") + "?status=draft",
        ),
        (
            "Active holds",
            Hold.objects.filter(state="active").count(),
            "hold",
            reverse("stability:hold_list") + "?status=active",
        ),
        (
            "Retention anchors not yet known",
            RetentionObligation.objects.filter(anchor_date__isnull=True).count(),
            "warning",
            reverse("stability:reserve_list"),
        ),
        (
            "Reserves below minimum quantity",
            ReserveSample.objects.filter(
                quantity__lt=F("minimum_multiple") * F("test_quantity")
            ).count(),
            "warning",
            reverse("stability:reserve_list") + "?status=below",
        ),
    ]
    return render(
        request,
        "ops/overview.html",
        {
            "page_title": "Stability and retention",
            "tabs": section_tabs(request),
            "intro": "Protocol-driven pulls, reserve samples, retention obligations and holds. "
            "A pull is tested in the system against the acceptance criteria of its protocol, "
            "or linked to an external stability system where one is used.",
            "queues": [
                {"label": label, "count": count, "tone": tone if count else "neutral", "href": href}
                for label, count, tone, href in queues
            ],
        },
    )


# --- Protocols -------------------------------------------------------------------------------

PROTOCOL_STATUS = [
    ("draft", "Draft"),
    ("approved", "Approved"),
    ("superseded", "Superseded"),
    ("withdrawn", "Withdrawn"),
]


def _protocol_state(protocol):
    tone = {
        "draft": "progress",
        "approved": "success",
        "superseded": "neutral",
        "withdrawn": "neutral",
    }[protocol.state]
    return status(protocol.get_state_display(), tone)


@login_required
def protocol_list(request):
    access(request.user)
    form, data = make_filter(request, PROTOCOL_STATUS)
    queryset = Protocol.objects.all()
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(code__icontains=q) | Q(title__icontains=q) | Q(product__icontains=q)
        )
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {"code": ["code", "version"], "product": ["product"], "created": ["created_at"]},
        "code",
    )
    rows = [
        [
            cell(p.identifier, reverse("stability:protocol_detail", args=[p.pk]), sub=p.title),
            p.product,
            _protocol_state(p),
            day(timezone.localdate(p.approved_at)) if p.approved_at else "",
        ]
        for p in page
    ]
    return list_page(
        request,
        title="Stability protocols",
        intro="Approved, product-specific protocols. Conditions and schedules come from the "
        "approved protocol, never from a universal default.",
        noun="protocols",
        columns=[
            ("Protocol", "code", False),
            ("Product", "product", False),
            ("State", None, False),
            ("Approved", "created", False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "protocol", "href": reverse("stability:protocol_new")}
        if can(request.user, *services.AUTHORS)
        else None,
        empty_body="Draft a protocol, add its conditions and timepoints, then have a "
        "different quality signer approve it.",
    )


@login_required
def protocol_new(request):
    require_role(request.user, *services.AUTHORS)
    form = ProtocolForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        protocol, _ = run_form(
            request,
            form,
            lambda: services.create_protocol(actor=request.user, **form.cleaned_data),
        )
        if protocol:
            messages.success(request, "Draft protocol created. Add conditions and timepoints.")
            return redirect("stability:protocol_detail", pk=protocol.pk)
    return form_page(
        request,
        form,
        title="New protocol",
        crumbs=crumbs(("Protocols", reverse("stability:protocol_list")), ("New protocol", None)),
        submit="Create draft",
        cancel_url=reverse("stability:protocol_list"),
        intro="Creates the next version of the code. Approved versions are frozen.",
    )


@login_required
def protocol_detail(request, pk):
    access(request.user)
    p = get_object_or_404(
        Protocol.objects.select_related("author", "specification__material"), pk=pk
    )
    user = request.user
    conditions = list(p.conditions.all())
    timepoints = list(p.timepoints.select_related("condition"))
    draft = p.state == Protocol.State.DRAFT
    version, criteria = testing.criteria_now(p)
    problems = [row["problem"] for row in criteria if row["problem"]]
    notice = None
    if problems and p.state in (Protocol.State.DRAFT, Protocol.State.APPROVED):
        consequence = (
            "The protocol cannot be approved until this is resolved in the specification."
            if draft
            else "Tests cannot be assigned to its pulls until this is resolved in the "
            "specification."
        )
        notice = {
            "tone": "warning",
            "label": "Criteria incomplete",
            "text": f"{' '.join(dict.fromkeys(problems))} {consequence}",
        }
    own_draft = draft and p.author_id == user.pk and can(user, *services.AUTHORS)
    actions = [
        action("Approve", reverse("stability:protocol_approve", args=[p.pk]), True)
        if draft and p.author_id != user.pk and can(user, "quality") and timepoints
        else None,
        action("Add condition", reverse("stability:condition_new", args=[p.pk]))
        if own_draft
        else None,
        action("Add timepoint", reverse("stability:timepoint_new", args=[p.pk]))
        if own_draft and conditions
        else None,
        action("Withdraw draft", reverse("stability:protocol_withdraw", args=[p.pk]))
        if draft
        and can(user, *services.AUTHORS)
        and (p.author_id == user.pk or can(user, "quality"))
        else None,
        action("Start study", reverse("stability:study_new") + f"?protocol={p.pk}")
        if p.state == Protocol.State.APPROVED and can(user, *services.AUTHORS)
        else None,
    ]
    return record_page(
        request,
        identifier=p.identifier,
        title=p.title,
        crumbs=crumbs(("Protocols", reverse("stability:protocol_list")), (p.identifier, None)),
        state=_protocol_state(p),
        facts=[
            ("Product", p.product),
            (
                "Protocol document",
                external_link(p.document_url, p.document_ref) if p.document_url else p.document_ref,
            ),
            ("Test profile revision", p.test_profile_ref),
            ("Acceptance criteria", _specification_cell(p)),
            ("Basis", p.basis),
            ("Author", str(p.author)),
            ("Approved", when(p.approved_at)),
            ("Content digest", p.content_digest[:12]),
            ("Revision", p.revision),
        ],
        actions=actions,
        notice=notice,
        sections=[
            section(
                "Storage conditions",
                [
                    ("Condition", False),
                    ("Setpoint", False),
                    ("Temperature (°C)", True),
                    ("Humidity (%)", True),
                ],
                [
                    [
                        c.label,
                        c.setpoint,
                        cell("" if c.temperature_c is None else c.temperature_c, numeric=True),
                        cell("" if c.humidity_pct is None else c.humidity_pct, numeric=True),
                    ]
                    for c in conditions
                ],
                "No conditions yet. Add the approved storage conditions.",
            ),
            section(
                "Timepoints",
                [
                    ("Condition", False),
                    ("Timepoint", False),
                    ("Day", True),
                    ("Window (± days)", True),
                    ("Tests", False),
                ],
                [
                    [
                        t.condition.label,
                        t.label,
                        cell(t.interval_days, numeric=True),
                        cell(t.window_days, numeric=True),
                        ", ".join(t.test_codes),
                    ]
                    for t in timepoints
                ],
                "No timepoints yet.",
            ),
            *(
                [
                    section(
                        "Acceptance criteria in force",
                        [
                            ("Test", False),
                            ("Name", False),
                            ("Acceptance criterion", False),
                            ("Method", False),
                        ],
                        [
                            [
                                row["code"],
                                row["name"],
                                status(row["problem"], "warning")
                                if row["problem"]
                                else row["acceptance"],
                                row["method"],
                            ]
                            for row in criteria
                        ],
                        "Add timepoints to see the acceptance criterion of each test.",
                        note=(
                            f"As {p.specification.code} v{version.version} states them now. "
                            if version
                            else ""
                        )
                        + "Each pull's tests freeze the version in force when they are "
                        "assigned, so a later version of the specification applies to "
                        "later pulls.",
                    )
                ]
                if p.specification_id
                else []
            ),
        ],
        related=[p],
    )


def _specification_cell(protocol):
    specification = protocol.specification
    if specification is None:
        return "Not in the system: pulls link a sample or external evidence"
    return cell(
        f"{specification.code} · {specification.title} ({specification.material.code}, "
        f"{specification.get_stage_display()}, scope {specification.scope})",
        reverse("catalog:specification", args=[specification.pk]),
    )


@login_required
def condition_new(request, pk):
    require_role(request.user, *services.AUTHORS)
    protocol = get_object_or_404(Protocol, pk=pk)
    form = ConditionForm(request.POST or None)
    detail = reverse("stability:protocol_detail", args=[pk])
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.add_condition(
                actor=request.user, protocol=protocol, **form.cleaned_data
            ),
        )
        if done:
            messages.success(request, "Condition added to the draft protocol.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Add condition · {protocol.identifier}",
        crumbs=crumbs(
            ("Protocols", reverse("stability:protocol_list")),
            (protocol.identifier, detail),
            ("Add condition", None),
        ),
        submit="Add condition",
        cancel_url=detail,
    )


@login_required
def timepoint_new(request, pk):
    require_role(request.user, *services.AUTHORS)
    protocol = get_object_or_404(Protocol, pk=pk)
    form = TimepointForm(request.POST or None, protocol=protocol)
    detail = reverse("stability:protocol_detail", args=[pk])
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.add_timepoint(
                actor=request.user, protocol=protocol, **form.cleaned_data
            ),
        )
        if done:
            messages.success(request, "Timepoint added to the draft protocol.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Add timepoint · {protocol.identifier}",
        crumbs=crumbs(
            ("Protocols", reverse("stability:protocol_list")),
            (protocol.identifier, detail),
            ("Add timepoint", None),
        ),
        submit="Add timepoint",
        cancel_url=detail,
    )


@login_required
def protocol_approve(request, pk):
    require_role(request.user, "quality")
    p = get_object_or_404(Protocol, pk=pk)
    denial = ""
    if p.author_id == request.user.pk:
        denial = "You authored this protocol, so you cannot approve it."
    elif p.state != Protocol.State.DRAFT:
        denial = "Only a draft protocol can be approved."
    elif problems := testing.protocol_problems(p):
        denial = " ".join(problems)
    version, _ = testing.criteria_now(p)
    form = SigningForm(request.POST or None, initial={"expected_revision": p.revision})
    detail = reverse("stability:protocol_detail", args=[p.pk])
    return sign_page(
        request,
        form,
        title=f"Approve {p.identifier}",
        identifier=p.identifier,
        meaning="approved",
        meaning_text="You approve the complete protocol: its conditions, timepoints and tests, "
        "and the specification that states their acceptance criteria where one is named. "
        "Earlier approved versions of this code are superseded.",
        button="Sign and approve",
        facts=[
            ("Product", p.product),
            ("Conditions", p.conditions.count()),
            ("Timepoints", p.timepoints.count()),
            (
                "Acceptance criteria",
                (
                    f"{p.specification.code}, v{version.version} in force now"
                    if version
                    else f"{p.specification.code}, no version in force"
                )
                if p.specification_id
                else "Not in the system",
            ),
            ("Author", str(p.author)),
            ("Content digest", p.content_digest[:12]),
        ],
        revision=p.revision,
        cancel_url=detail,
        run=lambda d: services.approve_protocol(
            actor=request.user,
            pin=d["pin"],
            protocol=p,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Protocol approved.",
        success_url=detail,
        denial=denial,
        crumbs=crumbs(
            ("Protocols", reverse("stability:protocol_list")),
            (p.identifier, detail),
            ("Approve", None),
        ),
    )


@login_required
def protocol_withdraw(request, pk):
    require_role(request.user, *services.AUTHORS)
    p = get_object_or_404(Protocol, pk=pk)
    detail = reverse("stability:protocol_detail", args=[p.pk])
    if p.state != Protocol.State.DRAFT:
        messages.warning(request, "Only a draft protocol can be withdrawn.")
        return redirect(detail)
    if p.author_id != request.user.pk and not can(request.user, "quality"):
        raise PermissionDenied("Only the draft's author or a quality person withdraws it.")
    form = WithdrawProtocolForm(request.POST or None, initial={"expected_revision": p.revision})
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.withdraw_protocol(
                actor=request.user,
                protocol=p,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
            ),
        )
        if done:
            messages.success(
                request, f"{p.identifier} withdrawn. The next version of {p.code} can be drafted."
            )
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Withdraw {p.identifier}",
        crumbs=crumbs(
            ("Protocols", reverse("stability:protocol_list")),
            (p.identifier, detail),
            ("Withdraw draft", None),
        ),
        submit="Withdraw draft",
        cancel_url=detail,
        intro="A withdrawn draft is never approved and keeps its content in the record. The "
        "next version of the code can then be drafted, for example to name another "
        "specification or to correct a time point.",
    )


# --- Studies ---------------------------------------------------------------------------------

STUDY_STATUS = [("active", "Active"), ("completed", "Completed"), ("terminated", "Terminated")]


def _study_state(study):
    tone = {"active": "progress", "completed": "success", "terminated": "neutral"}[study.state]
    return status(study.get_state_display(), tone)


@login_required
def study_list(request):
    access(request.user)
    form, data = make_filter(request, STUDY_STATUS)
    queryset = Study.objects.select_related("protocol", "lot")
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(identifier__icontains=q)
            | Q(lot__number__icontains=q)
            | Q(protocol__product__icontains=q)
        )
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {"identifier": ["identifier"], "start": ["start_date"], "lot": ["lot__number"]},
        "-start",
    )
    rows = [
        [
            cell(
                s.identifier,
                reverse("stability:study_detail", args=[s.pk]),
                sub=s.protocol.identifier,
            ),
            cell(
                s.lot.number,
                reverse("quality:lot_detail", args=[s.lot_id]),
                sub=s.protocol.product,
            ),
            s.container_closure,
            day(s.start_date),
            _study_state(s),
        ]
        for s in page
    ]
    return list_page(
        request,
        title="Stability studies",
        intro="One study per approved protocol, lot and container closure.",
        noun="studies",
        columns=[
            ("Study", "identifier", False),
            ("Lot", "lot", False),
            ("Container closure", None, False),
            ("Time zero", "start", False),
            ("State", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "study", "href": reverse("stability:study_new")}
        if can(request.user, *services.AUTHORS)
        else None,
        empty_body="Start a study on an approved protocol to schedule its pulls.",
    )


@login_required
def study_new(request):
    require_role(request.user, *services.AUTHORS)
    initial = {"protocol": request.GET.get("protocol")} if request.method == "GET" else None
    form = StudyForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        study, _ = run_form(
            request,
            form,
            lambda: services.start_study(actor=request.user, **form.cleaned_data),
        )
        if study:
            messages.success(request, "Study started; pulls are scheduled from time zero.")
            return redirect("stability:study_detail", pk=study.pk)
    return form_page(
        request,
        form,
        title="New study",
        crumbs=crumbs(("Studies", reverse("stability:study_list")), ("New study", None)),
        submit="Start study",
        cancel_url=reverse("stability:study_list"),
        intro="Creates a pull for every timepoint of the approved protocol revision.",
    )


def _pull_row(pull, user, today):
    label, tone = _pull_tone(pull, today)
    can_pull = pull.state == "scheduled" and can(user, "analyst")
    links = []
    if can_pull:
        links.append(("Record pull", reverse("stability:pull_record", args=[pull.pk])))
    if pull.state == "scheduled" and timing_closed(pull, today) and can(user, *services.AUTHORS):
        links.append(("Mark missed", reverse("stability:pull_missed", args=[pull.pk])))
    return [
        cell(pull.timepoint.__str__(), reverse("stability:pull_detail", args=[pull.pk])),
        day(pull.due_date),
        f"{day(pull.window[0])} to {day(pull.window[1])}",
        status(label, tone),
        cell(", ".join(pull.timepoint.test_codes)),
        pull.pulled_by and str(pull.pulled_by) or "",
        cell(links[0][0], links[0][1]) if links else "",
    ]


def _schedule(pulls, today):
    """The study's pulls as a grid: one row per storage condition, one column per time point
    (its label and planned date), each cell the pull's status; None where a condition has no
    pull at that time point."""
    columns = sorted(
        {(p.timepoint.interval_days, p.timepoint.label): p.due_date for p in pulls}.items()
    )
    conditions = {}
    for pull in pulls:
        row = conditions.setdefault(pull.timepoint.condition, {})
        row[(pull.timepoint.interval_days, pull.timepoint.label)] = pull
    rows = []
    for condition, by_column in conditions.items():
        cells = []
        for key, _ in columns:
            pull = by_column.get(key)
            if pull is None:
                cells.append(None)
                continue
            label, tone = _pull_tone(pull, today)
            cells.append(
                {
                    "label": label,
                    "tone": tone,
                    "href": reverse("stability:pull_detail", args=[pull.pk]),
                    "due_now": pull.timing(today)[0] == "due",
                }
            )
        rows.append({"condition": condition, "cells": cells})
    return {
        "columns": [{"label": label, "date": day(date)} for (_, label), date in columns],
        "rows": rows,
    }


def _next_pull(pulls, today):
    """The earliest scheduled pull as a clock fact: its time point and due date in the pull's
    status tone (Overdue, Due now, Upcoming); blank when none is scheduled."""
    scheduled = [p for p in pulls if p.state == Pull.State.SCHEDULED]
    if not scheduled:
        return ""
    pull = min(scheduled, key=lambda p: (p.due_date, p.pk))
    due = day(pull.due_date)
    detail = format_html('{} · due <time datetime="{}">{}</time>', pull.timepoint, due, due)
    label, tone = _pull_tone(pull, today)
    if tone in ("danger", "warning"):  # overdue or due now: the fact that must not hide
        return critical(label, tone, detail)
    return cell(detail, pill=(label, tone))


def timing_closed(pull, today):
    return today > pull.window[1]


@login_required
def study_detail(request, pk):
    access(request.user)
    s = get_object_or_404(Study.objects.select_related("protocol", "lot", "created_by"), pk=pk)
    user = request.user
    today = timezone.localdate()
    pulls = list(s.pulls.select_related("timepoint__condition", "pulled_by", "sample"))
    # Closing is the next step only once no pull is still scheduled; until then the next pull
    # is the emphasis and Close study stays a secondary button.
    scheduled = any(p.state == Pull.State.SCHEDULED for p in pulls)
    actions = [
        action("Close study", reverse("stability:study_close", args=[s.pk]), not scheduled)
        if s.state == "active" and can(user, "quality") and s.created_by_id != user.pk
        else None
    ]
    failing = [p for p in pulls if p.outcome == FAILS]
    notice = None
    if failing:
        notice = {
            "tone": "danger",
            "label": "Criteria not met",
            "text": "Results outside the acceptance criteria were confirmed at "
            + ", ".join(str(p.timepoint) for p in failing)
            + f". The record of lot {s.lot.number} is not changed by a stability result: "
            "whether the lot or other lots need a hold or other action is for quality to "
            "decide.",
        }
    return record_page(
        request,
        identifier=s.identifier,
        schedule=_schedule(pulls, today) if pulls else None,
        title=f"{s.protocol.product} · {s.lot.number}",
        crumbs=crumbs(("Studies", reverse("stability:study_list")), (s.identifier, None)),
        state=_study_state(s),
        facts=[
            ("Next pull", _next_pull(pulls, today)),
            ("Lot", cell(s.lot.number, reverse("quality:lot_detail", args=[s.lot_id]))),
            (
                "Protocol",
                cell(
                    s.protocol.identifier,
                    reverse("stability:protocol_detail", args=[s.protocol_id]),
                ),
            ),
            ("Container and closure", s.container_closure),
            ("Time zero", day(s.start_date)),
            ("Lot rule basis at start", s.rule_basis),
            ("Started by", str(s.created_by)),
            ("Closed", when(s.closed_at)),
            ("Revision", s.revision),
        ],
        actions=actions,
        sections=[
            section(
                "Pulls",
                [
                    ("Timepoint", False),
                    ("Due", False),
                    ("Window", False),
                    ("Status", False),
                    ("Tests", False),
                    ("Pulled by", False),
                    ("Next", False),
                ],
                [_pull_row(p, user, today) for p in pulls],
                "No pulls scheduled.",
            ),
            *_comparison(pulls),
        ],
        notice=notice,
        related=[s],
    )


def _result_cell(test):
    """One reported result as a status: the value, and in words when it does not conform."""
    text = test.reportable_with_unit or "No result"
    if test.conforms:
        return status(text, "success")
    return status(f"{text} · out of specification", "danger")


def _comparison(pulls):
    """One section for each storage condition: the time points as rows, the tests as columns
    and each reviewed result with the acceptance criterion it was judged against.

    Time points are rows because a study gains them over the years while it tests a handful
    of attributes, so the table grows down the page and a phone shows every result without
    scrolling sideways. A criterion that differs between time points is written in the cell.
    """
    tested = study_results(pulls)
    if not tested:
        return []
    by_condition = {}
    for pull in pulls:
        by_condition.setdefault(pull.timepoint.condition, []).append(pull)
    sections = []
    for condition, members in by_condition.items():
        members.sort(key=lambda p: (p.timepoint.interval_days, p.pk))
        codes = []
        for pull in members:
            codes += [code for code in pull.timepoint.test_codes if code not in codes]
        found = {}  # (pull pk, code) -> the row of that test's lineage on the pull
        names, criteria = dict.fromkeys(codes), {code: [] for code in codes}
        for pull in members:
            for row in tested.get(pull.pk, ([], [], ""))[1]:
                found[(pull.pk, row["test_code"])] = row
                if row["lineage"]:
                    spec = row["lineage"][0].spec
                    names[row["test_code"]] = f"{spec.name} ({row['test_code']})"
                    if spec.acceptance not in criteria[row["test_code"]]:
                        criteria[row["test_code"]].append(spec.acceptance)
        rows = []
        for pull in members:
            cells = []
            for code in codes:
                row = found.get((pull.pk, code))
                if code not in pull.timepoint.test_codes:
                    cells.append("")
                elif row is None or not row["lineage"]:
                    cells.append(status(*_untested(pull)))
                elif not row["tests"]:
                    missed = pull.state == Pull.State.MISSED
                    cells.append(
                        status(*(("Missed", "neutral") if missed else ("In testing", "progress")))
                    )
                else:
                    text = "; ".join(_result_cell(test)["text"] for test in row["tests"])
                    if len(criteria[code]) > 1:
                        text += f" (against {row['tests'][0].spec.acceptance})"
                    tone = {FAILS: "danger", CONFORMS: "success"}.get(row["outcome"], "progress")
                    cells.append(status(text if row["outcome"] else f"{text} · open", tone))
            rows.append(
                [
                    cell(pull.timepoint.label, reverse("stability:pull_detail", args=[pull.pk])),
                    *cells,
                ]
            )
        headings = [
            names[code] or code
            if len(criteria[code]) != 1
            else f"{names[code] or code}: {criteria[code][0]}"
            for code in codes
        ]
        sections.append(
            section(
                f"Results · {condition.label}",
                [("Time point", False), *((heading, False) for heading in headings)],
                rows,
                "No results yet.",
                note=f"{condition.setpoint}. Reviewed results of the pulls tested in the "
                "system, each judged against the acceptance criterion frozen on its test and "
                "named in the column heading. Where the criterion changed between time points, "
                "each result names the criterion it was judged against.",
            )
        )
    return sections


def _untested(pull):
    """What a results cell says for a time point without tests of its own."""
    if pull.state == Pull.State.MISSED:
        return "Missed", "neutral"
    if pull.state == Pull.State.SCHEDULED:
        return "Not pulled yet", "neutral"
    if pull.sample_id:
        return f"Sample {pull.sample.reference}, tested with the lot", "neutral"
    if pull.external_sample_ref or pull.evidence_ref:
        return "External evidence", "neutral"
    return "No test assigned", "neutral"


@login_required
def study_close(request, pk):
    require_role(request.user, "quality")
    s = get_object_or_404(Study, pk=pk)
    denial = ""
    if s.created_by_id == request.user.pk:
        denial = "You started this study, so you cannot close it."
    elif s.state != Study.State.ACTIVE:
        denial = "This study is already closed."
    elif reasons := testing_in_progress(s):
        denial = "Testing of the study's pulls is in progress; finish it first: " + " ".join(
            reasons
        )
    form = CloseStudyForm(request.POST or None, initial={"expected_revision": s.revision})
    detail = reverse("stability:study_detail", args=[s.pk])
    return sign_page(
        request,
        form,
        title=f"Close {s.identifier}",
        identifier=s.identifier,
        meaning="approved",
        meaning_text="You approve closing the study. Completion needs every pull accepted or "
        "recorded as missed; early termination is recorded as such. A closed study's pulls take "
        "no more testing, and open tests that hold nothing are left as they are.",
        button="Sign and approve",
        facts=[
            ("Lot", s.lot.number),
            ("Protocol", s.protocol.identifier),
            ("Open pulls", s.pulls.filter(state__in=["scheduled", "pulled"]).count()),
        ],
        revision=s.revision,
        cancel_url=detail,
        run=lambda d: services.close_study(
            actor=request.user,
            pin=d["pin"],
            study=s,
            expected_revision=d["expected_revision"],
            outcome=d["outcome"],
            reason=d["reason"],
        ),
        success="Study closed.",
        success_url=detail,
        denial=denial,
        crumbs=crumbs(
            ("Studies", reverse("stability:study_list")), (s.identifier, detail), ("Close", None)
        ),
    )


# --- Pulls -----------------------------------------------------------------------------------

PULL_STATUS = [
    ("overdue", "Overdue"),
    ("due", "Due now"),
    ("upcoming", "Upcoming"),
    ("pulled", "Awaiting acceptance"),
    ("accepted", "Accepted"),
    ("fails", "Accepted, acceptance criteria not met"),
    ("missed", "Missed"),
]


@login_required
def pull_list(request):
    access(request.user)
    today = timezone.localdate()
    form, data = make_filter(request, PULL_STATUS)
    queryset = Pull.objects.select_related("study", "timepoint__condition", "pulled_by")
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(study__identifier__icontains=q) | Q(study__lot__number__icontains=q)
        )
    if data.get("status"):
        queryset = _pull_filter(queryset, data["status"], today)
    page, sort, descending = paginate(
        request,
        queryset,
        {"due": ["due_date"], "study": ["study__identifier", "due_date"], "state": ["state"]},
        "due",
    )
    rows = []
    for p in page:
        label, tone = _pull_tone(p, today)
        rows.append(
            [
                cell(str(p), reverse("stability:pull_detail", args=[p.pk])),
                day(p.due_date),
                f"{day(p.window[0])} to {day(p.window[1])}",
                status(label, tone),
                ", ".join(p.timepoint.test_codes),
            ]
        )
    return list_page(
        request,
        title="Stability pulls",
        intro="Scheduled pulls across active and closed studies, oldest due first.",
        noun="pulls",
        columns=[
            ("Pull", "study", False),
            ("Due", "due", False),
            ("Window", None, False),
            ("Status", "state", False),
            ("Tests", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        empty_body="Pulls appear when a study starts on an approved protocol.",
    )


@login_required
def pull_detail(request, pk):
    access(request.user)
    p = get_object_or_404(
        Pull.objects.select_related(
            "study__lot",
            "study__protocol__specification__material",
            "timepoint__condition",
            "pulled_by",
            "sample",
            "chamber",
            "evidence_recorded_by",
        ),
        pk=pk,
    )
    user = request.user
    today = timezone.localdate()
    label, tone = _pull_tone(p, today)
    detail_actions = []
    if p.state == "scheduled" and can(user, "analyst") and p.study.state == "active":
        detail_actions.append(
            action("Record pull", reverse("stability:pull_record", args=[p.pk]), True)
        )
    if p.state in ("scheduled", "pulled") and can(user, *services.AUTHORS):
        if services.missed_refusal(p) is None:
            detail_actions.append(
                action("Mark missed", reverse("stability:pull_missed", args=[p.pk]))
            )
    tested = has_tests(p)
    blockers, rows, outcome = pull_results(p) if tested else ([], [], "")
    assignable, unassigned = _assignable(p, rows if tested else None)
    if assignable and can(user, "analyst"):
        detail_actions.append(
            action("Assign tests", reverse("stability:pull_tests", args=[p.pk]), not tested)
        )
    if p.state == "pulled" and can(user, "analyst") and not tested:
        detail_actions.append(
            action("Link evidence", reverse("stability:pull_evidence", args=[p.pk]))
        )
    # A pull tested here is offered for acceptance once its testing is complete; the Tests
    # section says what is still open. The header's primary is the first primary action: the
    # analyst's Record pull or Assign tests (untested), else Accept pull, so an analyst who is
    # also a reviewer is offered acceptance first once the tests are done.
    if (
        p.state == "pulled"
        and can(user, "reviewer")
        and user.pk not in services.pull_author_ids(p)
        and not (tested and (blockers or not outcome))
    ):
        detail_actions.append(
            action("Accept pull", reverse("stability:pull_accept", args=[p.pk]), True)
        )
    sections = []
    notice = None
    if tested:
        sections.append(_tests_section(p, rows, blockers, outcome))
        if FAILS in {row["outcome"] for row in rows}:
            notice = {
                "tone": "danger",
                "label": "Criteria not met",
                "text": "An investigation confirmed a result outside the acceptance criteria "
                f"of this time point. The record of lot {p.study.lot.number} is not changed "
                "by a stability result: whether the lot or other lots need a hold or other "
                "action is for quality to decide.",
            }
    elif p.state == "pulled" and not p.sample_id and unassigned:
        sections.append(
            section(
                "Tests",
                [("Status", False)],
                [[status(unassigned, "warning")]],
                "",
                note="This pull is not tested in the system.",
            )
        )
    elif p.state == "pulled" and not p.sample_id and not p.evidence_ref:
        sections.append(
            section(
                "Tests",
                [("Status", False)],
                [],
                "No tests assigned yet. An analyst assigns the tests of this time point to "
                "test the pull in the system, or links a sample or external evidence instead.",
            )
        )
    if p.state == "pulled" and p.sample_id:
        blockers, _ = sample_evidence(p.sample, p.timepoint.test_codes)
        sections.append(
            section(
                "Testing evidence",
                [("Status", False)],
                [[status(b, "warning")] for b in blockers]
                or [[status("Required tests reviewed and conforming", "success")]],
                "",
                note="Acceptance requires every required test reviewed, conforming and free of "
                "open investigations. Results stay in the testing spine.",
            )
        )
    return record_page(
        request,
        identifier=f"{p.study.identifier}-P{p.pk}",
        title=str(p.timepoint),
        crumbs=crumbs(
            ("Studies", reverse("stability:study_list")),
            (p.study.identifier, reverse("stability:study_detail", args=[p.study_id])),
            (f"Pull {p.pk}", None),
        ),
        state=status(label, tone),
        facts=[
            (
                "Due",
                critical(label, tone, day(p.due_date))
                if p.state == "scheduled" and tone in ("danger", "warning")
                else day(p.due_date),
            ),
            ("Window", f"{day(p.window[0])} to {day(p.window[1])}"),
            (
                "Study",
                cell(p.study.identifier, reverse("stability:study_detail", args=[p.study_id])),
            ),
            ("Required tests", ", ".join(p.timepoint.test_codes)),
            ("Pulled on", day(p.pulled_on)),
            ("Pulled by", str(p.pulled_by or "")),
            (
                "Quantity",
                f"{p.quantity.normalize():f} {p.quantity_unit}" if p.quantity is not None else "",
            ),
            ("Held at", p.storage_location),
            ("Chamber", str(p.chamber or "")),
            ("Sample", p.sample.reference if p.sample_id else ""),
            ("External sample", p.external_sample_ref),
            (
                "External evidence",
                external_link(p.evidence_url, p.evidence_ref or None)
                if p.evidence_url
                else p.evidence_ref,
            ),
            ("Deviation", p.deviation_reason),
            ("Missed reason", p.missed_reason),
            ("Accepted", when(p.accepted_at)),
            ("Outcome", p.get_outcome_display()),
            ("Revision", p.revision),
        ],
        actions=detail_actions,
        sections=sections,
        notice=notice,
        related=[p],
    )


def _assignable(pull, rows=None):
    """(whether tests can be assigned to the pull now, why not when it has none).

    ``rows`` are the pull's results when it already has tests; it is then assignable only
    while a test of its time point is still missing."""
    if reason := testing.assignment_refusal(pull):
        return False, "" if pull.state != Pull.State.PULLED else reason
    if rows is not None and all(row["lineage"] for row in rows):
        return False, ""
    _, holds = resolve_pull(pull)
    return not holds, " ".join(holds)


def _test_state(test):
    """The test's result and where it stands, as one status: the value first."""
    result = test.reportable_with_unit
    if test.state == "invalidated":
        return status(f"{result} · invalidated" if result else "Invalidated", "neutral")
    if test.state == "open":
        return status("Open", "progress")
    if test.conforms is False:
        waiting = "awaiting review" if test.state == "submitted" else "reviewed"
        return status(f"{result} · out of specification · {waiting}", "danger")
    if test.state == "submitted":
        return status(f"{result} · awaiting review", "info")
    return status(f"{result} · conforms · reviewed", "success")


def _tests_section(pull, rows, blockers, outcome):
    """The pull's own tests, each with the criterion frozen on it, and what stands in the
    way of accepting the pull."""
    table = []
    for row in rows:
        for test in row["lineage"]:
            spec = test.spec
            table.append(
                [
                    cell(
                        f"{test.label} · {spec.name} ({test.test_code})",
                        reverse("analytical:test_detail", args=[test.pk]),
                    ),
                    _test_state(test),
                    spec.acceptance,
                    test.get_kind_display(),
                ]
            )
        if not row["lineage"]:
            table.append([row["test_code"], status("No test assigned", "warning"), "", ""])
    if pull.state == Pull.State.ACCEPTED:
        note = f"Accepted: {pull.get_outcome_display().lower()}."
    elif blockers or not outcome:
        note = "The pull cannot be accepted yet: " + (" ".join(blockers) or "testing is open.")
    else:
        label = dict(Pull.Outcome.choices)[outcome].lower()
        note = f"Every test is reviewed: the pull {label}. A reviewer can accept it."
    return section(
        "Tests",
        [
            ("Test", False),
            ("Result and status", False),
            ("Acceptance criterion", False),
            ("Kind", False),
        ],
        table,
        "",
        note=note + " Each test is recorded, reviewed and signed on its own page, against the "
        "acceptance criterion frozen when it was assigned.",
    )


def _pull_context(pk):
    pull = get_object_or_404(
        Pull.objects.select_related(
            "study__protocol__specification__material", "timepoint__condition", "sample"
        ),
        pk=pk,
    )
    detail = reverse("stability:pull_detail", args=[pull.pk])
    trail = crumbs(
        ("Studies", reverse("stability:study_list")),
        (pull.study.identifier, reverse("stability:study_detail", args=[pull.study_id])),
        (f"Pull {pull.pk}", detail),
    )
    return pull, detail, trail


@login_required
def pull_record(request, pk):
    require_role(request.user, "analyst")
    pull, detail, trail = _pull_context(pk)
    form = PullForm(request.POST or None, initial={"pulled_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.record_pull(actor=request.user, pull=pull, **form.cleaned_data),
        )
        if done:
            messages.success(request, "Pull recorded; assign its tests or link its evidence.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Record pull · {pull.timepoint}",
        crumbs=[*trail, ("Record pull", None)],
        submit="Record pull",
        cancel_url=detail,
        intro=f"Window {day(pull.window[0])} to {day(pull.window[1])}. A pull outside it needs a "
        "deviation reason.",
    )


@login_required
def pull_evidence(request, pk):
    require_role(request.user, "analyst")
    pull, detail, trail = _pull_context(pk)
    if has_tests(pull):
        messages.warning(request, services.TESTED_HERE)
        return redirect(detail)
    form = EvidenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.attach_pull_evidence(
                actor=request.user, pull=pull, **form.cleaned_data
            ),
        )
        if done:
            messages.success(request, "Evidence linked; independent acceptance needed.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Link evidence · {pull.timepoint}",
        crumbs=[*trail, ("Link evidence", None)],
        submit="Link evidence",
        cancel_url=detail,
        intro="Link the sample registered for testing, or the external stability system's "
        "sample and evidence references. Earlier links stay in the history.",
    )


@login_required
def pull_tests(request, pk):
    """Assign the tests of the pull's time point, showing the acceptance criteria that would
    be frozen on them."""
    require_role(request.user, "analyst")
    pull, detail, trail = _pull_context(pk)
    if reason := testing.assignment_refusal(pull):
        messages.warning(request, reason)
        return redirect(detail)
    accepted, holds = resolve_pull(pull)
    if holds:
        messages.warning(request, "Tests cannot be assigned: " + " ".join(holds))
        return redirect(detail)
    existing = set(pull.tests.values_list("test_code", flat=True))
    if not set(accepted) - existing:
        messages.info(request, "Every test of this time point is already assigned.")
        return redirect(detail)
    shown = analytical.pull_criteria_hash(accepted)
    form = PullTestsForm(request.POST or None, initial={"criteria": shown})
    if request.method == "POST" and form.is_valid():
        created, _ = run_form(
            request,
            form,
            lambda: analytical.assign_pull_tests(
                actor=request.user,
                pull=pull,
                reason=form.cleaned_data["reason"],
                criteria_hash=form.cleaned_data["criteria"],
            ),
        )
        if created:
            messages.success(request, f"Assigned {len(created)} test(s) to the pull.")
            return redirect(detail)
        if created is not None:  # another analyst assigned them meanwhile
            messages.info(request, "Every test of this time point is already assigned.")
            return redirect(detail)
    if form.is_bound:
        # Show the criteria in force now, read after the refusal, with their token, so the
        # page can be submitted after review without being opened again.
        accepted, holds = resolve_pull(pull)
        if holds:
            messages.warning(request, "Tests cannot be assigned: " + " ".join(holds))
            return redirect(detail)
        current = analytical.pull_criteria_hash(accepted)
        if form.data.get("criteria") != current:
            errors = list(form.non_field_errors())
            if analytical.CRITERIA_CHANGED not in errors:
                errors.append(analytical.CRITERIA_CHANGED)
            form = PullTestsForm({**form.data.dict(), "criteria": current})
            form.is_valid()
            for error in errors:
                form.add_error(None, error)
        existing = set(pull.tests.values_list("test_code", flat=True))
    criteria = []
    for code, payload in accepted.items():
        spec = parse_requirement(payload)
        criteria.append(
            {
                "code": code,
                "name": spec.name,
                "acceptance": spec.acceptance,
                "method": f"{spec.method.code} revision {spec.method.revision}",
                "replicates": spec.replicates,
                "assigned": code in existing,
            }
        )
    specification = pull.study.protocol.specification
    source = next(iter(accepted.values()))["source"]
    return render(
        request,
        "stability/pull_tests.html",
        {
            "page_title": f"Assign tests · {pull.timepoint}",
            "crumbs": [*trail, ("Assign tests", None)],
            "pull": pull,
            "criteria": criteria,
            "specification": specification,
            "source": source,
            "form": form,
            "cancel_url": detail,
        },
        status=422 if request.method == "POST" and form.errors else 200,
    )


@login_required
def pull_missed(request, pk):
    require_role(request.user, *services.AUTHORS)
    pull, detail, trail = _pull_context(pk)
    form = ReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.mark_pull_missed(
                actor=request.user, pull=pull, reason=form.cleaned_data["reason"]
            ),
        )
        if done:
            messages.warning(request, "Pull recorded as missed.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Mark missed · {pull.timepoint}",
        crumbs=[*trail, ("Mark missed", None)],
        submit="Mark missed",
        cancel_url=detail,
        intro="A missed pull stays on the study record and cannot be rescheduled silently. A "
        "pull that was taken but cannot be tested (for example lost or insufficient material) "
        "is recorded as missed too, once nothing of its testing is in progress; its reviewed "
        "results stay in the record and its untouched tests take no more work.",
    )


@login_required
def pull_accept(request, pk):
    require_role(request.user, "reviewer")
    pull, detail, trail = _pull_context(pk)
    denial = ""
    if request.user.pk in services.pull_author_ids(pull):
        denial = (
            "You pulled, documented or produced test data for this pull, so you cannot accept it."
        )
    elif pull.state != Pull.State.PULLED:
        denial = "This pull is not awaiting acceptance."
    tested = has_tests(pull)
    results = []
    meaning_text = "You reviewed the pull, its evidence and the linked testing outcome."
    if tested:
        blockers, rows, outcome = pull_results(pull)
        if blockers and not denial:
            denial = "Testing is not complete: " + " ".join(blockers)
        for row in rows:
            for test in row["tests"]:
                results.append(
                    (
                        f"{test.spec.name} ({test.test_code})",
                        status(
                            f"{test.label}: {test.reportable_with_unit} against "
                            f"{test.spec.acceptance}",
                            "success" if test.conforms else "danger",
                        ),
                    )
                )
        if outcome:
            results.append(
                (
                    "Outcome recorded with your signature",
                    status(
                        dict(Pull.Outcome.choices)[outcome],
                        "success" if outcome == CONFORMS else "danger",
                    ),
                )
            )
        meaning_text = (
            "You reviewed the pull and the reviewed results of its tests. Your signature "
            "records how they compare with the acceptance criteria and freezes them with "
            "the pull; it does not change the record of the lot."
        )
    form = SigningForm(request.POST or None, initial={"expected_revision": pull.revision})
    return sign_page(
        request,
        form,
        title=f"Accept pull · {pull.timepoint}",
        identifier=f"{pull.study.identifier}-P{pull.pk}",
        meaning="reviewed",
        meaning_text=meaning_text,
        button="Sign and review",
        facts=[
            ("Required tests", ", ".join(pull.timepoint.test_codes)),
            ("Pulled on", day(pull.pulled_on)),
            (
                "Evidence",
                "Tested in the system"
                if tested
                else (pull.sample.reference if pull.sample_id else pull.external_sample_ref),
            ),
            *results,
            ("Deviation", pull.deviation_reason),
        ],
        revision=pull.revision,
        cancel_url=detail,
        run=lambda d: services.accept_pull(
            actor=request.user,
            pin=d["pin"],
            pull=pull,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Pull accepted.",
        success_url=detail,
        denial=denial,
        crumbs=[*trail, ("Accept", None)],
    )


# --- Reserves and retention ------------------------------------------------------------------


@login_required
def reserve_list(request):
    access(request.user)
    form, data = make_filter(request, [("below", "Below minimum quantity")])
    queryset = ReserveSample.objects.select_related("lot").prefetch_related("obligations")
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(Q(identifier__icontains=q) | Q(lot__number__icontains=q))
    if data.get("status") == "below":
        queryset = queryset.filter(quantity__lt=F("minimum_multiple") * F("test_quantity"))
    page, sort, descending = paginate(
        request,
        queryset,
        {"identifier": ["identifier"], "lot": ["lot__number"], "retained": ["retained_on"]},
        "-retained",
    )
    rows = [
        [
            cell(r.identifier, reverse("stability:reserve_detail", args=[r.pk]), sub=r.lot.number),
            cell(f"{r.quantity.normalize():f} {r.quantity_unit}", numeric=True),
            day(r.retained_on),
            r.storage_location,
            status("Meets minimum", "success")
            if r.meets_minimum
            else status("Below minimum", "warning"),
            day(_retain_through(r)),
            status("Active", "hold") if gates.active_holds(r.lot, r).exists() else "",
        ]
        for r in page
    ]
    return list_page(
        request,
        title="Reserve samples",
        intro="Identified reserve samples with quantity against the configured minimum and "
        "their retention obligations and holds. Nothing here can be disposed of.",
        noun="reserve samples",
        columns=[
            ("Reserve", "identifier", False),
            ("Quantity", None, True),
            ("Retained", "retained", False),
            ("Location", None, False),
            ("Quantity check", None, False),
            ("Retain through", None, False),
            ("Hold", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "reserve sample", "href": reverse("stability:reserve_new")}
        if can(request.user, *services.AUTHORS)
        else None,
        empty_body="Record a reserve sample to track its quantity, retention and holds.",
    )


@login_required
def reserve_new(request):
    require_role(request.user, *services.AUTHORS)
    form = ReserveForm(request.POST or None, initial={"minimum_multiple": 2})
    if request.method == "POST" and form.is_valid():
        reserve, _ = run_form(
            request,
            form,
            lambda: services.record_reserve(actor=request.user, **form.cleaned_data),
        )
        if reserve:
            messages.success(request, "Reserve sample recorded. Record its retention obligations.")
            return redirect("stability:reserve_detail", pk=reserve.pk)
    return form_page(
        request,
        form,
        title="New reserve sample",
        crumbs=crumbs(
            ("Reserve samples", reverse("stability:reserve_list")), ("New reserve sample", None)
        ),
        submit="Record reserve sample",
        cancel_url=reverse("stability:reserve_list"),
        intro="Reserve records are immutable. The minimum multiple is prefilled from the "
        "researched drug and supplement rules; the quality owner confirms what applies.",
    )


def _retain_through(reserve):
    """The latest date an obligation of the reserve retains it to, or None while an obligation
    has no anchor yet (its date is unknown) or there is none."""
    dates = [o.retain_until for o in reserve.obligations.all()]
    return max(dates) if dates and None not in dates else None


def _obligation_row(o, user, today):
    blocker = o.blocker(today)
    return [
        o.get_anchor_kind_display(),
        day(o.anchor_date),
        cell(o.offset_months, numeric=True),
        day(o.retain_until),
        o.basis,
        status("Cleared", "success") if not blocker else status("Retained", "warning"),
        cell("Set anchor", reverse("stability:anchor_set", args=[o.pk]))
        if o.anchor_date is None and can(user, *services.AUTHORS)
        else "",
    ]


@login_required
def reserve_detail(request, pk):
    access(request.user)
    r = get_object_or_404(ReserveSample.objects.select_related("lot", "recorded_by"), pk=pk)
    user = request.user
    today = timezone.localdate()
    obligations = list(r.obligations.all())
    holds = list(r.holds.select_related("placed_by"))
    blockers = gates.disposal_blockers(r.lot, reserve=r, today=today)
    return record_page(
        request,
        identifier=r.identifier,
        title=f"Reserve of {r.lot.number}",
        crumbs=crumbs(("Reserve samples", reverse("stability:reserve_list")), (r.identifier, None)),
        state=status("Meets minimum", "success")
        if r.meets_minimum
        else status("Below minimum", "warning"),
        facts=[
            ("Lot", cell(r.lot.number, reverse("quality:lot_detail", args=[r.lot_id]))),
            ("Container", r.container_description),
            ("Location", r.storage_location),
            ("Quantity retained", f"{r.quantity.normalize():f} {r.quantity_unit}"),
            ("One test set", f"{r.test_quantity.normalize():f} {r.quantity_unit}"),
            ("Multiple of test set", f"{r.multiple:.2f} (minimum {r.minimum_multiple})"),
            ("Retained on", day(r.retained_on)),
            ("Recorded by", str(r.recorded_by)),
        ],
        actions=[
            action(
                "Record retention obligation",
                reverse("stability:obligation_new") + f"?reserve={r.pk}",
                True,
            )
            if can(user, *services.AUTHORS)
            else None,
            action("Place hold", reverse("stability:hold_new") + f"?reserve={r.pk}")
            if can(user, *services.ANY_SCIENTIFIC)
            else None,
        ],
        sections=[
            section(
                "Retention obligations",
                [
                    ("Anchor", False),
                    ("Anchor date", False),
                    ("Months", True),
                    ("Retain through", False),
                    ("Basis", False),
                    ("Status", False),
                    ("Next", False),
                ],
                [_obligation_row(o, user, today) for o in obligations],
                "No obligation recorded: applicability is unresolved, so nothing may be "
                "disposed of.",
                note="Every obligation computes its own deadline from its own anchor; all must "
                "clear before disposal.",
            ),
            section(
                "Holds",
                [("Hold", False), ("Kind", False), ("State", False), ("Placed by", False)],
                [
                    [
                        cell(h.identifier, reverse("stability:hold_detail", args=[h.pk])),
                        h.get_kind_display(),
                        _hold_state(h),
                        str(h.placed_by),
                    ]
                    for h in holds
                ],
                "No holds on this reserve sample.",
            ),
            section(
                "Disposal readiness",
                [("Blocking reason", False)],
                [[status(b, "warning")] for b in blockers],
                "Nothing currently blocks disposal. No disposal action exists in this system yet.",
            ),
        ],
        related=[r],
    )


def _reserve_from_query(request):
    """The reserve named by `?reserve=`; anything but a record number is not found."""
    value = request.GET["reserve"]
    if not value.isascii() or not value.isdigit() or len(value) > 19:  # a bigint has <= 19
        raise Http404("No such reserve sample.")
    return get_object_or_404(ReserveSample, pk=value)


@login_required
def obligation_new(request):
    require_role(request.user, *services.AUTHORS)
    reserve = None
    if request.GET.get("reserve"):
        reserve = _reserve_from_query(request)
    form = ObligationForm(request.POST or None, with_lot=reserve is None)
    back = (
        reverse("stability:reserve_detail", args=[reserve.pk])
        if reserve
        else reverse("stability:reserve_list")
    )
    if request.method == "POST" and form.is_valid():
        values = dict(form.cleaned_data)
        lot = reserve.lot if reserve else values.pop("lot")
        done, _ = run_form(
            request,
            form,
            lambda: services.add_obligation(actor=request.user, lot=lot, reserve=reserve, **values),
        )
        if done:
            messages.success(request, "Retention obligation recorded.")
            return redirect(back)
    return form_page(
        request,
        form,
        title="New retention obligation",
        crumbs=crumbs(
            ("Reserve samples", reverse("stability:reserve_list")),
            ("New retention obligation", None),
        ),
        submit="Record obligation",
        cancel_url=back,
        intro="One obligation per applicable retention basis. The deadline is the anchor date "
        "plus the months; an unknown anchor keeps the item retained until it is set.",
    )


@login_required
def anchor_set(request, pk):
    require_role(request.user, *services.AUTHORS)
    o = get_object_or_404(RetentionObligation.objects.select_related("reserve", "lot"), pk=pk)
    form = AnchorForm(request.POST or None)
    back = (
        reverse("stability:reserve_detail", args=[o.reserve_id])
        if o.reserve_id
        else reverse("stability:reserve_list")
    )
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.set_anchor(actor=request.user, obligation=o, **form.cleaned_data),
        )
        if done:
            messages.success(request, "Retention anchor set.")
            return redirect(back)
    return form_page(
        request,
        form,
        title=f"Set anchor · {o.get_anchor_kind_display()}",
        crumbs=crumbs(("Reserve samples", reverse("stability:reserve_list")), ("Set anchor", None)),
        submit="Set anchor",
        cancel_url=back,
        intro="The anchor can be set once. If it later moves, record a new obligation.",
    )


# --- Holds -----------------------------------------------------------------------------------

HOLD_STATUS = [("active", "Active"), ("released", "Released")]


def _hold_state(h):
    return status(h.get_state_display(), "hold" if h.state == "active" else "neutral")


@login_required
def hold_list(request):
    access(request.user)
    form, data = make_filter(request, HOLD_STATUS)
    queryset = Hold.objects.select_related("lot", "placed_by")
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(lot__number__icontains=q) | Q(reference__icontains=q) | Q(reason__icontains=q)
        )
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request, queryset, {"placed": ["placed_at"], "lot": ["lot__number"]}, "-placed"
    )
    rows = [
        [
            cell(
                h.identifier,
                reverse("stability:hold_detail", args=[h.pk]),
                sub=h.get_kind_display(),
            ),
            h.lot.number,
            cell(h.reference, code=True) if h.reference else "",
            _hold_state(h),
            when(h.placed_at),
        ]
        for h in page
    ]
    return list_page(
        request,
        title="Holds",
        intro="Holds block QC disposition and disposal until a different quality signer "
        "releases them.",
        noun="holds",
        columns=[
            ("Hold", None, False),
            ("Lot", "lot", False),
            ("Reference", None, False),
            ("State", None, False),
            ("Placed", "placed", False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "hold", "href": reverse("stability:hold_new")}
        if can(request.user, *services.ANY_SCIENTIFIC)
        else None,
        empty_body="Place a hold on a lot or reserve sample to stop disposition or disposal.",
    )


@login_required
def hold_new(request):
    require_role(request.user, *services.ANY_SCIENTIFIC)
    reserve = None
    initial = {}
    if request.GET.get("reserve"):
        reserve = _reserve_from_query(request)
        initial["lot"] = reserve.lot_id
    form = HoldForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        hold, _ = run_form(
            request,
            form,
            lambda: services.place_hold(actor=request.user, reserve=reserve, **form.cleaned_data),
        )
        if hold:
            messages.warning(request, f"{hold.identifier} placed.")
            return redirect("stability:hold_detail", pk=hold.pk)
    return form_page(
        request,
        form,
        title="New hold",
        crumbs=crumbs(("Holds", reverse("stability:hold_list")), ("New hold", None)),
        submit="Place hold",
        cancel_url=reverse("stability:hold_list"),
        intro="Placing a hold is protective and immediate. Releasing it needs a different "
        "quality signer.",
        record=reserve,
    )


@login_required
def hold_detail(request, pk):
    access(request.user)
    h = get_object_or_404(Hold.objects.select_related("lot", "reserve", "placed_by"), pk=pk)
    user = request.user
    return record_page(
        request,
        identifier=h.identifier,
        title=f"{h.get_kind_display()} hold · {h.lot.number}",
        crumbs=crumbs(("Holds", reverse("stability:hold_list")), (h.identifier, None)),
        state=_hold_state(h),
        facts=[
            (
                "Status",
                critical("On hold", "hold", "QC disposition and disposal of this lot are blocked.")
                if h.state == "active"
                else _hold_state(h),
            ),
            ("Lot", cell(h.lot.number, reverse("quality:lot_detail", args=[h.lot_id]))),
            (
                "Reserve sample",
                cell(h.reserve.identifier, reverse("stability:reserve_detail", args=[h.reserve_id]))
                if h.reserve_id
                else "",
            ),
            ("Kind", h.get_kind_display()),
            ("Reference", cell(h.reference, code=True) if h.reference else ""),
            ("Reason", h.reason),
            ("Placed by", str(h.placed_by)),
            ("Placed", when(h.placed_at)),
            ("Released", when(h.released_at)),
            ("Revision", h.revision),
        ],
        actions=[
            action("Release hold", reverse("stability:hold_release", args=[h.pk]), True)
            if h.state == "active" and can(user, "quality") and h.placed_by_id != user.pk
            else None
        ],
        related=[h],
    )


@login_required
def hold_release(request, pk):
    require_role(request.user, "quality")
    h = get_object_or_404(Hold.objects.select_related("lot"), pk=pk)
    denial = ""
    if h.placed_by_id == request.user.pk:
        denial = "You placed this hold, so you cannot release it."
    elif h.state != Hold.State.ACTIVE:
        denial = "This hold is already released."
    form = SigningForm(request.POST or None, initial={"expected_revision": h.revision})
    detail = reverse("stability:hold_detail", args=[h.pk])
    return sign_page(
        request,
        form,
        title=f"Release {h.identifier}",
        identifier=h.identifier,
        meaning="approved",
        meaning_text="You approve releasing this hold. Other holds and retention obligations "
        "continue to apply.",
        button="Sign and approve",
        facts=[
            ("Lot", h.lot.number),
            ("Kind", h.get_kind_display()),
            ("Reason", h.reason),
            ("Reference", h.reference),
        ],
        revision=h.revision,
        cancel_url=detail,
        run=lambda d: services.release_hold(
            actor=request.user,
            pin=d["pin"],
            hold=h,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Hold released.",
        success_url=detail,
        denial=denial,
        crumbs=crumbs(
            ("Holds", reverse("stability:hold_list")), (h.identifier, detail), ("Release", None)
        ),
    )
