"""Pages of the reassessment of a released lot (HTTP only; rules in ``quality.reassessment``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from analytical import services as analytical
from analytical.contracts import parse_requirement, resolve_reassessment
from catalog.web import run
from core.people import person
from core.services import require_role
from laboratory.forms import SigningForm
from laboratory.ui import action, cell, day, record_page, refused, section, sign_page, status
from laboratory.ui import when as stamp

from . import reassessment
from .forms import ReassessmentConclusionForm, ReassessmentForm, ReassessmentTestsForm
from .models import Lot, Reassessment
from .views import LOTS, access, action_page

STATE = Reassessment.State
OUTCOME = Reassessment.Outcome
WHAT_IT_IS = (
    "The tests belong to the reassessment: the lot's record, its dates as frozen at release and "
    "its disposition are not changed."
)


def detail_url(item):
    return reverse("quality:reassessment_detail", args=[item.pk])


def _lot_url(lot):
    return reverse("quality:lot_detail", args=[lot.pk])


def _crumbs(lot, *pairs):
    return [(LOTS, reverse("quality:lot_list")), (lot.number, _lot_url(lot)), *pairs]


def _roles(user):
    return set(user.groups.values_list("name", flat=True))


def state_cell(item):
    """The reassessment's state as a status label: its outcome once concluded."""
    return status(*reassessment.status_of(item))


def _item(pk):
    return get_object_or_404(Reassessment.objects.select_related("lot__rules", "started_by"), pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def reassessment_new(request, pk):
    """Start the reassessment of a released lot, recording the sample taken for it."""
    require_role(request.user, *reassessment.START_ROLES)
    lot = get_object_or_404(Lot.objects.select_related("rules"), pk=pk)
    back = _lot_url(lot)
    if request.method != "POST" and (refusal := reassessment.start_refusal(lot)):
        messages.error(request, refusal)
        return redirect(back)
    form = ReassessmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        item = run(form, lambda: reassessment.start(actor=request.user, lot=lot, **data))
        if item:
            messages.success(request, f"{item.label} started; assign its tests.")
            return redirect(detail_url(item))
    found = reassessment.dates.in_force(lot)
    title = "Start reassessment"
    return action_page(
        request,
        form,
        title=title,
        crumbs=_crumbs(lot, (title, None)),
        cancel_url=back,
        submit=title,
        intro="Record the sample taken to examine the material again. Its tests are then "
        "assigned from the specifications in force for the lot. " + WHAT_IT_IS,
        facts=[
            ("Lot", lot.number),
            ("Material", lot.material),
            ("Retest date", day(found.retest_on)),
            ("Expiry date", day(found.expiry_on) or "None"),
        ],
    )


def _test_state(test):
    """The test's result as plain data, then where it stands as its status label."""
    result = test.reportable_with_unit
    if test.state == "invalidated":
        return cell(result, pill=("Invalidated", "neutral")) if result else status("Invalidated")
    if test.state == "not_completed":
        return status("Not completed", "neutral")
    if test.state == "open":
        return status("Open", "progress")
    if test.conforms is False:
        waiting = "awaiting review" if test.state == "submitted" else "reviewed"
        return cell(result, pill=(f"Out of specification · {waiting}", "danger"))
    if test.state == "submitted":
        return cell(result, pill=("Awaiting review", "info"))
    return cell(result, pill=("Conforms · reviewed", "success"))


def _tests_section(item, found):
    table = []
    for row in found.rows:
        for test in row["lineage"]:
            spec = test.spec
            table.append(
                [
                    cell(
                        f"{test.label} · {spec.name} ({test.test_code})",
                        reverse("analytical:test_detail", args=[test.pk]),
                    ),
                    _test_state(test),
                    spec.acceptance,
                    test.get_kind_display(),
                ]
            )
    if item.state == STATE.CONCLUDED:
        note = f"Concluded: {item.get_outcome_display().lower()}."
    elif item.state == STATE.WITHDRAWN:
        note = "Withdrawn; its tests take no more work."
    elif not found.codes:
        note = "No test is assigned yet."
    elif found.suitable_refusal:
        note = found.suitable_refusal
    else:
        note = "Every test has a reviewed result that conforms. A quality person concludes it."
    return section(
        "Tests",
        [
            ("Test", False),
            ("Result and status", False),
            ("Acceptance criterion", False, "medium"),
            ("Kind", False, "low"),
        ],
        table,
        "No test assigned.",
        note=note + " Each test is recorded, reviewed and signed on its own page, against the "
        "acceptance criterion frozen when it was assigned.",
    )


def _notice(item, found):
    if item.state == STATE.CONCLUDED and item.outcome == OUTCOME.SUITABLE:
        return {
            "tone": "success",
            "label": "Suitable",
            "text": f"The lot's retest date in force is {item.retest_on.isoformat()}, set by this "
            "reassessment.",
        }
    if item.state == STATE.CONCLUDED:
        return {
            "tone": "danger",
            "label": "Use ended",
            "text": "This reassessment ended the use of the lot. It keeps its released "
            "disposition as signed, takes no certificate and is not reassessed again.",
        }
    if item.state == STATE.WITHDRAWN:
        return {
            "tone": "info",
            "label": "Withdrawn",
            "text": f"This reassessment was withdrawn and is kept as recorded. Reason: "
            f"{item.decision_reason}",
        }
    if found.failed:
        return {
            "tone": "danger",
            "label": "Out of specification",
            "text": "A result does not meet its acceptance criterion. Once its investigation is "
            "concluded, quality concludes that the material is not suitable.",
        }
    return None


@login_required
def reassessment_detail(request, pk):
    access(request.user)
    item = _item(pk)
    lot, roles = item.lot, _roles(request.user)
    found = reassessment.review(item)
    is_open = item.state == STATE.OPEN
    actions = []
    if is_open and "analyst" in roles:
        accepted, holds = resolve_reassessment(item)
        if holds:
            actions.append(refused("Tests cannot be assigned: " + " ".join(holds)))
        elif set(accepted) - set(found.codes):
            actions.append(
                action(
                    "Assign tests",
                    reverse("quality:reassessment_tests", args=[item.pk]),
                    not found.codes,
                )
            )
    if is_open and reassessment.QUALITY in roles:
        if request.user.pk in reassessment.author_ids(item):
            actions.append(
                refused(
                    "You started, tested or investigated it: another quality person concludes it."
                )
            )
        else:
            actions.append(
                action(
                    "Conclude",
                    reverse("quality:reassessment_conclude", args=[item.pk]),
                    bool(found.codes) and not found.suitable_refusal,
                )
            )
        if not found.withdraw_refusal:
            actions.append(
                action(
                    "Withdraw",
                    reverse("quality:reassessment_withdraw", args=[item.pk]),
                    danger=True,
                    more=True,
                )
            )
    basis = item.dates_basis
    return record_page(
        request,
        identifier=item.label,
        title=f"Reassessment of {lot.number}",
        crumbs=_crumbs(lot, (item.label, None)),
        state=state_cell(item),
        facts=[
            ("Lot", cell(f"{lot.number} · {lot.material}", _lot_url(lot))),
            ("Retest date when started", basis.get("retest_on") or ""),
            ("Expiry date", basis.get("expiry_on") or "None"),
            ("Sample", item.sample_reference),
            ("Date sampled", day(item.sampled_on)),
            ("Quantity taken", f"{item.quantity_text} {item.quantity_unit}"),
            ("Containers sampled", item.containers),
            ("Reason", item.reason),
            ("Started by", person(item.started_by)),
            ("Started", stamp(item.started_at)),
            ("New retest date", day(item.retest_on)),
            ("Decided", stamp(item.decided_at)),
            ("Reason for the decision", item.decision_reason),
            ("Revision", item.revision),
        ],
        actions=actions,
        sections=[_tests_section(item, found)],
        related=[item],
        notice=_notice(item, found),
    )


@login_required
@require_http_methods(["GET", "POST"])
def reassessment_tests(request, pk):
    """Assign the reassessment's tests, showing the acceptance criteria that will be frozen."""
    require_role(request.user, "analyst")
    item = _item(pk)
    detail = detail_url(item)
    if refusal := reassessment.refusal(item):
        messages.warning(request, refusal)
        return redirect(detail)
    accepted, holds = resolve_reassessment(item)
    if holds:
        messages.warning(request, "Tests cannot be assigned: " + " ".join(holds))
        return redirect(detail)
    existing = set(item.tests.values_list("test_code", flat=True))
    if not set(accepted) - existing:
        messages.info(request, "Every test of the reassessment is already assigned.")
        return redirect(detail)
    form = ReassessmentTestsForm(
        request.POST or None, initial={"criteria": analytical.pull_criteria_hash(accepted)}
    )
    if request.method == "POST" and form.is_valid():
        created = run(
            form,
            lambda: analytical.assign_reassessment_tests(
                actor=request.user,
                reassessment=item,
                reason=form.cleaned_data["reason"],
                criteria_hash=form.cleaned_data["criteria"],
            ),
        )
        if created:
            messages.success(request, f"Assigned {len(created)} test(s) to {item.label}.")
            return redirect(detail)
        if created is not None:  # another analyst assigned them meanwhile
            messages.info(request, "Every test of the reassessment is already assigned.")
            return redirect(detail)
        # Show the criteria in force now with their token, so the page can be submitted after
        # review without being opened again.
        accepted, holds = resolve_reassessment(item)
        if holds:
            messages.warning(request, "Tests cannot be assigned: " + " ".join(holds))
            return redirect(detail)
        data = form.data.copy()
        data["criteria"] = analytical.pull_criteria_hash(accepted)
        form.data = data
        existing = set(item.tests.values_list("test_code", flat=True))
    criteria = []
    for code, payload in accepted.items():
        spec = parse_requirement(payload)
        criteria.append(
            {
                "code": code,
                "name": spec.name,
                "acceptance": spec.acceptance,
                "method": f"{spec.method.code} revision {spec.method.revision}",
                "replicates": spec.replicates,
                "source": spec.source,
                "assigned": code in existing,
            }
        )
    return render(
        request,
        "quality/reassessment_tests.html",
        {
            "page_title": f"Assign tests · {item.label}",
            "crumbs": _crumbs(item.lot, (item.label, detail), ("Assign tests", None)),
            "item": item,
            "criteria": criteria,
            "form": form,
            "cancel_url": detail,
        },
        status=422 if request.method == "POST" and form.errors else 200,
    )


def _summary(item, found):
    """What the signer of a conclusion or a withdrawal sees: the lot, its dates, the sample and
    the outcome of each test."""
    facts = [
        ("Lot", f"{item.lot.number} · {item.lot.material}"),
        ("Reassessment", f"{item.label} · sample {item.sample_reference}"),
        ("Retest date in force", day(found.retest_on)),
        ("Expiry date", day(found.expiry_on) or "None"),
    ]
    labels = {"conforms": "Conforms", "fails": "Does not conform", "": "Not decided"}
    for row in found.rows:
        reported = ", ".join(test.reportable_with_unit for test in row["tests"]) or "no result"
        name = row["lineage"][0].spec.name if row["lineage"] else row["test_code"]
        facts.append((name, f"{reported} · {labels[row['outcome']]}"))
    if found.blockers:
        facts.append(("Not complete", " ".join(found.blockers)))
    return facts


@login_required
@require_http_methods(["GET", "POST"])
def reassessment_conclude(request, pk):
    require_role(request.user, reassessment.QUALITY)
    item = _item(pk)
    detail = detail_url(item)
    found = reassessment.review(item)
    denial = ""
    if item.state != STATE.OPEN:
        denial = reassessment.NOT_OPEN
    elif request.user.pk in reassessment.author_ids(item):
        denial = reassessment.SELF_CONCLUSION
    elif found.suitable_refusal and found.end_refusal:
        denial = found.end_refusal
    form = ReassessmentConclusionForm(
        request.POST or None,
        initial={
            "expected_revision": item.revision,
            "outcome": OUTCOME.NOT_SUITABLE if found.suitable_refusal else OUTCOME.SUITABLE,
        },
    )
    if found.suitable_refusal:
        form.fields[
            "outcome"
        ].help_text = f"The material cannot be found suitable: {found.suitable_refusal}"
    return sign_page(
        request,
        form,
        title=f"Conclude {item.label}",
        identifier=item.label,
        meaning="reassessed",
        meaning_text=(
            "You conclude the reassessment of the lot's material on the results shown. Suitable: "
            "the material may be used until the new retest date, which becomes the lot's retest "
            "date in force. Not suitable: the lot's use ends; it keeps its released disposition "
            "as signed, takes no certificate and is not reassessed again."
        ),
        button="Sign and conclude",
        facts=_summary(item, found),
        revision=item.revision,
        cancel_url=detail,
        run=lambda d: reassessment.conclude(
            actor=request.user,
            pin=d["pin"],
            reassessment=item,
            expected_revision=d["expected_revision"],
            outcome=d["outcome"],
            retest_on=d["retest_on"],
            reason=d["reason"],
        ),
        success=f"{item.label} concluded.",
        success_url=detail,
        denial=denial,
        crumbs=_crumbs(item.lot, (item.label, detail), ("Conclude", None)),
    )


@login_required
@require_http_methods(["GET", "POST"])
def reassessment_withdraw(request, pk):
    require_role(request.user, reassessment.QUALITY)
    item = _item(pk)
    detail = detail_url(item)
    found = reassessment.review(item)
    denial = reassessment.NOT_OPEN if item.state != STATE.OPEN else found.withdraw_refusal
    form = SigningForm(request.POST or None, initial={"expected_revision": item.revision})
    return sign_page(
        request,
        form,
        title=f"Withdraw {item.label}",
        identifier=item.label,
        meaning="withdrawn",
        meaning_text=(
            "You withdraw a reassessment started in error. Its tests take no more work and the "
            "lot's dates in force do not change. The record, its tests and their results are "
            "kept."
        ),
        button="Sign and withdraw",
        facts=_summary(item, found),
        revision=item.revision,
        cancel_url=detail,
        run=lambda d: reassessment.withdraw(
            actor=request.user,
            pin=d["pin"],
            reassessment=item,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"{item.label} withdrawn; the record is kept.",
        success_url=detail,
        denial=denial,
        crumbs=_crumbs(item.lot, (item.label, detail), ("Withdraw", None)),
    )
