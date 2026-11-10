from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.models import AuditEvent, ElectronicSignature
from core.services import require_role
from quality.models import Lot, Sample

from . import gates, services
from .contracts import batch_methods
from .forms import (
    BatchAssignForm,
    BatchForm,
    ConcludeForm,
    CorrectionForm,
    EntryForm,
    ObservationForm,
    ReasonForm,
    RetestForm,
    RevisionReasonForm,
    SigningForm,
)
from .models import AnalyticalTest, Investigation, Observation, QCBatch, QCResult

READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
PAGE_SIZE = 30


def query_params(request):
    """Current filters without the page number, ready for '?{{ params }}page=N'."""
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode() + "&" if params else ""


def access(user):
    require_role(user, *READ_ROLES)


def roles(user):
    return set(user.groups.values_list("name", flat=True))


def perform(form, action):
    try:
        return action()
    except ValidationError as exc:
        form.add_error(None, " ".join(exc.messages))
        return None


def history(*objects):
    query = Q()
    for obj in objects:
        query |= Q(object_type=obj._meta.label_lower, object_id=str(obj.pk))
    return AuditEvent.objects.filter(query).select_related("actor").order_by("occurred_at", "pk")


def signatures(*objects):
    query = Q()
    for obj in objects:
        query |= Q(object_type=obj._meta.label_lower, object_id=str(obj.pk))
    return ElectronicSignature.objects.filter(query).order_by("signed_at", "pk")


def tabs(request, current):
    return [
        {"label": label, "url": reverse(name), "current": name == current}
        for label, name in [
            ("Tests", "analytical:test_list"),
            ("QC batches", "analytical:batch_list"),
            ("Investigations", "analytical:investigation_list"),
        ]
    ]


def unavailable(request, message, url):
    """Refuse an action page for a record in the wrong state; the service rechecks on submit."""
    messages.warning(request, message)
    return redirect(url)


def action_page(request, form, *, title, submit, crumbs, cancel_url, record=None, summary=None):
    return render(
        request,
        "analytical/form.html",
        {
            "page_title": title,
            "form": form,
            "submit_label": submit,
            "crumbs": crumbs,
            "cancel_url": cancel_url,
            "record": record,
            "summary": summary or [],
        },
        status=422 if request.method == "POST" else 200,
    )


def sign_page(
    request, form, *, title, submit, meaning, record, record_label, crumbs, cancel_url, summary
):
    return render(
        request,
        "analytical/sign.html",
        {
            "page_title": title,
            "form": form,
            "submit_label": submit,
            "meaning": meaning,
            "record": record,
            "record_label": record_label,
            "crumbs": crumbs,
            "cancel_url": cancel_url,
            "summary": summary,
        },
        status=422 if request.method == "POST" else 200,
    )


# Lists ------------------------------------------------------------------------------------


TEST_FILTERS = {
    "": ("All tests", Q()),
    "open": ("Open", Q(state="open")),
    "submitted": ("Awaiting review", Q(state="submitted")),
    "oos": ("Out of specification", Q(conforms=False) & ~Q(state="invalidated")),
    "reviewed": ("Reviewed", Q(state="reviewed")),
    "invalidated": ("Invalidated", Q(state="invalidated")),
}


@login_required
def test_list(request):
    access(request.user)
    state = request.GET.get("state", "")
    if state not in TEST_FILTERS:
        state = ""
    query = request.GET.get("q", "").strip()
    tests = AnalyticalTest.objects.select_related("lot", "sample", "batch").filter(
        TEST_FILTERS[state][1]
    )
    if query:
        tests = tests.filter(
            Q(lot__number__icontains=query)
            | Q(sample__reference__icontains=query)
            | Q(test_code__icontains=query)
        )
    tests = tests.order_by("-created_at", "-pk")
    return render(
        request,
        "analytical/test_list.html",
        {
            "page_title": "Testing",
            "tabs": tabs(request, "analytical:test_list"),
            "page_obj": Paginator(tests, PAGE_SIZE).get_page(request.GET.get("page")),
            "query": query,
            "state": state,
            "states": [(key, label) for key, (label, _) in TEST_FILTERS.items()],
            "filtered": bool(query or state),
            "params": query_params(request),
        },
    )


@login_required
def batch_list(request):
    access(request.user)
    state = request.GET.get("state", "")
    batches = QCBatch.objects.select_related("created_by")
    if state in QCBatch.State.values:
        batches = batches.filter(state=state)
    else:
        state = ""
    query = request.GET.get("q", "").strip()
    if query:
        batches = batches.filter(Q(number__icontains=query) | Q(method_code__icontains=query))
    page = Paginator(batches, PAGE_SIZE).get_page(request.GET.get("page"))
    for batch in page:
        batch.status, _ = batch.qc_status()
    return render(
        request,
        "analytical/batch_list.html",
        {
            "page_title": "Testing",
            "tabs": tabs(request, "analytical:batch_list"),
            "page_obj": page,
            "query": query,
            "state": state,
            "states": QCBatch.State.choices,
            "filtered": bool(query or state),
            "can_create": "analyst" in roles(request.user),
            "params": query_params(request),
        },
    )


@login_required
def investigation_list(request):
    access(request.user)
    state = request.GET.get("state", "open")
    investigations = Investigation.objects.select_related("lot", "test")
    if state == "open":
        investigations = investigations.exclude(phase="closed")
    elif state == "closed":
        investigations = investigations.filter(phase="closed")
    else:
        state = "all"
    query = request.GET.get("q", "").strip()
    if query:
        investigations = investigations.filter(
            Q(lot__number__icontains=query) | Q(test__test_code__icontains=query)
        )
    return render(
        request,
        "analytical/investigation_list.html",
        {
            "page_title": "Testing",
            "tabs": tabs(request, "analytical:investigation_list"),
            "page_obj": Paginator(investigations, PAGE_SIZE).get_page(request.GET.get("page")),
            "query": query,
            "state": state,
            "filtered": bool(query) or state != "open",
            "params": query_params(request),
        },
    )


# Lot testing --------------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def lot_testing(request, pk):
    access(request.user)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    if request.method == "POST":
        return assign_tests(request, lot)
    blockers, _, tests, investigations = gates.lot_status(lot)
    by_sample = {}
    for test in tests:
        by_sample.setdefault(test.sample_id, []).append(test)
    samples = list(Sample.objects.filter(lot=lot).order_by("collected_at", "pk"))
    for sample in samples:
        sample.tests = by_sample.get(sample.pk, [])
    return render(
        request,
        "analytical/lot_testing.html",
        {
            "page_title": f"Testing · {lot.number}",
            "lot": lot,
            "blockers": blockers,
            "samples": samples,
            "investigations": sorted(investigations.values(), key=lambda i: -i.pk),
            "can_assign": "analyst" in roles(request.user) and lot.state == "quarantine",
        },
    )


def assign_tests(request, lot):
    """POST on the lot testing page: assign the lot's required tests to one of its samples."""
    sample = get_object_or_404(Sample, pk=request.POST.get("sample") or 0, lot=lot)
    form = ReasonForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a reason to assign tests.")
        return redirect("analytical:lot_testing", pk=sample.lot_id)
    try:
        created, holds = services.assign_tests(
            actor=request.user, sample=sample, reason=form.cleaned_data["reason"]
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("analytical:lot_testing", pk=sample.lot_id)
    if created:
        messages.success(request, f"Assigned {len(created)} test(s) to {sample.reference}.")
    elif not holds:
        messages.info(request, "Every required test is already assigned to this sample.")
    for hold in holds:
        messages.warning(request, f"Held: {hold}")
    return redirect("analytical:lot_testing", pk=sample.lot_id)


# Tests ----------------------------------------------------------------------------------------


def test_crumbs(test, current=None):
    crumbs = [
        ("Testing", reverse("analytical:test_list")),
        (test.lot.number, reverse("analytical:lot_testing", args=[test.lot_id])),
    ]
    if current:
        crumbs += [(test.label, reverse("analytical:test_detail", args=[test.pk])), (current, None)]
    else:
        crumbs.append((test.label, None))
    return crumbs


def test_summary(test):
    spec = test.spec
    return [
        ("Test", f"{test.label} · {spec.name} ({test.test_code})"),
        ("Lot and sample", f"{test.lot.number} / {test.sample.reference}"),
        ("Specification", f"{spec.source} · {limits_text(spec)}"),
        ("Record revision", test.revision),
    ]


def limits_text(spec):
    if spec.lower is not None and spec.upper is not None:
        return f"{spec.lower} to {spec.upper} {spec.unit}"
    if spec.lower is not None:
        return f"at least {spec.lower} {spec.unit}"
    return f"at most {spec.upper} {spec.unit}"


def get_test(pk):
    return get_object_or_404(
        AnalyticalTest.objects.select_related("lot", "sample", "batch", "parent", "investigation"),
        pk=pk,
    )


@login_required
@require_http_methods(["GET", "POST"])
def test_detail(request, pk):
    access(request.user)
    test = get_test(pk)
    if request.method == "POST":
        return test_submit(request, test)
    spec = test.spec
    observations = list(test.observations.select_related("recorded_by", "supersedes"))
    superseded = {o.supersedes_id for o in observations if o.supersedes_id}
    for obs in observations:
        obs.is_current = obs.pk not in superseded
        obs.in_limits = spec.conforms(obs.value)
    user_roles = roles(request.user)
    is_open = test.state == "open" and test.lot.state == "quarantine"
    current_count = sum(1 for o in observations if o.is_current)
    batch_status = test.batch.qc_status()[0] if test.batch else None
    qc_ready = not spec.method.requires_batch or (
        test.batch is not None and test.batch.state == "open" and batch_status == "passed"
    )
    return render(
        request,
        "analytical/test_detail.html",
        {
            "page_title": test.label,
            "test": test,
            "spec": spec,
            "limits": limits_text(spec),
            "observations": observations,
            "current_count": current_count,
            "batch_status": batch_status,
            "children": test.children.order_by("pk"),
            "triggered": Investigation.objects.filter(test=test).first(),
            "history": history(test),
            "signatures": signatures(test),
            "can_record": "analyst" in user_roles
            and is_open
            and current_count < spec.replicates
            and (test.batch_id or not spec.method.requires_batch),
            "can_correct": "analyst" in user_roles and is_open,
            "can_batch": "analyst" in user_roles
            and is_open
            and spec.method.requires_batch
            and not test.batch_id
            and not observations,
            "can_submit": "analyst" in user_roles
            and is_open
            and current_count == spec.replicates
            and qc_ready,
            "qc_ready": qc_ready,
            "can_review": "reviewer" in user_roles and test.state == "submitted" and qc_ready,
            "can_return": "reviewer" in user_roles and test.state == "submitted" and test.conforms,
            "submit_form": RevisionReasonForm(
                initial={"expected_revision": test.revision, "reason": "Results complete"}
            ),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def observation_new(request, pk):
    require_role(request.user, "analyst")
    test = get_test(pk)
    back = reverse("analytical:test_detail", args=[test.pk])
    if test.state != "open" or test.lot.state != "quarantine":
        return unavailable(request, "This test is not accepting observations.", back)
    if test.spec.method.requires_batch and not test.batch_id:
        return unavailable(request, "Add this test to a QC batch before recording results.", back)
    if test.current_observations().count() >= test.spec.replicates:
        return unavailable(request, "All replicates are recorded. Correct a value instead.", back)
    form = ObservationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.record_observation(actor=request.user, test=test, **form.cleaned_data),
        ):
            messages.success(request, "Observation recorded.")
            return redirect("analytical:test_detail", pk=test.pk)
    replicate = test.current_observations().count() + 1
    return action_page(
        request,
        form,
        title=f"Record replicate {replicate} · {test.label}",
        submit="Record observation",
        crumbs=test_crumbs(test, "Record observation"),
        cancel_url=reverse("analytical:test_detail", args=[test.pk]),
        summary=[*test_summary(test), ("Unit", test.spec.unit)],
    )


@login_required
@require_http_methods(["GET", "POST"])
def observation_correct(request, pk):
    require_role(request.user, "analyst")
    observation = get_object_or_404(Observation.objects.select_related("test"), pk=pk)
    test = get_test(observation.test_id)
    if test.state != "open" or Observation.objects.filter(supersedes=observation).exists():
        return unavailable(
            request,
            "Only current observations of open tests can be corrected.",
            reverse("analytical:test_detail", args=[test.pk]),
        )
    form = CorrectionForm(
        request.POST or None, initial={"raw_reference": observation.raw_reference}
    )
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.correct_observation(
                actor=request.user, observation=observation, **form.cleaned_data
            ),
        ):
            messages.success(request, "Correction recorded; the original value is preserved.")
            return redirect("analytical:test_detail", pk=test.pk)
    return action_page(
        request,
        form,
        title=f"Correct replicate {observation.replicate} · {test.label}",
        submit="Correct observation",
        crumbs=test_crumbs(test, "Correct observation"),
        cancel_url=reverse("analytical:test_detail", args=[test.pk]),
        summary=[
            *test_summary(test),
            ("Value being corrected", f"{observation.value_text} {observation.unit}"),
            ("Original record", observation.raw_reference),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def test_batch(request, pk):
    require_role(request.user, "analyst")
    test = get_test(pk)
    method = test.spec.method
    if test.state != "open" or not method.requires_batch or test.batch_id:
        return unavailable(
            request,
            "This test cannot be added to a QC batch.",
            reverse("analytical:test_detail", args=[test.pk]),
        )
    batches = QCBatch.objects.filter(state="open", method_code=method.code).order_by("-pk")
    batches = batches.filter(pk__in=[b.pk for b in batches if b.method_spec == method])
    form = BatchAssignForm(request.POST or None, batches=batches)
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.assign_to_batch(actor=request.user, test=test, **form.cleaned_data),
        ):
            messages.success(request, "Test added to the QC batch.")
            return redirect("analytical:test_detail", pk=test.pk)
    return action_page(
        request,
        form,
        title=f"Add {test.label} to a QC batch",
        submit="Add to batch",
        crumbs=test_crumbs(test, "Add to QC batch"),
        cancel_url=reverse("analytical:test_detail", args=[test.pk]),
        summary=[*test_summary(test), ("Method", f"{method.code} revision {method.revision}")],
    )


def test_submit(request, test):
    """POST on the test record: submit complete results for independent review."""
    require_role(request.user, "analyst")
    form = RevisionReasonForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a reason to submit the results.")
        return redirect("analytical:test_detail", pk=test.pk)
    try:
        submitted, investigation = services.submit_test(
            actor=request.user, test=test, **form.cleaned_data
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("analytical:test_detail", pk=test.pk)
    if investigation:
        messages.warning(
            request,
            f"Out of specification: {investigation.label} opened and lot {test.lot.number} "
            "is held until it is concluded.",
        )
        return redirect("analytical:investigation_detail", pk=investigation.pk)
    messages.success(request, "Results submitted for independent review.")
    return redirect("analytical:test_detail", pk=submitted.pk)


@login_required
@require_http_methods(["GET", "POST"])
def test_return(request, pk):
    require_role(request.user, "reviewer")
    test = get_test(pk)
    if test.state != "submitted" or not test.conforms:
        return unavailable(
            request,
            "Only conforming results awaiting review can be returned.",
            reverse("analytical:test_detail", args=[test.pk]),
        )
    form = RevisionReasonForm(request.POST or None, initial={"expected_revision": test.revision})
    if request.method == "POST" and form.is_valid():
        if perform(
            form, lambda: services.return_test(actor=request.user, test=test, **form.cleaned_data)
        ):
            messages.success(request, "Test returned to the analyst.")
            return redirect("analytical:test_detail", pk=test.pk)
    return action_page(
        request,
        form,
        title=f"Return {test.label} for correction",
        submit="Return test",
        crumbs=test_crumbs(test, "Return test"),
        cancel_url=reverse("analytical:test_detail", args=[test.pk]),
        summary=[
            *test_summary(test),
            ("Reportable", f"{test.reportable_display} {test.spec.unit}"),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def test_review(request, pk):
    require_role(request.user, "reviewer")
    test = get_test(pk)
    if test.state != "submitted":
        return unavailable(
            request,
            "This test is not awaiting review.",
            reverse("analytical:test_detail", args=[test.pk]),
        )
    form = SigningForm(request.POST or None, initial={"expected_revision": test.revision})
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}
        if perform(form, lambda: services.review_test(actor=request.user, test=test, **data)):
            messages.success(request, f"Signed review recorded for {test.label}.")
            return redirect("analytical:test_detail", pk=test.pk)
    spec = test.spec
    values = ", ".join(o.value_text for o in test.current_observations())
    return sign_page(
        request,
        form,
        title=f"Sign review · {test.label}",
        submit="Sign and review",
        meaning="reviewed",
        record=test,
        record_label=test.label,
        crumbs=test_crumbs(test, "Sign review"),
        cancel_url=reverse("analytical:test_detail", args=[test.pk]),
        summary=[
            *test_summary(test),
            ("Replicates", f"{values} {spec.unit}"),
            (
                "Reportable",
                f"{test.reportable_display} {spec.unit}"
                + (" · conforms" if test.conforms else " · OUT OF SPECIFICATION"),
            ),
        ],
    )


# Batches ------------------------------------------------------------------------------------


def batch_crumbs(batch, current=None):
    crumbs = [("QC batches", reverse("analytical:batch_list"))]
    if current:
        return [
            *crumbs,
            (batch.number, reverse("analytical:batch_detail", args=[batch.pk])),
            (current, None),
        ]
    return [*crumbs, (batch.number, None)]


@login_required
@require_http_methods(["GET", "POST"])
def batch_new(request):
    require_role(request.user, "analyst")
    methods = batch_methods()
    form = BatchForm(request.POST or None, methods=sorted(methods.items()))
    if request.method == "POST" and form.is_valid():
        batch = perform(
            form, lambda: services.create_batch(actor=request.user, **form.cleaned_data)
        )
        if batch:
            messages.success(request, f"QC batch {batch.number} created.")
            return redirect("analytical:batch_detail", pk=batch.pk)
    if not methods:
        form.add_error(None, "No approved batch method is available; batches are held.")
    return action_page(
        request,
        form,
        title="New QC batch",
        submit="Create batch",
        crumbs=[("QC batches", reverse("analytical:batch_list")), ("New QC batch", None)],
        cancel_url=reverse("analytical:batch_list"),
    )


@login_required
def batch_detail(request, pk):
    access(request.user)
    batch = get_object_or_404(QCBatch.objects.select_related("created_by"), pk=pk)
    status, checks = batch.qc_status()
    corrections = batch.qc_results.filter(supersedes__isnull=False).select_related(
        "supersedes", "recorded_by"
    )
    user_roles = roles(request.user)
    frozen = qc_frozen(batch)
    return render(
        request,
        "analytical/batch_detail.html",
        {
            "page_title": batch.number,
            "batch": batch,
            "status": status,
            "checks": checks,
            "corrections": corrections,
            "tests": batch.tests.select_related("lot", "sample").order_by("pk"),
            "history": history(batch),
            "signatures": signatures(batch),
            "frozen": frozen,
            "can_qc": "analyst" in user_roles and not frozen,
            "can_reject": "reviewer" in user_roles and batch.state == "open" and status == "failed",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def qc_record(request, pk, code):
    require_role(request.user, "analyst")
    batch = get_object_or_404(QCBatch, pk=pk)
    check = qc_check(batch, code)
    if qc_frozen(batch):
        return unavailable(
            request,
            "QC entries for this batch are closed.",
            reverse("analytical:batch_detail", args=[batch.pk]),
        )
    form = ObservationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.record_qc(
                actor=request.user, batch=batch, check_code=code, **form.cleaned_data
            ),
        ):
            messages.success(request, f"{check.name} recorded.")
            return redirect("analytical:batch_detail", pk=batch.pk)
    return action_page(
        request,
        form,
        title=f"Record {check.name} · {batch.number}",
        submit="Record QC result",
        crumbs=batch_crumbs(batch, "Record QC result"),
        cancel_url=reverse("analytical:batch_detail", args=[batch.pk]),
        summary=[
            ("Batch", batch.number),
            ("QC check", check.name),
            ("Acceptance", limits_text(check)),
            ("Unit", check.unit),
        ],
    )


def qc_frozen(batch):
    return batch.state != "open" or batch.tests.exclude(state="open").exists()


def qc_check(batch, code):
    try:
        return batch.method_spec.check(code)
    except ValidationError as exc:
        raise Http404("Unknown QC check") from exc


@login_required
@require_http_methods(["GET", "POST"])
def qc_correct(request, pk):
    require_role(request.user, "analyst")
    result = get_object_or_404(QCResult.objects.select_related("batch"), pk=pk)
    batch = result.batch
    check = qc_check(batch, result.check_code)
    if qc_frozen(batch) or QCResult.objects.filter(supersedes=result).exists():
        return unavailable(
            request,
            "This QC result can no longer be corrected.",
            reverse("analytical:batch_detail", args=[batch.pk]),
        )
    form = CorrectionForm(request.POST or None, initial={"raw_reference": result.raw_reference})
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.correct_qc(actor=request.user, qc_result=result, **form.cleaned_data),
        ):
            messages.success(request, "QC correction recorded; the original value is preserved.")
            return redirect("analytical:batch_detail", pk=batch.pk)
    return action_page(
        request,
        form,
        title=f"Correct {check.name} · {batch.number}",
        submit="Correct QC result",
        crumbs=batch_crumbs(batch, "Correct QC result"),
        cancel_url=reverse("analytical:batch_detail", args=[batch.pk]),
        summary=[
            ("QC check", check.name),
            ("Acceptance", limits_text(check)),
            ("Value being corrected", f"{result.value_text} {result.unit}"),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def batch_reject(request, pk):
    require_role(request.user, "reviewer")
    batch = get_object_or_404(QCBatch, pk=pk)
    if batch.state != "open" or batch.qc_status()[0] != "failed":
        return unavailable(
            request,
            "Only an open batch with failed QC can be rejected.",
            reverse("analytical:batch_detail", args=[batch.pk]),
        )
    form = SigningForm(request.POST or None, initial={"expected_revision": batch.revision})
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}
        if perform(form, lambda: services.reject_batch(actor=request.user, batch=batch, **data)):
            messages.success(request, f"{batch.number} rejected; linked reruns were created.")
            return redirect("analytical:batch_detail", pk=batch.pk)
    status, _ = batch.qc_status()
    return sign_page(
        request,
        form,
        title=f"Reject QC batch · {batch.number}",
        submit="Sign and reject",
        meaning="rejected",
        record=batch,
        record_label=batch.number,
        crumbs=batch_crumbs(batch, "Reject batch"),
        cancel_url=reverse("analytical:batch_detail", args=[batch.pk]),
        summary=[
            ("Batch", batch.number),
            ("QC status", status.capitalize()),
            ("Tests invalidated", batch.tests.count()),
            (
                "Effect",
                "Each test is invalidated with a linked rerun; any out-of-limit "
                "value opens an investigation.",
            ),
        ],
    )


# Investigations -----------------------------------------------------------------------------


def investigation_crumbs(inv, current=None):
    crumbs = [("Investigations", reverse("analytical:investigation_list"))]
    if current:
        return [
            *crumbs,
            (inv.label, reverse("analytical:investigation_detail", args=[inv.pk])),
            (current, None),
        ]
    return [*crumbs, (inv.label, None)]


def get_investigation(pk):
    return get_object_or_404(
        Investigation.objects.select_related("lot", "test", "test__sample", "opened_by"), pk=pk
    )


def investigation_summary(inv):
    return [
        ("Investigation", f"{inv.label} · {inv.get_phase_display()}"),
        ("Lot", inv.lot.number),
        ("Trigger", inv.trigger),
        ("Record revision", inv.revision),
    ]


@login_required
def investigation_detail(request, pk):
    access(request.user)
    inv = get_investigation(pk)
    user_roles = roles(request.user)
    original = inv.test
    tests = [original, *inv.tests.select_related("sample").order_by("pk")]
    for test in tests:
        test.values = ", ".join(o.value_text for o in test.current_observations())
    return render(
        request,
        "analytical/investigation_detail.html",
        {
            "page_title": inv.label,
            "inv": inv,
            "tests": tests,
            "entries": inv.entries.select_related("author"),
            "history": history(inv),
            "signatures": signatures(inv),
            "can_enter": bool(user_roles & {"analyst", "reviewer", "quality"}) and inv.is_open,
            "can_escalate": bool(user_roles & {"reviewer", "quality"})
            and inv.phase == "laboratory",
            "can_decide": "quality" in user_roles and inv.is_open,
            "used": inv.tests.exclude(state="invalidated").count(),
            "allowed": original.spec.max_retests,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def entry_new(request, pk):
    require_role(request.user, "analyst", "reviewer", "quality")
    inv = get_investigation(pk)
    if not inv.is_open:
        return unavailable(
            request,
            "This investigation is closed.",
            reverse("analytical:investigation_detail", args=[inv.pk]),
        )
    form = EntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.add_entry(actor=request.user, investigation=inv, **form.cleaned_data),
        ):
            messages.success(request, "Investigation entry recorded.")
            return redirect("analytical:investigation_detail", pk=inv.pk)
    return action_page(
        request,
        form,
        title=f"Record entry · {inv.label}",
        submit="Record entry",
        crumbs=investigation_crumbs(inv, "Record entry"),
        cancel_url=reverse("analytical:investigation_detail", args=[inv.pk]),
        summary=investigation_summary(inv),
    )


@login_required
@require_http_methods(["GET", "POST"])
def escalate(request, pk):
    require_role(request.user, "reviewer", "quality")
    inv = get_investigation(pk)
    if inv.phase != "laboratory":
        return unavailable(
            request,
            "Only a Phase I investigation can be escalated.",
            reverse("analytical:investigation_detail", args=[inv.pk]),
        )
    form = RevisionReasonForm(request.POST or None, initial={"expected_revision": inv.revision})
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.escalate(actor=request.user, investigation=inv, **form.cleaned_data),
        ):
            messages.success(request, f"{inv.label} escalated to a full investigation.")
            return redirect("analytical:investigation_detail", pk=inv.pk)
    return action_page(
        request,
        form,
        title=f"Escalate {inv.label}",
        submit="Escalate investigation",
        crumbs=investigation_crumbs(inv, "Escalate"),
        cancel_url=reverse("analytical:investigation_detail", args=[inv.pk]),
        summary=investigation_summary(inv),
    )


@login_required
@require_http_methods(["GET", "POST"])
def authorize(request, pk):
    require_role(request.user, "quality")
    inv = get_investigation(pk)
    if not inv.is_open:
        return unavailable(
            request,
            "This investigation is closed.",
            reverse("analytical:investigation_detail", args=[inv.pk]),
        )
    used = AnalyticalTest.objects.filter(sample__lot=inv.lot_id).values("sample_id")
    samples = Sample.objects.filter(lot_id=inv.lot_id).exclude(pk__in=used).order_by("-pk")
    form = RetestForm(
        request.POST or None, samples=samples, initial={"expected_revision": inv.revision}
    )
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}
        if perform(
            form, lambda: services.authorize_retest(actor=request.user, investigation=inv, **data)
        ):
            messages.success(request, "Retest authorized; the linked test is ready to record.")
            return redirect("analytical:investigation_detail", pk=inv.pk)
    return sign_page(
        request,
        form,
        title=f"Authorize retest · {inv.label}",
        submit="Sign and authorize",
        meaning="authorized",
        record=inv,
        record_label=inv.label,
        crumbs=investigation_crumbs(inv, "Authorize retest"),
        cancel_url=reverse("analytical:investigation_detail", args=[inv.pk]),
        summary=[
            *investigation_summary(inv),
            (
                "Allowance",
                f"{inv.tests.exclude(state='invalidated').count()} of "
                f"{inv.test.spec.max_retests} retests or resamples used",
            ),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def conclude(request, pk):
    require_role(request.user, "quality")
    inv = get_investigation(pk)
    if not inv.is_open:
        return unavailable(
            request,
            "This investigation is already closed.",
            reverse("analytical:investigation_detail", args=[inv.pk]),
        )
    form = ConcludeForm(request.POST or None, initial={"expected_revision": inv.revision})
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}
        if perform(form, lambda: services.conclude(actor=request.user, investigation=inv, **data)):
            messages.success(request, f"{inv.label} concluded.")
            return redirect("analytical:investigation_detail", pk=inv.pk)
    return sign_page(
        request,
        form,
        title=f"Conclude {inv.label}",
        submit="Sign conclusion",
        meaning="concluded",
        record=inv,
        record_label=inv.label,
        crumbs=investigation_crumbs(inv, "Conclude"),
        cancel_url=reverse("analytical:investigation_detail", args=[inv.pk]),
        summary=investigation_summary(inv),
    )
