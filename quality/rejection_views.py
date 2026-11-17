"""Pages for the signed rejection of a lot and the cancellation of a lot received in error
(HTTP only; the rules are in ``rejection``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.web import form_status, run
from core.services import require_role

from . import rejection
from .forms import CancellationForm, RejectionForm
from .models import Lot
from .views import LOTS

TEST_STATES = {
    "open": "Open",
    "submitted": "Awaiting review",
    "reviewed": "Reviewed",
    "invalidated": "Invalidated",
    "superseded": "Superseded",
}

MODES = {
    "rejected": {
        "title": "Reject lot",
        "form": RejectionForm,
        "preview": rejection.rejection_preview,
        "denial": rejection.rejection_denial,
        "sign": rejection.reject_lot,
        "button": "Sign and reject the lot",
        "success": "Lot rejected. Its records are kept as they were signed.",
    },
    "cancelled": {
        "title": "Cancel lot received in error",
        "form": CancellationForm,
        "preview": rejection.cancellation_preview,
        "denial": rejection.cancellation_denial,
        "sign": rejection.cancel_receipt,
        "button": "Sign and cancel the lot",
        "success": "Lot cancelled as received in error. Its records are kept.",
    },
}


def _reissue(form, lot, basis):
    """After a refused signature the page shows the lot as it is now, so the form carries the
    basis and the revision of what is shown. The signer reviews it and enters the PIN again."""
    form.data = form.data.copy()
    form.data["basis"] = basis
    form.data["expected_revision"] = str(lot.revision)


def _test_rows(evidence):
    return [
        {**row, "state_label": TEST_STATES.get(row["state"], row["state"])}
        for row in evidence.get("tests", [])
    ]


def _closure_page(request, pk, decision):
    require_role(request.user, "quality")
    mode = MODES[decision]
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    back = reverse("quality:lot_detail", args=[lot.pk])
    closure = mode["preview"](lot)
    if closure.blocker:
        messages.error(request, closure.blocker)
        return redirect(back)
    denied = mode["denial"](request.user, lot)
    form = mode["form"](
        request.POST or None,
        initial={"expected_revision": lot.revision, "basis": closure.basis},
    )
    attempted = request.method == "POST" and not denied and closure.possible
    if attempted and form.is_valid():
        data = form.cleaned_data
        extra = {"grounds": data["grounds"]} if decision == "rejected" else {}
        done = run(
            form,
            lambda: mode["sign"](
                actor=request.user,
                pin=data["pin"],
                lot=lot,
                expected_revision=data["expected_revision"],
                reason=data["reason"],
                basis=data["basis"],
                reference=data["reference"],
                **extra,
            ),
        )
        if done:
            messages.success(request, mode["success"])
            return redirect(back)
    if request.method == "POST":
        lot.refresh_from_db()
        closure = mode["preview"](lot)
        if closure.blocker:
            messages.error(request, closure.blocker)
            return redirect(back)
        denied = mode["denial"](request.user, lot)
        if not attempted and not denied and closure.possible:
            # Submitted while it could not be signed; the lot has changed since. Say so.
            form.add_error(None, rejection.CLOSURE_STALE)
        _reissue(form, lot, closure.basis)
    evidence = closure.evidence
    return render(
        request,
        "quality/closure.html",
        {
            "page_title": f"{mode['title']} · {lot.number}",
            "lot": lot,
            "decision": decision,
            "closure": closure,
            "evidence": evidence,
            "tests": _test_rows(evidence),
            "form": form,
            "denied": denied,
            "button": mode["button"],
            "cancel_url": back,
            "crumbs": [
                (LOTS, reverse("quality:lot_list")),
                (lot.number, back),
                (mode["title"], None),
            ],
        },
        # A signature submitted while the lot cannot be rejected or cancelled signs nothing.
        status=403
        if denied
        else 422
        if request.method == "POST" and not closure.possible
        else form_status(request, form),
    )


@login_required
@require_http_methods(["GET", "POST"])
def lot_reject(request, pk):
    """Signed rejection of a lot in quarantine."""
    return _closure_page(request, pk, "rejected")


@login_required
@require_http_methods(["GET", "POST"])
def lot_cancel(request, pk):
    """Signed cancellation of a lot whose receipt was recorded in error."""
    return _closure_page(request, pk, "cancelled")
