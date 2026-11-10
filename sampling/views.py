from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog import services as catalog_services
from catalog.models import Material, RevisionStatus
from catalog.services import AUTHOR_ROLE
from catalog.web import (
    approve_page,
    can,
    form_status,
    history,
    page,
    read_access,
    run,
    signatures,
    sorted_by,
    withdraw_page,
)
from core.services import require_role
from quality.models import Lot

from . import services
from .forms import (
    AssignForm,
    CorrectionForm,
    DeviationForm,
    PlanForm,
    PlanRevisionForm,
    SamplingForm,
)
from .models import (
    AssignmentStatus,
    DeviationReview,
    LotAssignment,
    SamplingPlan,
    SamplingPlanRevision,
    SamplingRecord,
)

SECTION = "Sampling"
STATUS_FILTERS = [
    ("ready", "Requirements assigned"),
    ("hold", "Applicability hold"),
    ("none", "Not assigned"),
]


def tabs(current):
    items = [("Lots", reverse("sampling:lots")), ("Sampling plans", reverse("sampling:plans"))]
    return [{"label": label, "url": url, "current": label == current} for label, url in items]


def crumbs_for(*trail):
    return [(SECTION, reverse("sampling:lots")), *trail]


def form_page(request, form, *, title, crumbs, cancel_url, submit_label, intro="", facts=None):
    return render(
        request,
        "catalog/form.html",
        {
            "page_title": title,
            "form": form,
            "crumbs": crumbs,
            "cancel_url": cancel_url,
            "submit_label": submit_label,
            "intro": intro,
            "facts": facts or [],
        },
        status=form_status(request, form),
    )


# Lots ------------------------------------------------------------------------------------------


@login_required
def lot_list(request):
    read_access(request)
    latest = LotAssignment.objects.filter(lot=OuterRef("pk")).order_by("-assigned_at", "-id")
    lots = Lot.objects.annotate(
        requirement_status=Subquery(latest.values("status")[:1]),
        sampled=Count("sampling_records", filter=Q(sampling_records__corrects__isnull=True)),
    )
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        lots = lots.filter(Q(number__icontains=query) | Q(material__icontains=query))
    if status == "none":
        lots = lots.filter(requirement_status__isnull=True)
    elif status in AssignmentStatus.values:
        lots = lots.filter(requirement_status=status)
    else:
        status = ""
    lots, sort = sorted_by(
        request,
        lots,
        {"number": ["number"], "-number": ["-number"], "received": ["-created_at", "-pk"]},
        "received",
    )
    return render(
        request,
        "sampling/lot_list.html",
        {
            "page_title": SECTION,
            "tabs": tabs("Lots"),
            "page_obj": page(request, lots),
            "query": query,
            "status": status,
            "statuses": STATUS_FILTERS,
            "sort": sort,
            "filtered": bool(query or status),
        },
    )


@login_required
def lot_detail(request, pk):
    read_access(request)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    assignments = list(
        LotAssignment.objects.filter(lot=lot)
        .select_related("material", "assigned_by", "specification_revision", "plan_revision")
        .order_by("-assigned_at", "-id")
    )
    current = assignments[0] if assignments else None
    records = list(
        SamplingRecord.objects.filter(lot=lot)
        .select_related(
            "sample",
            "sampled_by",
            "recorded_by",
            "plan_revision__plan",
            "resample_of",
            "deviation_review__decided_by",
        )
        .order_by("recorded_at", "id")
    )
    corrected = {r.corrects_id for r in records if r.corrects_id}
    is_quality = can(request.user, AUTHOR_ROLE)
    for record in records:
        record.superseded = record.pk in corrected
        record.review = getattr(record, "deviation_review", None)
        record.can_assess = (
            is_quality
            and lot.state == "quarantine"
            and not record.superseded
            and record.review is not None
            and record.review.status == "pending"
            and request.user.pk not in {record.sampled_by_id, record.recorded_by_id}
        )
    is_analyst = can(request.user, "analyst")
    testing = services.testing_started(lot)
    return render(
        request,
        "sampling/lot_detail.html",
        {
            "page_title": f"{lot.number} · requirements and sampling",
            "lot": lot,
            "current": current,
            "assignments": assignments,
            "records": records,
            "history": history(*assignments, *records, *[r.review for r in records if r.review]),
            "blockers": services.lot_blockers(lot),
            "crumbs": crumbs_for((lot.number, None)),
            "open": lot.state == "quarantine",
            "testing_started": testing,
            "can_assign": lot.state == "quarantine"
            and not testing
            and can(request.user, "analyst", "quality"),
            "can_sample": lot.state == "quarantine"
            and is_analyst
            and current is not None
            and current.status == AssignmentStatus.READY,
            "is_analyst": is_analyst,
        },
    )


def _guess_material(lot):
    return Material.objects.filter(
        Q(name__iexact=lot.material) | Q(code__iexact=lot.material)
    ).first()


@login_required
@require_http_methods(["GET", "POST"])
def assign(request, pk):
    require_role(request.user, "analyst", "quality")
    lot = get_object_or_404(Lot, pk=pk)
    back = reverse("sampling:lot", args=[lot.pk])
    if lot.state != "quarantine":
        messages.error(request, "Only quarantined lots can receive requirements.")
        return redirect(back)
    if services.testing_started(lot):
        messages.error(request, services.REASSIGNMENT_REFUSED)
        return redirect(back)
    current = services.current_assignment(lot)
    initial = {"scope": "general"}
    if current:
        initial.update(material=current.material, stage=current.stage, scope=current.scope)
    else:
        initial["material"] = _guess_material(lot)
    form = AssignForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        assignment = run(
            form,
            lambda: services.assign_requirements(actor=request.user, lot=lot, **form.cleaned_data),
        )
        if assignment:
            if assignment.status == AssignmentStatus.READY:
                messages.success(request, "Approved requirements frozen for this lot.")
            else:
                messages.warning(
                    request, "Applicability hold recorded: " + " ".join(assignment.hold_reasons)
                )
            return redirect(back)
    return form_page(
        request,
        form,
        title=f"Assign requirements · {lot.number}",
        crumbs=crumbs_for((lot.number, back), ("Assign requirements", None)),
        cancel_url=back,
        submit_label="Assign requirements",
        intro="The approved specification, its methods and the sampling plan effective now are "
        "frozen for this lot. If anything is missing or not approved, the lot is placed on an "
        "applicability hold with the reasons; nothing is guessed or merged.",
        facts=[
            ("Lot", lot.number),
            ("Material as received", lot.material),
            ("Rule set", str(lot.rules)),
            ("Current requirements", current.get_status_display() if current else "None"),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def sampling_new(request, pk):
    require_role(request.user, "analyst")
    lot = get_object_or_404(Lot, pk=pk)
    back = reverse("sampling:lot", args=[lot.pk])
    current = services.current_assignment(lot)
    if current is None or current.status != AssignmentStatus.READY:
        messages.error(request, "Assign approved requirements before recording sampling.")
        return redirect(back)
    plan = current.plan_revision
    form = SamplingForm(
        request.POST or None, lot=lot, initial={"quantity_unit": plan.quantity_unit}
    )
    if request.method == "POST" and form.is_valid():
        record = run(
            form,
            lambda: services.record_sampling(actor=request.user, lot=lot, **form.cleaned_data),
        )
        if record:
            messages.success(request, f"Sample {record.sample.reference} recorded.")
            return redirect(back)
    return form_page(
        request,
        form,
        title=f"Record sampling · {lot.number}",
        crumbs=crumbs_for((lot.number, back), ("Record sampling", None)),
        cancel_url=back,
        submit_label="Record sampling",
        intro="Record what was actually sampled. You are recorded as the sampler.",
        facts=[
            ("Sampling plan", f"{plan} · {plan.get_basis_display()}"),
            ("Minimum amount", f"{plan.minimum_quantity.normalize():f} {plan.quantity_unit}"),
            ("Instructions", plan.instructions),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def sampling_correct(request, pk):
    require_role(request.user, "analyst")
    record = get_object_or_404(SamplingRecord.objects.select_related("lot", "sample"), pk=pk)
    back = reverse("sampling:lot", args=[record.lot_id])
    if record.lot.state != "quarantine" or SamplingRecord.objects.filter(corrects=record).exists():
        messages.error(
            request, "Only the latest sampling record of a quarantined lot can be corrected."
        )
        return redirect(back)
    fields = [
        "sampled_at",
        "location",
        "containers_total",
        "containers_sampled",
        "container_ids",
        "quantity",
        "quantity_unit",
        "deviation",
    ]
    form = CorrectionForm(
        request.POST or None, initial={name: getattr(record, name) for name in fields}
    )
    if request.method == "POST" and form.is_valid():
        correction = run(
            form,
            lambda: services.correct_sampling(
                actor=request.user, record=record, **form.cleaned_data
            ),
        )
        if correction:
            messages.success(request, "Correction recorded; the original record is preserved.")
            return redirect(back)
    return form_page(
        request,
        form,
        title=f"Correct sampling · {record.sample.reference}",
        crumbs=crumbs_for((record.lot.number, back), (f"Correct {record.sample.reference}", None)),
        cancel_url=back,
        submit_label="Record correction",
        intro="A correction adds a linked record. The original stays visible in the history.",
        facts=[
            ("Sample", record.sample.reference),
            ("Sampled by", record.sampled_by.get_full_name() or record.sampled_by.username),
            ("Original containers", record.container_ids),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def deviation_assess(request, pk):
    require_role(request.user, AUTHOR_ROLE)
    record = get_object_or_404(
        SamplingRecord.objects.select_related("lot", "sample", "sampled_by", "plan_revision"),
        pk=pk,
    )
    back = reverse("sampling:lot", args=[record.lot_id])
    review = DeviationReview.objects.filter(record=record).first()
    if review is None or review.status != "pending":
        messages.error(request, "This record has no deviation awaiting assessment.")
        return redirect(back)
    blocked = ""
    if request.user.pk in {record.sampled_by_id, record.recorded_by_id}:
        blocked = "You sampled or recorded this sample; another person must assess."
    form = DeviationForm(request.POST or None, initial={"expected_revision": review.revision})
    if request.method == "POST" and not blocked and form.is_valid():
        data = form.cleaned_data
        done = run(
            form,
            lambda: services.assess_deviation(
                actor=request.user,
                pin=data["pin"],
                review=review,
                expected_revision=data["expected_revision"],
                accept=data["decision"] == "accept",
                reason=data["reason"],
            ),
        )
        if done:
            messages.success(request, f"Deviation for {record.sample.reference} {done.status}.")
            return redirect(back)
    return render(
        request,
        "sampling/deviation_assess.html",
        {
            "page_title": f"Assess sampling deviation · {record.sample.reference}",
            "record": record,
            "review": review,
            "form": form,
            "blocked": blocked,
            "cancel_url": back,
            "crumbs": crumbs_for(
                (record.lot.number, back), (f"Assess deviation {record.sample.reference}", None)
            ),
        },
        status=403 if blocked else form_status(request, form),
    )


# Plans -----------------------------------------------------------------------------------------


@login_required
def plan_list(request):
    read_access(request)
    plans = SamplingPlan.objects.select_related("material").annotate(
        versions=Count("revisions"),
        approved=Count("revisions", filter=Q(revisions__status="approved")),
        drafts=Count("revisions", filter=Q(revisions__status="draft")),
    )
    query = request.GET.get("q", "").strip()
    if query:
        plans = plans.filter(
            Q(code__icontains=query)
            | Q(title__icontains=query)
            | Q(material__code__icontains=query)
        )
    plans, sort = sorted_by(request, plans, {"code": ["code"], "-code": ["-code"]}, "code")
    return render(
        request,
        "sampling/plan_list.html",
        {
            "page_title": SECTION,
            "tabs": tabs("Sampling plans"),
            "page_obj": page(request, plans),
            "query": query,
            "sort": sort,
            "filtered": bool(query),
            "can_edit": can(request.user, AUTHOR_ROLE),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def plan_new(request):
    require_role(request.user, AUTHOR_ROLE)
    form = PlanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        created = run(form, lambda: services.create_plan(actor=request.user, **form.cleaned_data))
        if created:
            messages.success(request, "Sampling plan created with draft version 1.")
            return redirect("sampling:plan", pk=created[0].pk)
    return form_page(
        request,
        form,
        title="New sampling plan",
        crumbs=crumbs_for(
            ("Sampling plans", reverse("sampling:plans")), ("New sampling plan", None)
        ),
        cancel_url=reverse("sampling:plans"),
        submit_label="Create draft",
        intro="One plan covers one material at one stage. Another quality approver signs each "
        "version before lots can be sampled against it.",
    )


@login_required
def plan_detail(request, pk):
    read_access(request)
    plan = get_object_or_404(SamplingPlan.objects.select_related("material"), pk=pk)
    revisions = list(plan.revisions.select_related("author"))
    sigs = list(signatures(*revisions))
    can_edit = can(request.user, AUTHOR_ROLE)
    for revision in revisions:
        revision.signature_list = [s for s in sigs if s.object_id == str(revision.pk)]
        revision.can_approve = False
        if can_edit and revision.status == RevisionStatus.DRAFT:
            try:
                catalog_services.ensure_independent(request.user, revision)
                revision.can_approve = True
            except PermissionDenied:
                pass
    return render(
        request,
        "sampling/plan_detail.html",
        {
            "page_title": plan.code,
            "plan": plan,
            "revisions": revisions,
            "history": history(plan, *revisions),
            "crumbs": crumbs_for(("Sampling plans", reverse("sampling:plans")), (plan.code, None)),
            "can_edit": can_edit,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def plan_version_new(request, pk):
    require_role(request.user, AUTHOR_ROLE)
    plan = get_object_or_404(SamplingPlan, pk=pk)
    form = PlanRevisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        revision = run(
            form,
            lambda: services.new_plan_revision(actor=request.user, plan=plan, **form.cleaned_data),
        )
        if revision:
            messages.success(request, f"Draft {revision} created.")
            return redirect("sampling:plan", pk=plan.pk)
    detail = reverse("sampling:plan", args=[plan.pk])
    return form_page(
        request,
        form,
        title=f"New version of {plan.code}",
        crumbs=crumbs_for(
            ("Sampling plans", reverse("sampling:plans")),
            (plan.code, detail),
            ("New version", None),
        ),
        cancel_url=detail,
        submit_label="Create draft version",
    )


def _plan_crumbs(revision, action):
    detail = reverse("sampling:plan", args=[revision.plan_id])
    return detail, crumbs_for(
        ("Sampling plans", reverse("sampling:plans")),
        (revision.plan.code, detail),
        (f"Version {revision.version} · {action}", None),
    )


@login_required
@require_http_methods(["GET", "POST"])
def plan_approve(request, pk):
    revision = get_object_or_404(
        SamplingPlanRevision.objects.select_related("plan__material", "author"), pk=pk
    )
    detail, crumbs = _plan_crumbs(revision, "Approve")
    return approve_page(
        request,
        revision,
        kind="Sampling plan",
        crumbs=crumbs,
        success_url=detail,
        detail_template="sampling/includes/plan_content.html",
    )


@login_required
@require_http_methods(["GET", "POST"])
def plan_withdraw(request, pk):
    revision = get_object_or_404(SamplingPlanRevision.objects.select_related("plan"), pk=pk)
    detail, crumbs = _plan_crumbs(revision, "Withdraw")
    return withdraw_page(request, revision, kind="Sampling plan", crumbs=crumbs, success_url=detail)
