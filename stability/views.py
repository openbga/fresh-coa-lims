from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DateField, DurationField, ExpressionWrapper, F, Q, Value
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.services import require_role
from laboratory.ui import (
    access,
    action,
    cell,
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

from . import gates, services
from .evidence import sample_evidence
from .forms import (
    AnchorForm,
    CloseStudyForm,
    ConditionForm,
    EvidenceForm,
    HoldForm,
    ObligationForm,
    ProtocolForm,
    PullForm,
    ReasonForm,
    ReserveForm,
    SigningForm,
    StudyForm,
    TimepointForm,
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


def _pull_tone(pull, today):
    timing, label = pull.timing(today)
    tone = {"overdue": "danger", "due": "warning", "upcoming": "neutral"}.get(timing)
    if tone is None:
        tone = {"pulled": "progress", "accepted": "success", "missed": "danger"}[pull.state]
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
            "Native scheduling is thin: link external stability systems where used.",
            "queues": [
                {"label": label, "count": count, "tone": tone if count else "neutral", "href": href}
                for label, count, tone, href in queues
            ],
        },
    )


# --- Protocols -------------------------------------------------------------------------------

PROTOCOL_STATUS = [("draft", "Draft"), ("approved", "Approved"), ("superseded", "Superseded")]


def _protocol_state(protocol):
    tone = {"draft": "progress", "approved": "success", "superseded": "neutral"}[protocol.state]
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
            cell(p.identifier, reverse("stability:protocol_detail", args=[p.pk])),
            p.title,
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
            ("Title", None, False),
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
    p = get_object_or_404(Protocol.objects.select_related("author"), pk=pk)
    user = request.user
    conditions = list(p.conditions.all())
    timepoints = list(p.timepoints.select_related("condition"))
    draft = p.state == Protocol.State.DRAFT
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
            ("Basis", p.basis),
            ("Author", str(p.author)),
            ("Approved", when(p.approved_at)),
            ("Content digest", p.content_digest[:12]),
            ("Revision", p.revision),
        ],
        actions=actions,
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
        ],
        related=[p],
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
    form = SigningForm(request.POST or None, initial={"expected_revision": p.revision})
    detail = reverse("stability:protocol_detail", args=[p.pk])
    return sign_page(
        request,
        form,
        title=f"Approve {p.identifier}",
        identifier=p.identifier,
        meaning="approved",
        meaning_text="You approve the complete protocol: its conditions, timepoints and tests. "
        "Earlier approved versions of this code are superseded.",
        button="Sign and approve",
        facts=[
            ("Product", p.product),
            ("Conditions", p.conditions.count()),
            ("Timepoints", p.timepoints.count()),
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
            cell(s.identifier, reverse("stability:study_detail", args=[s.pk])),
            s.lot.number,
            s.protocol.identifier,
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
            ("Protocol", None, False),
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


def timing_closed(pull, today):
    return today > pull.window[1]


@login_required
def study_detail(request, pk):
    access(request.user)
    s = get_object_or_404(Study.objects.select_related("protocol", "lot", "created_by"), pk=pk)
    user = request.user
    today = timezone.localdate()
    pulls = list(s.pulls.select_related("timepoint__condition", "pulled_by"))
    actions = [
        action("Close study", reverse("stability:study_close", args=[s.pk]), True)
        if s.state == "active" and can(user, "quality") and s.created_by_id != user.pk
        else None
    ]
    return record_page(
        request,
        identifier=s.identifier,
        title=f"{s.protocol.product} · {s.lot.number}",
        crumbs=crumbs(("Studies", reverse("stability:study_list")), (s.identifier, None)),
        state=_study_state(s),
        facts=[
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
            )
        ],
        related=[s],
    )


@login_required
def study_close(request, pk):
    require_role(request.user, "quality")
    s = get_object_or_404(Study, pk=pk)
    denial = ""
    if s.created_by_id == request.user.pk:
        denial = "You started this study, so you cannot close it."
    elif s.state != Study.State.ACTIVE:
        denial = "This study is already closed."
    form = CloseStudyForm(request.POST or None, initial={"expected_revision": s.revision})
    detail = reverse("stability:study_detail", args=[s.pk])
    return sign_page(
        request,
        form,
        title=f"Close {s.identifier}",
        identifier=s.identifier,
        meaning="approved",
        meaning_text="You approve closing the study. Completion needs every pull accepted or "
        "recorded as missed; early termination is recorded as such.",
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
            "study__protocol",
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
    if p.state == "scheduled" and today > p.window[1] and can(user, *services.AUTHORS):
        detail_actions.append(action("Mark missed", reverse("stability:pull_missed", args=[p.pk])))
    if p.state == "pulled" and can(user, "analyst"):
        detail_actions.append(
            action("Link evidence", reverse("stability:pull_evidence", args=[p.pk]))
        )
    if p.state == "pulled" and can(user, "reviewer") and user.pk not in services.pull_author_ids(p):
        detail_actions.append(
            action("Accept pull", reverse("stability:pull_accept", args=[p.pk]), True)
        )
    sections = []
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
                "Study",
                cell(p.study.identifier, reverse("stability:study_detail", args=[p.study_id])),
            ),
            ("Due", day(p.due_date)),
            ("Window", f"{day(p.window[0])} to {day(p.window[1])}"),
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
            ("Revision", p.revision),
        ],
        actions=detail_actions,
        sections=sections,
        related=[p],
    )


def _pull_context(pk):
    pull = get_object_or_404(Pull.objects.select_related("study", "timepoint"), pk=pk)
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
            messages.success(request, "Pull recorded; link its testing evidence.")
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
        intro="A missed pull stays on the study record and cannot be rescheduled silently.",
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
    form = SigningForm(request.POST or None, initial={"expected_revision": pull.revision})
    return sign_page(
        request,
        form,
        title=f"Accept pull · {pull.timepoint}",
        identifier=f"{pull.study.identifier}-P{pull.pk}",
        meaning="reviewed",
        meaning_text="You reviewed the pull, its evidence and the linked testing outcome.",
        button="Sign and review",
        facts=[
            ("Required tests", ", ".join(pull.timepoint.test_codes)),
            ("Pulled on", day(pull.pulled_on)),
            ("Sample", pull.sample.reference if pull.sample_id else pull.external_sample_ref),
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
    queryset = ReserveSample.objects.select_related("lot")
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
            cell(r.identifier, reverse("stability:reserve_detail", args=[r.pk])),
            r.lot.number,
            cell(f"{r.quantity.normalize():f} {r.quantity_unit}", numeric=True),
            day(r.retained_on),
            r.storage_location,
            status("Meets minimum", "success")
            if r.meets_minimum
            else status("Below minimum", "warning"),
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
            ("Lot", "lot", False),
            ("Quantity", None, True),
            ("Retained", "retained", False),
            ("Location", None, False),
            ("Quantity check", None, False),
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
                        h.get_state_display(),
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
            cell(h.identifier, reverse("stability:hold_detail", args=[h.pk])),
            h.lot.number,
            h.get_kind_display(),
            h.reference,
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
            ("Kind", None, False),
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
            ("Lot", cell(h.lot.number, reverse("quality:lot_detail", args=[h.lot_id]))),
            (
                "Reserve sample",
                cell(h.reserve.identifier, reverse("stability:reserve_detail", args=[h.reserve_id]))
                if h.reserve_id
                else "",
            ),
            ("Kind", h.get_kind_display()),
            ("Reference", h.reference),
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
        notice={
            "tone": "warning",
            "label": "On hold",
            "text": "QC disposition and disposal of this lot are blocked.",
        }
        if h.state == "active"
        else None,
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
