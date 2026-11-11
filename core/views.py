import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import PINForm, RuleForm, SignForm
from .models import AuditEvent, ElectronicSignature, RuleSet
from .services import (
    approve_rule,
    check_rule_approval,
    require_role,
    review_audit,
    save_rule,
    set_pin,
)


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
    if request.method == "POST":
        require_role(request.user, "quality")
    can_configure = request.user.groups.filter(name="quality").exists()
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
    return render(
        request,
        "core/rules.html",
        {"rules": revisions, "form": form, "can_configure": can_configure},
    )


@login_required
@require_http_methods(["GET", "POST"])
def rule_approve(request, pk):
    require_role(request.user, "quality")
    rule = get_object_or_404(RuleSet, pk=pk)
    if request.method == "GET":
        try:
            check_rule_approval(actor=request.user, rule=rule)
        except (PermissionDenied, ValidationError) as exc:
            reason = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.warning(request, reason)
            return redirect("core:rules")
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
    import uuid

    from django import forms
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from django.core.paginator import Paginator
    from django.db.models import Prefetch
    from django.urls import reverse

    from .models import AuditReview

    require_role(request.user, "admin", "quality", "auditor")
    can_review = request.user.groups.filter(name__in=["quality", "auditor"]).exists()
    if request.method == "POST":
        require_role(request.user, "quality", "auditor")

    class AuditFilters(forms.Form):
        object_type = forms.CharField(required=False, label="Record type", max_length=100)
        object_id = forms.CharField(required=False, label="Record ID", max_length=64)
        actor = forms.ModelChoiceField(
            required=False,
            empty_label="All actors",
            queryset=get_user_model()
            .objects.filter(auditevent__isnull=False)
            .distinct()
            .order_by("username"),
        )
        action = forms.ChoiceField(
            required=False,
            choices=[("", "All actions")]
            + [
                (value, value)
                for value in AuditEvent.objects.order_by("action")
                .values_list("action", flat=True)
                .distinct()
            ],
        )
        date_from = forms.DateField(
            required=False, label="From date", widget=forms.DateInput(attrs={"type": "date"})
        )
        date_to = forms.DateField(
            required=False, label="Through date", widget=forms.DateInput(attrs={"type": "date"})
        )

        def clean(self):
            values = super().clean()
            if (
                values.get("date_from")
                and values.get("date_to")
                and values["date_from"] > values["date_to"]
            ):
                raise forms.ValidationError("From date must be on or before through date.")
            return values

    filters = AuditFilters(request.GET)
    for field in filters.fields.values():
        field.widget.attrs["class"] = (
            "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        )
    events = AuditEvent.objects.select_related("actor").order_by("-occurred_at", "-id")
    valid_filters = filters.is_valid()
    if valid_filters:
        values = filters.cleaned_data
        for field in ("object_type", "object_id", "actor", "action"):
            if values[field]:
                events = events.filter(**{field: values[field]})
        if values["date_from"]:
            events = events.filter(occurred_at__date__gte=values["date_from"])
        if values["date_to"]:
            events = events.filter(occurred_at__date__lte=values["date_to"])
    else:
        events = events.none()

    params = request.GET.copy()
    params.pop("export", None)
    params.pop("page", None)
    base_query = params.urlencode()
    page = Paginator(
        events.prefetch_related(
            Prefetch(
                "auditreview_set",
                queryset=AuditReview.objects.select_related("reviewer").order_by(
                    "-reviewed_at", "-pk"
                ),
                to_attr="reviews",
            )
        ),
        50,
    ).get_page(request.GET.get("page"))
    error = ""
    conclusion = request.POST.get("conclusion", "")
    selected_ids = request.POST.getlist("events")
    if request.method == "POST":
        try:
            if not valid_filters:
                raise ValidationError("Correct the filters before recording a review.")
            if not selected_ids or len(selected_ids) > 50:
                raise ValidationError("Select between 1 and 50 events on this page.")
            selected = {str(uuid.UUID(value)) for value in selected_ids}
            visible = {str(event.pk) for event in page}
            if not selected.issubset(visible) or len(selected) != len(selected_ids):
                raise ValidationError("Select only the events displayed on this page.")
            review_audit(actor=request.user, event_ids=list(selected), conclusion=conclusion)
            messages.success(request, f"Independent review recorded for {len(selected)} events.")
            params["page"] = page.number
            return redirect(f"{reverse('core:audit')}?{params.urlencode()}")
        except (ValidationError, PermissionDenied, ValueError) as exc:
            error = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)

    if request.method == "GET" and request.GET.get("export") == "csv" and valid_filters:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit.csv"'
        writer = csv.writer(response)
        writer.writerow(["ID", "Time", "Actor", "Action", "Record", "Before", "After", "Reason"])
        for event in events.iterator():
            row = [
                str(event.pk),
                str(event.occurred_at),
                event.actor.username,
                event.action,
                f"{event.object_type}:{event.object_id}",
                str(event.before),
                str(event.after),
                event.reason,
            ]
            writer.writerow(
                ["'" + value if value.startswith(("=", "+", "-", "@")) else value for value in row]
            )
        return response
    return render(
        request,
        "core/audit.html",
        {
            "page": page,
            "can_review": can_review,
            "filters": filters,
            "error": error,
            "conclusion": conclusion,
            "selected_ids": selected_ids,
            "base_query": base_query,
            "filtered": any(request.GET.get(key) for key in filters.fields),
        },
        status=422 if error or not valid_filters else 200,
    )
