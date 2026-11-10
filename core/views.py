import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import PINForm, RuleForm, SignForm
from .models import AuditEvent, ElectronicSignature, RuleSet
from .services import approve_rule, require_role, review_audit, save_rule, set_pin


@login_required
@require_http_methods(["GET", "POST"])
def pin(request):
    form = PINForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            set_pin(actor=request.user, **form.cleaned_data)
            messages.success(request, "Signature PIN saved.")
            return redirect("core:pin")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "core/form.html", {"form": form, "heading": "Signature PIN"})


@login_required
@require_http_methods(["GET", "POST"])
def rules(request):
    require_role(request.user, "admin", "quality", "analyst", "reviewer", "auditor")
    form = RuleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            save_rule(actor=request.user, **form.cleaned_data)
            return redirect("core:rules")
        except ValidationError as exc:
            form.add_error(None, exc)
    revisions = list(RuleSet.objects.all())
    signatures = ElectronicSignature.objects.filter(object_type="core.ruleset")
    by_record = {}
    for signature in signatures:
        by_record.setdefault(signature.object_id, []).append(signature)
    for revision in revisions:
        revision.signatures = by_record.get(str(revision.pk), [])
    return render(request, "core/rules.html", {"rules": revisions, "form": form})


@login_required
@require_http_methods(["GET", "POST"])
def rule_approve(request, pk):
    require_role(request.user, "quality")
    rule = get_object_or_404(RuleSet, pk=pk)
    form = SignForm(request.POST or None, initial={"revision": rule.revision})
    if request.method == "POST" and form.is_valid():
        try:
            approve_rule(
                actor=request.user,
                rule=rule,
                pin=form.cleaned_data["pin"],
                expected_revision=form.cleaned_data["revision"],
                reason=form.cleaned_data["reason"],
            )
            return redirect("core:rules")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request,
        "core/form.html",
        {"form": form, "heading": f"Approve {rule}", "signing": True, "record": rule},
    )


@login_required
@require_http_methods(["GET", "POST"])
def audit(request):
    require_role(request.user, "quality", "auditor")
    events = AuditEvent.objects.select_related("actor").order_by("-occurred_at", "-id")
    if request.GET.get("object_type"):
        events = events.filter(object_type=request.GET["object_type"])
    if request.GET.get("object_id"):
        events = events.filter(object_id=request.GET["object_id"])
    error = ""
    if request.method == "POST":
        try:
            review_audit(
                actor=request.user,
                event_ids=request.POST.getlist("events"),
                conclusion=request.POST.get("conclusion", ""),
            )
            messages.success(request, "Audit review recorded.")
            return redirect("core:audit")
        except (ValidationError, ValueError) as exc:
            error = str(exc)
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit.csv"'
        writer = csv.writer(response)
        writer.writerow(["ID", "Time", "Actor", "Action", "Record", "Before", "After", "Reason"])
        for e in events.iterator():
            # Neutralize spreadsheet formula interpretation in user-entered strings.
            row = [
                str(e.pk),
                str(e.occurred_at),
                e.actor.username,
                e.action,
                f"{e.object_type}:{e.object_id}",
                str(e.before),
                str(e.after),
                e.reason,
            ]
            writer.writerow(["'" + v if v.startswith(("=", "+", "-", "@")) else v for v in row])
        return response
    from django.core.paginator import Paginator

    page = Paginator(events, 50).get_page(request.GET.get("page"))
    return render(request, "core/audit.html", {"page": page, "error": error})
