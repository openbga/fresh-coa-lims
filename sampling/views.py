from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.models import Material
from catalog.services import AUTHOR_ROLE
from catalog.web import (
    approval_offer,
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
from core.grids import Column
from core.models import ElectronicSignature
from core.services import require_role
from quality.models import Lot

from . import services
from .forms import (
    AssignForm,
    CorrectionForm,
    DecisionForm,
    DeviationForm,
    PlanForm,
    PlanRevisionForm,
    ReplacementForm,
    SamplingForm,
    chosen_scopes,
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


class LotFilterForm(forms.Form):
    """The sampling lot list's requirements filter; the search box is the toolbar's own (q)."""

    status = forms.ChoiceField(
        label="Status",
        choices=[
            ("", "All statuses"),
            ("ready", "Requirements assigned"),
            ("hold", "Applicability hold"),
            ("none", "Not assigned"),
            ("deviation", "Awaiting quality assessment"),
        ],
        required=False,
    )


def deviation_to_assess():
    """Lots in Quarantine with a current sampling record (not corrected since) whose deviation
    still awaits the independent quality assessment: the condition sampling.services.lot_blockers
    reports. The list's "Awaiting quality assessment" filter and the dashboard queue are this
    queryset."""
    awaiting = (
        SamplingRecord.objects.filter(lot=OuterRef("pk"))
        .exclude(deviation="")
        .exclude(Exists(SamplingRecord.objects.filter(corrects=OuterRef("pk"))))
        .filter(Q(deviation_review__isnull=True) | Q(deviation_review__status="pending"))
    )
    return Lot.objects.filter(state="quarantine").filter(Exists(awaiting))


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


def with_choices(conflicts, form_id=""):
    """Give each conflict ``options``: its statements paired with the radio inputs of the field
    ``choice-<test code>``, rendered through the shared radio widget and checked for the scope
    already chosen. ``forms.chosen_scopes`` reads the submitted choices back; ``form_id`` names
    the form the inputs belong to when they sit outside it."""
    form = forms.Form(auto_id="%s")
    attrs = {"form": form_id} if form_id else {}
    for conflict in conflicts:
        name = f"choice-{conflict['code']}"
        chosen = conflict.get("chosen")
        form.fields[name] = forms.ChoiceField(
            choices=[(item["scope"], item["scope"]) for item in conflict["candidates"]],
            widget=forms.RadioSelect(attrs=attrs),
            required=False,
            initial=next(
                (i["scope"] for i in conflict["candidates"] if chosen and chosen in i["scopes"]),
                None,
            ),
        )
        conflict["options"] = list(zip(form[name], conflict["candidates"], strict=True))
    return conflicts


LOT_COLUMNS = (
    Column("lot", "Lot", asc="number", desc="-number", locked=True),
    Column("material", "Material as received"),
    Column("lot_status", "Lot status"),
    Column("requirements", "Requirements"),
    Column("samples", "Samples", css="text-end", priority="low"),
)


@login_required
def lot_list(request):
    read_access(request)
    latest = LotAssignment.objects.filter(lot=OuterRef("pk")).order_by("-assigned_at", "-id")
    # A current sampling record (not corrected since) with a deviation still awaiting the
    # independent quality assessment: the same condition sampling.services.lot_blockers reports.
    awaiting = (
        SamplingRecord.objects.filter(lot=OuterRef("pk"))
        .exclude(deviation="")
        .exclude(Exists(SamplingRecord.objects.filter(corrects=OuterRef("pk"))))
        .filter(Q(deviation_review__isnull=True) | Q(deviation_review__status="pending"))
    )
    lots = Lot.objects.annotate(
        requirement_status=Subquery(latest.values("status")[:1]),
        sampled=Count("sampling_records", filter=Q(sampling_records__corrects__isnull=True)),
        deviation_pending=Exists(awaiting),
    )
    query = request.GET.get("q", "").strip()
    filters = LotFilterForm(request.GET)
    if not filters.is_valid():  # an unknown status lists every lot
        filters = LotFilterForm()
    status = filters.cleaned_data["status"] if filters.is_bound else ""
    if query:
        lots = lots.filter(Q(number__icontains=query) | Q(material__icontains=query))
    if status == "none":
        lots = lots.filter(requirement_status__isnull=True)
    elif status == "deviation":
        lots = lots.filter(pk__in=deviation_to_assess().values("pk"))
    elif status:
        lots = lots.filter(requirement_status=status)
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
            "columns": LOT_COLUMNS,
            "page_obj": page(request, lots),
            "query": query,
            "filters": filters,
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
    by_pk = {r.pk: r for r in records}
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
            and request.user.pk not in services.record_author_ids(record, by_pk)
        )
    is_analyst = can(request.user, "analyst")
    testing = services.testing_started(lot)
    # Each replacement and each decided conflict names the lot revision its signature is
    # bound to.
    signed = {
        (s.meaning, s.revision): s
        for s in ElectronicSignature.objects.filter(
            object_type="quality.lot",
            object_id=str(lot.pk),
            meaning__in=[services.REPLACED_MEANING, services.DECIDED_MEANING],
        )
    }
    for assignment in assignments:
        assignment.signature = None
        if assignment.is_replacement:
            key = (services.REPLACED_MEANING, assignment.replacement.get("lot_revision"))
            assignment.signature = signed.get(key)
        elif assignment.is_decision:
            key = (services.DECIDED_MEANING, assignment.decision.get("lot_revision"))
            assignment.signature = signed.get(key)
    # A hold may be one that quality settles with a signature: specifications that apply
    # state a test differently.
    decision = None
    if current is not None and current.status == AssignmentStatus.HOLD:
        decision = services.decision_preview(lot)
        if decision.blocker:
            decision = None
    # Once testing has started, say when the versions in force are no longer the frozen ones:
    # the lot keeps its own until quality replaces them.
    newer = services.newer_versions(lot)
    # A replacement is offered only when signing it would be accepted: the versions in force
    # apply to the lot (newer.reasons is shown in the notice otherwise) and this person made
    # none of the lot's records (services.replacement_denial; shown in the header instead).
    replace_denied = services.replacement_denial(request.user, lot) if is_quality else ""
    replaceable = newer is not None and not newer.get("reasons")
    return render(
        request,
        "sampling/lot_detail.html",
        {
            "page_title": f"{lot.number} · requirements and sampling",
            "lot": lot,
            "current": current,
            "assignments": assignments,
            "newer": newer,
            "can_replace": is_quality and replaceable and not replace_denied,
            "replace_note": replace_denied if replaceable else "",
            "decision": decision,
            # Offered to quality people who recorded none of the lot's data; the others read
            # the conflict and who decides it.
            "can_decide": is_quality
            and decision is not None
            and not decision.reasons
            and not services.decision_denial(request.user, lot),
            # In testing, a chosen requirement is changed only by a signed replacement, also
            # when no version has changed since.
            "can_revisit": is_quality
            and not replace_denied
            and newer is None
            and testing
            and lot.state == "quarantine"
            and current is not None
            and current.status == AssignmentStatus.READY
            and bool(current.payload.get("decisions")),
            "rule_problems": services.additional_rule_problems(lot)
            if lot.state == "quarantine"
            else [],
            "records": records,
            "history": history(*assignments, *records, *[r.review for r in records if r.review]),
            "blockers": services.lot_blockers(lot),
            "crumbs": crumbs_for((lot.number, None)),
            "open": lot.state == "quarantine",
            "testing_started": testing,
            "can_assign": services.assignment_blocker(lot) is None
            and can(request.user, "analyst", "quality")
            and not services.reassignment_denial(request.user, lot, current),
            "can_sample": is_analyst and services.sampling_blocker(lot) is None,
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
    if blocker := services.assignment_blocker(lot):
        messages.error(request, blocker)
        return redirect(back)
    current = services.current_assignment(lot)
    if denial := services.reassignment_denial(request.user, lot, current):
        messages.error(request, denial)
        return redirect(back)
    initial = {"scopes": "general"}
    if current:
        initial.update(
            material=current.material, stage=current.stage, scopes=", ".join(current.scope_list)
        )
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
    configured = services.configured_scopes()
    return form_page(
        request,
        form,
        title=f"Assign requirements · {lot.number}",
        crumbs=crumbs_for((lot.number, back), ("Assign requirements", None)),
        cancel_url=back,
        submit_label="Assign requirements",
        intro="The approved specification of every scope named, its methods and the sampling "
        "plan effective now are frozen for this lot, with the rule sets in force that name "
        "its material, stage or scopes. If anything is missing or not approved, or the "
        "specifications state a test differently, the lot is placed on an applicability hold "
        "with the reasons; nothing is guessed, merged or picked.",
        facts=[
            ("Lot", lot.number),
            ("Material as received", lot.material),
            ("Rule set", str(lot.rules)),
            ("Current requirements", current.get_status_display() if current else "None"),
            ("Scopes in the configuration", ", ".join(configured) if configured else "None"),
        ],
    )


def _reissue(form, lot, basis):
    """After a refused signature the page shows the record as it is now, so the form carries
    the token and the revision of what is shown, not those of the page that was refused. The
    signer reviews what is shown and enters the PIN again."""
    form.data = form.data.copy()
    form.data["basis"] = basis
    form.data["expected_revision"] = str(lot.revision)


@login_required
@require_http_methods(["GET", "POST"])
def decide(request, pk):
    """Signed decision of which requirement applies where the specifications that apply to a
    lot state a test differently, before testing has started."""
    require_role(request.user, AUTHOR_ROLE)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    back = reverse("sampling:lot", args=[lot.pk])
    preview = services.decision_preview(lot)
    if preview.blocker:
        messages.error(request, preview.blocker)
        return redirect(back)
    blocked = services.decision_denial(request.user, lot)
    choices = chosen_scopes(request.POST)
    form = DecisionForm(
        request.POST or None,
        initial={"expected_revision": lot.revision, "basis": preview.basis},
    )
    if request.method == "POST" and not blocked and preview.possible and form.is_valid():
        data = form.cleaned_data
        done = run(
            form,
            lambda: services.decide_conflicts(
                actor=request.user,
                pin=data["pin"],
                lot=lot,
                expected_revision=data["expected_revision"],
                reason=data["reason"],
                choices=choices,
                basis=data["basis"],
            ),
        )
        if done:
            messages.success(request, "Decision signed. The requirements are frozen for this lot.")
            return redirect(back)
    if request.method == "POST":
        if services.DECISION_STALE in form.non_field_errors():
            # What applies changed: the page shows it as it is now and asks for the choice
            # again, because a statement chosen before may be the one that changed.
            preview, choices = services.decision_preview(lot), {}
            if preview.blocker:
                messages.error(request, preview.blocker)
                return redirect(back)
        _reissue(form, lot, preview.basis)
    for conflict in preview.conflicts:
        conflict["chosen"] = choices.get(conflict["code"], "")
    with_choices(preview.conflicts, form_id="decision-form")
    return render(
        request,
        "sampling/decide.html",
        {
            "page_title": f"Decide conflicting requirements · {lot.number}",
            "lot": lot,
            "preview": preview,
            "current": preview.current,
            "form": form,
            "blocked": blocked,
            "cancel_url": back,
            "crumbs": crumbs_for((lot.number, back), ("Decide conflicting requirements", None)),
        },
        # A signature submitted while something else holds the lot signs nothing.
        status=403
        if blocked
        else 422
        if request.method == "POST" and not preview.possible
        else form_status(request, form),
    )


@login_required
@require_http_methods(["GET", "POST"])
def replace(request, pk):
    """Signed replacement of a lot's requirements once testing has started."""
    require_role(request.user, AUTHOR_ROLE)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    back = reverse("sampling:lot", args=[lot.pk])
    # Where the specifications in force state a test differently, the page is reviewed again
    # with the chosen statements (GET) before it is signed with them (POST).
    choices = chosen_scopes(request.POST if request.method == "POST" else request.GET)
    preview = services.replacement_preview(lot, choices=choices)
    # Nothing differs from the frozen requirements, but a requirement was chosen where the
    # specifications state a test differently: the page stays open so that another one can
    # be chosen and the replacement reviewed with it. Nothing is signed from this state.
    unchanged = preview.blocker == services.NOTHING_TO_REPLACE and bool(
        (preview.payload or {}).get("decisions")
    )
    if preview.blocker and not unchanged:
        messages.error(request, preview.blocker)
        return redirect(back)
    blocked = services.replacement_denial(request.user, lot)
    form = ReplacementForm(
        request.POST or None,
        initial={"expected_revision": lot.revision, "basis": preview.basis},
    )
    if request.method == "POST" and not blocked and preview.possible and form.is_valid():
        data = form.cleaned_data
        done = run(
            form,
            lambda: services.replace_requirements(
                actor=request.user,
                pin=data["pin"],
                lot=lot,
                expected_revision=data["expected_revision"],
                reason=data["reason"],
                basis=data["basis"],
                choices=choices,
            ),
        )
        if done:
            messages.success(
                request,
                "Requirements replaced and signed. Assign the required tests again for "
                "the tests that were superseded."
                if preview.superseded
                else "Requirements replaced and signed. Every test carried over.",
            )
            return redirect(back)
    stale = request.method == "POST" and services.REPLACEMENT_STALE in form.non_field_errors()
    if stale:
        # What applies changed: the page shows it as it is now. A choice that was submitted
        # is not kept, because the statement chosen may be the one that changed; a choice of
        # the lot's frozen requirements still stands while its statement is unchanged.
        preview = services.replacement_preview(lot)
        if preview.blocker and not (
            preview.blocker == services.NOTHING_TO_REPLACE
            and (preview.payload or {}).get("decisions")
        ):
            messages.error(request, preview.blocker)
            return redirect(back)
    if request.method == "POST":
        _reissue(form, lot, preview.basis)
    # Tests the specifications in force state differently: the ones already chosen for, with
    # the choice, then the ones still to choose for. Choices that settle a test not listed
    # here travel with the page.
    decided = (preview.payload or {}).get("decisions") or []
    statement = ("scope", "scopes", "specification", "name", "text", "required")
    differing = [
        {
            "code": item["code"],
            "name": item["name"],
            "differs": item["differs"],
            # The statement chosen, then the others.
            "candidates": [{key: item[key] for key in statement}, *item["alternatives"]],
            "chosen": item["scope"],
        }
        for item in decided
    ] + [{**conflict, "chosen": ""} for conflict in preview.conflicts]
    with_choices(differing)
    listed = {conflict["code"] for conflict in differing}
    carried = sorted((c, scope) for c, scope in preview.choices.items() if c not in listed)
    # A signature submitted while a test still waits for a choice signs nothing.
    unchosen = request.method == "POST" and not blocked and bool(preview.conflicts)
    unchanged = preview.blocker == services.NOTHING_TO_REPLACE and bool(decided)
    return render(
        request,
        "sampling/replace.html",
        {
            "page_title": f"Replace requirements · {lot.number}",
            "lot": lot,
            "preview": preview,
            "current": preview.current,
            "form": form,
            "blocked": blocked,
            "cancel_url": back,
            "differing": differing,
            "carried": carried,
            "decided": decided,
            "choice_missing": unchosen and not stale,
            "stale": stale,
            "unchanged": unchanged,
            "frozen": services.payload_specifications(preview.current.payload),
            "several": "specifications" in preview.current.payload
            or "specifications" in (preview.payload or {}),
            "crumbs": crumbs_for((lot.number, back), ("Replace requirements", None)),
        },
        status=403
        if blocked
        else 422
        if unchosen or (unchanged and request.method == "POST")
        else form_status(request, form),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sampling_new(request, pk):
    require_role(request.user, "analyst")
    lot = get_object_or_404(Lot, pk=pk)
    back = reverse("sampling:lot", args=[lot.pk])
    assignment, blocker = services.sampling_preflight(lot)
    if blocker:
        messages.error(request, blocker)
        return redirect(back)
    plan = assignment.plan_revision  # same snapshot that passed the preflight
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
    if blocker := services.correction_blocker(record):
        messages.error(request, blocker)
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
    if review is None:
        messages.error(request, "This record has no deviation awaiting assessment.")
        return redirect(back)
    reason, is_permission = services.assessment_blocker(review, request.user)
    if reason and not is_permission:
        messages.error(request, reason)
        return redirect(back)
    blocked = reason or ""
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


PLAN_COLUMNS = (
    Column("plan", "Plan", asc="code", desc="-code", locked=True),
    Column("material", "Material"),
    Column("stage", "Stage"),
    Column("versions", "Versions", css="text-end", priority="low"),
    Column("status", "Status"),
)


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
            "columns": PLAN_COLUMNS,
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
        revision.can_approve, revision.approve_note = (
            approval_offer(request.user, revision) if can_edit else (False, "")
        )
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
    require_role(request.user, AUTHOR_ROLE)  # before lookup: no 404/403 existence leak
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
    require_role(request.user, AUTHOR_ROLE)  # before lookup: no 404/403 existence leak
    revision = get_object_or_404(SamplingPlanRevision.objects.select_related("plan"), pk=pk)
    detail, crumbs = _plan_crumbs(revision, "Withdraw")
    return withdraw_page(request, revision, kind="Sampling plan", crumbs=crumbs, success_url=detail)
