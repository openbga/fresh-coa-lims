from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.services import require_role

from . import services
from .forms import (
    MaterialForm,
    MethodForm,
    MethodRevisionForm,
    QCCheckForm,
    ReasonForm,
    SpecificationForm,
    SpecificationRevisionForm,
    TestLineForm,
)
from .models import (
    Material,
    Method,
    MethodQCCheck,
    MethodRevision,
    RevisionStatus,
    Specification,
    SpecificationRevision,
    SpecificationTest,
    Stage,
)
from .web import (
    approve_page,
    can,
    form_status,
    history,
    page,
    read_access,
    run,
    signatures,
    sorted_by,
    withdraw_page,
)

SECTION = "Specifications and methods"


def tabs(request, current):
    items = [
        ("Specifications", reverse("catalog:specifications")),
        ("Methods", reverse("catalog:methods")),
        ("Materials", reverse("catalog:materials")),
    ]
    return [{"label": label, "url": url, "current": label == current} for label, url in items]


def crumbs_for(*trail):
    return [(SECTION, reverse("catalog:specifications")), *trail]


def form_page(request, form, *, title, crumbs, cancel_url, submit_label, intro="", facts=None):
    return render(
        request,
        "catalog/form.html",
        {
            "page_title": title,
            "form": form,
            "crumbs": crumbs,
            "cancel_url": cancel_url,
            "submit_label": submit_label,
            "intro": intro,
            "facts": facts or [],
        },
        status=form_status(request, form),
    )


# Specifications --------------------------------------------------------------------------------


@login_required
def specification_list(request):
    read_access(request)
    specs = Specification.objects.select_related("material").annotate(
        versions=Count("revisions"),
        approved=Count("revisions", filter=Q(revisions__status="approved")),
        drafts=Count("revisions", filter=Q(revisions__status="draft")),
        latest=Max("revisions__version"),
    )
    query = request.GET.get("q", "").strip()
    stage = request.GET.get("stage", "")
    if query:
        specs = specs.filter(
            Q(code__icontains=query)
            | Q(title__icontains=query)
            | Q(material__code__icontains=query)
        )
    if stage in Stage.values:
        specs = specs.filter(stage=stage)
    else:
        stage = ""
    specs, sort = sorted_by(
        request,
        specs,
        {
            "code": ["code"],
            "-code": ["-code"],
            "material": ["material__code", "code"],
            "-material": ["-material__code", "code"],
        },
        "code",
    )
    return render(
        request,
        "catalog/specification_list.html",
        {
            "page_title": SECTION,
            "tabs": tabs(request, "Specifications"),
            "page_obj": page(request, specs),
            "query": query,
            "stage": stage,
            "stages": Stage.choices,
            "sort": sort,
            "filtered": bool(query or stage),
            "can_edit": can(request.user, services.AUTHOR_ROLE),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def specification_new(request):
    require_role(request.user, services.AUTHOR_ROLE)
    form = SpecificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        created = run(form, lambda: services.create_specification(actor=request.user, **data))
        if created:
            messages.success(request, "Specification created as draft version 1. Add its tests.")
            return redirect("catalog:specification_revision", pk=created[1].pk)
    return form_page(
        request,
        form,
        title="New specification",
        crumbs=crumbs_for(("New specification", None)),
        cancel_url=reverse("catalog:specifications"),
        submit_label="Create draft",
        intro="One specification covers one material at one stage for one scope. "
        "Version 1 starts as a draft; add tests, then ask another quality approver to sign it.",
    )


@login_required
def specification_detail(request, pk):
    read_access(request)
    spec = get_object_or_404(Specification.objects.select_related("material"), pk=pk)
    revisions = list(spec.revisions.select_related("author").annotate(test_count=Count("tests")))
    sigs = list(signatures(*revisions))
    for revision in revisions:
        revision.signature_list = [s for s in sigs if s.object_id == str(revision.pk)]
    return render(
        request,
        "catalog/specification_detail.html",
        {
            "page_title": spec.code,
            "spec": spec,
            "revisions": revisions,
            "history": history(spec, *revisions),
            "crumbs": crumbs_for((spec.code, None)),
            "can_edit": can(request.user, services.AUTHOR_ROLE),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def specification_version_new(request, pk):
    require_role(request.user, services.AUTHOR_ROLE)
    spec = get_object_or_404(Specification, pk=pk)
    form = SpecificationRevisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        revision = run(
            form,
            lambda: services.new_specification_revision(
                actor=request.user, specification=spec, **form.cleaned_data
            ),
        )
        if revision:
            messages.success(request, f"Draft {revision} created from the latest version.")
            return redirect("catalog:specification_revision", pk=revision.pk)
    detail = reverse("catalog:specification", args=[spec.pk])
    return form_page(
        request,
        form,
        title=f"New version of {spec.code}",
        crumbs=crumbs_for((spec.code, detail), ("New version", None)),
        cancel_url=detail,
        submit_label="Create draft version",
        intro="The new draft copies the tests of the latest version. Its effective period must "
        "not overlap an approved version when it is approved.",
    )


@login_required
def specification_revision(request, pk):
    read_access(request)
    revision = get_object_or_404(
        SpecificationRevision.objects.select_related("specification__material", "author"), pk=pk
    )
    spec = revision.specification
    is_draft = revision.status == RevisionStatus.DRAFT
    can_edit = can(request.user, services.AUTHOR_ROLE)
    independent = True
    if is_draft and can_edit:
        try:
            services.ensure_independent(request.user, revision)
        except PermissionDenied:
            independent = False
    return render(
        request,
        "catalog/specification_revision.html",
        {
            "page_title": str(revision),
            "revision": revision,
            "spec": spec,
            "tests": revision.tests.select_related("method", "created_by"),
            "signatures": signatures(revision),
            "history": history(revision),
            "is_draft": is_draft,
            "can_edit": can_edit and is_draft,
            "can_approve": can_edit and is_draft and independent,
            "crumbs": crumbs_for(
                (spec.code, reverse("catalog:specification", args=[spec.pk])),
                (f"Version {revision.version}", None),
            ),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def test_new(request, pk):
    require_role(request.user, services.AUTHOR_ROLE)
    revision = get_object_or_404(SpecificationRevision, pk=pk)
    back = reverse("catalog:specification_revision", args=[revision.pk])
    if revision.status != RevisionStatus.DRAFT:
        messages.error(request, "Tests can only be added to a draft version.")
        return redirect(back)
    form = TestLineForm(request.POST or None, initial={"position": revision.tests.count() + 1})
    if request.method == "POST" and form.is_valid():
        line = run(
            form,
            lambda: services.add_test_line(
                actor=request.user, revision=revision, **form.cleaned_data
            ),
        )
        if line:
            messages.success(request, f"Test {line.code} added to {revision}.")
            return redirect(back)
    return form_page(
        request,
        form,
        title=f"Add test · {revision}",
        crumbs=crumbs_for(
            (
                revision.specification.code,
                reverse("catalog:specification", args=[revision.specification_id]),
            ),
            (f"Version {revision.version}", back),
            ("Add test", None),
        ),
        cancel_url=back,
        submit_label="Add test",
        intro="Numeric tests need a unit and at least one limit; qualitative tests need the "
        "expected result. Values are stored exactly as entered decimals.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def test_remove(request, pk, line_pk):
    require_role(request.user, services.AUTHOR_ROLE)
    line = get_object_or_404(
        SpecificationTest.objects.select_related("specification_revision__specification"),
        pk=line_pk,
        specification_revision_id=pk,
    )
    revision = line.specification_revision
    back = reverse("catalog:specification_revision", args=[revision.pk])
    if revision.status != RevisionStatus.DRAFT:
        messages.error(request, "Tests can only be removed from a draft version.")
        return redirect(back)
    form = ReasonForm(request.POST or None, initial={"expected_revision": revision.revision})
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["expected_revision"] != revision.revision:
            form.add_error(None, "Record changed. Reload before removing this test.")
        elif run(
            form,
            lambda: services.remove_test_line(
                actor=request.user, line=line, reason=form.cleaned_data["reason"]
            ),
        ):
            messages.success(request, f"Test {line.code} removed from draft {revision}.")
            return redirect(back)
    return form_page(
        request,
        form,
        title=f"Remove test {line.code} · {revision}",
        crumbs=crumbs_for(
            (
                revision.specification.code,
                reverse("catalog:specification", args=[revision.specification_id]),
            ),
            (f"Version {revision.version}", back),
            (f"Remove {line.code}", None),
        ),
        cancel_url=back,
        submit_label="Remove test",
        intro="Removal from a draft is recorded in its history with your reason.",
        facts=[("Test", str(line)), ("Criterion", line.limit_text), ("Method", line.method.code)],
    )


@login_required
@require_http_methods(["GET", "POST"])
def specification_approve(request, pk):
    revision = get_object_or_404(
        SpecificationRevision.objects.select_related("specification__material", "author"), pk=pk
    )
    back = reverse("catalog:specification_revision", args=[revision.pk])
    return approve_page(
        request,
        revision,
        kind="Specification",
        crumbs=crumbs_for(
            (
                revision.specification.code,
                reverse("catalog:specification", args=[revision.specification_id]),
            ),
            (f"Version {revision.version}", back),
            ("Approve", None),
        ),
        success_url=back,
        detail_template="catalog/includes/specification_content.html",
    )


@login_required
@require_http_methods(["GET", "POST"])
def specification_withdraw(request, pk):
    revision = get_object_or_404(SpecificationRevision, pk=pk)
    back = reverse("catalog:specification_revision", args=[revision.pk])
    return withdraw_page(
        request,
        revision,
        kind="Specification",
        crumbs=crumbs_for(
            (
                revision.specification.code,
                reverse("catalog:specification", args=[revision.specification_id]),
            ),
            (f"Version {revision.version}", back),
            ("Withdraw", None),
        ),
        success_url=back,
    )


# Methods ---------------------------------------------------------------------------------------


@login_required
def method_list(request):
    read_access(request)
    methods = Method.objects.annotate(
        versions=Count("revisions"),
        approved=Count("revisions", filter=Q(revisions__status="approved")),
        drafts=Count("revisions", filter=Q(revisions__status="draft")),
    )
    query = request.GET.get("q", "").strip()
    if query:
        methods = methods.filter(Q(code__icontains=query) | Q(title__icontains=query))
    methods, sort = sorted_by(request, methods, {"code": ["code"], "-code": ["-code"]}, "code")
    return render(
        request,
        "catalog/method_list.html",
        {
            "page_title": SECTION,
            "tabs": tabs(request, "Methods"),
            "page_obj": page(request, methods),
            "query": query,
            "sort": sort,
            "filtered": bool(query),
            "can_edit": can(request.user, services.AUTHOR_ROLE),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def method_new(request):
    require_role(request.user, services.AUTHOR_ROLE)
    form = MethodForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        created = run(form, lambda: services.create_method(actor=request.user, **form.cleaned_data))
        if created:
            messages.success(request, "Method created with draft version 1.")
            return redirect("catalog:method", pk=created[0].pk)
    return form_page(
        request,
        form,
        title="New method",
        crumbs=crumbs_for(("Methods", reverse("catalog:methods")), ("New method", None)),
        cancel_url=reverse("catalog:methods"),
        submit_label="Create draft",
        intro="Link the controlled procedure and the evidence that the method is suitable for its "
        "intended use. Another quality approver signs the version before tests can rely on it.",
    )


@login_required
def method_detail(request, pk):
    read_access(request)
    method = get_object_or_404(Method, pk=pk)
    revisions = list(method.revisions.select_related("author").prefetch_related("qc_checks"))
    sigs = list(signatures(*revisions))
    can_edit = can(request.user, services.AUTHOR_ROLE)
    for revision in revisions:
        revision.signature_list = [s for s in sigs if s.object_id == str(revision.pk)]
        revision.can_approve = False
        if can_edit and revision.status == RevisionStatus.DRAFT:
            try:
                services.ensure_independent(request.user, revision)
                revision.can_approve = True
            except PermissionDenied:
                pass
    return render(
        request,
        "catalog/method_detail.html",
        {
            "page_title": method.code,
            "method": method,
            "revisions": revisions,
            "history": history(method, *revisions),
            "crumbs": crumbs_for(("Methods", reverse("catalog:methods")), (method.code, None)),
            "can_edit": can_edit,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def method_version_new(request, pk):
    require_role(request.user, services.AUTHOR_ROLE)
    method = get_object_or_404(Method, pk=pk)
    form = MethodRevisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        revision = run(
            form,
            lambda: services.new_method_revision(
                actor=request.user, method=method, **form.cleaned_data
            ),
        )
        if revision:
            messages.success(request, f"Draft {revision} created.")
            return redirect("catalog:method", pk=method.pk)
    detail = reverse("catalog:method", args=[method.pk])
    return form_page(
        request,
        form,
        title=f"New version of {method.code}",
        crumbs=crumbs_for(
            ("Methods", reverse("catalog:methods")), (method.code, detail), ("New version", None)
        ),
        cancel_url=detail,
        submit_label="Create draft version",
    )


def _method_crumbs(revision, action):
    detail = reverse("catalog:method", args=[revision.method_id])
    return detail, crumbs_for(
        ("Methods", reverse("catalog:methods")),
        (revision.method.code, detail),
        (f"Version {revision.version} · {action}", None),
    )


@login_required
@require_http_methods(["GET", "POST"])
def method_approve(request, pk):
    revision = get_object_or_404(MethodRevision.objects.select_related("method", "author"), pk=pk)
    detail, crumbs = _method_crumbs(revision, "Approve")
    return approve_page(
        request,
        revision,
        kind="Method",
        crumbs=crumbs,
        success_url=detail,
        detail_template="catalog/includes/method_content.html",
    )


@login_required
@require_http_methods(["GET", "POST"])
def method_withdraw(request, pk):
    revision = get_object_or_404(MethodRevision.objects.select_related("method"), pk=pk)
    detail, crumbs = _method_crumbs(revision, "Withdraw")
    return withdraw_page(request, revision, kind="Method", crumbs=crumbs, success_url=detail)


@login_required
@require_http_methods(["GET", "POST"])
def qc_check_new(request, pk):
    require_role(request.user, services.AUTHOR_ROLE)
    revision = get_object_or_404(MethodRevision.objects.select_related("method"), pk=pk)
    detail, crumbs = _method_crumbs(revision, "Add QC check")
    if revision.status != RevisionStatus.DRAFT or not revision.requires_batch:
        messages.error(request, "QC checks can only be added to a draft batch method version.")
        return redirect(detail)
    form = QCCheckForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        check = run(
            form,
            lambda: services.add_qc_check(
                actor=request.user, revision=revision, **form.cleaned_data
            ),
        )
        if check:
            messages.success(request, f"QC check {check.code} added to {revision}.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Add QC check · {revision}",
        crumbs=crumbs,
        cancel_url=detail,
        submit_label="Add QC check",
        intro="Each analytical batch run with this method must record these checks within limits.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def qc_check_remove(request, pk, check_pk):
    require_role(request.user, services.AUTHOR_ROLE)
    check = get_object_or_404(
        MethodQCCheck.objects.select_related("method_revision__method"),
        pk=check_pk,
        method_revision_id=pk,
    )
    revision = check.method_revision
    detail, crumbs = _method_crumbs(revision, f"Remove {check.code}")
    if revision.status != RevisionStatus.DRAFT:
        messages.error(request, "QC checks can only be removed from a draft version.")
        return redirect(detail)
    form = ReasonForm(request.POST or None, initial={"expected_revision": revision.revision})
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["expected_revision"] != revision.revision:
            form.add_error(None, "Record changed. Reload before removing this QC check.")
        elif run(
            form,
            lambda: services.remove_qc_check(
                actor=request.user, check=check, reason=form.cleaned_data["reason"]
            ),
        ):
            messages.success(request, f"QC check {check.code} removed from draft {revision}.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Remove QC check {check.code} · {revision}",
        crumbs=crumbs,
        cancel_url=detail,
        submit_label="Remove QC check",
        intro="Removal from a draft is recorded in its history with your reason.",
        facts=[("QC check", str(check)), ("Unit", check.unit)],
    )


# Materials -------------------------------------------------------------------------------------


@login_required
def material_list(request):
    read_access(request)
    materials = Material.objects.annotate(spec_count=Count("specifications"))
    query = request.GET.get("q", "").strip()
    if query:
        materials = materials.filter(Q(code__icontains=query) | Q(name__icontains=query))
    materials, sort = sorted_by(
        request,
        materials,
        {"code": ["code"], "-code": ["-code"], "name": ["name"], "-name": ["-name"]},
        "code",
    )
    return render(
        request,
        "catalog/material_list.html",
        {
            "page_title": SECTION,
            "tabs": tabs(request, "Materials"),
            "page_obj": page(request, materials),
            "query": query,
            "sort": sort,
            "filtered": bool(query),
            "can_edit": can(request.user, services.AUTHOR_ROLE),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def material_new(request):
    require_role(request.user, services.AUTHOR_ROLE)
    form = MaterialForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        material = run(
            form, lambda: services.create_material(actor=request.user, **form.cleaned_data)
        )
        if material:
            messages.success(request, f"Material {material.code} created.")
            return redirect("catalog:materials")
    return form_page(
        request,
        form,
        title="New material",
        crumbs=crumbs_for(("Materials", reverse("catalog:materials")), ("New material", None)),
        cancel_url=reverse("catalog:materials"),
        submit_label="Create material",
        intro="Material identity cannot be edited after creation; use synthetic names only.",
    )
