"""Pages for method evidence records and the suitability of a draft method version (HTTP only;
the rules are in ``catalog.evidence``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.services import require_role
from laboratory.forms import SigningForm
from laboratory.ui import (
    action,
    cell,
    critical,
    day,
    external_link,
    list_page,
    make_filter,
    paginate,
    person,
    record_page,
    refused,
    section,
    sign_page,
    status,
)
from laboratory.ui import when as stamp

from . import evidence as services
from .forms import (
    CharacteristicForm,
    EvidenceChangeForm,
    EvidenceForm,
    ReasonForm,
    SuitabilityForm,
)
from .models import Method, MethodEvidence, MethodEvidenceCharacteristic, MethodRevision
from .services import AUTHOR_ROLE
from .views import _method_crumbs, crumbs_for, form_page, tabs
from .web import can, read_access, run

LIST = "Method evidence"


def _crumbs(*trail):
    return crumbs_for((LIST, reverse("catalog:evidence_list")), *trail)


def evidence_status(item):
    """(label, tone) of a record's state."""
    tone = {"draft": "progress", "approved": "success", "withdrawn": "neutral"}[item.state]
    return item.get_state_display(), tone


def conclusion_cell(item, *, fact=False):
    tone = "success" if item.conclusion == MethodEvidence.Conclusion.SUITABLE else "warning"
    if fact:
        return critical(item.get_conclusion_display(), tone)
    return status(item.get_conclusion_display(), tone)


def _detail_url(item):
    return reverse("catalog:evidence_detail", args=[item.pk])


# List -----------------------------------------------------------------------------------


@login_required
def evidence_list(request):
    read_access(request)
    form, data = make_filter(
        request,
        MethodEvidence.State.choices,
        extra={
            "kind": ("Kind", MethodEvidence._meta.get_field("kind").choices),
            "conclusion": ("Conclusion", MethodEvidence.Conclusion.choices),
        },
    )
    queryset = MethodEvidence.objects.select_related("method").annotate(
        versions=Count("method_versions", filter=Q(method_versions__status="approved"))
    )
    if q := data.get("q"):
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(method__code__icontains=q)
            | Q(method__title__icontains=q)
            | Q(procedure_ref__icontains=q)
            | Q(report_ref__icontains=q)
            | Q(source__icontains=q)
        )
    for name, field in (("status", "state"), ("kind", "kind"), ("conclusion", "conclusion")):
        if data.get(name):
            queryset = queryset.filter(**{field: data[name]})
    page, sort, descending = paginate(
        request,
        queryset,
        {"completed": ["completed_on"], "method": ["method__code", "completed_on"]},
        "-completed",
    )
    rows = []
    for item in page:
        rows.append(
            [
                cell(item.identifier, _detail_url(item), sub=item.title),
                cell(
                    item.method.code,
                    reverse("catalog:method", args=[item.method_id]),
                    sub=item.method.title,
                ),
                item.get_kind_display(),
                cell(item.report_ref, wrap=True),
                day(item.completed_on),
                conclusion_cell(item),
                cell(str(item.versions), numeric=True),
                status(*evidence_status(item)),
            ]
        )
    return list_page(
        request,
        title=LIST,
        intro="The evidence that each method is suitable for its intended use: validations, "
        "verifications of compendial procedures, transfers and other documented fitness for "
        "use, each summarizing a report kept in the laboratory's document system.",
        noun="evidence records",
        columns=[
            ("Record", None, False),
            ("Method", "method", False),
            ("Kind", None, False),
            ("Report", None, False, "low"),
            ("Completed on", "completed", False),
            ("Conclusion", None, False),
            ("Approved versions", None, True, "low"),
            ("State", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "evidence record", "href": reverse("catalog:evidence_new")}
        if can(request.user, *services.RECORDERS)
        else None,
        empty_body="Record the validation, verification or transfer of a method.",
        extra={"page_title": LIST, "tabs": tabs(request, LIST)},
    )


# Recording and changing a draft ----------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def evidence_new(request):
    require_role(request.user, *services.RECORDERS)
    initial = {}
    if (method_id := request.GET.get("method", "")).isdigit():
        if method := Method.objects.filter(pk=method_id).first():
            initial["method"] = method
    form = EvidenceForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = run(
            form,
            lambda: services.record_evidence(
                actor=request.user,
                method=form.cleaned_data["method"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if item:
            messages.success(
                request,
                f"{item.identifier} recorded as a draft. Add the characteristics evaluated; "
                "another quality person approves it.",
            )
            return redirect(_detail_url(item))
    return form_page(
        request,
        form,
        title="New method evidence record",
        crumbs=_crumbs(("New record", None)),
        cancel_url=reverse("catalog:evidence_list"),
        submit_label="Record draft",
        intro="Summarize the report that shows the method is suitable for its intended use. The "
        "record stays a draft, and supports no method version, until a quality person who did "
        "not record or change it approves it.",
    )


def _draft(request, pk, *, roles=services.RECORDERS):
    """(record, detail url, redirect) for a page that changes a draft."""
    require_role(request.user, *roles)
    item = get_object_or_404(MethodEvidence.objects.select_related("method"), pk=pk)
    detail = _detail_url(item)
    if item.state != MethodEvidence.State.DRAFT:
        messages.error(request, "Only a draft record can be changed.")
        return item, detail, redirect(detail)
    return item, detail, None


@login_required
@require_http_methods(["GET", "POST"])
def evidence_edit(request, pk):
    item, detail, refused_page = _draft(request, pk)
    if refused_page:
        return refused_page
    initial = {name: getattr(item, name) for name in services.FIELDS}
    initial["expected_revision"] = item.revision
    form = EvidenceChangeForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        changed = run(
            form,
            lambda: services.change_evidence(
                actor=request.user,
                evidence=item,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
                **form.values(),
            ),
        )
        if changed:
            messages.success(request, f"Draft {item.identifier} changed.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Change draft {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Change", None)),
        cancel_url=detail,
        submit_label="Save changes",
        intro="Whoever changes a draft cannot approve it.",
        facts=[("Method", str(item.method))],
    )


@login_required
@require_http_methods(["GET", "POST"])
def characteristic_new(request, pk):
    item, detail, refused_page = _draft(request, pk)
    if refused_page:
        return refused_page
    form = CharacteristicForm(request.POST or None, initial={"expected_revision": item.revision})
    if request.method == "POST" and form.is_valid():
        added = run(
            form,
            lambda: services.add_characteristic(
                actor=request.user, evidence=item, **form.cleaned_data
            ),
        )
        if added:
            messages.success(request, f"{added.label} added to {item.identifier}.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Add characteristic · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Add characteristic", None)),
        cancel_url=detail,
        submit_label="Add characteristic",
        intro="One performance characteristic the study evaluated, with the acceptance "
        "criterion set in advance and the result the report gives.",
        facts=[("Record", str(item)), ("Method", str(item.method))],
    )


@login_required
@require_http_methods(["GET", "POST"])
def characteristic_remove(request, pk, item_pk):
    item, detail, refused_page = _draft(request, pk)
    if refused_page:
        return refused_page
    line = get_object_or_404(MethodEvidenceCharacteristic, pk=item_pk, evidence=item)
    form = ReasonForm(request.POST or None, initial={"expected_revision": item.revision})
    if request.method == "POST" and form.is_valid():
        if run(
            form,
            lambda: services.remove_characteristic(
                actor=request.user,
                item=line,
                reason=form.cleaned_data["reason"],
                expected_revision=form.cleaned_data["expected_revision"],
            ),
        ):
            messages.success(request, f"{line.label} removed from draft {item.identifier}.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Remove characteristic · {item.identifier}",
        crumbs=_crumbs((item.identifier, detail), ("Remove characteristic", None)),
        cancel_url=detail,
        submit_label="Remove characteristic",
        intro="Removal from a draft is recorded in its history with your reason.",
        facts=[
            ("Characteristic", line.label),
            ("Acceptance criterion", line.criterion),
            ("Result obtained", line.result),
            ("Criterion", line.get_outcome_display()),
        ],
    )


# Record ----------------------------------------------------------------------------------


def characteristic_rows(item, *, removable=False):
    rows = []
    for line in item.characteristics.all():
        row = [
            cell(line.label, wrap=True),
            cell(line.criterion, wrap=True),
            cell(line.result, wrap=True),
            status(
                line.get_outcome_display(),
                "success" if line.outcome == line.Outcome.MET else "warning",
            ),
        ]
        if removable:
            row.append(
                cell(
                    "Remove",
                    reverse("catalog:evidence_characteristic_remove", args=[item.pk, line.pk]),
                )
            )
        rows.append(row)
    return rows


def evidence_facts(item):
    facts = [
        ("Conclusion", conclusion_cell(item, fact=True)),
        ("Method", cell(str(item.method), reverse("catalog:method", args=[item.method_id]))),
        ("Kind", item.get_kind_display()),
        ("Procedure studied", cell(item.procedure_ref, code=True)),
        ("Intended use", cell(item.intended_use, wrap=True)),
    ]
    if item.source:
        facts.append(("Source of the procedure", item.source))
    if item.transfer_approach:
        facts.append(("Transfer approach", item.get_transfer_approach_display()))
    facts += [
        ("Protocol", cell(item.protocol_ref, code=True) if item.protocol_ref else ""),
        ("Report", cell(item.report_ref, code=True)),
        ("Report link", external_link(item.report_url)),
        ("Report completed on", day(item.completed_on)),
        ("Statement of suitability", cell(item.statement, wrap=True)),
        ("Deviations", cell(item.deviations, wrap=True)),
    ]
    return facts


@login_required
def evidence_detail(request, pk):
    read_access(request)
    item = get_object_or_404(MethodEvidence.objects.select_related("method", "recorded_by"), pk=pk)
    user = request.user
    label, tone = evidence_status(item)
    draft = item.state == MethodEvidence.State.DRAFT
    recorder = can(user, *services.RECORDERS)
    quality = can(user, services.APPROVER)
    problems = services.approval_problems(item) if draft else []
    actions = []
    if draft and recorder:
        actions.append(
            action("Add characteristic", reverse("catalog:evidence_characteristic_new", args=[pk]))
        )
        actions.append(action("Change", reverse("catalog:evidence_edit", args=[pk])))
    if draft and (user.pk == item.recorded_by_id or quality) and recorder:
        actions.append(
            action(
                "Withdraw draft",
                reverse("catalog:evidence_withdraw", args=[pk]),
                danger=True,
                more=True,
            )
        )
    if item.state == MethodEvidence.State.APPROVED and quality:
        actions.append(
            action(
                "Withdraw", reverse("catalog:evidence_withdraw", args=[pk]), danger=True, more=True
            )
        )
        if can(user, AUTHOR_ROLE) and item.conclusion == MethodEvidence.Conclusion.SUITABLE:
            drafts = MethodRevision.objects.filter(method=item.method, status="draft")
            if draft_version := drafts.order_by("-version").first():
                actions.append(
                    action(
                        f"Rely on it in version {draft_version.version}",
                        reverse("catalog:suitability_set", args=[draft_version.pk])
                        + f"?evidence={item.pk}",
                    )
                )
    if draft and quality:
        if user.pk in services.changed_by(item):
            actions.insert(0, refused(services.INDEPENDENT))
        elif not problems:
            actions.append(
                action("Review and approve", reverse("catalog:evidence_approve", args=[pk]), True)
            )
    notice = None
    if draft and problems:
        notice = {
            "tone": "info",
            "label": "Before approval",
            "text": " ".join(problems),
        }
    elif item.state == MethodEvidence.State.WITHDRAWN and item.approved_at:
        notice = {
            "tone": "warning",
            "label": "Withdrawn",
            "text": "Quality withdrew this record after approving it. The method versions "
            "approved on it keep it as approved; no draft version can link it again.",
        }
    versions = list(services.relying_versions(item).select_related("method"))
    now = timezone.now()
    in_force = {revision.pk for revision in versions if revision.is_effective(now)}
    moments = [("Approved", item.approved_at), ("Withdrawn", item.withdrawn_at)]
    return record_page(
        request,
        identifier=item.identifier,
        title=item.title,
        crumbs=_crumbs((item.identifier, None)),
        state=status(label, tone),
        facts=evidence_facts(item)
        + [("Recorded by", person(item.recorded_by))]
        + [(label, stamp(moment)) for label, moment in moments if moment],
        meta=[("Revision", item.revision)],
        actions=actions,
        notice=notice,
        sections=[
            section(
                "Characteristics evaluated",
                [
                    ("Characteristic", False),
                    ("Acceptance criterion", False),
                    ("Result obtained", False),
                    ("Criterion", False),
                    *([("Action", False)] if draft and recorder else []),
                ],
                characteristic_rows(item, removable=draft and recorder),
                "No characteristics recorded yet.",
            ),
            section(
                "Method versions relying on it",
                [("Version", False), ("Status", False), ("In force", False)],
                [
                    [
                        cell(
                            f"{revision.method.code} v{revision.version}",
                            reverse("catalog:method", args=[revision.method_id])
                            + f"#version-{revision.pk}",
                        ),
                        revision.get_status_display(),
                        "Yes" if revision.pk in in_force else "No",
                    ]
                    for revision in versions
                ],
                "No method version relies on this record.",
            ),
        ],
        related=[item],
    )


# Approval and withdrawal -----------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def evidence_approve(request, pk):
    require_role(request.user, services.APPROVER)
    item = get_object_or_404(MethodEvidence.objects.select_related("method", "recorded_by"), pk=pk)
    detail = _detail_url(item)
    denial = ""
    if item.state != MethodEvidence.State.DRAFT:
        denial = "Only a draft record can be approved."
    elif request.user.pk in services.changed_by(item):
        denial = services.INDEPENDENT
    elif problems := services.approval_problems(item):
        # Refused before any PIN is asked; the service checks again when signing.
        denial = "Not ready for approval. " + " ".join(problems)
    form = SigningForm(request.POST or None, initial={"expected_revision": item.revision})
    facts = evidence_facts(item) + [
        ("Characteristics", f"{item.characteristics.count()} evaluated"),
        ("Recorded by", person(item.recorded_by)),
    ]
    return sign_page(
        request,
        form,
        title=f"Approve {item.identifier}",
        identifier=item.identifier,
        meaning="approved",
        meaning_text="You approve this record and its characteristics as the evidence of the "
        "method's suitability for the intended use stated. Your signature freezes them.",
        button="Sign and approve",
        facts=facts,
        revision=item.revision,
        cancel_url=detail,
        run=lambda d: services.approve_evidence(
            actor=request.user,
            pin=d["pin"],
            evidence=item,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"{item.identifier} approved.",
        success_url=detail,
        denial=denial,
        crumbs=_crumbs((item.identifier, detail), ("Approve", None)),
    )


@login_required
@require_http_methods(["GET", "POST"])
def evidence_withdraw(request, pk):
    require_role(request.user, *services.RECORDERS)
    item = get_object_or_404(MethodEvidence.objects.select_related("method", "recorded_by"), pk=pk)
    detail = _detail_url(item)
    crumbs = _crumbs((item.identifier, detail), ("Withdraw", None))
    if item.state == MethodEvidence.State.DRAFT:
        if request.user.pk != item.recorded_by_id and not can(request.user, services.APPROVER):
            messages.error(
                request, "Only the person who recorded this draft or quality withdraws it."
            )
            return redirect(detail)
        form = ReasonForm(request.POST or None, initial={"expected_revision": item.revision})
        if request.method == "POST" and form.is_valid():
            done = run(
                form,
                lambda: services.discard_evidence(
                    actor=request.user,
                    evidence=item,
                    expected_revision=form.cleaned_data["expected_revision"],
                    reason=form.cleaned_data["reason"],
                ),
            )
            if done:
                messages.success(request, f"Draft {item.identifier} withdrawn.")
                return redirect(detail)
        return form_page(
            request,
            form,
            title=f"Withdraw draft {item.identifier}",
            crumbs=crumbs,
            cancel_url=detail,
            submit_label="Withdraw draft",
            intro="A withdrawn draft stays in the list and its history and can no longer be "
            "changed or approved. Only the person who recorded it or quality withdraws it.",
            facts=[("Record", str(item)), ("Method", str(item.method))],
        )
    denial = ""
    if item.state != MethodEvidence.State.APPROVED:
        denial = "This record is already withdrawn."
    elif not can(request.user, services.APPROVER):
        denial = "Only quality withdraws an approved record."
    versions = list(services.relying_versions(item))
    form = SigningForm(request.POST or None, initial={"expected_revision": item.revision})
    return sign_page(
        request,
        form,
        title=f"Withdraw {item.identifier}",
        identifier=item.identifier,
        meaning="withdrawn",
        meaning_text="You withdraw this approved record: no draft method version can link it "
        "again. Its approved content stays, and the method versions already approved on it keep "
        "it as approved; replace them with a new version where the evidence no longer holds.",
        button="Sign and withdraw",
        facts=[
            ("Record", str(item)),
            ("Method", str(item.method)),
            ("Conclusion", item.get_conclusion_display()),
            (
                "Method versions relying on it",
                ", ".join(f"v{v.version} ({v.get_status_display().lower()})" for v in versions)
                or "None",
            ),
        ],
        revision=item.revision,
        cancel_url=detail,
        run=lambda d: services.withdraw_evidence(
            actor=request.user,
            pin=d["pin"],
            evidence=item,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"{item.identifier} withdrawn.",
        success_url=detail,
        denial=denial,
        crumbs=crumbs,
    )


# The suitability of a draft method version -----------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def suitability_set(request, pk):
    require_role(request.user, AUTHOR_ROLE)  # before lookup: no 404/403 existence leak
    revision = get_object_or_404(MethodRevision.objects.select_related("method", "evidence"), pk=pk)
    detail, crumbs = _method_crumbs(revision, "Suitability evidence")
    if not revision.is_draft:
        messages.error(request, "Suitability evidence can only be changed on a draft version.")
        return redirect(detail)
    choices = services.relied_on_choices(revision.method)
    initial = {
        "expected_revision": revision.revision,
        "evidence": revision.evidence_id,
        "suitability_kind": "" if revision.evidence_id else revision.suitability_kind,
        "suitability_ref": "" if revision.evidence_id else revision.suitability_ref,
    }
    if (chosen := request.GET.get("evidence", "")).isdigit():
        if choices.filter(pk=chosen).exists():
            initial["evidence"] = int(chosen)
    elif not revision.evidence_id:
        previous = (
            MethodRevision.objects.filter(method=revision.method, version__lt=revision.version)
            .exclude(evidence=None)
            .order_by("-version")
            .first()
        )
        if previous and choices.filter(pk=previous.evidence_id).exists():
            initial["evidence"] = previous.evidence_id
    form = SuitabilityForm(request.POST or None, initial=initial, choices=choices)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        done = run(
            form,
            lambda: services.set_suitability(
                actor=request.user,
                revision=revision,
                reason=data["reason"],
                evidence=data.get("evidence"),
                suitability_kind=data.get("suitability_kind") or "",
                suitability_ref=data.get("suitability_ref") or "",
                expected_revision=data["expected_revision"],
            ),
        )
        if done:
            messages.success(request, f"Suitability evidence of draft {revision} set.")
            return redirect(detail)
    current = (
        str(revision.evidence)
        if revision.evidence_id
        else f"{revision.get_suitability_kind_display()} · {revision.suitability_ref}"
    )
    return form_page(
        request,
        form,
        title=f"Suitability evidence · {revision}",
        crumbs=crumbs,
        cancel_url=detail,
        submit_label="Save suitability evidence",
        intro="Choose an approved evidence record of this method, or name a report kept "
        "elsewhere. Whoever changes a draft cannot approve it; approval checks the record again.",
        facts=[("Now", current)],
    )
