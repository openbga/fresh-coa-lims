import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from core.models import AuditEvent
from quality.models import Lot

from . import evidence as ev
from . import services
from .forms import AmendForm, IssueForm, LotPickForm
from .models import Report

SORTS = {
    "number": "number",
    "lot": "lot__number",
    "material": "lot__material",
    "recipient": "recipient",
    "status": "version_count",
    "created": "created_at",
}
STATUS_FILTERS = {
    "draft": Q(state="draft"),
    "issued": Q(state="issued", version_count=1),
    "amended": Q(state="issued", version_count__gt=1),
}


def has_role(user, *roles):
    return user.groups.filter(name__in=roles).exists()


def signing_data(form):
    """Service arguments; the typed signing username is verified centrally, not passed on."""
    return {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}


def preflight(request, evidence, digest, problems, verb):
    """Reason the signing form must not be offered, or None. POST revalidates everything."""
    if request.GET.get("evidence") != digest:
        return "The evidence changed since you reviewed it. Review it again."
    if problems:
        return f"This certificate cannot be {verb}: " + " ".join(problems)
    if ev.independence_conflict(evidence, request.user):
        return f"You authored records on this lot, so you cannot sign this certificate as {verb}."
    return None


def failure(exc):
    return "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)


@login_required
@require_GET
def report_list(request):
    services.require_reader(request.user)
    reports = Report.objects.select_related("lot")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        reports = reports.filter(
            Q(number__icontains=query)
            | Q(lot__number__icontains=query)
            | Q(lot__material__icontains=query)
            | Q(recipient__icontains=query)
        )
    if status in STATUS_FILTERS:
        reports = reports.filter(STATUS_FILTERS[status])
    sort = request.GET.get("sort", "-created")
    key = SORTS.get(sort.lstrip("-"), "created_at")
    reports = reports.order_by(("-" if sort.startswith("-") else "") + key, "-id")
    page = Paginator(reports, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "reporting/report_list.html",
        {
            "page_title": "Certificates of analysis",
            "page_obj": page,
            "query": query,
            "status": status,
            "sort": sort,
            "filtered": bool(query or status),
            "querystring": params.urlencode(),
            "can_issue": has_role(request.user, services.ISSUE_ROLE),
            "status_choices": [
                ("draft", "Not issued"),
                ("issued", "Issued"),
                ("amended", "Amended"),
            ],
        },
    )


@login_required
@require_http_methods(["GET"])
def report_new(request):
    services.require_role(request.user, services.ISSUE_ROLE)
    form = LotPickForm(request.GET or None)
    if request.GET and form.is_valid():
        return redirect("reporting:issue_preview", lot_pk=form.cleaned_data["lot"].pk)
    return render(
        request,
        "reporting/report_new.html",
        {"page_title": "New certificate of analysis", "form": form},
        status=422 if request.GET and form.errors else 200,
    )


def _review_context(request, lot, evidence, digest, problems):
    return {
        "lot": lot,
        "evidence": evidence,
        "snapshot": {**evidence, "evidence_hash": digest},
        "evidence_hash": digest,
        "blockers": problems,
        "is_preview": True,
        "can_sign": has_role(request.user, services.ISSUE_ROLE),
        "conflict": ev.independence_conflict(evidence, request.user),
    }


@login_required
@require_GET
def issue_preview(request, lot_pk):
    services.require_reader(request.user)
    lot = get_object_or_404(Lot, pk=lot_pk)
    evidence, digest, problems = services.preview(lot)
    context = _review_context(request, lot, evidence, digest, problems)
    context.update(
        page_title=f"Review certificate · {lot.number}",
        reports=lot.reports.all(),
    )
    return render(request, "reporting/preview.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def issue_sign(request, lot_pk):
    services.require_role(request.user, services.ISSUE_ROLE)
    lot = get_object_or_404(Lot, pk=lot_pk)
    status = 200
    if request.method == "GET":
        evidence, digest, problems = services.preview(lot)
        refusal = preflight(request, evidence, digest, problems, "issued")
        if refusal:
            messages.warning(request, refusal)
            return redirect("reporting:issue_preview", lot_pk=lot.pk)
        form = IssueForm(initial={"evidence_hash": digest})
    else:
        form = IssueForm(request.POST)
        status = 422
        if form.is_valid():
            try:
                report = services.issue_report(actor=request.user, lot=lot, **signing_data(form))
            except PermissionDenied as exc:
                form.add_error(None, failure(exc))
                status = 403
            except ValidationError as exc:
                form.add_error(None, failure(exc))
            else:
                messages.success(request, f"{report.number} version 1 issued.")
                return redirect("reporting:detail", pk=report.pk)
    return render(
        request,
        "reporting/sign.html",
        {
            "page_title": f"Sign certificate · {lot.number}",
            "form": form,
            "lot": lot,
            "heading": "Sign and issue certificate",
            "submit": "Sign and issue certificate",
            "meaning": "issued",
            "target": f"CoA for lot {lot.number}, version 1",
            "cancel_url": reverse("reporting:issue_preview", args=[lot.pk]),
            "evidence_short": form["evidence_hash"].value()[:16]
            if form["evidence_hash"].value()
            else "",
        },
        status=status,
    )


@login_required
@require_GET
def report_detail(request, pk):
    services.require_reader(request.user)
    report = get_object_or_404(Report.objects.select_related("lot", "created_by"), pk=pk)
    versions = list(report.versions.select_related("issued_by").order_by("-number"))
    for version in versions:
        version.signature = services.signature_for(version)
    latest = versions[0] if versions else None
    history = []
    can_audit = has_role(request.user, *services.HISTORY_ROLES)
    if can_audit:
        history = AuditEvent.objects.filter(
            object_type="reporting.report", object_id=str(report.pk)
        ).select_related("actor")
    return render(
        request,
        "reporting/report_detail.html",
        {
            "page_title": report.number,
            "report": report,
            "versions": versions,
            "latest": latest,
            "snapshot": latest.snapshot if latest else None,
            "history": history,
            "can_issue": has_role(request.user, services.ISSUE_ROLE),
            "can_audit": can_audit,
        },
    )


def _amendment_context(request, report):
    latest = report.versions.order_by("-number").first()
    if latest is None:
        raise ValidationError("Only an issued certificate can be amended.")
    evidence, digest, problems = services.preview(report.lot)
    return latest, evidence, digest, problems


@login_required
@require_GET
def amend_preview(request, pk):
    services.require_reader(request.user)
    report = get_object_or_404(Report.objects.select_related("lot"), pk=pk)
    try:
        latest, evidence, digest, problems = _amendment_context(request, report)
    except ValidationError as exc:
        messages.error(request, failure(exc))
        return redirect("reporting:detail", pk=report.pk)
    previous = {k: v for k, v in latest.snapshot.items() if k not in {"report", "evidence_hash"}}
    context = _review_context(request, report.lot, evidence, digest, problems)
    context.update(
        page_title=f"Amend certificate · {report.number}",
        report=report,
        latest=latest,
        changed=ev.changed_sections(previous, evidence),
        amending=True,
    )
    return render(request, "reporting/preview.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def amend_sign(request, pk):
    services.require_role(request.user, services.ISSUE_ROLE)
    report = get_object_or_404(Report.objects.select_related("lot"), pk=pk)
    latest = report.versions.order_by("-number").first()
    if latest is None:
        messages.error(request, "Only an issued certificate can be amended.")
        return redirect("reporting:detail", pk=report.pk)
    status = 200
    if request.method == "GET":
        evidence, digest, problems = services.preview(report.lot)
        refusal = preflight(request, evidence, digest, problems, "amended")
        if refusal:
            messages.warning(request, refusal)
            return redirect("reporting:amend_preview", pk=report.pk)
        form = AmendForm(
            initial={
                "evidence_hash": digest,
                "expected_version": latest.number,
                "remarks": latest.remarks,
            }
        )
    else:
        form = AmendForm(request.POST)
        status = 422
        if form.is_valid():
            try:
                services.amend_report(actor=request.user, report=report, **signing_data(form))
            except PermissionDenied as exc:
                form.add_error(None, failure(exc))
                status = 403
            except ValidationError as exc:
                form.add_error(None, failure(exc))
            else:
                messages.success(request, f"{report.number} amended.")
                return redirect("reporting:detail", pk=report.pk)
    return render(
        request,
        "reporting/sign.html",
        {
            "page_title": f"Sign amendment · {report.number}",
            "form": form,
            "lot": report.lot,
            "report": report,
            "heading": "Sign and amend certificate",
            "submit": "Sign and amend certificate",
            "meaning": "amended",
            "target": f"{report.number}, new version {latest.number + 1}",
            "cancel_url": reverse("reporting:amend_preview", args=[report.pk]),
            "evidence_short": (form["evidence_hash"].value() or "")[:16],
        },
        status=status,
    )


def _version(pk, number):
    report = get_object_or_404(Report.objects.select_related("lot"), pk=pk)
    version = get_object_or_404(report.versions.select_related("issued_by"), number=number)
    version.report = report
    return report, version


@login_required
@require_GET
def version_detail(request, pk, number):
    services.require_reader(request.user)
    report, version = _version(pk, number)
    return render(
        request,
        "reporting/version.html",
        {
            "page_title": f"{report.number} version {version.number}",
            "report": report,
            "version": version,
            "snapshot": version.snapshot,
            "signature": services.signature_for(version),
            "is_current": version.is_current,
        },
    )


@login_required
@require_GET
def version_pdf(request, pk, number):
    report, version = _version(pk, number)
    try:
        data = services.read_pdf(actor=request.user, version=version)
    except ValidationError as exc:
        messages.error(request, failure(exc))
        return redirect("reporting:version", pk=report.pk, number=version.number)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{report.number}-v{version.number}") + ".pdf"
    disposition = "inline" if request.GET.get("inline") == "1" else "attachment"
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'{disposition}; filename="{name}"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response
