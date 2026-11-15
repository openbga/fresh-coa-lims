"""Pages for supplier qualifications (HTTP only; the rules are in ``qualification``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.web import form_status, run
from core.services import require_role
from laboratory.forms import SigningForm
from laboratory.ui import action, cell, day, external_link, record_page, section, sign_page, status
from laboratory.ui import when as stamp

from . import qualification as rules
from . import services
from .forms import MaterialChoiceForm, QualificationForm
from .models import Supplier, SupplierQualification

SECTION = "Suppliers"
KEEPER = rules.KEEPER_ROLE
ACCEPTANCES_SHOWN = 50
NOT_BY_ITSELF = (
    "A qualification lets a result the supplier's certificate states stand in for a test only "
    "where the lot's rule set allows it, and only through an acceptance signed on the lot."
)


def _supplier_url(supplier):
    return reverse("suppliers:detail", args=[supplier.pk])


def qualification_url(qualification):
    return reverse("suppliers:qualification_detail", args=[qualification.pk])


def _crumbs(supplier, *pairs):
    return [
        (SECTION, reverse("suppliers:list")),
        (supplier.code, _supplier_url(supplier)),
        *pairs,
    ]


def _keeper(user):
    return user.groups.filter(name=KEEPER).exists()


def tests_text(qualification, names=None):
    """The tests a qualification covers, by name where the material's specifications name them."""
    names = names if names is not None else rules.material_test_codes(qualification.material)
    return ", ".join(
        f"{names[code]} ({code})" if code in names else code for code in qualification.test_codes
    )


def qualification_rows(supplier):
    """A supplier's qualifications for its record page, newest first."""
    rows = []
    for item in supplier.qualifications.select_related("material").order_by("-valid_from", "-pk"):
        label, tone = rules.qualification_status(item)
        rows.append({"qualification": item, "label": label, "tone": tone})
    return rows


@login_required
@require_http_methods(["GET", "POST"])
def qualification_new(request, pk):
    require_role(request.user, KEEPER)
    supplier = get_object_or_404(Supplier, pk=pk)
    title = f"Record qualification · {supplier.code}"
    crumbs = _crumbs(supplier, ("Record qualification", None))
    chosen = MaterialChoiceForm(request.GET if "material" in request.GET else None)
    if not chosen.is_bound or not chosen.is_valid():
        # First step, without a write: the material decides which tests can be covered.
        return render(
            request,
            "suppliers/qualification_material.html",
            {
                "page_title": title,
                "form": chosen,
                "crumbs": crumbs,
                "cancel_url": _supplier_url(supplier),
                "supplier": supplier,
            },
        )
    material = chosen.cleaned_data["material"]
    tests = rules.material_test_codes(material)
    form = QualificationForm(request.POST or None, tests=tests)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        done = run(
            form,
            lambda: rules.record_qualification(
                actor=request.user, supplier=supplier, material=material, **data
            ),
        )
        if done:
            messages.success(
                request, "Qualification evidence recorded; a second quality signer approves."
            )
            return redirect(qualification_url(done))
    return render(
        request,
        "catalog/form.html",
        {
            "page_title": title,
            "form": form,
            "crumbs": crumbs,
            "cancel_url": _supplier_url(supplier),
            "submit_label": "Record qualification",
            "intro": "Recording evidence qualifies nothing. A different quality signer approves "
            "it. " + NOT_BY_ITSELF,
            "facts": [
                ("Supplier", str(supplier)),
                ("Material", str(material)),
                *(
                    []
                    if tests
                    else [
                        (
                            "Tests",
                            "No specification of this material states a test yet. Add the "
                            "material's specification first.",
                        )
                    ]
                ),
            ],
        },
        status=form_status(request, form),
    )


def _qualification(pk):
    return get_object_or_404(
        SupplierQualification.objects.select_related("supplier", "material", "recorded_by"),
        pk=pk,
    )


def _accepted_section(qualification):
    """The supplier results proposed or accepted under this qualification, newest first."""
    acceptances = qualification.acceptances.select_related("lot", "proposed_by").order_by(
        "-proposed_at", "-pk"
    )
    total = acceptances.count()
    rows = []
    for item in acceptances[:ACCEPTANCES_SHOWN]:
        evidence = item.evidence
        stated = evidence["stated"]
        rows.append(
            [
                cell(item.label, reverse("quality:acceptance_detail", args=[item.pk])),
                cell(item.lot.number, reverse("quality:lot_detail", args=[item.lot_id])),
                item.lot.state.capitalize(),
                f"{evidence['name']} ({item.test_code})",
                f"{stated['result']} {evidence['unit']}".strip(),
                evidence["certificate"]["number"],
                evidence["received_on"],
                item.get_state_display(),
                str(item.proposed_by),
            ]
        )
    note = (
        "Each row is one result of a supplier's certificate proposed or accepted in place of a "
        "test under this qualification, with the lot as it stands now."
    )
    if total > len(rows):
        note += f" Showing the latest {len(rows)} of {total}."
    return total, section(
        "Supplier results that relied on this qualification",
        [
            ("Acceptance", False),
            ("Lot", False),
            ("Lot status", False),
            ("Test", False),
            ("Result stated", False),
            ("Certificate", False),
            ("Lot received", False),
            ("State", False),
            ("Proposed by", False),
        ],
        rows,
        "No supplier result has relied on it.",
        note=note,
    )


def _signed_count(qualification):
    """Signed acceptances under this qualification that have not been withdrawn."""
    return qualification.acceptances.filter(state="accepted").count()


def _facts(qualification, *, revoke=False):
    """What the signer signs: everything the signature's snapshot holds."""
    supplier = qualification.supplier
    facts = [
        ("Supplier", cell(str(supplier), _supplier_url(supplier))),
        ("Material", str(qualification.material)),
        ("Tests covered", tests_text(qualification)),
        ("Valid", f"{day(qualification.valid_from)} to {day(qualification.valid_until)}"),
        ("How the supplier was qualified", qualification.basis),
        ("Evidence", qualification.evidence_ref),
        ("Evidence link", external_link(qualification.evidence_url)),
        ("Recorded by", str(qualification.recorded_by)),
    ]
    if revoke:
        facts.append(("Accepted supplier results that relied on it", _signed_count(qualification)))
    return facts


@login_required
def qualification_detail(request, pk):
    require_role(request.user, *services.READ_ROLES)
    qualification = _qualification(pk)
    supplier = qualification.supplier
    label, tone = rules.qualification_status(qualification)
    keeper = _keeper(request.user)
    _, accepted = _accepted_section(qualification)
    signed = _signed_count(qualification)
    notice = None
    if qualification.state == "revoked" and signed:
        notice = {
            "tone": "warning",
            "label": "Assess the results",
            "text": f"{signed} accepted supplier result{'s' if signed != 1 else ''} relied on "
            "this qualification before it was revoked. Each acceptance stands as signed. "
            "Assess them under your procedure: the software records no assessment and holds "
            "no lot by itself. A proposal not yet accepted can no longer be signed.",
        }
    return record_page(
        request,
        identifier=qualification.label,
        title=f"{supplier.code} · {qualification.material.code}",
        crumbs=_crumbs(supplier, (qualification.label, None)),
        state=status(label, tone),
        facts=[
            ("Supplier", cell(str(supplier), _supplier_url(supplier))),
            ("Material", str(qualification.material)),
            ("Tests covered", tests_text(qualification)),
            ("Valid from", day(qualification.valid_from)),
            ("Valid until (inclusive)", day(qualification.valid_until)),
            ("How the supplier was qualified", qualification.basis),
            ("Evidence reference", qualification.evidence_ref),
            ("Evidence link", external_link(qualification.evidence_url)),
            ("Recorded by", str(qualification.recorded_by)),
            ("Recorded", stamp(qualification.recorded_at)),
            ("Approved", stamp(qualification.approved_at)),
            ("Revoked", stamp(qualification.revoked_at)),
            ("Revision", qualification.revision),
        ],
        actions=[
            action(
                "Approve",
                reverse("suppliers:qualification_approve", args=[qualification.pk]),
                True,
            )
            if keeper and not rules.qualification_denial(request.user, qualification, approve=True)
            else None,
            action("Revoke", reverse("suppliers:qualification_revoke", args=[qualification.pk]))
            if keeper and not rules.qualification_denial(request.user, qualification, approve=False)
            else None,
        ],
        sections=[accepted],
        related=[qualification],
        notice=notice
        or {"tone": "info", "label": "What a qualification does", "text": NOT_BY_ITSELF},
    )


def _sign(request, pk, *, approve):
    require_role(request.user, KEEPER)
    qualification = _qualification(pk)
    detail = qualification_url(qualification)
    form = SigningForm(request.POST or None, initial={"expected_revision": qualification.revision})
    service = rules.approve_qualification if approve else rules.revoke_qualification
    return sign_page(
        request,
        form,
        title=f"{'Approve' if approve else 'Revoke'} supplier qualification",
        identifier=qualification.label,
        meaning="approved" if approve else "revoked",
        meaning_text=(
            "You approve this evidence as showing that the supplier's certificate results for "
            "the tests covered can be relied on, for lots received within the stated dates."
            if approve
            else "You withdraw this qualification; no further supplier result is accepted "
            "under it. Acceptances already signed stay as they are and remain listed on the "
            "qualification."
        ),
        button="Sign and approve" if approve else "Sign and revoke",
        facts=_facts(qualification, revoke=not approve),
        revision=qualification.revision,
        cancel_url=detail,
        run=lambda d: service(
            actor=request.user,
            pin=d["pin"],
            qualification=qualification,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success="Supplier qualification signed." if approve else "Supplier qualification revoked.",
        success_url=detail,
        denial=rules.qualification_denial(request.user, qualification, approve=approve),
        crumbs=_crumbs(
            qualification.supplier,
            (qualification.label, detail),
            ("Approve" if approve else "Revoke", None),
        ),
    )


@login_required
def qualification_approve(request, pk):
    return _sign(request, pk, approve=True)


@login_required
def qualification_revoke(request, pk):
    return _sign(request, pk, approve=False)
