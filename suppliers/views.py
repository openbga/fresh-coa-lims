from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from catalog.web import can, form_status, history, page, run, sorted_by
from core.grids import Column
from core.services import require_role

from . import services
from .forms import SupplierForm
from .models import Supplier
from .qualification import qualification_status

SECTION = "Suppliers"
# A lot's receipt details are append-only; the record without a correction is the current one.
CURRENT = Q(receipts__corrected_by__isnull=True)


def read_access(request):
    require_role(request.user, *services.READ_ROLES)


SUPPLIER_COLUMNS = (
    Column("supplier", "Supplier", asc="code", desc="-code", locked=True),
    Column("location", "Location", priority="medium"),
    Column("qualification", "Qualification"),
    Column("lots", "Lots received", css="text-end"),
    Column("created", "Created", priority="low"),
)


# A supplier's qualifications ranked for its list row: the one that lets results be relied on
# soonest and longest first, then those awaiting approval, then expired and revoked.
QUALIFICATION_RANK = [
    "Approved",
    "Expiring soon",
    "Approved, starts later",
    "Awaiting approval",
    "Expired",
    "Revoked",
]


def best_qualification(qualifications, today):
    """(label, tone) of the supplier's best qualification state, or None when it has none."""
    states = [qualification_status(q, today) for q in qualifications]
    return min(states, key=lambda state: QUALIFICATION_RANK.index(state[0]), default=None)


@login_required
def supplier_list(request):
    read_access(request)
    suppliers = Supplier.objects.annotate(lot_count=Count("receipts", filter=CURRENT))
    query = request.GET.get("q", "").strip()
    if query:
        suppliers = suppliers.filter(
            Q(code__icontains=query) | Q(name__icontains=query) | Q(location__icontains=query)
        )
    suppliers, sort = sorted_by(
        request,
        suppliers,
        {
            "code": ["code"],
            "-code": ["-code"],
            "name": ["name", "code"],
            "-name": ["-name", "code"],
        },
        "code",
    )
    page_obj = page(request, suppliers.prefetch_related("qualifications"))
    today = timezone.localdate()
    for supplier in page_obj:
        supplier.qualification = best_qualification(supplier.qualifications.all(), today)
    return render(
        request,
        "suppliers/list.html",
        {
            "page_title": SECTION,
            "columns": SUPPLIER_COLUMNS,
            "page_obj": page_obj,
            "query": query,
            "sort": sort,
            "filtered": bool(query),
            "can_edit": can(request.user, services.AUTHOR_ROLE),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def supplier_new(request):
    require_role(request.user, services.AUTHOR_ROLE)
    form = SupplierForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        supplier = run(
            form, lambda: services.create_supplier(actor=request.user, **form.cleaned_data)
        )
        if supplier:
            messages.success(request, f"Supplier {supplier.code} created.")
            return redirect("suppliers:detail", pk=supplier.pk)
    return render(
        request,
        "catalog/form.html",
        {
            "page_title": "New supplier",
            "form": form,
            "crumbs": [(SECTION, reverse("suppliers:list")), ("New supplier", None)],
            "cancel_url": reverse("suppliers:list"),
            "submit_label": "Create supplier",
            "intro": "A supplier's identity cannot be edited after creation; use synthetic names "
            "only. Adding a supplier does not qualify it; a qualification is recorded on the "
            "supplier's page and signed by a second quality person.",
        },
        status=form_status(request, form),
    )


@login_required
def supplier_detail(request, pk):
    read_access(request)
    supplier = get_object_or_404(Supplier.objects.select_related("created_by"), pk=pk)
    receipts = (
        supplier.receipts.filter(corrected_by__isnull=True)
        .select_related("lot")
        .order_by("-received_on", "-id")
    )
    from .qualification_views import qualification_rows, tests_text

    qualifications = qualification_rows(supplier)
    for row in qualifications:
        row["tests"] = tests_text(row["qualification"])
    return render(
        request,
        "suppliers/detail.html",
        {
            "page_title": supplier.code,
            "supplier": supplier,
            "crumbs": [(SECTION, reverse("suppliers:list")), (supplier.code, None)],
            "page_obj": page(request, receipts),
            "history": history(supplier),
            "qualifications": qualifications,
            "can_qualify": can(request.user, services.AUTHOR_ROLE),
            "can_assess": can(request.user, "quality"),
        },
    )
