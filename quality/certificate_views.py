"""Pages for supplier certificates: record, read, correct and withdraw what a certificate states."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.web import run
from core.services import require_role

from . import certificates, reliance
from .forms import CertificateCorrectionForm, CertificateForm, CertificateWithdrawalForm
from .models import Lot, SupplierCertificate
from .services import current_receipt
from .views import LOTS, access, action_page, lot_facts

HEADER_LABELS = (
    ("number", "Certificate number"),
    ("issued_by", "Issued by"),
    ("issued_on", "Date of the certificate"),
    ("stated_lot", "Lot number on the certificate"),
    ("document_ref", "Where the certificate is kept"),
    ("notes", "Notes"),
)
MEETS, FAILS = "Meets the specification", "Does not meet the specification"
INTRO = (
    "Record what the supplier's certificate states, against the lot's approved requirements. "
    "These are the supplier's results: they are kept apart from the laboratory's own tests. "
    "One stands in for a test only through an acceptance signed on the lot."
)


def certificate_url(certificate):
    return reverse("quality:certificate_detail", args=[certificate.pk])


def certificate_crumbs(certificate, action=None):
    lot = certificate.lot
    title = f"Supplier certificate {certificate.number}"
    crumbs = [
        (LOTS, reverse("quality:lot_list")),
        (lot.number, reverse("quality:lot_detail", args=[lot.pk])),
        (title, certificate_url(certificate) if action else None),
    ]
    return [*crumbs, (action, None)] if action else crumbs


def receipt_facts(lot):
    """The lot and what its receipt states, beside which the certificate is read."""
    receipt = current_receipt(lot)
    facts = lot_facts(lot)
    if receipt is not None and receipt.supplier_id:
        facts += [
            ("Supplier", str(receipt.supplier)),
            ("Supplier lot number", receipt.supplier_lot or "Not known"),
            ("Manufacturer lot number", receipt.manufacturer_lot or "Not stated"),
        ]
    return facts


def result_text(row):
    line = row["line"]
    if line.outcome:
        return f"{line.value_text} (stated as: {line.stated_text})"
    return f"{line.value_text} {row['unit']}".strip()


def shown(certificate, hashes):
    """A certificate record as the words its page shows: {key: (label, text)} in page order."""
    words = {name: (label, str(getattr(certificate, name) or "")) for name, label in HEADER_LABELS}
    for row in certificates.result_rows(certificate, hashes):
        line, name = row["line"], row["name"]
        words[line.test_code, "result"] = (f"{name} result", result_text(row))
        words[line.test_code, "method"] = (f"{name} method", line.method)
        words[line.test_code, "limits"] = (f"{name} limits", line.limits)
        words[line.test_code, "specification"] = (f"{name} specification", row["acceptance"])
        words[line.test_code, "source"] = (f"{name} requirement", row["source"])
        words[line.test_code, "comparison"] = (
            f"{name} comparison",
            MEETS if line.conforms else FAILS,
        )
    return words


def chain_history(chain, hashes):
    """Every record of one certificate, oldest first; a correction lists what it changed."""
    entries, before = [], None
    for record in chain:
        after = shown(record, hashes)
        changes = []
        if before is not None:
            for key in [*after, *(k for k in before if k not in after)]:
                label = (after.get(key) or before[key])[0]
                old = before[key][1] if key in before else ""
                new = after[key][1] if key in after else ""
                if old != new:
                    changes.append((label, old, new))
        entries.append(
            {
                "title": "Supplier certificate corrected"
                if record.corrects_id
                else "Supplier certificate recorded",
                "at": record.recorded_at,
                "actor": record.recorded_by,
                "by": "Recorded by",
                "reason": record.reason,
                "changes": changes,
            }
        )
        before = after
    head = chain[-1]
    if certificates.is_withdrawn(head):
        entries.append(
            {
                "title": "Supplier certificate withdrawn",
                "at": head.withdrawal.withdrawn_at,
                "actor": head.withdrawal.withdrawn_by,
                "by": "Withdrawn by",
                "reason": head.withdrawal.reason,
                "changes": [],
            }
        )
    return entries


@login_required
def certificate_detail(request, pk):
    access(request.user)
    certificate = get_object_or_404(SupplierCertificate.objects.select_related("lot"), pk=pk)
    lot = certificate.lot
    chain = next(c for c in certificates.lot_chains(lot) if any(r.pk == pk for r in c))
    head = chain[-1]
    if head.pk != pk:
        return redirect(certificate_url(head))  # A replaced record leads to the current one.
    hashes = certificates.current_hashes(lot)
    rows = certificates.result_rows(head, hashes)
    withdrawn = certificates.is_withdrawn(head)
    receipt = current_receipt(lot)
    can_change = (
        request.user.groups.filter(name="analyst").exists()
        and lot.state == "quarantine"
        and not withdrawn
    )
    # Each stated result with the proposal or acceptance that stands for its requirement, or,
    # for an analyst, whether it can be proposed in place of a test and why not.
    standing = {
        item.test_code: item
        for item in reliance.lot_acceptances(lot)
        if item.stands and item.result.certificate_id == head.pk
    }
    for row in rows:
        row["standing"] = standing.get(row["line"].test_code)
        row["refusal"] = (
            reliance.proposal_refusal(lot, row["line"])
            if can_change and row["standing"] is None
            else ""
        )
        row["can_propose"] = can_change and row["standing"] is None and not row["refusal"]
    return render(
        request,
        "quality/certificate_detail.html",
        {
            "page_title": f"Supplier certificate {head.number}",
            "crumbs": certificate_crumbs(head),
            "lot": lot,
            "certificate": head,
            "withdrawn": withdrawn,
            "rows": rows,
            "failing": any(not row["line"].conforms for row in rows),
            "replaced": any(row["replaced"] for row in rows),
            "receipt": receipt,
            "lot_check": certificates.lot_number_check(head, receipt),
            "history": chain_history(chain, hashes),
            "can_propose": can_change,
            "can_withdraw": can_change,
            # A correction needs what a new record needs: a supplier receipt and requirements.
            "can_correct": can_change and not certificates.recording_requirements(lot)[1],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def certificate_new(request, pk):
    require_role(request.user, "analyst")
    lot = get_object_or_404(Lot, pk=pk)
    lot_url = reverse("quality:lot_detail", args=[lot.pk])
    required, refusal = certificates.recording_requirements(lot)
    if refusal:
        messages.error(request, refusal)
        return redirect(lot_url)
    form = CertificateForm(
        request.POST or None,
        required=required,
        initial={"basis": certificates.requirements_basis(required)},
    )
    if request.method == "POST" and form.is_valid():
        certificate = run(
            form,
            lambda: certificates.record_certificate(
                actor=request.user,
                lot=lot,
                reason=form.cleaned_data["reason"],
                basis=form.cleaned_data["basis"],
                results=form.results(),
                **form.header_values(),
            ),
        )
        if certificate:
            messages.success(request, "Supplier certificate recorded.")
            return redirect(certificate_url(certificate))
    form.show_current_requirements()
    title = "Record supplier certificate"
    return action_page(
        request,
        form,
        title=title,
        crumbs=[(LOTS, reverse("quality:lot_list")), (lot.number, lot_url), (title, None)],
        cancel_url=lot_url,
        submit=title,
        intro=INTRO,
        facts=receipt_facts(lot),
    )


@login_required
@require_http_methods(["GET", "POST"])
def certificate_correct(request, pk):
    require_role(request.user, "analyst")
    certificate = get_object_or_404(SupplierCertificate.objects.select_related("lot"), pk=pk)
    lot, url = certificate.lot, certificate_url(certificate)
    required, refusal = certificates.recording_requirements(lot)
    # A record replaced or withdrawn after the page opened is refused by the service on
    # submission, so the entries stay on screen beside the refusal.
    if not refusal and request.method != "POST":
        refusal = certificates.change_blocker(certificate)
    if refusal:
        messages.error(request, refusal)
        return redirect(url)
    initial = CertificateCorrectionForm.initial_from(certificate, required)
    initial["basis"] = certificates.requirements_basis(required)
    form = CertificateCorrectionForm(request.POST or None, required=required, initial=initial)
    if request.method == "POST" and form.is_valid():
        corrected = run(
            form,
            lambda: certificates.correct_certificate(
                actor=request.user,
                certificate=certificate,
                reason=form.cleaned_data["reason"],
                basis=form.cleaned_data["basis"],
                results=form.results(),
                **form.header_values(),
            ),
        )
        if corrected:
            messages.success(request, "Supplier certificate corrected; the original is kept.")
            return redirect(certificate_url(corrected))
    form.show_current_requirements()
    title = "Correct supplier certificate"
    return action_page(
        request,
        form,
        title=title,
        crumbs=certificate_crumbs(certificate, title),
        cancel_url=url,
        submit=title,
        intro="A correction adds a record and keeps the one it replaces. Every result is "
        "compared again with the lot's current requirements. State what was wrong in the reason.",
        facts=receipt_facts(lot),
    )


@login_required
@require_http_methods(["GET", "POST"])
def certificate_withdraw(request, pk):
    require_role(request.user, "analyst")
    certificate = get_object_or_404(SupplierCertificate.objects.select_related("lot"), pk=pk)
    lot, url = certificate.lot, certificate_url(certificate)
    refusal = certificates.QUARANTINE_ONLY if lot.state != "quarantine" else ""
    if not refusal and request.method != "POST":
        refusal = certificates.change_blocker(certificate)
    if refusal:
        messages.error(request, refusal)
        return redirect(url)
    form = CertificateWithdrawalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        withdrawal = run(
            form,
            lambda: certificates.withdraw_certificate(
                actor=request.user, certificate=certificate, reason=form.cleaned_data["reason"]
            ),
        )
        if withdrawal:
            messages.success(request, "Supplier certificate withdrawn; the record is kept.")
            return redirect(url)
    title = "Withdraw supplier certificate"
    return action_page(
        request,
        form,
        title=title,
        crumbs=certificate_crumbs(certificate, title),
        cancel_url=url,
        submit=title,
        tone="danger",
        intro="Withdraw a certificate record that should not stand, for example one recorded on "
        "the wrong lot. The record and its results are kept and marked as withdrawn; a withdrawn "
        "record cannot be corrected.",
        facts=[
            *lot_facts(lot),
            ("Certificate number", certificate.number),
            ("Issued by", certificate.issued_by),
        ],
    )
