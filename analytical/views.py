import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.grids import paginate
from core.models import AuditEvent, ElectronicSignature
from core.services import require_role
from quality.models import Lot, Sample

from . import gates, services
from .contracts import (
    WorkRefused,
    batch_methods,
    bench,
    plain,
    reported_source,
    supplier_results,
    supplier_standing,
    supplier_standing_by_lot,
)
from .forms import (
    BatchAssignForm,
    BatchForm,
    ConcludeForm,
    ContractResultForm,
    CorrectionForm,
    EntryForm,
    ObservationForm,
    ReadingCorrectionForm,
    ReadingForm,
    ReasonForm,
    RetestForm,
    RevisionReasonForm,
    SigningForm,
)
from .models import AnalyticalTest, Investigation, Observation, QCBatch, QCResult

READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
# What a page shows of the stability pull a test belongs to: its study, lot and time point.
PULL = ("pull__study__lot", "pull__timepoint__condition")


def access(user):
    require_role(user, *READ_ROLES)


def roles(user):
    return set(user.groups.values_list("name", flat=True))


def perform(form, action):
    try:
        return action()
    except WorkRefused as exc:
        # Each refusal names its subject; show it on the checkbox that selected it when there is
        # one (a refused instrument or lot), otherwise above the form (the analyst).
        for refusal in exc.refusals:
            field = form.bench_field(refusal["subject"]) if hasattr(form, "bench_field") else None
            for reason in refusal["reasons"]:
                form.add_error(field, f"Refused: {refusal['subject']}: {reason}")
        return None
    except ValidationError as exc:
        if hasattr(exc, "error_dict") and set(exc.error_dict) <= set(form.fields):
            form.add_error(None, exc)
        else:
            form.add_error(None, " ".join(exc.messages))
        return None


def bench_choices():
    """The bench's equipment and lot choices, or (None, hold message) without a bench."""
    try:
        return bench().choices(), None
    except ValidationError as exc:
        return None, " ".join(exc.messages)


def contract_choices(method_code):
    """Contract laboratories approved for the method, or (None, hold message) without a bench."""
    try:
        return bench().contract_choices(method_code), None
    except ValidationError as exc:
        return None, " ".join(exc.messages)


def contract_notice(source):
    """What has happened since to the approval a reported result relied on, or ""."""
    try:
        return bench().contract_notice(source) if source else ""
    except ValidationError:
        return ""


def contract_text(source):
    """One line naming the contract laboratory and its report, from frozen evidence."""
    laboratory, report = source["laboratory"], source["report"]
    return (
        f"{laboratory.get('code', '')} · {laboratory.get('name', '')} · report "
        f"{report.get('number', '')} dated {report.get('date', '')}"
    )


def calculation_summary(spec):
    calculation = spec.calculation
    if calculation is None:
        return []
    places = calculation.decimals
    return [
        (
            "Calculation",
            f"{calculation.formula} · result in {calculation.unit}, rounded half-up to "
            f"{places} decimal place{'s' if places != 1 else ''} · method {spec.method.code} "
            f"revision {spec.method.revision}",
        )
    ]


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


def action_page(
    request, form, *, title, submit, crumbs, cancel_url, record=None, summary=None, held=""
):
    """An action form; `held` is why the action cannot be taken now (shown instead of the form)."""
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
            "held": held,
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
    "oos": (
        "Out of specification",
        Q(conforms=False) & ~Q(state__in=["invalidated", "superseded"]),
    ),
    "reviewed": ("Reviewed", Q(state="reviewed")),
    "invalidated": ("Invalidated", Q(state="invalidated")),
    "superseded": ("Superseded", Q(state="superseded")),
}


class TestFilterForm(forms.Form):
    """The test list's status filter; the search box is the toolbar's own (q)."""

    state = forms.ChoiceField(
        label="Status",
        choices=[(key, label) for key, (label, _) in TEST_FILTERS.items()],
        required=False,
    )


class BatchFilterForm(forms.Form):
    """The QC batch list's status filter."""

    state = forms.ChoiceField(
        label="Status",
        choices=[
            ("", "All batches"),
            *QCBatch.State.choices,
            # An open batch's QC status (analytical/_qc_status.html), worked out per batch.
            ("failed", "QC failed"),
            ("incomplete", "QC incomplete"),
        ],
        required=False,
    )


class InvestigationFilterForm(forms.Form):
    """The investigation list's status filter: open investigations unless another is chosen."""

    state = forms.ChoiceField(
        label="Status",
        choices=[("open", "Open"), ("closed", "Closed"), ("all", "All investigations")],
        required=False,
        initial="open",
    )


def mark_supplier_results(tests):
    """Set ``supplier_result`` on each open test whose requirement a supplier's certificate
    result is proposed or accepted for: such a test is not work waiting to be done."""
    tests = list(tests)
    standing = supplier_standing_by_lot(
        {t.lot_id for t in tests if t.state == "open" and t.lot_id is not None}
    )
    for test in tests:
        test.supplier_result = (
            standing.get((test.lot_id, test.test_code)) if test.state == "open" else None
        )
    return tests


@login_required
def test_list(request):
    access(request.user)
    filters = TestFilterForm(request.GET)
    if not filters.is_valid():  # an unknown status lists every test
        filters = TestFilterForm()
    state = filters.cleaned_data["state"] if filters.is_bound else ""
    query = request.GET.get("q", "").strip()
    tests = AnalyticalTest.objects.select_related("lot", "sample", "batch", *PULL).filter(
        TEST_FILTERS[state][1]
    )
    if query:
        tests = tests.filter(
            Q(lot__number__icontains=query)
            | Q(sample__reference__icontains=query)
            | Q(pull__study__identifier__icontains=query)
            | Q(pull__study__lot__number__icontains=query)
            | Q(test_code__icontains=query)
        )
    tests = tests.order_by("-created_at", "-pk")
    page_obj = paginate(request, tests)
    mark_supplier_results(page_obj)
    return render(
        request,
        "analytical/test_list.html",
        {
            "page_title": "Testing",
            "tabs": tabs(request, "analytical:test_list"),
            "page_obj": page_obj,
            "query": query,
            "filters": filters,
            "filtered": bool(query or state),
        },
    )


@login_required
def batch_list(request):
    access(request.user)
    filters = BatchFilterForm(request.GET)
    if not filters.is_valid():  # an unknown status lists every batch
        filters = BatchFilterForm()
    state = filters.cleaned_data["state"] if filters.is_bound else ""
    batches = QCBatch.objects.select_related("created_by")
    if state in ("failed", "incomplete"):
        # The QC status is computed from each batch's current results, not stored.
        open_batches = batches.filter(state=QCBatch.State.OPEN)
        batches = batches.filter(pk__in=[b.pk for b in open_batches if b.qc_status()[0] == state])
    elif state:
        batches = batches.filter(state=state)
    query = request.GET.get("q", "").strip()
    if query:
        batches = batches.filter(Q(number__icontains=query) | Q(method_code__icontains=query))
    page = paginate(request, batches)
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
            "filters": filters,
            "filtered": bool(query or state),
            "can_create": "analyst" in roles(request.user),
        },
    )


@login_required
def investigation_list(request):
    access(request.user)
    filters = InvestigationFilterForm(request.GET)
    if not filters.is_valid():  # an unknown status lists every investigation
        filters = InvestigationFilterForm({"state": "all"})
        filters.is_valid()
    state = filters.cleaned_data["state"] or "open"
    investigations = Investigation.objects.select_related(
        "lot", "test", *(f"test__{name}" for name in PULL)
    )
    if state == "open":
        investigations = investigations.exclude(phase="closed")
    elif state == "closed":
        investigations = investigations.filter(phase="closed")
    query = request.GET.get("q", "").strip()
    if query:
        investigations = investigations.filter(
            Q(lot__number__icontains=query)
            | Q(test__pull__study__identifier__icontains=query)
            | Q(test__pull__study__lot__number__icontains=query)
            | Q(test__test_code__icontains=query)
        )
    return render(
        request,
        "analytical/investigation_list.html",
        {
            "page_title": "Testing",
            "tabs": tabs(request, "analytical:investigation_list"),
            "page_obj": paginate(request, investigations),
            "query": query,
            "filters": filters,
            "filtered": bool(query) or state != "open",
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
    relied = supplier_results(lot)
    by_sample = {}
    for test in tests:
        test.supplier_result = (
            relied["standing"].get(test.test_code) if test.state == "open" else None
        )
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
            "supplier_results": [relied["accepted"][code] for code in sorted(relied["accepted"])],
            "samples": samples,
            "investigations": sorted(investigations.values(), key=lambda i: -i.pk),
            "can_assign": "analyst" in roles(request.user) and lot.state == "quarantine",
        },
    )


def assign_tests(request, lot):
    """POST on the lot testing page: assign the lot's required tests to one of its samples."""
    require_role(request.user, "analyst")  # read roles (admin, auditor) may view, not assign
    sample_id = request.POST.get("sample", "")
    if not (sample_id.isascii() and sample_id.isdigit() and len(sample_id) <= 19):
        raise Http404("Unknown sample")
    sample = get_object_or_404(Sample, pk=sample_id, lot=lot)
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
    relied = supplier_standing(lot)
    if created:
        messages.success(request, f"Assigned {len(created)} test(s) to {sample.reference}.")
    elif not holds and relied:
        messages.info(
            request,
            "No test to assign: every requirement of this sample has a test or a supplier's "
            "result that stands for it.",
        )
    elif not holds:
        messages.info(request, "Every required test is already assigned to this sample.")
    untested = sorted(
        set(relied)
        - set(
            AnalyticalTest.objects.filter(sample=sample, kind="original").values_list(
                "test_code", flat=True
            )
        )
    )
    if created and untested:
        messages.info(
            request,
            "No test was assigned for " + ", ".join(untested) + ": a supplier's result is "
            "proposed or accepted in place of it.",
        )
    for hold in holds:
        messages.warning(request, f"Held: {hold}")
    return redirect("analytical:lot_testing", pk=sample.lot_id)


# Tests ----------------------------------------------------------------------------------------


def subject_crumb(test):
    """The page a test is reached from: its lot's testing page, or its stability pull."""
    if test.pull_id is not None:
        return (test.pull.label, reverse("stability:pull_detail", args=[test.pull_id]))
    return (test.lot.number, reverse("analytical:lot_testing", args=[test.lot_id]))


def test_crumbs(test, current=None):
    crumbs = [("Testing", reverse("analytical:test_list")), subject_crumb(test)]
    if current:
        crumbs += [(test.label, reverse("analytical:test_detail", args=[test.pk])), (current, None)]
    else:
        crumbs.append((test.label, None))
    return crumbs


def test_summary(test):
    spec = test.spec
    return [
        ("Test", f"{test.label} · {spec.name} ({test.test_code})"),
        ("Lot and stability pull" if test.pull_id else "Lot and sample", test.subject_text),
        ("Specification", f"{spec.source} · {spec.acceptance}"),
        ("Record revision", test.revision),
    ]


def readings_text(test):
    """Current replicates as recorded, with what was observed for qualitative readings."""
    readings = "; ".join(
        o.value_text + (f" ({o.observed_text})" if o.observed_text else "")
        for o in test.current_observations()
    )
    return f"{readings} {test.spec.unit}" if readings and test.spec.unit else readings


def inputs_text(observation):
    """Calculation inputs as entered, e.g. "Sample absorbance 0.512 AU; ..."."""
    return "; ".join(
        f"{i.get('name', i.get('code', ''))} {i.get('value', '')} {i.get('unit', '')}".strip()
        for i in observation.inputs
        if isinstance(i, dict)
    )


def limits_text(spec):
    """Inclusive QC check limits (batch QC checks stay numeric and inclusive)."""
    if spec.lower is not None and spec.upper is not None:
        return f"{spec.lower} to {spec.upper} {spec.unit}"
    if spec.lower is not None:
        return f"at least {spec.lower} {spec.unit}"
    return f"at most {spec.upper} {spec.unit}"


def get_test(pk):
    return get_object_or_404(
        AnalyticalTest.objects.select_related(
            "lot", "sample", "batch", "parent", "investigation", *PULL
        ),
        pk=pk,
    )


# A requirement's source names the specification and its version first, e.g.
# "catalog:syn-assay@v2#rev6/lot-req:…" or "fixture:SYN-SPEC-ASSAY@1".
SOURCE = re.compile(r"^[^:]+:(?P<code>[^@#/]+)@v?(?P<version>\d+)")


def source_label(source):
    """The specification code and version of a requirement source, else the source itself."""
    match = SOURCE.match(source)
    return f"{match['code']} v{match['version']}" if match else source


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
        obs.in_limits = spec.conforms(obs.reading)
    user_roles = roles(request.user)
    subject_closed = services.subject_refusal(test)
    is_open = test.state == "open" and subject_closed is None
    current = [o for o in observations if o.is_current]
    current_count = len(current)
    # Reported by a contract laboratory: every current replicate carries its evidence.
    contract = reported_source(current)
    batch_status = test.batch.qc_status()[0] if test.batch else None
    qc_ready = (
        contract is not None
        or not spec.method.requires_batch
        or (test.batch is not None and test.batch.state == "open" and batch_status == "passed")
    )
    # A supplier's result proposed or accepted in place of this test: it takes no laboratory
    # work until that is withdrawn on the lot record.
    supplier_label = (
        supplier_standing(test.lot).get(test.test_code)
        if test.state == "open" and test.lot_id is not None
        else None
    )
    test.supplier_result = supplier_label
    is_open = is_open and supplier_label is None
    can_contract = (
        "analyst" in user_roles and is_open and services.contract_refusal(test, current) is None
    )
    return render(
        request,
        "analytical/test_detail.html",
        {
            "page_title": test.label,
            "test": test,
            "spec": spec,
            "spec_label": source_label(spec.source),
            "subject_closed": subject_closed,
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
            "contract": contract,
            "contract_notice": contract_notice(contract),
            "supplier_result": supplier_label,
            "can_contract": can_contract and not current,
            "can_contract_correct": can_contract and contract is not None,
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
    if test.state != "open" or services.subject_refusal(test):
        return unavailable(request, "This test is not accepting observations.", back)
    if refusal := services.supplier_refusal(test):
        return unavailable(request, refusal, back)
    if test.contract_source() is not None:
        return unavailable(request, services.REPORTED, back)
    if test.spec.method.requires_batch and not test.batch_id:
        return unavailable(request, "Add this test to a QC batch before recording results.", back)
    if test.current_observations().count() >= test.spec.replicates:
        return unavailable(request, "All replicates are recorded. Correct a value instead.", back)
    choices, hold = bench_choices()
    if hold:
        return unavailable(request, hold, back)
    form = ReadingForm(request.POST or None, spec=test.spec, choices=choices)
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
        summary=[
            *test_summary(test),
            *([("Unit", test.spec.unit)] if test.spec.unit else []),
            *calculation_summary(test.spec),
        ],
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
    if observation.contract is not None:
        return unavailable(
            request,
            services.CONTRACT_REPLICATE,
            reverse("analytical:test_detail", args=[test.pk]),
        )
    choices, hold = bench_choices()
    if hold:
        return unavailable(request, hold, reverse("analytical:test_detail", args=[test.pk]))
    form = ReadingCorrectionForm(
        request.POST or None,
        spec=test.spec,
        choices=choices,
        initial={"raw_reference": observation.raw_reference},
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
            (
                "Result being corrected",
                f"{observation.value_text} {observation.unit}".strip(),
            ),
            *(
                [("What was observed", observation.observed_text)]
                if observation.observed_text
                else []
            ),
            *([("Inputs being corrected", inputs_text(observation))] if observation.inputs else []),
            ("Original record", observation.raw_reference),
            *calculation_summary(test.spec),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def contract_result(request, pk):
    """Record, or correct as a whole, the result a contract laboratory reported for a test."""
    require_role(request.user, "analyst")
    test = get_test(pk)
    back = reverse("analytical:test_detail", args=[test.pk])
    current = list(test.current_observations().order_by("replicate", "pk"))
    refusal = (
        services.subject_refusal(test)
        or services.contract_refusal(test, current)
        or services.supplier_refusal(test)
    )
    if refusal:
        return unavailable(request, refusal, back)
    spec = test.spec
    laboratories, hold = contract_choices(spec.method.code)
    if hold:
        return unavailable(request, hold, back)
    correcting = bool(current)
    initial = {"expected_revision": test.revision}
    if correcting:
        initial.update(ContractResultForm.initial_from(test, current))
        # The laboratory already relied on stays selectable, so a transcription error can be
        # corrected whatever has happened to its approval since.
        recorded = current[0].contract["laboratory"]
        if recorded.get("id") not in {pk for pk, _ in laboratories}:
            label = f"{recorded.get('code', '')} · {recorded.get('name', '')} · as recorded"
            laboratories = [(recorded.get("id"), label), *laboratories]
    if not laboratories:
        return unavailable(
            request,
            f"No contract laboratory is approved for method {spec.method.code}. Quality records "
            "and signs the approval under Laboratory, Contract laboratories.",
            back,
        )
    form = ContractResultForm(
        request.POST or None,
        spec=spec,
        laboratories=laboratories,
        correcting=correcting,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        if perform(
            form,
            lambda: services.record_contract_result(
                actor=request.user, test=test, **form.cleaned_data
            ),
        ):
            messages.success(
                request,
                "Contract laboratory result corrected; the result recorded before is kept."
                if correcting
                else "Contract laboratory result recorded.",
            )
            return redirect("analytical:test_detail", pk=test.pk)
    action = "Correct" if correcting else "Record"
    replicates = spec.replicates
    return action_page(
        request,
        form,
        title=f"{action} contract laboratory result · {test.label}",
        submit=f"{action} contract laboratory result",
        crumbs=test_crumbs(test, f"{action} contract laboratory result"),
        cancel_url=back,
        summary=[
            *test_summary(test),
            ("Method", f"{spec.method.code} revision {spec.method.revision}"),
            (
                "Replicates",
                f"{replicates}: the report must state "
                + ("it" if replicates == 1 else "each of them"),
            ),
            *(
                [
                    ("Result being corrected", readings_text(test)),
                    ("Reported by", contract_text(current[0].contract)),
                    ("Report kept at", current[0].raw_reference),
                ]
                if correcting
                else []
            ),
            (
                "What is checked",
                "The laboratory needs a signed approval for this method that covers the date of "
                "its report. Its batch QC, instruments, reagents and any calculation inputs "
                "stay in its own report, which the reviewer checks."
                + (
                    " A correction that keeps the laboratory and the report keeps the approval "
                    "already relied on."
                    if correcting
                    else ""
                ),
            ),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def test_batch(request, pk):
    require_role(request.user, "analyst")
    test = get_test(pk)
    method = test.spec.method
    back = reverse("analytical:test_detail", args=[test.pk])
    refusal = (
        services.subject_refusal(test)
        or services.batching_refusal(test)
        or services.supplier_refusal(test)
    )
    if not refusal and not method.requires_batch:
        refusal = "This test cannot be added to a QC batch."
    if refusal:
        return unavailable(request, refusal, back)
    batches = QCBatch.objects.filter(state="open", method_code=method.code).order_by("-pk")
    # Offer only batches the locked add would accept (same predicate; rechecked on submit).
    batches = batches.filter(
        pk__in=[
            b.pk for b in batches if b.method_spec == method and not services.batch_join_refusal(b)
        ]
    )
    if not batches:
        return unavailable(
            request,
            f"No open QC batch accepting tests uses {method.code} revision {method.revision}. "
            "Create one under QC batches first.",
            back,
        )
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
        held = f"stability pull {test.pull.label}" if test.pull_id else f"lot {test.lot.number}"
        messages.warning(
            request,
            f"Out of specification: {investigation.label} opened and {held} is held until "
            "it is concluded.",
        )
        return redirect("analytical:investigation_detail", pk=investigation.pk)
    messages.success(request, "Results submitted for independent review.")
    return redirect("analytical:test_detail", pk=submitted.pk)


@login_required
@require_http_methods(["GET", "POST"])
def test_return(request, pk):
    require_role(request.user, "reviewer")
    test = get_test(pk)
    refusal = services.subject_refusal(test) or services.return_refusal(request.user, test)
    if refusal:
        return unavailable(request, refusal, reverse("analytical:test_detail", args=[test.pk]))
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
            ("Reportable", test.reportable_with_unit),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def test_review(request, pk):
    require_role(request.user, "reviewer")
    test = get_test(pk)
    # Preflight with the service's own predicate so no PIN form is offered for an impossible
    # signature; the signing service rechecks everything under lock.
    refusal = services.subject_refusal(test) or services.review_refusal(request.user, test)
    if refusal:
        return unavailable(request, refusal, reverse("analytical:test_detail", args=[test.pk]))
    form = SigningForm(request.POST or None, initial={"expected_revision": test.revision})
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}
        if perform(form, lambda: services.review_test(actor=request.user, test=test, **data)):
            messages.success(request, f"Signed review recorded for {test.label}.")
            return redirect("analytical:test_detail", pk=test.pk)
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
            ("Replicates", readings_text(test)),
            *(
                [
                    ("Reported by contract laboratory", contract_text(source)),
                    *(
                        [("Approval revoked", notice)]
                        if (notice := contract_notice(source))
                        else []
                    ),
                ]
                if (source := test.contract_source())
                else []
            ),
            *(
                [("Mean", f"{plain(test.mean_value)} {test.spec.unit}")]
                if test.mean_value is not None
                else []
            ),
            (
                "Reportable",
                test.reportable_with_unit
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
    # Earlier revisions that tests in progress are frozen to: a lot keeps its frozen versions.
    earlier = sorted(services.earlier_batch_methods())
    form = BatchForm(request.POST or None, methods=sorted(methods.items()), earlier=earlier)
    if request.method == "POST" and form.is_valid():
        batch = perform(
            form, lambda: services.create_batch(actor=request.user, **form.batch_data())
        )
        if batch:
            messages.success(request, f"QC batch {batch.number} created.")
            return redirect("analytical:batch_detail", pk=batch.pk)
    return action_page(
        request,
        form,
        title="New QC batch",
        submit="Create batch",
        crumbs=[("QC batches", reverse("analytical:batch_list")), ("New QC batch", None)],
        cancel_url=reverse("analytical:batch_list"),
        held=""
        if methods or earlier
        else "No approved batch method is available; batches are held.",
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
            "tests": batch.tests.select_related("lot", "sample", *PULL).order_by("pk"),
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
    choices, hold = bench_choices()
    if hold:
        return unavailable(request, hold, reverse("analytical:batch_detail", args=[batch.pk]))
    form = ObservationForm(request.POST or None, choices=choices, method=batch.method_spec)
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
    return batch.state != "open" or services.results_submitted(batch)


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
    choices, hold = bench_choices()
    if hold:
        return unavailable(request, hold, reverse("analytical:batch_detail", args=[batch.pk]))
    form = CorrectionForm(
        request.POST or None,
        choices=choices,
        method=batch.method_spec,
        initial={"raw_reference": result.raw_reference},
    )
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
            reruns = batch.tests.filter(state=AnalyticalTest.State.INVALIDATED).exists()
            messages.success(
                request,
                f"{batch.number} rejected; linked reruns were created."
                if reruns
                else f"{batch.number} rejected; no test was invalidated, so no rerun was created.",
            )
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
            (
                "Tests invalidated",
                batch.tests.exclude(state="superseded")
                .exclude(pull__state="missed")
                .exclude(pull__study__state__in=["completed", "terminated"])
                # A rejected lot keeps its tests as the rejection froze them.
                .exclude(lot__state__in=sorted(services.DECIDED_WITHOUT_RELEASE))
                .count(),
            ),
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
        Investigation.objects.select_related(
            "lot", "test", "test__sample", "opened_by", *(f"test__{name}" for name in PULL)
        ),
        pk=pk,
    )


def investigation_summary(inv):
    return [
        ("Investigation", f"{inv.label} · {inv.get_phase_display()}"),
        ("Lot and stability pull", inv.test.subject_text)
        if inv.lot_id is None
        else ("Lot", inv.lot.number),
        ("Trigger", inv.trigger),
        ("Record revision", inv.revision),
    ]


@login_required
def investigation_detail(request, pk):
    access(request.user)
    inv = get_investigation(pk)
    user_roles = roles(request.user)
    original = inv.test
    tests = [original, *inv.tests.select_related("sample", *PULL).order_by("pk")]
    for test in tests:
        test.values = readings_text(test)
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
    refusal = services.subject_refusal(inv.test) or services.authorize_refusal(
        request.user, inv, inv.test
    )
    if refusal:
        return unavailable(
            request, refusal, reverse("analytical:investigation_detail", args=[inv.pk])
        )
    if inv.lot_id is None:
        # A stability pull has no other sample: only a retest of what was pulled.
        samples = None
    else:
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
                f"{inv.test.spec.max_retests} "
                + ("retests used" if inv.lot_id is None else "retests or resamples used"),
            ),
        ],
    )


@login_required
@require_http_methods(["GET", "POST"])
def conclude(request, pk):
    require_role(request.user, "quality")
    inv = get_investigation(pk)
    refusal = services.subject_refusal(inv.test) or services.conclude_refusal(
        request.user, inv, inv.test, list(inv.tests.all())
    )
    if refusal:
        return unavailable(
            request, refusal, reverse("analytical:investigation_detail", args=[inv.pk])
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
