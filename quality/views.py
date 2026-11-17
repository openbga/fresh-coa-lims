from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.services import ROLES
from catalog.web import form_status, run
from core.grids import Column, paginate
from core.models import ElectronicSignature
from core.services import AUDIT_READ_ROLES, require_role

from . import certificates, dashboard, reliance, route, services
from .forms import LotForm, ReceiptCorrectionForm, ReceiptForm, ResultForm, SampleForm, SigningForm
from .models import Lot, LotReceipt, LotState, ReceiptSource, Result, Sample
from .rejection import RejectionGrounds

LOTS = "Material lots"
# Labels of the receipt details, in the order the lot record and its history show them.
RECEIPT_LABELS = (
    ("source", "Source"),
    ("supplier", "Supplier"),
    ("supplier_lot", "Supplier lot number"),
    ("manufacturer", "Manufacturer"),
    ("manufacturer_location", "Manufacturer location"),
    ("manufacturer_lot", "Manufacturer lot number"),
    ("shipment_ref", "Delivery or batch document"),
    ("received_on", "Date received"),
    ("quantity", "Quantity received"),
    ("containers", "Number of containers"),
    ("container_description", "Containers"),
    ("condition", "Examination on receipt"),
    ("condition_notes", "Examination notes"),
)


def access(user):
    require_role(user, "analyst", "reviewer", "quality", "admin", "auditor")


# The material lot list's columns (core.grids.Column; keys are saved in users' layouts).
LOT_COLUMNS = (
    Column("lot", "Lot", locked=True),
    Column("status", "Status"),
    Column("material", "Material"),
    Column("supplier", "Supplier", priority="medium"),
    Column("received", "Received", priority="medium"),
    Column("route", "Where it is"),
    Column("rules", "Rule set", priority="low"),
)


class LotFilterForm(forms.Form):
    """The material lot list's status filter; the search box is the toolbar's own (q)."""

    state = forms.ChoiceField(
        label="Status", choices=[("", "All lots"), *LotState.choices], required=False
    )
    queue = forms.ChoiceField(
        label="Queue",
        choices=[("", "Any queue"), *dashboard.LOT_QUEUES.items()],
        required=False,
    )


@login_required
def lot_list(request):
    if (
        request.method in {"GET", "HEAD"}
        and not request.user.groups.filter(name__in=ROLES).exists()
    ):
        return redirect("accounts:access")
    access(request.user)
    current = LotReceipt.objects.filter(corrected_by__isnull=True)
    lots = Lot.objects.select_related("rules").prefetch_related(
        Prefetch("receipts", queryset=current.select_related("supplier"), to_attr="current")
    )
    filters = LotFilterForm(request.GET)
    if not filters.is_valid():  # an unknown status lists every lot, as before the filter
        filters = LotFilterForm()
    state = filters.cleaned_data["state"] if filters.is_bound else ""
    if state:
        lots = lots.filter(state=state)
    # The dashboard counts the same queryset, so its count equals the rows listed here.
    queue = filters.cleaned_data["queue"] if filters.is_bound else ""
    if queue:
        lots = lots.filter(pk__in=dashboard.lot_queues()[queue].values("pk"))
    query = request.GET.get("q", "").strip()
    if query:
        lots = lots.filter(
            Q(number__icontains=query)
            | Exists(
                current.filter(lot=OuterRef("pk")).filter(
                    Q(supplier_lot__icontains=query) | Q(manufacturer_lot__icontains=query)
                )
            )
        )
    page_obj = paginate(request, route.annotate_route(lots))
    for lot in page_obj:
        lot.route = route.list_route(lot)
        lot.route_summary = route.summary(lot.route)
        lot.hold_labels = route.hold_labels(lot)
    return render(
        request,
        "quality/lot_list.html",
        {
            "page_title": "Material lots",
            "page_obj": page_obj,
            "columns": LOT_COLUMNS,
            "query": query,
            "filters": filters,
            "filtered": bool(query or state or queue),
            "can_receive": request.user.groups.filter(name="analyst").exists(),
        },
    )


def closure_offers(user, lot):
    """Reject lot and Cancel lot received in error, for quality on a lot in quarantine, offered
    only when signing them would be accepted (quality.rejection's own refusals and denials);
    otherwise the reason to show in the header instead."""
    from .rejection import (
        cancellation_denial,
        cancellation_refusals,
        rejection_denial,
        rejection_refusals,
    )

    if lot.state != "quarantine" or not user.groups.filter(name="quality").exists():
        return {"reject_note": "", "can_reject": False, "can_cancel": False}
    reject_note = rejection_denial(user, lot) or next(iter(rejection_refusals(lot)), "")
    return {
        "reject_note": reject_note,
        "can_reject": not reject_note,
        "can_cancel": not (cancellation_denial(user, lot) or cancellation_refusals(lot)),
    }


@login_required
def lot_detail(request, pk):
    access(request.user)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    from sampling.services import current_assignment

    assignment = current_assignment(lot)
    receipts = list(lot.receipts.select_related("supplier", "recorded_by"))
    corrected = {receipt.corrects_id for receipt in receipts}
    receipt = next((r for r in receipts if r.pk not in corrected), None)
    can_record = request.user.groups.filter(name="analyst").exists()
    from analytical import gates

    _, _, tests, investigations = gates.lot_status(lot)
    from stability.gates import active_holds

    quarantine = lot.state == "quarantine"
    holds = list(active_holds(lot)) if quarantine else []
    # Exactly what signing the disposition checks (services.dispose_lot).
    blockers = services.disposition_blockers(lot) if quarantine else []
    tests_by_pk = {test.pk: test for test in tests}
    open_investigations = []
    for investigation in sorted(investigations.values(), key=lambda i: i.pk):
        if investigation.is_open:
            investigation.held_test = tests_by_pk.get(investigation.test_id)
            open_investigations.append(investigation)
    reports = list(lot.reports.all())
    samples = list(lot.samples.prefetch_related("results__analyst"))
    # Native evidence: each sample's analytical tests, from the tests lot_status already loaded
    # (no query per sample); an open test answered by an accepted supplier result says so.
    from analytical.contracts import supplier_results

    standing = supplier_results(lot)["standing"] if tests else {}
    native_by_sample = {}
    for test in tests:
        test.supplier_result = standing.get(test.test_code) if test.state == "open" else None
        native_by_sample.setdefault(test.sample_id, []).append(test)
    for sample in samples:
        sample.native_tests = native_by_sample.get(sample.pk, [])
    acceptances = reliance.lot_acceptances(lot)
    from stability.models import RetentionObligation

    # The lot's retention obligations, with or without a reserve sample: a lot-level obligation
    # has no other page. Set anchor is offered as stability.services.set_anchor allows it.
    retention = list(
        RetentionObligation.objects.filter(lot=lot)
        .select_related("reserve")
        .order_by("anchor_date", "pk")
    )
    lot_signatures = list(
        ElectronicSignature.objects.filter(object_type="quality.lot", object_id=str(lot.pk))
        .select_related("audit_event")
        .order_by("signed_at")
    )
    return render(
        request,
        "quality/lot_detail.html",
        {
            "page_title": lot.number,
            "lot": lot,
            "receipt": receipt,
            "receipt_history": receipt_history(receipts),
            "certificates": certificates.lot_summary(lot),
            "supplied": receipt is not None and receipt.source == ReceiptSource.SUPPLIER,
            "certificate_blocker": certificates.recording_requirements(lot)[1],
            "acceptances": acceptances,
            "retention": retention,
            "can_set_anchor": request.user.groups.filter(name__in=("analyst", "quality")).exists(),
            "supplier_accepted": any(item.state == "accepted" for item in acceptances),
            "can_record": can_record,
            "can_review": request.user.groups.filter(name="reviewer").exists(),
            "can_dispose": request.user.groups.filter(name="quality").exists(),
            # A disposition author is refused on the signing page; not offered as the next step.
            "disposition_denied": services.disposition_denial(request.user, lot)
            if lot.state == "quarantine"
            else "",
            **closure_offers(request.user, lot),
            "can_issue_coa": request.user.groups.filter(name="quality").exists(),
            # The exported record includes the audit trail, so it needs a role that reads it.
            "can_export": request.user.groups.filter(name__in=AUDIT_READ_ROLES).exists(),
            "reports": reports,
            "issued": any(report.state == "issued" for report in reports),
            "blockers": blockers,
            "holds": holds,
            "awaiting_review": sum(
                1
                for sample in samples
                for result in sample.results.all()
                if result.state == "recorded" and result.analyst_id != request.user.pk
            )
            if request.user.groups.filter(name="reviewer").exists()
            else 0,
            "open_investigations": open_investigations,
            "route": route.route(
                lot,
                assignment=assignment,
                tests=tests,
                investigations=investigations.values(),
                reports=reports,
            ),
            "assignment": assignment,
            "samples": samples,
            "signatures": lot_signatures,
            # A lot is also signed when its requirements are replaced during testing.
            "disposition_signed": any(s.meaning in DECISION_MEANINGS for s in lot_signatures),
            "decision": decision_display(lot, lot_signatures),
            "result_signatures": ElectronicSignature.objects.filter(
                object_type="quality.result",
                object_id__in=[
                    str(pk)
                    for pk in Result.objects.filter(sample__lot=lot).values_list("pk", flat=True)
                ],
            ).order_by("signed_at"),
        },
    )


# Signatures that decide a lot: its release, its rejection or its cancellation.
DECISION_MEANINGS = ("approved", "rejected", "cancelled")


def decision_display(lot, signatures):
    """The signed rejection or cancellation of the lot as the lot record shows it, or None."""
    evidence = lot.decision
    if evidence is None:
        return None
    signature = next((s for s in signatures if s.meaning == lot.state), None)
    grounds = evidence.get("grounds")
    return {
        "evidence": evidence,
        "signature": signature,
        "signatures": [signature] if signature else [],
        "reason": signature.audit_event.reason if signature else "",
        "grounds": RejectionGrounds(grounds).label if grounds in RejectionGrounds.values else "",
        "tests": len(evidence.get("tests", [])),
        "unfinished": [
            row for row in evidence.get("tests", []) if row["state"] in ("open", "submitted")
        ],
    }


def receipt_display(receipt):
    """Receipt details as the words the lot record shows, keyed like RECEIPT_LABELS."""
    return {
        "source": receipt.get_source_display(),
        "supplier": str(receipt.supplier) if receipt.supplier_id else "",
        "supplier_lot": receipt.supplier_lot,
        "manufacturer": receipt.manufacturer,
        "manufacturer_location": receipt.manufacturer_location,
        "manufacturer_lot": receipt.manufacturer_lot,
        "shipment_ref": receipt.shipment_ref,
        "received_on": receipt.received_on.isoformat(),
        "quantity": f"{receipt.quantity_text} {receipt.quantity_unit}",
        "containers": str(receipt.containers),
        "container_description": receipt.container_description,
        "condition": receipt.get_condition_display(),
        "condition_notes": receipt.condition_notes,
    }


def receipt_history(receipts):
    """Every receipt record of a lot, oldest first; a correction lists what it changed."""
    shown = {receipt.pk: receipt_display(receipt) for receipt in receipts}
    return [
        {
            "receipt": receipt,
            "title": "Receipt details corrected" if receipt.corrects_id else "Receipt recorded",
            "icon": "pencil-square" if receipt.corrects_id else "",
            "changes": [
                (label, shown[receipt.corrects_id][key], shown[receipt.pk][key])
                for key, label in RECEIPT_LABELS
                if shown[receipt.corrects_id][key] != shown[receipt.pk][key]
            ]
            if receipt.corrects_id
            else [],
        }
        for receipt in receipts
    ]


def form_page(request, form, title, submit, lot):
    """An action page on a lot record (add a sample, record a result)."""
    return render(
        request,
        "quality/form.html",
        {
            "page_title": title,
            "form": form,
            "submit": submit,
            "lot": lot,
            "cancel_url": reverse("quality:lot_detail", args=[lot.pk]),
        },
        status=422 if request.method == "POST" else 200,
    )


def perform(form, action):
    try:
        return action()
    except ValidationError as exc:
        form.add_error(None, "; ".join(exc.messages))
        return None


def action_page(
    request, form, *, title, crumbs, cancel_url, submit, intro, facts=None, tone="primary"
):
    return render(
        request,
        "catalog/form.html",
        {
            "page_title": title,
            "form": form,
            "crumbs": crumbs,
            "cancel_url": cancel_url,
            "submit_label": submit,
            "submit_tone": tone,
            "intro": intro,
            "facts": facts or [],
        },
        status=form_status(request, form),
    )


def lot_crumbs(lot, action):
    return [
        (LOTS, reverse("quality:lot_list")),
        (lot.number, reverse("quality:lot_detail", args=[lot.pk])),
        (action, None),
    ]


def lot_facts(lot):
    return [("Lot", lot.number), ("Material", lot.material), ("Status", lot.state.capitalize())]


@login_required
@require_http_methods(["GET", "POST"])
def lot_new(request):
    require_role(request.user, "analyst")
    form = LotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        lot = run(
            form,
            lambda: services.receive_lot(
                actor=request.user,
                number=data["number"],
                material=data["material"],
                rules=data["rules"],
                reason=data["reason"],
                receipt=form.receipt_values(),
            ),
        )
        if lot:
            messages.success(request, "Lot received in quarantine.")
            return redirect("quality:lot_detail", pk=lot.pk)
    return action_page(
        request,
        form,
        title="New material lot",
        crumbs=[(LOTS, reverse("quality:lot_list")), ("New material lot", None)],
        cancel_url=reverse("quality:lot_list"),
        submit="Receive lot",
        intro="Receive a lot into quarantine with the details of its receipt: where it came "
        "from, what arrived and what the examination on receipt found.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def receipt_new(request, pk):
    """Receipt details for a lot that has none: one received before they were kept."""
    require_role(request.user, "analyst")
    lot = get_object_or_404(Lot, pk=pk)
    lot_url = reverse("quality:lot_detail", args=[lot.pk])
    if lot.state != "quarantine" or lot.receipts.exists():
        messages.error(
            request,
            "Only quarantined lots accept receipt details."
            if lot.state != "quarantine"
            else "Receipt details are already recorded; correct them instead.",
        )
        return redirect(lot_url)
    form = ReceiptForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        receipt = run(
            form,
            lambda: services.record_receipt(
                actor=request.user,
                lot=lot,
                reason=form.cleaned_data["reason"],
                **form.receipt_values(),
            ),
        )
        if receipt:
            messages.success(request, "Receipt details recorded.")
            return redirect(lot_url)
    return action_page(
        request,
        form,
        title="Record receipt details",
        crumbs=lot_crumbs(lot, "Record receipt details"),
        cancel_url=lot_url,
        submit="Record receipt details",
        intro="This lot was received before receipt details were kept. Record them from the "
        "delivery documents.",
        facts=lot_facts(lot),
    )


@login_required
@require_http_methods(["GET", "POST"])
def receipt_correct(request, pk):
    require_role(request.user, "analyst")
    lot = get_object_or_404(Lot, pk=pk)
    lot_url = reverse("quality:lot_detail", args=[lot.pk])
    current = services.current_receipt(lot)
    if lot.state != "quarantine" or current is None:
        messages.error(
            request,
            "Only quarantined lots accept receipt corrections."
            if lot.state != "quarantine"
            else "This lot has no receipt details to correct.",
        )
        return redirect(lot_url)
    initial = {name: getattr(current, name) for name in services.RECEIPT_FIELDS}
    initial["quantity"] = current.quantity_text
    form = ReceiptCorrectionForm(request.POST or None, initial={**initial, "receipt": current.pk})
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["receipt"] != current.pk:
            form.add_error(None, services.RECEIPT_STALE)
        else:
            corrected = run(
                form,
                lambda: services.correct_receipt(
                    actor=request.user,
                    receipt=current,
                    reason=form.cleaned_data["reason"],
                    **form.receipt_values(),
                ),
            )
            if corrected:
                messages.success(request, "Receipt details corrected; the original is kept.")
                return redirect(lot_url)
    return action_page(
        request,
        form,
        title="Correct receipt details",
        crumbs=lot_crumbs(lot, "Correct receipt details"),
        cancel_url=lot_url,
        submit="Correct receipt details",
        intro="A correction adds a record and keeps the one it replaces. State what was wrong "
        "in the reason.",
        facts=lot_facts(lot),
    )


@login_required
def sample_new(request, pk):
    require_role(request.user, "analyst")
    lot = get_object_or_404(Lot, pk=pk)
    form = SampleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        sample = perform(
            form, lambda: services.add_sample(actor=request.user, lot=lot, **form.cleaned_data)
        )
        if sample:
            return redirect("quality:lot_detail", pk=lot.pk)
    return form_page(request, form, f"Add sample · {lot.number}", "Add sample", lot)


@login_required
def result_new(request, pk):
    require_role(request.user, "analyst")
    sample = get_object_or_404(Sample.objects.select_related("lot"), pk=pk)
    form = ResultForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = perform(
            form,
            lambda: services.record_result(actor=request.user, sample=sample, **form.cleaned_data),
        )
        if result:
            return redirect("quality:lot_detail", pk=sample.lot_id)
    return form_page(
        request, form, f"Record result · {sample.reference}", "Record result", sample.lot
    )


@login_required
def sign(request, pk, action):
    is_review = action == "review"
    require_role(request.user, "reviewer" if is_review else "quality")
    obj = get_object_or_404(Result if is_review else Lot, pk=pk)
    lot = obj.sample.lot if is_review else obj
    form = SigningForm(request.POST or None, initial={"expected_revision": obj.revision})
    denial = "" if is_review else services.disposition_denial(request.user, obj)
    if not denial and request.method == "POST" and form.is_valid():
        signing_data = {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}

        def commit():
            if is_review:
                services.review_result(actor=request.user, result=obj, **signing_data)
            else:
                services.dispose_lot(actor=request.user, lot=obj, **signing_data)
            return True

        if perform(form, commit):
            messages.success(request, "Signed review recorded." if is_review else "Lot released.")
            return redirect("quality:lot_detail", pk=lot.pk)
    return render(
        request,
        "signatures/sign.html",
        {
            "page_title": "Sign result review" if is_review else "Sign lot disposition",
            "form": form,
            "lot": lot,
            "record": obj,
            "is_review": is_review,
            "meaning": "reviewed" if is_review else "approved",
            "denial": denial,
            "notices": [] if is_review or denial else services.disposition_notices(obj),
        },
        status=403 if denial else 422 if request.method == "POST" else 200,
    )
