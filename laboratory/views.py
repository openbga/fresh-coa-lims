from datetime import timedelta

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.services import require_role
from quality.models import Sample

from . import services
from .eligibility import (
    DUE_SOON_DAYS,
    affected_uses,
    equipment_filter,
    equipment_queryset,
    equipment_status,
    reagent_status,
)
from .forms import (
    CalibrationForm,
    EquipmentForm,
    ImpactSigningForm,
    QualificationForm,
    ReagentForm,
    ReasonForm,
    SigningForm,
    UseForm,
)
from .models import Calibration, Equipment, Qualification, ReagentLot, ResourceUse
from .services import UseBlocked
from .ui import (
    access,
    action,
    cell,
    day,
    external_link,
    form_page,
    impact_columns,
    impact_row,
    impact_summary,
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
    work_cell,
    work_labels,
)

HOME = "Laboratory"
IMPACT_SHOWN = 50


def crumbs(*pairs):
    return [(HOME, reverse("laboratory:overview")), *pairs]


def can(user, *roles):
    return bool(roles_of(user) & set(roles))


def _soon():
    today = timezone.localdate()
    return today, today + timedelta(days=DUE_SOON_DAYS)


def _tone(ok):
    return "success" if ok else "danger"


# --- Overview --------------------------------------------------------------------------------


@login_required
def overview(request):
    access(request.user)
    today, soon = _soon()
    equipment = equipment_queryset(today)
    queues = [
        (
            "Calibration overdue",
            equipment_filter(equipment, "overdue", today).count(),
            "danger",
            reverse("laboratory:equipment_list") + "?status=overdue",
        ),
        (
            "Calibration due within 30 days",
            equipment_filter(equipment, "due_soon", today).count(),
            "warning",
            reverse("laboratory:equipment_list") + "?status=due_soon",
        ),
        (
            "Equipment out of service",
            equipment.exclude(state="in_service").count(),
            "danger",
            reverse("laboratory:equipment_list") + "?status=out_of_service",
        ),
        (
            "Calibrations awaiting acceptance",
            Calibration.objects.filter(state="recorded").count(),
            "info",
            reverse("laboratory:calibration_list") + "?status=recorded",
        ),
        (
            "Reagent lots awaiting release",
            ReagentLot.objects.filter(state="received").count(),
            "info",
            reverse("laboratory:reagent_list") + "?status=received",
        ),
        (
            "Released lots expiring within 30 days",
            ReagentLot.objects.filter(
                state="released", expiry_date__gte=today, expiry_date__lte=soon
            ).count(),
            "warning",
            reverse("laboratory:reagent_list") + "?status=expiring",
        ),
        (
            "Released lots past expiry",
            ReagentLot.objects.filter(state="released", expiry_date__lt=today).count(),
            "danger",
            reverse("laboratory:reagent_list") + "?status=expired",
        ),
        (
            "Qualifications awaiting approval",
            Qualification.objects.filter(state="recorded").count(),
            "info",
            reverse("laboratory:qualification_list") + "?status=recorded",
        ),
        (
            "Qualifications expiring within 30 days",
            Qualification.objects.filter(
                state="approved",
                valid_from__lte=today,
                valid_until__gte=today,
                valid_until__lte=soon,
            ).count(),
            "warning",
            reverse("laboratory:qualification_list") + "?status=expiring",
        ),
    ]
    return render(
        request,
        "ops/overview.html",
        {
            "page_title": "Laboratory operations",
            "tabs": section_tabs(request),
            "intro": "Equipment fitness, reagent and standard provenance, and analyst "
            "qualification gates for laboratory work.",
            "queues": [
                {"label": label, "count": count, "tone": tone if count else "neutral", "href": href}
                for label, count, tone, href in queues
            ],
        },
    )


# --- Equipment -------------------------------------------------------------------------------

EQUIPMENT_STATUS = [
    ("ready", "Ready"),
    ("due_soon", "Calibration due soon"),
    ("overdue", "Calibration overdue"),
    ("unfit", "Not calibrated or qualified"),
    ("out_of_service", "Out of service"),
]


@login_required
def equipment_list(request):
    access(request.user)
    form, data = make_filter(request, EQUIPMENT_STATUS)
    queryset = equipment_queryset()
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(asset_id__icontains=q) | Q(description__icontains=q) | Q(category__icontains=q)
        )
    if data.get("status"):
        queryset = equipment_filter(queryset, data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {
            "asset": ["asset_id"],
            "category": ["category", "asset_id"],
            "due": ["last_due"],
            "state": ["state", "asset_id"],
        },
        "asset",
    )
    rows = []
    for item in page:
        label, tone, _ = equipment_status(item)
        rows.append(
            [
                cell(item.asset_id, reverse("laboratory:equipment_detail", args=[item.pk])),
                item.description,
                item.category,
                item.location,
                day(item.last_due),
                status(label, tone),
            ]
        )
    return list_page(
        request,
        title="Equipment",
        intro="Fitness for use from accepted calibration, qualification and service state.",
        noun="equipment",
        columns=[
            ("Asset", "asset", False),
            ("Description", None, False),
            ("Category", "category", False),
            ("Location", None, False),
            ("Calibration due", "due", False),
            ("Fitness", "state", False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "equipment", "href": reverse("laboratory:equipment_new")}
        if can(request.user, *services.RECORDERS)
        else None,
        empty_body="Register an instrument to track calibration, qualification and use.",
    )


@login_required
def equipment_new(request):
    require_role(request.user, *services.RECORDERS)
    form = EquipmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item, _ = run_form(
            request,
            form,
            lambda: services.register_equipment(actor=request.user, **form.cleaned_data),
        )
        if item:
            messages.success(request, "Equipment registered.")
            return redirect("laboratory:equipment_detail", pk=item.pk)
    return form_page(
        request,
        form,
        title="New equipment",
        crumbs=crumbs(("Equipment", reverse("laboratory:equipment_list")), ("New equipment", None)),
        submit="Register equipment",
        cancel_url=reverse("laboratory:equipment_list"),
        intro="Registration does not make equipment fit for use; calibration and any "
        "required qualification must be independently accepted.",
    )


def _equipment_crumbs(item, current):
    return crumbs(
        ("Equipment", reverse("laboratory:equipment_list")),
        (item.asset_id, reverse("laboratory:equipment_detail", args=[item.pk])),
        (current, None),
    )


@login_required
def equipment_detail(request, pk):
    access(request.user)
    item = get_object_or_404(equipment_queryset().select_related("status_changed_by"), pk=pk)
    label, tone, _ = equipment_status(item)
    user = request.user
    calibrations = list(item.calibrations.select_related("recorded_by"))
    qualifications = list(item.qualifications.select_related("recorded_by"))
    uses = list(item.uses.select_related("used_by")[:25])
    today = timezone.localdate()
    out_of_service = item.state != Equipment.State.IN_SERVICE
    calibration_rows = []
    for c in calibrations:
        offer = (
            c.state == Calibration.State.RECORDED
            and c.recorded_by_id != user.pk
            and can(user, "reviewer")
        )
        calibration_rows.append(
            [
                when(c.performed_at),
                day(c.due_date),
                status(c.get_outcome_display(), "success" if c.outcome == "pass" else "danger"),
                status(c.get_state_display(), "success" if c.state == "accepted" else "progress"),
                c.standard_ref,
                external_link(c.certificate_url, c.certificate_ref or c.certificate_url)
                if c.certificate_url
                else c.certificate_ref,
                str(c.recorded_by),
                cell("Accept", reverse("laboratory:calibration_accept", args=[c.pk]))
                if offer
                else "",
            ]
        )
    sections = [
        section(
            "Calibrations",
            [
                ("Performed", False),
                ("Due (inclusive)", False),
                ("Outcome", False),
                ("State", False),
                ("Standard", False),
                ("Certificate", False),
                ("Recorded by", False),
                ("Action", False),
            ],
            calibration_rows,
            "No calibration recorded. Equipment is not fit for use until a passing "
            "calibration is independently accepted.",
        ),
        section(
            "Qualification evidence",
            [
                ("Stage or use", False),
                ("State", False),
                ("Valid from", False),
                ("Valid until", False),
                ("Evidence", False),
            ],
            [
                [
                    cell(q.activity, reverse("laboratory:qualification_detail", args=[q.pk])),
                    status(*qualification_status(q, today)[:2]),
                    day(q.valid_from),
                    day(q.valid_until),
                    q.evidence_ref,
                ]
                for q in qualifications
            ],
            "No qualification evidence recorded."
            if item.requires_qualification
            else "Qualification is not required for this equipment.",
        ),
    ]
    if out_of_service:
        impacted = list(affected_uses(item).select_related("used_by")[:IMPACT_SHOWN])
        impacted_work = work_labels([(u.context_type, u.context_id) for u in impacted])
        sections.append(
            section(
                "Uses to assess after failure",
                impact_columns(),
                [impact_row(u, impacted_work) for u in impacted],
                "No recorded uses since the last accepted passing calibration.",
                note="Uses since the last independently accepted passing calibration before "
                "the failure. The return-to-service signature records this assessment.",
            )
        )
    recent_work = work_labels([(u.context_type, u.context_id) for u in uses])
    sections.append(
        section(
            "Recent uses",
            [
                ("Used", False),
                ("Work", False),
                ("Activity", False),
                ("Test", False),
                ("By", False),
            ],
            [
                [
                    when(u.used_at),
                    work_cell(u, recent_work),
                    u.activity,
                    u.test_code,
                    str(u.used_by),
                ]
                for u in uses
            ],
            "No use recorded.",
        )
    )
    actions = [
        action("Record calibration", reverse("laboratory:calibration_new", args=[item.pk]), True)
        if can(user, *services.RECORDERS)
        else None,
        action(
            "Record qualification",
            reverse("laboratory:equipment_qualification_new", args=[item.pk]),
        )
        if can(user, "analyst", "reviewer", "quality")
        else None,
        action(
            "Take out of service", reverse("laboratory:equipment_out_of_service", args=[item.pk])
        )
        if not out_of_service and can(user, "analyst", "reviewer", "quality")
        else None,
        action("Return to service", reverse("laboratory:equipment_return", args=[item.pk]))
        if out_of_service and can(user, "quality")
        else None,
    ]
    return record_page(
        request,
        identifier=item.asset_id,
        title=item.description,
        crumbs=crumbs(("Equipment", reverse("laboratory:equipment_list")), (item.asset_id, None)),
        state=status(label, tone),
        facts=[
            ("Category", item.category),
            ("Location", item.location),
            ("Qualification required", "Yes" if item.requires_qualification else "No"),
            ("Service state", status(item.get_state_display(), _tone(not out_of_service))),
            ("Last status change", when(item.status_changed_at)),
            ("Changed by", str(item.status_changed_by or "")),
            ("Revision", item.revision),
        ],
        actions=actions,
        sections=sections,
        related=[item, *calibrations, *qualifications],
        notice={
            "tone": "danger",
            "label": "Out of service",
            "text": "This equipment cannot be used. Returning it requires an independently "
            "accepted passing calibration and a signed impact assessment.",
        }
        if out_of_service
        else None,
    )


def qualification_status(q, today):
    """(label, tone, key). Approved is effective only inside valid_from..valid_until."""
    if q.state == Qualification.State.APPROVED:
        if q.valid_from > today:
            return f"Approved, starts {q.valid_from.isoformat()}", "info", "scheduled"
        if q.valid_until < today:
            return "Expired", "danger", "expired"
        return "Approved", "success", "approved"
    tone = {"recorded": "progress", "revoked": "danger"}[q.state]
    return q.get_state_display(), tone, q.state


@login_required
def equipment_out_of_service(request, pk):
    require_role(request.user, "analyst", "reviewer", "quality")
    item = get_object_or_404(Equipment, pk=pk)
    form = ReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.take_out_of_service(
                actor=request.user, equipment=item, reason=form.cleaned_data["reason"]
            ),
        )
        if done:
            messages.success(request, "Equipment removed from service.")
            return redirect("laboratory:equipment_detail", pk=item.pk)
    return form_page(
        request,
        form,
        title=f"Take {item.asset_id} out of service",
        crumbs=_equipment_crumbs(item, "Take out of service"),
        submit="Take out of service",
        cancel_url=reverse("laboratory:equipment_detail", args=[item.pk]),
        intro="Use only when the equipment is unfit. Returning it needs a signed approval.",
    )


@login_required
def equipment_return(request, pk):
    require_role(request.user, "quality")
    item = get_object_or_404(equipment_queryset(), pk=pk)
    label, tone, _ = equipment_status(item)
    denial = ""
    if item.status_changed_by_id == request.user.pk:
        denial = "The person who removed equipment from service cannot return it."
    elif item.state != Equipment.State.OUT_OF_SERVICE:
        denial = "Equipment is already in service."
    uses, failures = scope = services.impact_scope(item)
    shown = list(ResourceUse.objects.filter(pk__in=uses[:IMPACT_SHOWN]).order_by("used_at", "pk"))
    resolved = work_labels([(u.context_type, u.context_id) for u in shown])
    affected = [
        (f"Affected use {number}", impact_summary(u, resolved))
        for number, u in enumerate(shown, start=1)
    ]
    if len(uses) > len(shown):
        affected.append(("More uses", f"{len(uses) - len(shown)} more, listed on the record"))
    form = ImpactSigningForm(
        request.POST or None,
        initial={
            "expected_revision": item.revision,
            "assessed": ImpactSigningForm.scope_token(scope),
        },
    )
    return sign_page(
        request,
        form,
        title=f"Return {item.asset_id} to service",
        identifier=item.asset_id,
        meaning="approved",
        meaning_text="You approve returning this equipment to service after assessing the "
        "impact on results produced since its last accepted passing calibration.",
        button="Sign and approve",
        facts=[
            ("Description", item.description),
            ("Current state", status(label, tone)),
            (
                "Impact scope",
                f"{len(failures)} failed calibration(s) and {len(uses)} use(s) to assess",
            ),
            *affected,
        ],
        revision=item.revision,
        cancel_url=reverse("laboratory:equipment_detail", args=[item.pk]),
        run=lambda d: services.return_to_service(
            actor=request.user,
            pin=d["pin"],
            equipment=item,
            expected_revision=d["expected_revision"],
            impact_assessment=d["reason"],
            assessed=d["assessed"],
        ),
        success="Equipment returned to service.",
        success_url=reverse("laboratory:equipment_detail", args=[item.pk]),
        denial=denial,
        crumbs=_equipment_crumbs(item, "Return to service"),
    )


# --- Calibration -----------------------------------------------------------------------------


@login_required
def calibration_list(request):
    access(request.user)
    form, data = make_filter(
        request,
        [("recorded", "Awaiting acceptance"), ("accepted", "Accepted"), ("fail", "Failed")],
    )
    queryset = Calibration.objects.select_related("equipment", "recorded_by")
    if data.get("q"):
        queryset = queryset.filter(equipment__asset_id__icontains=data["q"])
    if data.get("status") == "fail":
        queryset = queryset.filter(outcome="fail")
    elif data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {
            "performed": ["performed_at"],
            "equipment": ["equipment__asset_id"],
            "due": ["due_date"],
        },
        "-performed",
    )
    rows = [
        [
            cell(
                c.equipment.asset_id, reverse("laboratory:equipment_detail", args=[c.equipment_id])
            ),
            when(c.performed_at),
            day(c.due_date),
            status(c.get_outcome_display(), "success" if c.outcome == "pass" else "danger"),
            status(c.get_state_display(), "success" if c.state == "accepted" else "progress"),
            str(c.recorded_by),
            cell("Accept", reverse("laboratory:calibration_accept", args=[c.pk]))
            if c.state == "recorded"
            and c.recorded_by_id != request.user.pk
            and can(request.user, "reviewer")
            else "",
        ]
        for c in page
    ]
    return list_page(
        request,
        title="Calibrations",
        intro="Every recorded calibration. Passing records count only after independent "
        "acceptance; failures block use as soon as they are recorded.",
        noun="calibrations",
        columns=[
            ("Equipment", "equipment", False),
            ("Performed", "performed", False),
            ("Due (inclusive)", "due", False),
            ("Outcome", None, False),
            ("State", None, False),
            ("Recorded by", None, False),
            ("Action", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        empty_body="Record a calibration from an equipment page.",
    )


@login_required
def calibration_new(request, pk):
    require_role(request.user, *services.RECORDERS)
    item = get_object_or_404(Equipment, pk=pk)
    form = CalibrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.record_calibration(
                actor=request.user, equipment=item, **form.cleaned_data
            ),
        )
        if done:
            if done.outcome == "fail":
                messages.warning(
                    request,
                    "Failed calibration recorded; equipment is out of service pending "
                    "impact assessment.",
                )
            else:
                messages.success(request, "Calibration recorded; independent acceptance needed.")
            return redirect("laboratory:equipment_detail", pk=item.pk)
    return form_page(
        request,
        form,
        title=f"Record calibration · {item.asset_id}",
        crumbs=_equipment_crumbs(item, "Record calibration"),
        submit="Record calibration",
        cancel_url=reverse("laboratory:equipment_detail", args=[item.pk]),
        intro="A failed calibration removes the equipment from service immediately.",
    )


@login_required
def calibration_accept(request, pk):
    require_role(request.user, "reviewer")
    cal = get_object_or_404(Calibration.objects.select_related("equipment"), pk=pk)
    denial = ""
    if cal.recorded_by_id == request.user.pk:
        denial = "You recorded this calibration, so you cannot accept it."
    elif cal.state != Calibration.State.RECORDED:
        denial = "This calibration has already been accepted."
    form = SigningForm(request.POST or None, initial={"expected_revision": cal.revision})
    return sign_page(
        request,
        form,
        title=f"Accept calibration · {cal.equipment.asset_id}",
        identifier=f"{cal.equipment.asset_id} calibration {cal.pk}",
        meaning="reviewed",
        meaning_text="You reviewed the calibration evidence and accept the outcome shown.",
        button="Sign and review",
        facts=[
            ("Performed", when(cal.performed_at)),
            ("Due (inclusive)", day(cal.due_date)),
            ("Outcome", status(cal.get_outcome_display(), _tone(cal.outcome == "pass"))),
            ("Reference standard", cal.standard_ref),
            ("Tolerance note", cal.tolerance_note),
            ("Recorded by", str(cal.recorded_by)),
        ],
        revision=cal.revision,
        cancel_url=reverse("laboratory:equipment_detail", args=[cal.equipment_id]),
        run=lambda d: services.accept_calibration(
            actor=request.user,
            pin=d["pin"],
            calibration=cal,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Calibration accepted.",
        success_url=reverse("laboratory:equipment_detail", args=[cal.equipment_id]),
        denial=denial,
        crumbs=_equipment_crumbs(cal.equipment, "Accept calibration"),
    )


# --- Qualifications --------------------------------------------------------------------------

QUALIFICATION_STATUS = [
    ("recorded", "Awaiting approval"),
    ("scheduled", "Approved, starts later"),
    ("approved", "Approved and effective"),
    ("expiring", "Expiring within 30 days"),
    ("expired", "Expired"),
    ("revoked", "Revoked"),
]


@login_required
def qualification_list(request):
    access(request.user)
    today, soon = _soon()
    form, data = make_filter(request, QUALIFICATION_STATUS)
    queryset = Qualification.objects.select_related("user", "equipment")
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(activity__icontains=q)
            | Q(user__username__icontains=q)
            | Q(equipment__asset_id__icontains=q)
        )
    match data.get("status"):
        case "recorded" | "revoked" as state:
            queryset = queryset.filter(state=state)
        case "scheduled":
            queryset = queryset.filter(state="approved", valid_from__gt=today)
        case "approved":
            queryset = queryset.filter(
                state="approved", valid_from__lte=today, valid_until__gte=today
            )
        case "expiring":
            queryset = queryset.filter(
                state="approved",
                valid_from__lte=today,
                valid_until__gte=today,
                valid_until__lte=soon,
            )
        case "expired":
            queryset = queryset.filter(state="approved", valid_until__lt=today)
    page, sort, descending = paginate(
        request,
        queryset,
        {"recorded": ["recorded_at"], "until": ["valid_until"], "activity": ["activity"]},
        "-recorded",
    )
    rows = []
    for q in page:
        label, tone, _ = qualification_status(q, today)
        rows.append(
            [
                cell(
                    q.activity,
                    reverse("laboratory:qualification_detail", args=[q.pk]),
                ),
                str(q.subject),
                "Analyst" if q.user_id else "Equipment",
                day(q.valid_from),
                day(q.valid_until),
                status(label, tone),
            ]
        )
    return list_page(
        request,
        title="Qualifications",
        intro="Approved training and qualification evidence by activity or method. "
        "Group membership alone never qualifies anyone.",
        noun="qualifications",
        columns=[
            ("Activity", "activity", False),
            ("Subject", None, False),
            ("Type", None, False),
            ("Valid from", None, False),
            ("Valid until (inclusive)", "until", False),
            ("State", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "qualification", "href": reverse("laboratory:qualification_new")}
        if can(request.user, "analyst", "reviewer", "quality")
        else None,
        empty_body="Record controlled training evidence for an analyst and activity.",
    )


@login_required
def qualification_new(request, equipment_pk=None):
    require_role(request.user, "analyst", "reviewer", "quality")
    item = get_object_or_404(Equipment, pk=equipment_pk) if equipment_pk else None
    form = QualificationForm(request.POST or None, equipment=item)
    if request.method == "POST" and form.is_valid():
        values = dict(form.cleaned_data)
        done, _ = run_form(
            request,
            form,
            lambda: services.record_qualification(actor=request.user, equipment=item, **values),
        )
        if done:
            messages.success(request, "Qualification recorded; independent approval needed.")
            return redirect("laboratory:qualification_detail", pk=done.pk)
    base = [("Qualifications", reverse("laboratory:qualification_list"))]
    return form_page(
        request,
        form,
        title=f"Record qualification · {item.asset_id}" if item else "New qualification",
        crumbs=crumbs(*(base if not item else []), ("Record qualification", None))
        if not item
        else _equipment_crumbs(item, "Record qualification"),
        submit="Record qualification",
        cancel_url=reverse("laboratory:equipment_detail", args=[item.pk])
        if item
        else reverse("laboratory:qualification_list"),
        intro="Recording evidence does not qualify anyone. A different quality signer approves "
        "it; the person concerned can neither record nor approve their own.",
    )


@login_required
def qualification_detail(request, pk):
    access(request.user)
    q = get_object_or_404(Qualification.objects.select_related("user", "equipment"), pk=pk)
    today = timezone.localdate()
    state_label, state_tone, _ = qualification_status(q, today)
    user = request.user
    eligible_actor = user.pk not in (q.recorded_by_id, q.user_id)
    actions = [
        action("Approve", reverse("laboratory:qualification_approve", args=[q.pk]), True)
        if q.state == "recorded" and eligible_actor and can(user, "quality")
        else None,
        action("Revoke", reverse("laboratory:qualification_revoke", args=[q.pk]))
        if q.state == "approved" and q.user_id != user.pk and can(user, "quality")
        else None,
    ]
    return record_page(
        request,
        identifier=f"QUAL-{q.pk}",
        title=q.activity,
        crumbs=crumbs(
            ("Qualifications", reverse("laboratory:qualification_list")), (f"QUAL-{q.pk}", None)
        ),
        state=status(state_label, state_tone),
        facts=[
            ("Subject", str(q.subject)),
            ("Type", "Analyst" if q.user_id else "Equipment"),
            ("Valid from", day(q.valid_from)),
            ("Valid until (inclusive)", day(q.valid_until)),
            ("Evidence reference", q.evidence_ref),
            ("Evidence link", external_link(q.evidence_url)),
            ("Scope", q.scope_note),
            ("Recorded by", str(q.recorded_by)),
            ("Revision", q.revision),
        ],
        actions=actions,
        related=[q],
    )


def _qualification_sign(request, pk, *, approve):
    require_role(request.user, "quality")
    q = get_object_or_404(Qualification.objects.select_related("user", "equipment"), pk=pk)
    denial = ""
    if approve and request.user.pk in (q.recorded_by_id, q.user_id):
        denial = "The recorder and the qualified person cannot approve this qualification."
    elif not approve and q.user_id == request.user.pk:
        denial = "You cannot revoke your own qualification."
    elif q.state != ("recorded" if approve else "approved"):
        denial = f"This qualification is {q.get_state_display().lower()}."
    form = SigningForm(request.POST or None, initial={"expected_revision": q.revision})
    detail = reverse("laboratory:qualification_detail", args=[q.pk])
    service = services.approve_qualification if approve else services.revoke_qualification
    return sign_page(
        request,
        form,
        title=f"{'Approve' if approve else 'Revoke'} qualification",
        identifier=f"QUAL-{q.pk}",
        meaning="approved" if approve else "revoked",
        meaning_text=(
            "You approve this evidence as showing the subject is qualified for the activity "
            "between the stated dates."
            if approve
            else "You withdraw this qualification; work after the signature time is blocked."
        ),
        button="Sign and approve" if approve else "Sign and revoke",
        facts=[
            ("Subject", str(q.subject)),
            ("Activity", q.activity),
            ("Valid", f"{day(q.valid_from)} to {day(q.valid_until)}"),
            ("Evidence", q.evidence_ref),
        ],
        revision=q.revision,
        cancel_url=detail,
        run=lambda d: service(
            actor=request.user,
            pin=d["pin"],
            qualification=q,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Qualification approved." if approve else "Qualification revoked.",
        success_url=detail,
        denial=denial,
        crumbs=crumbs(
            ("Qualifications", reverse("laboratory:qualification_list")),
            (f"QUAL-{q.pk}", detail),
            ("Approve" if approve else "Revoke", None),
        ),
    )


@login_required
def qualification_approve(request, pk):
    return _qualification_sign(request, pk, approve=True)


@login_required
def qualification_revoke(request, pk):
    return _qualification_sign(request, pk, approve=False)


# --- Reagents and standards ------------------------------------------------------------------

REAGENT_STATUS = [
    ("received", "Awaiting release"),
    ("released", "Released for use"),
    ("expiring", "Expiring within 30 days"),
    ("expired", "Released but expired"),
    ("rejected", "Rejected"),
]


@login_required
def reagent_list(request):
    access(request.user)
    today, soon = _soon()
    form, data = make_filter(request, REAGENT_STATUS)
    queryset = ReagentLot.objects.all()
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(identifier__icontains=q) | Q(name__icontains=q) | Q(lot_number__icontains=q)
        )
    match data.get("status"):
        case "received" | "rejected" as state:
            queryset = queryset.filter(state=state)
        case "released":
            queryset = queryset.filter(state="released", expiry_date__gte=today)
        case "expiring":
            queryset = queryset.filter(
                state="released", expiry_date__gte=today, expiry_date__lte=soon
            )
        case "expired":
            queryset = queryset.filter(state="released", expiry_date__lt=today)
    page, sort, descending = paginate(
        request,
        queryset,
        {"identifier": ["identifier"], "name": ["name"], "expiry": ["expiry_date"]},
        "identifier",
    )
    rows = []
    for lot in page:
        label, tone = reagent_status(lot, today)
        rows.append(
            [
                cell(lot.identifier, reverse("laboratory:reagent_detail", args=[lot.pk])),
                lot.name,
                lot.get_kind_display(),
                lot.lot_number,
                day(lot.expiry_date),
                status(label, tone),
            ]
        )
    return list_page(
        request,
        title="Reagents and standards",
        intro="Reagent, reference-standard and prepared-solution lots with provenance, "
        "independent release and expiry gating.",
        noun="lots",
        columns=[
            ("Identifier", "identifier", False),
            ("Name", "name", False),
            ("Kind", None, False),
            ("Supplier lot", None, False),
            ("Expiry (last day of use)", "expiry", False),
            ("State", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "reagent lot", "href": reverse("laboratory:reagent_new")}
        if can(request.user, *services.RECORDERS)
        else None,
        empty_body="Record a received reagent or standard lot, or a prepared solution.",
    )


@login_required
def reagent_new(request):
    require_role(request.user, *services.RECORDERS)
    form = ReagentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lot, _ = run_form(
            request,
            form,
            lambda: services.receive_reagent(actor=request.user, **form.cleaned_data),
        )
        if lot:
            messages.success(request, "Lot recorded; independent release needed before use.")
            return redirect("laboratory:reagent_detail", pk=lot.pk)
    return form_page(
        request,
        form,
        title="New reagent lot",
        crumbs=crumbs(
            ("Reagents and standards", reverse("laboratory:reagent_list")),
            ("New reagent lot", None),
        ),
        submit="Record lot",
        cancel_url=reverse("laboratory:reagent_list"),
        intro="A lot cannot be used until a different reviewer signs its release. A prepared "
        "solution needs a released source lot and cannot outlive it.",
    )


@login_required
def reagent_detail(request, pk):
    access(request.user)
    lot = get_object_or_404(ReagentLot.objects.select_related("parent"), pk=pk)
    today = timezone.localdate()
    label, tone = reagent_status(lot, today)
    user = request.user
    lot_uses = list(lot.uses.select_related("used_by")[:25])
    lot_work = work_labels([(u.context_type, u.context_id) for u in lot_uses])
    actions = [
        action("Release for use", reverse("laboratory:reagent_release", args=[lot.pk]), True)
        if lot.state == "received" and lot.recorded_by_id != user.pk and can(user, "reviewer")
        else None,
        action("Reject lot", reverse("laboratory:reagent_reject", args=[lot.pk]))
        if lot.state != "rejected" and can(user, "analyst", "reviewer", "quality")
        else None,
    ]
    purity = (
        f"{lot.assigned_purity.normalize():f} {lot.purity_unit}"
        if lot.assigned_purity is not None
        else ""
    )
    return record_page(
        request,
        identifier=lot.identifier,
        title=lot.name,
        crumbs=crumbs(
            ("Reagents and standards", reverse("laboratory:reagent_list")), (lot.identifier, None)
        ),
        state=status(label, tone),
        facts=[
            ("Kind", lot.get_kind_display()),
            ("Supplier", lot.supplier),
            ("Supplier lot", lot.lot_number),
            ("Received or prepared", day(lot.received_on)),
            ("Expiry (last day of use)", day(lot.expiry_date)),
            ("Assigned purity", purity),
            (
                "Source lot",
                cell(
                    lot.parent.identifier,
                    reverse("laboratory:reagent_detail", args=[lot.parent_id]),
                )
                if lot.parent_id
                else "",
            ),
            ("Preparation", lot.preparation_note),
            (
                "Certificate",
                external_link(lot.certificate_url, lot.certificate_ref or None)
                if lot.certificate_url
                else lot.certificate_ref,
            ),
            ("Recorded by", str(lot.recorded_by)),
            ("Released", when(lot.released_at)),
            ("Revision", lot.revision),
        ],
        actions=actions,
        sections=[
            section(
                "Preparations from this lot",
                [("Identifier", False), ("Name", False), ("State", False)],
                [
                    [
                        cell(p.identifier, reverse("laboratory:reagent_detail", args=[p.pk])),
                        p.name,
                        p.get_state_display(),
                    ]
                    for p in lot.preparations.all()
                ],
                "No prepared solutions record this lot as their source.",
            ),
            section(
                "Uses",
                [("Used", False), ("Work", False), ("Activity", False), ("By", False)],
                [
                    [when(u.used_at), work_cell(u, lot_work), u.activity, str(u.used_by)]
                    for u in lot_uses
                ],
                "No use recorded.",
            ),
        ],
        related=[lot],
        notice={
            "tone": "danger",
            "label": "Rejected",
            "text": "This lot cannot be used; prepared solutions from it are also blocked.",
        }
        if lot.state == "rejected"
        else None,
    )


@login_required
def reagent_release(request, pk):
    require_role(request.user, "reviewer")
    lot = get_object_or_404(ReagentLot, pk=pk)
    denial = ""
    if lot.recorded_by_id == request.user.pk:
        denial = "You recorded this lot, so you cannot release it."
    elif lot.state != ReagentLot.State.RECEIVED:
        denial = "This lot is not awaiting release."
    form = SigningForm(request.POST or None, initial={"expected_revision": lot.revision})
    detail = reverse("laboratory:reagent_detail", args=[lot.pk])
    return sign_page(
        request,
        form,
        title=f"Release {lot.identifier} for use",
        identifier=lot.identifier,
        meaning="reviewed",
        meaning_text="You reviewed the provenance, certificate and expiry and release this lot.",
        button="Sign and review",
        facts=[
            ("Name", lot.name),
            ("Supplier lot", lot.lot_number),
            ("Expiry (last day of use)", day(lot.expiry_date)),
            ("Certificate", lot.certificate_ref),
            ("Recorded by", str(lot.recorded_by)),
        ],
        revision=lot.revision,
        cancel_url=detail,
        run=lambda d: services.release_reagent(
            actor=request.user,
            pin=d["pin"],
            reagent=lot,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Lot released for use.",
        success_url=detail,
        denial=denial,
        crumbs=crumbs(
            ("Reagents and standards", reverse("laboratory:reagent_list")),
            (lot.identifier, detail),
            ("Release", None),
        ),
    )


@login_required
def reagent_reject(request, pk):
    require_role(request.user, "analyst", "reviewer", "quality")
    lot = get_object_or_404(ReagentLot, pk=pk)
    form = ReasonForm(request.POST or None)
    detail = reverse("laboratory:reagent_detail", args=[lot.pk])
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.reject_reagent(
                actor=request.user, reagent=lot, reason=form.cleaned_data["reason"]
            ),
        )
        if done:
            messages.success(request, "Lot rejected.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Reject {lot.identifier}",
        crumbs=crumbs(
            ("Reagents and standards", reverse("laboratory:reagent_list")),
            (lot.identifier, detail),
            ("Reject", None),
        ),
        submit="Reject lot",
        cancel_url=detail,
        intro="Rejection is permanent and blocks the lot and any solution prepared from it.",
    )


# --- Use -------------------------------------------------------------------------------------


@login_required
def use_list(request):
    access(request.user)
    form, data = make_filter(request)
    queryset = ResourceUse.objects.select_related("equipment", "reagent_lot", "used_by")
    if data.get("q"):
        q = data["q"]
        # Visible sample references are searchable for every context that displays one, using
        # subqueries over all matching records (no capped ID lists).
        by_sample = Sample.objects.filter(reference__icontains=q).annotate(
            key=Cast("pk", CharField())
        )
        match = (
            Q(context_type="quality.sample", context_id__in=by_sample.values("key"))
            | Q(context_id__icontains=q)
            | Q(activity__icontains=q)
            | Q(test_code__icontains=q)
            | Q(equipment__asset_id__icontains=q)
            | Q(reagent_lot__identifier__icontains=q)
        )
        if apps.is_installed("analytical"):
            tests = apps.get_model("analytical", "AnalyticalTest").objects
            by_test = tests.filter(
                Q(sample__reference__icontains=q) | Q(lot__number__icontains=q)
            ).annotate(key=Cast("pk", CharField()))
            match |= Q(
                context_type="analytical.analyticaltest", context_id__in=by_test.values("key")
            )
            batches = apps.get_model("analytical", "QCBatch").objects
            by_batch = batches.filter(number__icontains=q).annotate(key=Cast("pk", CharField()))
            match |= Q(context_type="analytical.qcbatch", context_id__in=by_batch.values("key"))
        by_lot = Sample.objects.filter(lot__number__icontains=q).annotate(
            key=Cast("pk", CharField())
        )
        match |= Q(context_type="quality.sample", context_id__in=by_lot.values("key"))
        queryset = queryset.filter(match)
    page, sort, descending = paginate(request, queryset, {"used": ["used_at"]}, "-used")
    work = work_labels([(u.context_type, u.context_id) for u in page])
    rows = []
    for u in page:
        if u.equipment_id:
            resource = cell(
                u.equipment.asset_id, reverse("laboratory:equipment_detail", args=[u.equipment_id])
            )
        else:
            resource = cell(
                u.reagent_lot.identifier,
                reverse("laboratory:reagent_detail", args=[u.reagent_lot_id]),
            )
        rows.append(
            [
                when(u.used_at),
                resource,
                work_cell(u, work),
                u.activity,
                u.test_code,
                str(u.used_by),
            ]
        )
    return list_page(
        request,
        title="Resource use",
        intro="Append-only record of the eligible equipment and reagents used for work.",
        noun="uses",
        columns=[
            ("Used", "used", False),
            ("Resource", None, False),
            ("Work", None, False),
            ("Activity", None, False),
            ("Test", None, False),
            ("By", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "use", "href": reverse("laboratory:use_new")}
        if can(request.user, "analyst")
        else None,
        empty_body="Record the equipment and reagents used for a sample before testing.",
    )


@login_required
def use_new(request):
    require_role(request.user, "analyst")
    form = UseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            done = services.authorize_use(
                actor=request.user,
                context_type="quality.sample",
                context_id=form.sample.pk,
                activity=data["activity"],
                test_code=data["test_code"],
                profile_ref=data["profile_ref"],
                equipment=list(data["equipment"]),
                reagents=list(data["reagents"]),
                reason=data["reason"],
            )
        except UseBlocked as exc:
            form.add_error(None, "Work is blocked: " + " ".join(exc.messages))
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, f"Recorded {len(done)} eligible resource use(s).")
            return redirect("laboratory:use_list")
    return form_page(
        request,
        form,
        title="New use",
        crumbs=crumbs(("Resource use", reverse("laboratory:use_list")), ("New use", None)),
        submit="Record use",
        cancel_url=reverse("laboratory:use_list"),
        intro="Every resource and your own qualification for the activity must be eligible now. "
        "Refusals are audited.",
    )
