"""Recording and correcting the expiry and retest dates of a lot (quality.dates)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.web import run
from core.services import MATERIAL_DATES_RULES, require_role

from . import dates
from .forms import DatesForm
from .models import Lot
from .views import action_page, lot_crumbs, lot_facts


@login_required
@require_http_methods(["GET", "POST"])
def lot_dates(request, pk):
    """Record the dates of a lot in quarantine, or correct the record in force."""
    require_role(request.user, *dates.RECORD_ROLES)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    lot_url = reverse("quality:lot_detail", args=[lot.pk])
    if lot.state != "quarantine":
        messages.error(request, dates.NOT_QUARANTINED)
        return redirect(lot_url)
    current = dates.current_dates(lot)
    initial = {"current": current.pk if current else None}
    if current is not None:
        initial |= {
            "expiry_on": current.expiry_on,
            "retest_on": current.retest_on,
            "basis": current.basis,
        }
    form = DatesForm(request.POST or None, initial=initial)
    if current is not None:
        form.fields["reason"].label = "Reason for correction"
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        record = run(
            form,
            lambda: dates.record_dates(
                actor=request.user,
                lot=lot,
                expected=data["current"],
                reason=data["reason"],
                expiry_on=data["expiry_on"],
                retest_on=data["retest_on"],
                basis=data["basis"],
            ),
        )
        if record:
            messages.success(
                request,
                "Dates corrected; the record replaced is kept." if current else "Dates recorded.",
            )
            return redirect(lot_url)
    title = "Correct expiry and retest dates" if current else "Record expiry and retest dates"
    required = [
        f"{rule} requires {MATERIAL_DATES_RULES[key]}." for rule, key in dates.required_dates(lot)
    ]
    intro = (
        "A correction adds a record and keeps the one it replaces. State what was wrong in the "
        "reason."
        if current
        else "Record the dates the material carries: its expiry date, its retest date or both, "
        "with where they come from."
    )
    if required:
        intro += " " + " ".join(required)
    else:
        intro += " The lot's rule sets require no dates; record them where they apply."
    return action_page(
        request,
        form,
        title=title,
        crumbs=lot_crumbs(lot, title),
        cancel_url=lot_url,
        submit="Correct dates" if current else "Record dates",
        intro=intro,
        facts=lot_facts(lot),
    )
