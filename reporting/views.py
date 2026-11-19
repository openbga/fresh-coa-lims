import logging
import re

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_http_methods

from core.grids import Column, paginate
from core.models import AuditEvent, ElectronicSignature
from quality import authority
from quality.models import Lot

from . import certificate_data, checks, conformity, lot_record, services
from . import evidence as ev
from .forms import (
    AmendForm,
    CheckForm,
    IssueForm,
    LotPickForm,
    LotRecordForm,
    NotificationForm,
    ScopeForm,
    WithdrawForm,
)
from .models import CertificateCheck, RecipientNotification, Report
from .render import RenderError

logger = logging.getLogger(__name__)

SORTS = {
    "number": "number",
    "lot": "lot__number",
    "material": "lot__material",
    "recipient": "recipient",
    "status": "status_rank",
    "created": "created_at",
}
STATUS_RANK = Case(
    When(state="withdrawn", then=Value(3)),
    When(~Q(state="issued"), then=Value(0)),
    When(version_count=1, then=Value(1)),
    default=Value(2),
    output_field=IntegerField(),
)
# The certificate page lists this many of the newest checks of its versions.
CHECKS_SHOWN = 20
STATUS_FILTERS = {
    "draft": Q(state="draft"),
    "issued": Q(state="issued", version_count=1),
    "amended": Q(state="issued", version_count__gt=1),
    "withdrawn": Q(state="withdrawn"),
    "awaiting_notification": Q(state="withdrawn", notified=False),
}


class ReportFilterForm(forms.Form):
    """The certificate list's status filter; the search box is the toolbar's own (q)."""

    status = forms.ChoiceField(
        label="Status",
        choices=[
            ("", "All statuses"),
            ("draft", "Not issued"),
            ("issued", "Issued"),
            ("amended", "Amended"),
            ("withdrawn", "Withdrawn"),
            ("awaiting_notification", "Awaiting notification"),
        ],
        required=False,
    )


def has_role(user, *roles):
    return user.groups.filter(name__in=roles).exists()


def signing_data(form):
    """Service arguments; the typed signing username is verified centrally, not passed on."""
    return {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}


def preflight(request, lot, evidence, digest, problems, verb):
    """Reason the signing form must not be offered, or None. POST revalidates everything."""
    if request.GET.get("evidence") != digest:
        return "The evidence changed since you reviewed it. Review it again."
    if problems:
        return f"This certificate cannot be {verb}: " + " ".join(problems)
    if ev.independence_conflict(evidence, request.user):
        return f"You authored records on this lot, so you cannot sign this certificate as {verb}."
    # A qualification the lot's rule sets reserve certificates for (rechecked under lock).
    return authority.refusal(request.user, lot, authority.CERTIFICATE) or None


def failure(exc):
    return "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)


CERTIFICATE_COLUMNS = (
    Column("certificate", "Certificate", asc="number", desc="-number", locked=True),
    Column("lot", "Lot", asc="lot", desc="-lot"),
    Column("issued_to", "Issued to", priority="medium"),
    Column("status", "Status", asc="status", desc="-status"),
)


@login_required
@require_GET
def report_list(request):
    services.require_reader(request.user)
    reports = Report.objects.select_related("lot").annotate(
        notified=Exists(RecipientNotification.objects.filter(report=OuterRef("pk")))
    )
    query = request.GET.get("q", "").strip()
    filters = ReportFilterForm(request.GET)
    if not filters.is_valid():  # an unknown status lists every certificate
        filters = ReportFilterForm()
    status = filters.cleaned_data["status"] if filters.is_bound else ""
    if query:
        reports = reports.filter(
            Q(number__icontains=query)
            | Q(lot__number__icontains=query)
            | Q(lot__material__icontains=query)
            | Q(recipient__icontains=query)
            | Q(scope__icontains=query)
        )
    if status:
        reports = reports.filter(STATUS_FILTERS[status])
    sort = request.GET.get("sort", "-created")
    key = SORTS.get(sort.lstrip("-"), "created_at")
    # Status sorts by the label shown (Not issued, Issued, Amended, Withdrawn), newest first
    # within each.
    reports = reports.annotate(status_rank=STATUS_RANK).order_by(
        ("-" if sort.startswith("-") else "") + key, "-created_at", "-id"
    )
    return render(
        request,
        "reporting/report_list.html",
        {
            "page_title": "Certificates of analysis",
            "columns": CERTIFICATE_COLUMNS,
            "page_obj": paginate(request, reports),
            "query": query,
            "filters": filters,
            "sort": sort,
            "filtered": bool(query or status),
            "can_issue": has_role(request.user, services.ISSUE_ROLE),
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


def _scope(request):
    """The scope a new certificate is reviewed or signed for, from the address ("" for all of
    the lot's requirements). Validated by the evidence gates, never trusted."""
    return request.GET.get("scope", "").strip()[:60]


def _review_context(request, lot, evidence, digest, problems, scope=""):
    return {
        "lot": lot,
        "evidence": evidence,
        "snapshot": {**evidence, "evidence_hash": digest},
        "evidence_hash": digest,
        "scope": scope,
        "scope_text": services.scope_label(scope),
        "blockers": problems,
        "is_preview": True,
        "can_sign": has_role(request.user, services.ISSUE_ROLE),
        "conflict": ev.independence_conflict(evidence, request.user),
        "unauthorized": authority.refusal(request.user, lot, authority.CERTIFICATE)
        if has_role(request.user, services.ISSUE_ROLE)
        else "",
    }


def _preview_url(lot, scope):
    url = reverse("reporting:issue_preview", args=[lot.pk])
    return f"{url}?{urlencode({'scope': scope})}" if scope else url


@login_required
@require_GET
def issue_preview(request, lot_pk):
    services.require_reader(request.user)
    lot = get_object_or_404(Lot, pk=lot_pk)
    scope = _scope(request)
    evidence, digest, problems = services.preview(lot, scope)
    context = _review_context(request, lot, evidence, digest, problems, scope)
    scopes = conformity.scopes(evidence)
    context.update(
        page_title=f"Review certificate · {lot.number}",
        reports=lot.reports.all(),
        scope_form=ScopeForm({"scope": scope}, scopes=scopes) if scopes else None,
    )
    return render(request, "reporting/preview.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def issue_sign(request, lot_pk):
    services.require_role(request.user, services.ISSUE_ROLE)
    lot = get_object_or_404(Lot, pk=lot_pk)
    status = 200
    if request.method == "GET":
        scope = _scope(request)
        evidence, digest, problems = services.preview(lot, scope)
        refusal = preflight(request, lot, evidence, digest, problems, "issued")
        if refusal:
            messages.warning(request, refusal)
            return redirect(_preview_url(lot, scope))
        form = IssueForm(initial={"evidence_hash": digest, "scope": scope})
    else:
        form = IssueForm(request.POST)
        scope = (form.data.get("scope") or "").strip()[:60]
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
            "target": f"CoA for lot {lot.number}, version 1, {services.scope_label(scope)}",
            "cancel_url": _preview_url(lot, scope),
            "relied_on": authority.notices(request.user, lot, authority.CERTIFICATE),
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
    notifications = list(report.notifications.select_related("recorded_by"))
    signatures = list(
        ElectronicSignature.objects.filter(
            object_type="reporting.report", object_id=str(report.pk)
        ).order_by("signed_at", "id")
    )
    history = []
    can_audit = has_role(request.user, *services.HISTORY_ROLES)
    if can_audit:
        history = AuditEvent.objects.filter(
            object_type="reporting.report", object_id=str(report.pk)
        ).select_related("actor")
    checked = CertificateCheck.objects.filter(version__report=report).select_related(
        "version", "checked_by"
    )
    # The rows name their version; its stored files are never needed here.
    checked = checked.defer("version__pdf", "version__data", "version__snapshot")
    recent_checks = list(checked[:CHECKS_SHOWN])
    return render(
        request,
        "reporting/report_detail.html",
        {
            "page_title": report.number,
            "report": report,
            "versions": versions,
            "latest": latest,
            "snapshot": latest.snapshot if latest else None,
            "withdrawal": next((s for s in signatures if s.meaning == "withdrawn"), None),
            "notifications": notifications,
            "awaiting_notification": report.state == "withdrawn" and not notifications,
            "signatures": signatures,
            "history": history,
            "can_issue": has_role(request.user, services.ISSUE_ROLE),
            "can_audit": can_audit,
            "checks": recent_checks,
            "check_count": checked.count(),
            # A recipient still holds the withdrawn certificate: the newest check without an
            # account that found it so (staff checks show in the table).
            "checked_withdrawn": checked.filter(
                answer=CertificateCheck.Answer.WITHDRAWN, checked_by__isnull=True
            ).first()
            if report.state == "withdrawn"
            else None,
        },
    )


def _amendment_context(request, report):
    if report.state == "withdrawn":
        raise ValidationError(services.WITHDRAWN)
    latest = report.versions.order_by("-number").first()
    if latest is None:
        raise ValidationError("Only an issued certificate can be amended.")
    evidence, digest, problems = services.preview(report.lot, report.scope)
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
    context = _review_context(request, report.lot, evidence, digest, problems, report.scope)
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
    if report.state == "withdrawn":
        messages.error(request, services.WITHDRAWN)
        return redirect("reporting:detail", pk=report.pk)
    if latest is None:
        messages.error(request, "Only an issued certificate can be amended.")
        return redirect("reporting:detail", pk=report.pk)
    status = 200
    if request.method == "GET":
        evidence, digest, problems = services.preview(report.lot, report.scope)
        refusal = preflight(request, report.lot, evidence, digest, problems, "amended")
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
            "target": f"{report.number}, new version {latest.number + 1}, "
            f"{services.scope_label(report.scope)}",
            "cancel_url": reverse("reporting:amend_preview", args=[report.pk]),
            "relied_on": authority.notices(request.user, report.lot, authority.CERTIFICATE),
            "evidence_short": (form["evidence_hash"].value() or "")[:16],
        },
        status=status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def withdraw(request, pk):
    """Sign the withdrawal of an issued certificate. Opening the page never signs."""
    services.require_role(request.user, services.ISSUE_ROLE)
    report = get_object_or_404(Report.objects.select_related("lot"), pk=pk)
    detail = reverse("reporting:detail", args=[report.pk])
    form = WithdrawForm(request.POST or None, initial={"expected_revision": report.revision})
    context = {
        "page_title": f"Withdraw certificate · {report.number}",
        "report": report,
        "latest": report.versions.select_related("issued_by").order_by("-number").first(),
        "form": form,
        "cancel_url": detail,
        "denial": services.withdraw_refusal(report),
    }
    if context["denial"]:
        return render(request, "reporting/withdraw.html", context, status=403)
    status = 200
    if request.method == "POST":
        status = 422
        if form.is_valid():
            try:
                services.withdraw_report(
                    actor=request.user,
                    pin=form.cleaned_data["pin"],
                    report=report,
                    expected_revision=form.cleaned_data["expected_revision"],
                    reason=form.cleaned_data["reason"],
                    reference=form.cleaned_data["reference"],
                )
            except PermissionDenied as exc:
                context["denial"] = str(exc) or "This action is not permitted for you."
                return render(request, "reporting/withdraw.html", context, status=403)
            except ValidationError as exc:
                form.add_error(None, failure(exc))
            else:
                messages.success(
                    request,
                    f"{report.number} withdrawn; every issued version is kept. Record the "
                    "notification of its recipient.",
                )
                return redirect(detail)
    return render(request, "reporting/withdraw.html", context, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def notify(request, pk):
    """Record that a recipient was told that the certificate is withdrawn."""
    services.require_role(request.user, services.ISSUE_ROLE)
    report = get_object_or_404(Report.objects.select_related("lot"), pk=pk)
    detail = reverse("reporting:detail", args=[report.pk])
    if request.method != "POST" and report.state != "withdrawn":
        messages.error(request, services.NOT_WITHDRAWN)
        return redirect(detail)
    form = NotificationForm(request.POST or None, initial={"recipient": report.recipient})
    if request.method == "POST" and form.is_valid():
        try:
            services.record_notification(actor=request.user, report=report, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Notification of {form.cleaned_data['recipient']} recorded.")
            return redirect(detail)
    return render(
        request,
        "reporting/notify.html",
        {
            "page_title": "Record notification",
            "report": report,
            "withdrawal": services.withdrawal_signature(report),
            "form": form,
            "cancel_url": detail,
        },
        status=422 if request.method == "POST" and form.errors else 200,
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
            "authorization": authority.describe(
                (version.snapshot.get("report") or {}).get(authority.AUTHORIZATION),
                authority.CERTIFICATE,
            ),
            "is_current": version.is_current,
            "withdrawal": services.withdrawal_signature(report),
        },
    )


@login_required
@require_GET
def version_pdf(request, pk, number):
    services.require_reader(request.user)  # before the lookup: refusal must not reveal existence
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


@login_required
@require_GET
def version_data(request, pk, number):
    """The certificate data issued with a version: the bytes embedded in its PDF."""
    services.require_reader(request.user)  # before the lookup: refusal must not reveal existence
    report, version = _version(pk, number)
    try:
        data = services.read_data(actor=request.user, version=version)
    except ValidationError as exc:
        messages.error(request, failure(exc))
        return redirect("reporting:version", pk=report.pk, number=version.number)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{report.number}-v{version.number}") + ".json"
    response = HttpResponse(data, content_type=f"{certificate_data.MEDIA_TYPE}; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def lot_record_export(request, pk):
    """Offer, then download, the lot's complete record as one package."""
    lot_record.require_exporter(request.user)
    lot = get_object_or_404(Lot, pk=pk)
    form = LotRecordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            package = lot_record.export_lot_record(
                actor=request.user, lot_pk=lot.pk, purpose=form.cleaned_data["purpose"]
            )
        except lot_record.ExportError as exc:
            form.add_error(None, f"The record could not be exported: {exc}")
        except RenderError:
            logger.exception("The printed copy of lot %s could not be rendered", lot.pk)
            form.add_error(
                None,
                "The record could not be exported: its printed copy could not be produced. "
                "Nothing was recorded. Try again; if it fails again, tell your administrator.",
            )
        else:
            response = FileResponse(
                package.file,
                as_attachment=True,
                filename=package.filename,
                content_type="application/zip",
            )
            response["Content-Length"] = str(package.size)
            response["Cache-Control"] = "no-store, private"
            response["X-Content-Type-Options"] = "nosniff"
            return response
    return render(
        request,
        "reporting/lot_record.html",
        {
            "page_title": f"Export record · {lot.number}",
            "lot": lot,
            "form": form,
            "summary": lot_record.summarize(lot),
        },
        status=422 if form.errors else 200,
    )


def _hash_uploads(request):
    """Receive the files of this request as their SHA-256 only (reporting.checks). Must run
    before anything reads the body, so the views that call it are exempt from the CSRF
    middleware and check the token themselves, after it (Django's documented pattern)."""
    if request.method == "POST":
        request.upload_handlers = [checks.HashingUploadHandler(request)]


def _checked(request, actor):
    """The bound or unbound check form and, once it is valid, what the check found."""
    from core.uploads import size_text

    if request.method != "POST":
        return CheckForm(), None
    # Reading the files receives them; HashingUploadHandler stops one over the limit.
    files = request.FILES
    refused = (
        f"The file is larger than the limit of {size_text(checks.max_bytes())}. "
        "No issued certificate is that large."
        if getattr(request, "upload_too_large", False)
        else ""
    )
    form = CheckForm(request.POST, files, refused_file=refused)
    if not form.is_valid():
        return form, None
    return form, checks.check(form.cleaned_data["digest"], actor=actor)


@csrf_exempt  # the token is checked by _check_page, once the upload handlers are in place
@login_required
@require_http_methods(["GET", "POST"])
def check(request):
    """Check a certificate file, or its SHA-256, against every issued version (signed in)."""
    services.require_reader(request.user)
    _hash_uploads(request)
    return _check_page(request)


@csrf_protect
def _check_page(request):
    form, result = _checked(request, request.user)
    response = render(
        request,
        "reporting/check.html",
        {
            "page_title": "Check a certificate",
            "form": form,
            "result": result,
            "public_check": settings.CERTIFICATE_CHECK,
            "public_url": request.build_absolute_uri(reverse("certificate_check")),
        },
        status=422 if form.errors else 200,
    )
    response["Cache-Control"] = "no-store, private"
    return response


@csrf_exempt  # the token is checked by _public_check_page, after the rate limit
@require_http_methods(["GET", "POST"])
def public_check(request):
    """The check without an account, where the deployment offers it (CERTIFICATE_CHECK).

    A POST takes one of the deployment's checks of the minute before its body is read; past the
    limit it is answered 429 with the time to wait. No session is started: the page reads and
    writes nothing of the visitor apart from the CSRF cookie."""
    if not settings.CERTIFICATE_CHECK:
        raise Http404
    if request.method == "POST" and _cross_site(request):
        # Another site's page cannot make its visitors' browsers use up the minute's checks.
        raise PermissionDenied("A certificate is checked from this site's own page.")
    if request.method == "POST" and (wait := checks.take_slot()):
        response = _public_response(request, CheckForm(), None, status=429, wait=wait)
        response["Retry-After"] = str(wait)
        return response
    _hash_uploads(request)
    return _public_check_page(request)


def _cross_site(request):
    """A POST another site's page sent: the browser says so, or names another origin."""
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        return True
    origin = request.headers.get("Origin")
    if origin is None:
        return False
    own = f"{request.scheme}://{request.get_host()}"
    return origin != own and origin not in settings.CSRF_TRUSTED_ORIGINS


@csrf_protect
def _public_check_page(request):
    # Someone signed in who reads certificates is named on the check, as on the staff page.
    user = request.user
    reader = user.is_authenticated and has_role(user, *services.READ_ROLES) and user.is_active
    form, result = _checked(request, user if reader else None)
    return _public_response(request, form, result, status=422 if form.errors else 200)


def _public_response(request, form, result, *, status, wait=0):
    response = render(
        request,
        "reporting/check_public.html",
        {"form": form, "result": result, "wait": wait},
        status=status,
    )
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex"
    return response
