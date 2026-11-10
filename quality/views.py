from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from core.models import ElectronicSignature
from core.services import require_role

from . import services
from .forms import LotForm, ResultForm, SampleForm, SigningForm
from .models import Lot, Result, Sample


def access(user):
    require_role(user, "analyst", "reviewer", "quality", "admin", "auditor")


@login_required
def lot_list(request):
    access(request.user)
    lots = Lot.objects.select_related("rules")
    query = request.GET.get("q", "").strip()
    if query:
        lots = lots.filter(number__icontains=query)
    return render(
        request,
        "quality/lot_list.html",
        {"page_obj": Paginator(lots, 30).get_page(request.GET.get("page")), "query": query},
    )


@login_required
def lot_detail(request, pk):
    access(request.user)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    from sampling.services import current_assignment

    assignment = current_assignment(lot)
    return render(
        request,
        "quality/lot_detail.html",
        {
            "lot": lot,
            "can_issue_coa": request.user.groups.filter(name="quality").exists(),
            "reports": lot.reports.all(),
            "assignment": assignment,
            "samples": lot.samples.prefetch_related("results__analyst"),
            "signatures": ElectronicSignature.objects.filter(
                object_type="quality.lot", object_id=str(lot.pk)
            ).order_by("signed_at"),
            "result_signatures": ElectronicSignature.objects.filter(
                object_type="quality.result",
                object_id__in=[
                    str(pk)
                    for pk in Result.objects.filter(sample__lot=lot).values_list("pk", flat=True)
                ],
            ).order_by("signed_at"),
        },
    )


def form_page(request, form, title, submit):
    return render(
        request,
        "quality/form.html",
        {"form": form, "title": title, "submit": submit},
        status=422 if request.method == "POST" else 200,
    )


def perform(form, action):
    try:
        return action()
    except ValidationError as exc:
        form.add_error(None, "; ".join(exc.messages))
        return None


@login_required
def lot_new(request):
    require_role(request.user, "analyst")
    form = LotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lot = perform(form, lambda: services.receive_lot(actor=request.user, **form.cleaned_data))
        if lot:
            messages.success(request, "Lot received in quarantine.")
            return redirect("quality:lot_detail", pk=lot.pk)
    return form_page(request, form, "New material lot", "Receive lot")


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
    return form_page(request, form, f"Add sample · {lot.number}", "Add sample")


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
    return form_page(request, form, f"Record result · {sample.reference}", "Record result")


@login_required
def sign(request, pk, action):
    is_review = action == "review"
    require_role(request.user, "reviewer" if is_review else "quality")
    obj = get_object_or_404(Result if is_review else Lot, pk=pk)
    lot = obj.sample.lot if is_review else obj
    form = SigningForm(request.POST or None, initial={"expected_revision": obj.revision})
    if request.method == "POST" and form.is_valid():
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
            "form": form,
            "lot": lot,
            "record": obj,
            "is_review": is_review,
            "meaning": "reviewed" if is_review else "approved",
        },
        status=422 if request.method == "POST" else 200,
    )
