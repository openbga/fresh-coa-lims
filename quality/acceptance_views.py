"""Pages for supplier results accepted in place of a test (HTTP only; rules in ``reliance``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.web import run
from core.services import require_role
from laboratory.forms import SigningForm
from laboratory.ui import action, cell, record_page, sign_page, status
from laboratory.ui import when as stamp

from . import reliance
from .certificate_views import certificate_url
from .forms import AcceptanceProposalForm, AcceptanceWithdrawalForm
from .models import SupplierCertificateResult, SupplierResultAcceptance
from .views import LOTS, access, action_page

STATE = reliance.STATE
TONES = {STATE.PROPOSED: "progress", STATE.ACCEPTED: "success", STATE.WITHDRAWN: "neutral"}
WHAT_IT_IS = (
    "The supplier's stated result then answers this requirement of the lot in place of a "
    "laboratory test. It stays the supplier's result and is named as such on the certificate "
    "of analysis."
)


def acceptance_url(acceptance):
    return reverse("quality:acceptance_detail", args=[acceptance.pk])


def _lot_url(lot):
    return reverse("quality:lot_detail", args=[lot.pk])


def _crumbs(lot, *pairs):
    return [(LOTS, reverse("quality:lot_list")), (lot.number, _lot_url(lot)), *pairs]


def _roles(user):
    return set(user.groups.values_list("name", flat=True))


def evidence_facts(evidence, *, lot=None, links=True):
    """What an acceptance relies on, as the words every page of it shows."""
    certificate, supplier = evidence["certificate"], evidence["supplier"]
    qualification, rules = evidence["qualification"], evidence["rules"]
    stated = evidence["stated"]
    kept = rules["own_tests"]
    facts = [
        ("Test", f"{evidence['name']} ({evidence['test_code']})"),
        ("Specification", evidence["acceptance"]),
        ("Requirement", evidence["requirement_source"]),
        ("Supplier's result", reliance.stated_text(evidence)),
        ("Method stated", stated["method"]),
        ("Limits stated", stated["limits"]),
        (
            "Supplier certificate",
            cell(
                f"{certificate['number']} dated {certificate['issued_on']}, issued by "
                f"{certificate['issued_by']}",
                reverse("quality:certificate_detail", args=[certificate["id"]]) if links else None,
            ),
        ),
        ("Lot number on the certificate", certificate["stated_lot"]),
        ("Where the certificate is kept", certificate["document_ref"]),
        (
            "Supplier",
            cell(
                f"{supplier['code']} · {supplier['name']}, {supplier['location']}",
                reverse("suppliers:detail", args=[supplier["id"]]) if links else None,
            ),
        ),
        ("Lot received", evidence["received_on"]),
        (
            "Supplier qualification",
            cell(
                f"{qualification['label']} · {qualification['evidence_ref']} · valid "
                f"{qualification['valid_from']} to {qualification['valid_until']}",
                reverse("suppliers:qualification_detail", args=[qualification["id"]])
                if links
                else None,
            ),
        ),
        (
            "Rule set",
            f"{rules['code']} version {rules['version']} · the laboratory always performs: "
            f"{', '.join(kept) if kept else 'no test named'}",
        ),
    ]
    # Rule sets that apply to the lot in addition to its own each allowed the reliance too.
    for extra in evidence.get("additional_rules", []):
        facts.append(
            (
                "Additional rule set",
                f"{extra['code']} version {extra['version']} · the laboratory always performs: "
                f"{', '.join(extra['own_tests']) if extra['own_tests'] else 'no test named'}",
            )
        )
    if lot is not None:
        facts.insert(0, ("Lot", cell(f"{lot.number} · {lot.material}", _lot_url(lot))))
    return facts


@login_required
@require_http_methods(["GET", "POST"])
def acceptance_new(request, pk):
    """Propose one stated result of a supplier certificate in place of a test."""
    require_role(request.user, reliance.PROPOSER_ROLE)
    result = get_object_or_404(
        SupplierCertificateResult.objects.select_related("certificate__lot__rules"), pk=pk
    )
    lot, back = result.certificate.lot, certificate_url(result.certificate)
    evidence = None
    if request.method != "POST":
        # A page is not offered for a proposal the records, the rule set or the supplier's
        # qualification refuse; a submission is always decided by the service.
        refusal = reliance.proposal_refusal(lot, result)
        if refusal:
            messages.error(request, refusal)
            return redirect(back)
    try:
        evidence = reliance.proposal_basis(lot, result)
    except ValidationError:
        evidence = None  # The submission below reports why, and the refusal is audited.
    token = reliance.basis_token(evidence) if evidence else ""
    form = AcceptanceProposalForm(request.POST or None, initial={"basis": token})
    if request.method == "POST" and form.is_valid():
        acceptance = run(
            form,
            lambda: reliance.propose_acceptance(
                actor=request.user,
                result=result,
                basis=form.cleaned_data["basis"],
                reason=form.cleaned_data["reason"],
            ),
        )
        if acceptance:
            messages.success(
                request, "Supplier result proposed in place of a test; a reviewer accepts it."
            )
            return redirect(acceptance_url(acceptance))
        # A refused submission is shown again with what a proposal would rely on now, and
        # carries that token, so the proposer reviews it before submitting again.
        data = form.data.copy()
        data["basis"] = token
        form.data = data
    title = "Propose supplier result in place of a test"
    return action_page(
        request,
        form,
        title=title,
        crumbs=_crumbs(
            lot,
            (f"Supplier certificate {result.certificate.number}", back),
            (title, None),
        ),
        cancel_url=back,
        submit="Propose supplier result",
        intro="A proposal answers nothing by itself. A reviewer who recorded none of this "
        "certificate checks it against the certificate and signs the acceptance. " + WHAT_IT_IS,
        facts=[
            (label, value["text"] if isinstance(value, dict) else value)
            for label, value in (
                evidence_facts(evidence, lot=lot, links=False)
                if evidence
                else [("Lot", lot.number), ("Test", result.test_code)]
            )
        ],
    )


def _acceptance(pk):
    return get_object_or_404(
        SupplierResultAcceptance.objects.select_related(
            "lot", "result__certificate", "qualification", "proposed_by", "withdrawn_by"
        ),
        pk=pk,
    )


def _notice(acceptance, problems, revoked):
    if acceptance.state == STATE.WITHDRAWN:
        return {
            "tone": "info",
            "label": "Withdrawn",
            "text": "This record no longer stands and is kept as recorded. Reason: "
            f"{acceptance.withdrawal_reason}",
        }
    if problems:
        return {
            "tone": "warning",
            "label": "No longer stands",
            "text": "What this record relied on has changed: "
            + "; ".join(problems)
            + ". It answers nothing and blocks the lot's disposition until it is withdrawn. "
            "Then propose the supplier's result again or test the requirement in the "
            "laboratory.",
        }
    if revoked:
        return {"tone": "warning", "label": "Qualification revoked", "text": revoked}
    if acceptance.state == STATE.PROPOSED:
        return {
            "tone": "info",
            "label": "Awaiting acceptance",
            "text": "This proposal answers nothing yet and blocks the lot's disposition until "
            "a reviewer accepts it or it is withdrawn.",
        }
    return {
        "tone": "info",
        "label": "Accepted",
        "text": "The supplier's stated result answers this requirement of the lot in place of "
        "a laboratory test. It stays the supplier's result and is named as such on the "
        "certificate of analysis.",
    }


@login_required
def acceptance_detail(request, pk):
    access(request.user)
    acceptance = _acceptance(pk)
    lot, user, roles = acceptance.lot, request.user, _roles(request.user)
    problems = reliance.standing_problems(acceptance, lot) if acceptance.stands else []
    revoked = ""
    if acceptance.state == STATE.ACCEPTED:
        from suppliers.qualification import reliance_notice

        revoked = reliance_notice(acceptance.evidence)
    can_accept = (
        reliance.ACCEPTOR_ROLE in roles
        and lot.state == "quarantine"
        and not problems
        and not reliance.acceptance_denial(user, acceptance)
    )
    can_withdraw = bool(
        roles & set(reliance.withdrawal_roles(acceptance))
    ) and not reliance.withdrawal_refusal(acceptance)
    return record_page(
        request,
        identifier=acceptance.label,
        title=f"Supplier result · {acceptance.evidence['name']}",
        crumbs=_crumbs(lot, (acceptance.label, None)),
        state=status(acceptance.get_state_display(), TONES[acceptance.state]),
        facts=[
            *evidence_facts(acceptance.evidence, lot=lot),
            ("Proposed by", str(acceptance.proposed_by)),
            ("Proposed", stamp(acceptance.proposed_at)),
            ("Reason", acceptance.reason),
            ("Accepted", stamp(acceptance.accepted_at)),
            (
                "Withdrawn",
                f"{stamp(acceptance.withdrawn_at)} by {acceptance.withdrawn_by}"
                if acceptance.withdrawn_at
                else "",
            ),
            ("Revision", acceptance.revision),
        ],
        actions=[
            action("Accept", reverse("quality:acceptance_accept", args=[acceptance.pk]), True)
            if can_accept
            else None,
            action("Withdraw", reverse("quality:acceptance_withdraw", args=[acceptance.pk]))
            if can_withdraw
            else None,
        ],
        related=[acceptance],
        notice=_notice(acceptance, problems, revoked),
    )


@login_required
def acceptance_accept(request, pk):
    require_role(request.user, reliance.ACCEPTOR_ROLE)
    acceptance = _acceptance(pk)
    detail = acceptance_url(acceptance)
    denial = reliance.acceptance_denial(request.user, acceptance)
    if not denial and acceptance.lot.state != "quarantine":
        denial = reliance.QUARANTINE_ONLY
    if not denial and (problems := reliance.standing_problems(acceptance)):
        denial = "This proposal no longer stands: " + "; ".join(problems) + ". Withdraw it."
    form = SigningForm(request.POST or None, initial={"expected_revision": acceptance.revision})
    return sign_page(
        request,
        form,
        title="Accept supplier result in place of a test",
        identifier=acceptance.label,
        meaning="accepted",
        meaning_text=(
            "You accept the supplier's stated result in place of the laboratory's own test of "
            "this requirement, having checked the record against the supplier's certificate. "
            "It stays the supplier's result."
        ),
        button="Sign and accept",
        facts=[
            *evidence_facts(acceptance.evidence, lot=acceptance.lot),
            ("Proposed by", str(acceptance.proposed_by)),
            ("Reason", acceptance.reason),
        ],
        revision=acceptance.revision,
        cancel_url=detail,
        run=lambda d: reliance.accept_result(
            actor=request.user,
            pin=d["pin"],
            acceptance=acceptance,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Supplier result accepted in place of a test.",
        success_url=detail,
        denial=denial,
        crumbs=_crumbs(acceptance.lot, (acceptance.label, detail), ("Accept", None)),
    )


@login_required
@require_http_methods(["GET", "POST"])
def acceptance_withdraw(request, pk):
    """Withdraw a proposal with a reason, or an acceptance already signed with a signature."""
    require_role(request.user, *reliance.WITHDRAW_ROLES)
    acceptance = _acceptance(pk)
    detail = acceptance_url(acceptance)
    if request.method != "POST" and (refusal := reliance.withdrawal_refusal(acceptance)):
        messages.error(request, refusal)
        return redirect(detail)
    title = "Withdraw supplier result"
    crumbs = _crumbs(acceptance.lot, (acceptance.label, detail), (title, None))
    facts = [
        ("Lot", acceptance.lot.number),
        ("Record", acceptance.label),
        ("Test", f"{acceptance.evidence['name']} ({acceptance.test_code})"),
        ("Supplier's result", reliance.stated_text(acceptance.evidence)),
        ("State", acceptance.get_state_display()),
    ]
    if acceptance.state == STATE.ACCEPTED:
        # It reverses a signed decision: a reviewer or a quality person signs.
        require_role(request.user, *reliance.SIGNED_WITHDRAW_ROLES)
        form = SigningForm(request.POST or None, initial={"expected_revision": acceptance.revision})
        return sign_page(
            request,
            form,
            title=title,
            identifier=acceptance.label,
            meaning="withdrawn",
            meaning_text=(
                "You withdraw the acceptance of this supplier's result. It no longer answers "
                "the requirement: the laboratory tests it, or the supplier's result is proposed "
                "again. The record and its signatures are kept."
            ),
            button="Sign and withdraw",
            facts=facts,
            revision=acceptance.revision,
            cancel_url=detail,
            run=lambda d: reliance.withdraw_accepted(
                actor=request.user,
                pin=d["pin"],
                acceptance=acceptance,
                expected_revision=d["expected_revision"],
                reason=d["reason"],
            ),
            success="Supplier result withdrawn; the record is kept.",
            success_url=detail,
            denial=reliance.withdrawal_refusal(acceptance),
            crumbs=crumbs,
        )
    form = AcceptanceWithdrawalForm(
        request.POST or None, initial={"expected_revision": acceptance.revision}
    )
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: reliance.withdraw_proposal(
                actor=request.user, acceptance=acceptance, **form.cleaned_data
            ),
        )
        if done:
            messages.success(request, "Supplier result withdrawn; the record is kept.")
            return redirect(detail)
    return action_page(
        request,
        form,
        title=title,
        crumbs=crumbs,
        cancel_url=detail,
        submit=title,
        tone="danger",
        intro="A withdrawn proposal no longer stands for the requirement: the laboratory tests "
        "it, or the supplier's result is proposed again. The record is kept.",
        facts=facts,
    )
