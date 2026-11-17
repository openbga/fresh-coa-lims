"""Pages for the contract laboratory register and its approvals (HTTP only; rules in contract)."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Lower
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from core.services import require_role

from . import contract
from .eligibility import DUE_SOON_DAYS
from .forms import ContractApprovalForm, ContractLaboratoryForm, SigningForm
from .models import ContractApproval, ContractLaboratory, ContractUse
from .ui import (
    access,
    action,
    cell,
    day,
    external_link,
    form_page,
    list_page,
    make_filter,
    paginate,
    record_page,
    roles_of,
    run_form,
    section,
    sign_page,
    status,
    when,
    work_cell,
    work_labels,
)

HOME = "Laboratory"
SECTION = "Contract laboratories"
USES_SHOWN = 50
KEEPER = contract.KEEPER_ROLE
NOT_A_QUALIFICATION = (
    "The register says who a laboratory is. A result it reports is accepted only under an "
    "approval for the method, signed by a second quality person."
)


def _crumbs(*pairs):
    return [
        (HOME, reverse("laboratory:overview")),
        (SECTION, reverse("laboratory:contract_laboratory_list")),
        *pairs,
    ]


def _keeper(user):
    return KEEPER in roles_of(user)


def _laboratory_url(laboratory):
    return reverse("laboratory:contract_laboratory_detail", args=[laboratory.pk])


def _approval_url(approval):
    return reverse("laboratory:contract_approval_detail", args=[approval.pk])


def _uses_section(uses, total, *, with_approval):
    """The results that relied on an approval, newest first, with the work they belong to."""
    resolved = work_labels((use.context_type, use.context_id) for use in uses)
    rows = []
    for use in uses:
        detail = resolved[2].get((use.context_type, str(use.context_id)), {})
        rows.append(
            [
                when(use.used_at),
                work_cell(use, resolved),
                detail.get("lot", ""),
                detail.get("test_code", use.test_code),
                detail.get("state", ""),
                detail.get("result", ""),
                use.report_number,
                day(use.report_date),
                *([cell(use.approval.label, _approval_url(use.approval))] if with_approval else []),
                str(use.used_by),
            ]
        )
    note = (
        "Each row is one report accepted into a test record, with the test as it stands now. "
        "A correction that names another laboratory or another report is a new acceptance "
        "and adds a row."
    )
    if total > len(uses):
        note += f" Showing the latest {len(uses)} of {total}."
    return section(
        "Results that relied on this laboratory"
        if with_approval
        else "Results that relied on this approval",
        [
            ("Accepted", False),
            ("Work", False),
            ("Lot", False),
            ("Test", False),
            ("State", False),
            ("Reportable result", False),
            ("Report", False),
            ("Report dated", False),
            *([("Approval", False)] if with_approval else []),
            ("By", False),
        ],
        rows,
        "No result has relied on it.",
        note=note,
    )


LABORATORY_STATUS = [
    ("waiting", "Approval awaiting signature"),
    ("expiring", "Approval expiring within 30 days"),
    ("current", "Approved for a method today"),
    ("none", "No approval in force today"),
]


# A laboratory's approvals ranked for its list row: in force first (the soonest to expire, so
# an expiring approval shows), then starting later, awaiting signature, expired, revoked.
APPROVAL_RANK = [
    "Expiring soon",
    "Approved",
    "Approved, starts later",
    "Awaiting approval",
    "Expired",
    "Revoked",
]


def _approval_state(approvals, today):
    """The state pill of the laboratory's first approval by APPROVAL_RANK (approvals ordered by
    valid until, so the soonest-expiring wins a tie); blank when it has none."""
    states = [contract.approval_status(approval, today) for approval in approvals]
    best = min(states, key=lambda state: APPROVAL_RANK.index(state[0]), default=None)
    return status(*best) if best else ""


@login_required
def contract_laboratory_list(request):
    access(request.user)
    today = timezone.localdate()
    soon = today + timedelta(days=DUE_SOON_DAYS)
    form, data = make_filter(request, LABORATORY_STATUS)
    own = ContractApproval.objects.filter(laboratory=OuterRef("pk"))
    in_force = own.filter(state="approved", valid_from__lte=today, valid_until__gte=today)
    waiting = own.filter(state="recorded")

    def counted(approvals, what):
        return Coalesce(
            Subquery(
                approvals.order_by()
                .values("laboratory")
                .annotate(n=Count(what, distinct=True))
                .values("n"),
                output_field=IntegerField(),
            ),
            0,
        )

    # Methods, not approvals: two overlapping approvals of one method are one method.
    queryset = ContractLaboratory.objects.annotate(
        current_count=counted(in_force, Lower("method_code")),
        waiting_count=counted(waiting, "pk"),
    )
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(location__icontains=q)
            | Exists(own.filter(method_code__icontains=q))
        )
    match data.get("status"):
        case "waiting":
            queryset = queryset.filter(Exists(waiting))
        case "expiring":
            queryset = queryset.filter(Exists(in_force.filter(valid_until__lte=soon)))
        case "current":
            queryset = queryset.filter(Exists(in_force))
        case "none":
            queryset = queryset.exclude(Exists(in_force))
    page, sort, descending = paginate(
        request, queryset, {"code": ["code"], "name": ["name", "code"]}, "code"
    )
    approvals = ContractApproval.objects.filter(laboratory__in=list(page)).order_by("valid_until")
    by_laboratory = {}
    for approval in approvals:
        by_laboratory.setdefault(approval.laboratory_id, []).append(approval)
    rows = [
        [
            cell(item.code, _laboratory_url(item), sub=item.name),
            item.location,
            _approval_state(by_laboratory.get(item.pk, []), today),
            cell(str(item.current_count), numeric=True),
            cell(str(item.waiting_count), numeric=True),
        ]
        for item in page
    ]
    return list_page(
        request,
        title=SECTION,
        intro="Outside laboratories that test for this laboratory, and the methods each is "
        "approved for. " + NOT_A_QUALIFICATION,
        noun="contract laboratories",
        columns=[
            ("Code", "code", False),
            ("Location", None, False),
            ("Approval", None, False),
            ("Methods approved today", None, True),
            ("Approvals awaiting signature", None, True),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "contract laboratory", "href": reverse("laboratory:contract_laboratory_new")}
        if _keeper(request.user)
        else None,
        empty_body="Quality adds a contract laboratory, then records and approves the methods "
        "it may perform.",
    )


@login_required
def contract_laboratory_new(request):
    require_role(request.user, KEEPER)
    form = ContractLaboratoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: contract.register_contract_laboratory(actor=request.user, **form.cleaned_data),
        )
        if done:
            messages.success(request, f"Contract laboratory {done.code} added.")
            return redirect(_laboratory_url(done))
    return form_page(
        request,
        form,
        title="New contract laboratory",
        crumbs=_crumbs(("New contract laboratory", None)),
        submit="Add contract laboratory",
        cancel_url=reverse("laboratory:contract_laboratory_list"),
        intro="A laboratory's identity cannot be edited after it is added; use synthetic names "
        "only. Adding a laboratory approves nothing: record an approval for each method next.",
    )


@login_required
def contract_laboratory_detail(request, pk):
    access(request.user)
    laboratory = get_object_or_404(ContractLaboratory.objects.select_related("created_by"), pk=pk)
    today = timezone.localdate()
    approvals = list(laboratory.approvals.order_by("method_code", "-valid_from", "-pk"))
    approval_rows = []
    for approval in approvals:
        label, tone = contract.approval_status(approval, today)
        approval_rows.append(
            [
                cell(approval.label, _approval_url(approval)),
                approval.method_code,
                day(approval.valid_from),
                day(approval.valid_until),
                approval.evidence_ref,
                status(label, tone),
            ]
        )
    uses = ContractUse.objects.filter(approval__laboratory=laboratory).select_related(
        "approval", "used_by"
    )
    return record_page(
        request,
        identifier=laboratory.code,
        title=laboratory.name,
        crumbs=_crumbs((laboratory.code, None)),
        state=status("Identity only", "neutral"),
        facts=[
            ("Code", laboratory.code),
            ("Name", laboratory.name),
            ("Location", laboratory.location),
            ("Added by", str(laboratory.created_by)),
            ("Added", when(laboratory.created_at)),
        ],
        actions=[
            action(
                "Record approval",
                reverse("laboratory:contract_approval_new", args=[laboratory.pk]),
                True,
            )
            if _keeper(request.user)
            else None
        ],
        sections=[
            section(
                "Approvals by method",
                [
                    ("Approval", False),
                    ("Method", False),
                    ("Valid from", False),
                    ("Valid until (inclusive)", False),
                    ("Evidence", False),
                    ("State", False),
                ],
                approval_rows,
                "No approval is recorded. Results from this laboratory are refused until an "
                "approval for the method is signed.",
                note=NOT_A_QUALIFICATION,
            ),
            _uses_section(list(uses[:USES_SHOWN]), uses.count(), with_approval=True),
        ],
        related=[laboratory],
    )


@login_required
def contract_approval_new(request, pk):
    require_role(request.user, KEEPER)
    laboratory = get_object_or_404(ContractLaboratory, pk=pk)
    form = ContractApprovalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: contract.record_contract_approval(
                actor=request.user, laboratory=laboratory, **form.cleaned_data
            ),
        )
        if done:
            messages.success(
                request, "Approval evidence recorded; a second quality signer approves."
            )
            return redirect(_approval_url(done))
    return form_page(
        request,
        form,
        title=f"Record approval · {laboratory.code}",
        crumbs=_crumbs((laboratory.code, _laboratory_url(laboratory)), ("Record approval", None)),
        submit="Record approval",
        cancel_url=_laboratory_url(laboratory),
        intro="Recording evidence approves nothing. A different quality signer approves it; "
        "results are then accepted for reports dated within these dates.",
    )


def _approval(pk):
    return get_object_or_404(
        ContractApproval.objects.select_related("laboratory", "recorded_by"), pk=pk
    )


def _approval_facts(approval, *, approve):
    """What the signer signs: everything the signature's snapshot holds, and for a revocation
    how many accepted reports relied on the approval."""
    facts = [
        ("Laboratory", cell(str(approval.laboratory), _laboratory_url(approval.laboratory))),
        ("Method", approval.method_code),
        ("Valid", f"{day(approval.valid_from)} to {day(approval.valid_until)}"),
        ("Evidence", approval.evidence_ref),
        ("Evidence link", external_link(approval.evidence_url)),
        ("Scope", approval.scope_note),
        ("Recorded by", str(approval.recorded_by)),
    ]
    if not approve:
        facts.append(("Accepted reports that relied on it", approval.uses.count()))
    return facts


@login_required
def contract_approval_detail(request, pk):
    access(request.user)
    approval = _approval(pk)
    label, tone = contract.approval_status(approval)
    user = request.user
    keeper = _keeper(user)
    uses = ContractUse.objects.filter(approval=approval).select_related("approval", "used_by")
    total = uses.count()
    notice = None
    if approval.state == "revoked" and total:
        notice = {
            "tone": "warning",
            "label": "Assess the results",
            "text": f"{total} accepted report{'s' if total != 1 else ''} relied on this approval "
            "before it was revoked. Each result stands as recorded. Assess them under your "
            "procedure: the software records no assessment and holds no lot by itself.",
        }
    return record_page(
        request,
        identifier=approval.label,
        title=f"{approval.laboratory.code} · {approval.method_code}",
        crumbs=_crumbs(
            (approval.laboratory.code, _laboratory_url(approval.laboratory)),
            (approval.label, None),
        ),
        state=status(label, tone),
        facts=[
            ("Laboratory", cell(str(approval.laboratory), _laboratory_url(approval.laboratory))),
            ("Method", approval.method_code),
            ("Valid from", day(approval.valid_from)),
            ("Valid until (inclusive)", day(approval.valid_until)),
            ("Evidence reference", approval.evidence_ref),
            ("Evidence link", external_link(approval.evidence_url)),
            ("Scope", approval.scope_note),
            ("Recorded by", str(approval.recorded_by)),
            ("Recorded", when(approval.recorded_at)),
            ("Approved", when(approval.approved_at)),
            ("Revoked", when(approval.revoked_at)),
            ("Revision", approval.revision),
        ],
        actions=[
            action(
                "Approve", reverse("laboratory:contract_approval_approve", args=[approval.pk]), True
            )
            if keeper and not contract.approval_denial(user, approval, approve=True)
            else None,
            action("Revoke", reverse("laboratory:contract_approval_revoke", args=[approval.pk]))
            if keeper and not contract.approval_denial(user, approval, approve=False)
            else None,
        ],
        sections=[_uses_section(list(uses[:USES_SHOWN]), total, with_approval=False)],
        related=[approval],
        notice=notice,
    )


def _approval_sign(request, pk, *, approve):
    require_role(request.user, KEEPER)
    approval = _approval(pk)
    detail = _approval_url(approval)
    form = SigningForm(request.POST or None, initial={"expected_revision": approval.revision})
    service = contract.approve_contract_approval if approve else contract.revoke_contract_approval
    return sign_page(
        request,
        form,
        title=f"{'Approve' if approve else 'Revoke'} contract laboratory approval",
        identifier=approval.label,
        meaning="approved" if approve else "revoked",
        meaning_text=(
            "You approve this evidence as showing the laboratory may perform the method for "
            "reports dated within the stated dates."
            if approve
            else "You withdraw this approval; no further report is accepted under it. Results "
            "already recorded stay as they are and remain listed on the approval."
        ),
        button="Sign and approve" if approve else "Sign and revoke",
        facts=_approval_facts(approval, approve=approve),
        revision=approval.revision,
        cancel_url=detail,
        run=lambda d: service(
            actor=request.user,
            pin=d["pin"],
            approval=approval,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Contract laboratory approval signed."
        if approve
        else "Contract laboratory approval revoked.",
        success_url=detail,
        denial=contract.approval_denial(request.user, approval, approve=approve),
        crumbs=_crumbs(
            (approval.laboratory.code, _laboratory_url(approval.laboratory)),
            (approval.label, detail),
            ("Approve" if approve else "Revoke", None),
        ),
    )


@login_required
def contract_approval_approve(request, pk):
    return _approval_sign(request, pk, approve=True)


@login_required
def contract_approval_revoke(request, pk):
    return _approval_sign(request, pk, approve=False)
