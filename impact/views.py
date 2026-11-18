"""Pages of impact assessments (HTTP only; the rules are in ``impact.services``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.web import run
from core.people import person
from core.services import require_role
from laboratory.ui import (
    action,
    cell,
    day,
    list_page,
    make_filter,
    paginate,
    record_page,
    refused,
    section,
    sign_page,
    status,
)
from laboratory.ui import when as stamp
from quality.views import action_page

from . import scope, services
from .forms import AddRecordForm, AssessmentSigningForm, DecisionForm, FindForm, HoldForm, StartForm
from .models import Assessment, Item

STATE = Assessment.State
KIND = Item.Kind
DECISION = Item.Decision
TITLE = "Impact assessments"
WHAT_IT_IS = (
    "The assessment records what the problem affected and what is done about it. It changes "
    "none of the records it names: each is acted on through its own page and signature."
)
# Each kind of record in the order the page shows them, with its section title.
SECTIONS = (
    (KIND.TEST, "Tests"),
    (KIND.LOT, "Lots"),
    (KIND.STUDY, "Stability studies"),
    (KIND.CERTIFICATE, "Certificates"),
)


def access(user):
    require_role(user, *services.READ_ROLES)


def _roles(user):
    return set(user.groups.values_list("name", flat=True))


def detail_url(assessment):
    return reverse("impact:detail", args=[assessment.pk])


def _crumbs(*pairs):
    return [(TITLE, reverse("impact:list")), *pairs]


def _assessment(pk):
    return get_object_or_404(
        Assessment.objects.select_related(
            "equipment", "reagent_lot", "supplier", "contract_laboratory", "started_by"
        ),
        pk=pk,
    )


def _cause_text(assessment):
    source = services.source_label(assessment)
    cause = assessment.get_cause_display()
    return f"{cause} · {source}" if source else cause


# List ------------------------------------------------------------------------------------------


@login_required
def assessment_list(request):
    access(request.user)
    form, data = make_filter(request, STATE.choices)
    queryset = Assessment.objects.select_related(
        "equipment", "reagent_lot", "supplier", "contract_laboratory", "started_by"
    ).annotate(
        records=Count("items"),
        undecided=Count("items", filter=Q(items__decision="")),
    )
    if text := data.get("q"):
        match = Q(title__icontains=text) | Q(quality_reference__icontains=text)
        digits = text.upper().removeprefix("IA-")
        if scope.CANONICAL_ID.fullmatch(digits):
            match |= Q(pk=int(digits))
        queryset = queryset.filter(match)
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {
            "assessment": ["id"],
            "found": ["found_on"],
            "status": ["state", "-started_at"],
            "undecided": ["undecided"],
        },
        "-assessment",
    )
    rows = []
    for item in page:
        rows.append(
            [
                cell(item.label, detail_url(item), sub=item.title),
                _cause_text(item),
                day(item.found_on),
                status(*services.status_of(item)),
                cell(str(item.records), numeric=True),
                cell(str(item.undecided), numeric=True)
                if item.state == STATE.OPEN
                else cell("", numeric=True),
                person(item.started_by),
            ]
        )
    return list_page(
        request,
        title=TITLE,
        intro="What an equipment, reagent, supplier, contract-laboratory or other problem "
        "affected, and the decision on each record. " + WHAT_IT_IS,
        noun="impact assessments",
        columns=[
            ("Assessment", "assessment", False),
            ("Cause", None, False),
            ("Date found", "found", False),
            ("Status", "status", False),
            ("Records", None, True),
            ("Without a decision", "undecided", True, "low"),
            ("Started by", None, False, "low"),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "impact assessment", "href": reverse("impact:new")}
        if services.QUALITY in _roles(request.user)
        else None,
        empty_body="Start one when equipment, a reagent or standard, a supplier, a contract "
        "laboratory or anything else may have affected work already done.",
    )


# Starting --------------------------------------------------------------------------------------


def _initial(request):
    """A start opened from the record that failed names it (``?equipment=<pk>`` and so on)."""
    initial = {}
    for name, cause in (
        ("equipment", Assessment.Cause.EQUIPMENT),
        ("reagent_lot", Assessment.Cause.REAGENT),
        ("supplier", Assessment.Cause.SUPPLIER),
        ("contract_laboratory", Assessment.Cause.CONTRACT),
    ):
        value = request.GET.get(name, "")
        if scope.CANONICAL_ID.fullmatch(value):
            initial[name], initial["cause"] = int(value), cause
            break
    return initial


@login_required
@require_http_methods(["GET", "POST"])
def assessment_new(request):
    require_role(request.user, services.QUALITY)
    form = StartForm(request.POST or None, initial=_initial(request))
    if request.method == "POST" and form.is_valid():
        item = run(form, lambda: services.start(actor=request.user, **form.cleaned_data))
        if item:
            found = item.items.count()
            messages.success(
                request,
                f"{item.label} started with {found} record(s) found from the cause; record a "
                "decision for each.",
            )
            return redirect(detail_url(item))
    title = "New impact assessment"
    return action_page(
        request,
        form,
        title=title,
        crumbs=_crumbs((title, None)),
        cancel_url=reverse("impact:list"),
        submit="Start assessment",
        intro="Name what failed and the period it may have affected. The system then finds the "
        "tests, lots, stability studies and certificates it can from the cause. " + WHAT_IT_IS,
    )


# The record ------------------------------------------------------------------------------------


def _decision_cell(item):
    if item.decision == DECISION.AFFECTED:
        return cell("Affected", tone="danger", sub=item.follow_up)
    if item.decision == DECISION.NOT_AFFECTED:
        return cell("Not affected", tone="success", sub=item.rationale)
    return status("No decision", "warning")


def _record_cell(item):
    target = item.target
    if item.kind == KIND.TEST:
        href = reverse("analytical:test_detail", args=[target.pk])
    elif item.kind == KIND.LOT:
        href = reverse("quality:lot_detail", args=[target.pk])
    elif item.kind == KIND.STUDY:
        href = reverse("stability:study_detail", args=[target.pk])
    else:
        href = reverse("reporting:detail", args=[target.pk])
    return cell(services.record_label(item), href, wrap=True)


def _hold_cell(item):
    if not item.hold_id:
        return ""
    hold = item.hold
    return cell(
        hold.identifier,
        reverse("stability:hold_detail", args=[hold.pk]),
        sub=hold.get_state_display(),
    )


def _action_cell(item, can_act, is_open):
    if not (can_act and is_open):
        return ""
    verb = "Change decision" if item.decision else "Record decision"
    return cell(verb, reverse("impact:decide", args=[item.pk]))


def _sections(assessment, items, can_act):
    is_open = assessment.state == STATE.OPEN
    sections = []
    for kind, title in SECTIONS:
        rows = []
        for item in (i for i in items if i.kind == kind):
            label, tone = services.record_status(item)
            row = [
                _record_cell(item),
                cell(label, tone=tone),
                cell(item.basis, wrap=True, sub=item.get_origin_display()),
                _decision_cell(item),
                item.follow_up_reference,
            ]
            if kind == KIND.LOT:
                row.append(_hold_cell(item))
                hold_link = (
                    cell("Place hold", reverse("impact:hold", args=[item.pk]))
                    if can_act and is_open and not services.hold_refusal(item)
                    else ""
                )
                row.append(hold_link)
            row.append(_action_cell(item, can_act, is_open))
            rows.append(row)
        if not rows:
            continue
        columns = [
            ("Record", False),
            ("Now", False),
            ("Why it is in the assessment", False, "medium"),
            ("Decision", False),
            ("Follow-up reference", False, "low"),
        ]
        if kind == KIND.LOT:
            columns += [("Hold", False), ("Protect", False)]
        columns.append(("Decide", False))
        note = ""
        if kind == KIND.CERTIFICATE:
            note = (
                "A certificate is withdrawn, with a signature and the evidence that its "
                "recipients were notified, on its own page."
            )
        elif kind == KIND.LOT:
            note = (
                "A hold placed here is the lot's quality hold, referenced to this assessment: it "
                "blocks the lot's disposition or its certificates until a quality person who did "
                "not place it releases it with a signature."
            )
        sections.append(section(title, columns, rows, f"No {title.lower()}.", note=note))
    return sections


def _notice(assessment, undecided, found):
    if assessment.state == STATE.CONCLUDED:
        evidence = assessment.evidence
        return {
            "tone": "success",
            "label": "Concluded",
            "text": f"{evidence.get('affected', 0)} record(s) affected and "
            f"{evidence.get('not_affected', 0)} not affected, as signed. "
            f"{assessment.decision_reason}",
        }
    if assessment.state == STATE.WITHDRAWN:
        return {
            "tone": "info",
            "label": "Withdrawn",
            "text": f"This assessment was withdrawn and is kept as recorded. Reason: "
            f"{assessment.decision_reason}",
        }
    if found:
        return {
            "tone": "warning",
            "label": "New records found",
            "text": f"The cause now finds {len(found)} record(s) that are not in the assessment. "
            "Find affected records again to add them before it is concluded.",
        }
    if undecided:
        return {
            "tone": "info",
            "label": "Decisions needed",
            "text": f"{len(undecided)} record(s) have no decision yet.",
        }
    return None


@login_required
def assessment_detail(request, pk):
    access(request.user)
    assessment = _assessment(pk)
    roles = _roles(request.user)
    items, undecided, found, _ = services.review(assessment)
    is_open = assessment.state == STATE.OPEN
    can_act = services.QUALITY in roles
    actions = []
    if is_open and can_act:
        if found:
            actions.append(
                action("Find affected records", reverse("impact:find", args=[assessment.pk]))
            )
        actions.append(action("Add record", reverse("impact:add", args=[assessment.pk])))
        if request.user.pk in services.author_ids(assessment, items):
            actions.append(
                refused(
                    "You took part in this assessment or in the work it assesses: another "
                    "quality person concludes it."
                )
            )
        elif not undecided and not found:
            actions.append(
                action("Conclude", reverse("impact:conclude", args=[assessment.pk]), True)
            )
        if not services.withdrawal_refusal(assessment):
            actions.append(
                action(
                    "Withdraw",
                    reverse("impact:withdraw", args=[assessment.pk]),
                    danger=True,
                    more=True,
                )
            )
    return record_page(
        request,
        identifier=assessment.label,
        title=f"{assessment.label} · {assessment.title}",
        crumbs=_crumbs((assessment.label, None)),
        state=status(*services.status_of(assessment)),
        facts=[
            ("Cause", _cause_text(assessment)),
            ("What happened", cell(assessment.description, wrap=True)),
            ("Date found", day(assessment.found_on)),
            (
                "Period of concern",
                f"{day(assessment.period_from)} to {day(assessment.period_until)}",
            ),
            ("Quality-system reference", assessment.quality_reference or "None"),
            ("Records", f"{len(items)} · {len(undecided)} without a decision"),
            ("Started by", person(assessment.started_by)),
            ("Started", stamp(assessment.started_at)),
            ("Decided", stamp(assessment.decided_at)),
            ("Reason for the decision", assessment.decision_reason),
        ],
        actions=actions,
        sections=_sections(assessment, items, can_act)
        or [
            section(
                "Records",
                [("Record", False)],
                [],
                "No record is in the assessment. Add the records it may have affected.",
            )
        ],
        related=[assessment, *items],
        notice=_notice(assessment, undecided, found),
        meta=[("Revision", assessment.revision)],
    )


def _open_or_back(request, assessment):
    """None while the assessment is open; else a redirect to it with the reason."""
    if assessment.state == STATE.OPEN:
        return None
    messages.warning(request, services.NOT_OPEN)
    return redirect(detail_url(assessment))


@login_required
@require_http_methods(["GET", "POST"])
def assessment_find(request, pk):
    """Add the records the cause finds now that are not in the assessment yet."""
    require_role(request.user, services.QUALITY)
    assessment = _assessment(pk)
    if back := _open_or_back(request, assessment):
        return back
    form = FindForm(request.POST or None, initial={"expected_revision": assessment.revision})
    if request.method == "POST" and form.is_valid():
        created = run(
            form,
            lambda: services.find_records(
                actor=request.user,
                assessment=assessment,
                expected_revision=form.cleaned_data["expected_revision"],
            ),
        )
        if created:
            messages.success(request, f"{len(created)} record(s) added to {assessment.label}.")
            return redirect(detail_url(assessment))
        if created is not None:
            messages.info(request, "The cause finds no record that is not in the assessment.")
            return redirect(detail_url(assessment))
    found = scope.missing(assessment)
    facts = [("Assessment", f"{assessment.label} · {assessment.title}")]
    facts += [
        (dict(Item.Kind.choices)[candidate.kind], candidate.basis) for candidate in found[:50]
    ]
    if len(found) > 50:
        facts.append(("More", f"{len(found) - 50} more"))
    title = "Find affected records"
    return action_page(
        request,
        form,
        title=title,
        crumbs=_crumbs((assessment.label, detail_url(assessment)), (title, None)),
        cancel_url=detail_url(assessment),
        submit=f"Add {len(found)} record(s)" if found else "Find again",
        intro="The cause finds these records now that are not in the assessment yet, for "
        "example a test recorded since it was started, or a certificate of a lot added to it. "
        "They are added without a decision.",
        facts=facts,
    )


@login_required
@require_http_methods(["GET", "POST"])
def record_add(request, pk):
    require_role(request.user, services.QUALITY)
    assessment = _assessment(pk)
    if back := _open_or_back(request, assessment):
        return back
    form = AddRecordForm(request.POST or None, initial={"expected_revision": assessment.revision})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        item = run(
            form,
            lambda: services.add_record(
                actor=request.user,
                assessment=assessment,
                expected_revision=data["expected_revision"],
                kind=data["kind"],
                identifier=data["identifier"],
                reason=data["reason"],
            ),
        )
        if item:
            messages.success(request, f"{services.record_label(item)} added to {assessment.label}.")
            return redirect(detail_url(assessment))
    title = "Add record"
    return action_page(
        request,
        form,
        title=title,
        crumbs=_crumbs((assessment.label, detail_url(assessment)), (title, None)),
        cancel_url=detail_url(assessment),
        submit=title,
        intro="Add a test, lot, stability study or issued certificate that the problem may have "
        "affected and the cause does not find by itself. The certificates of a lot you add are "
        "then found from it.",
        facts=[("Assessment", f"{assessment.label} · {assessment.title}")],
    )


def _item(pk):
    return get_object_or_404(
        Item.objects.select_related(
            "assessment",
            "test__lot",
            "test__pull__study__lot",
            "test__reassessment__lot",
            "lot",
            "study__lot",
            "report__lot",
            "hold",
        ),
        pk=pk,
    )


def _item_facts(item):
    label, _ = services.record_status(item)
    return [
        ("Assessment", f"{item.assessment.label} · {item.assessment.title}"),
        (item.get_kind_display(), services.record_label(item)),
        ("Now", label),
        ("Why it is in the assessment", item.basis),
    ]


@login_required
@require_http_methods(["GET", "POST"])
def record_decide(request, pk):
    require_role(request.user, services.QUALITY)
    item = _item(pk)
    assessment = item.assessment
    if back := _open_or_back(request, assessment):
        return back
    form = DecisionForm(
        request.POST or None,
        initial={
            "expected_revision": item.revision,
            "decision": item.decision,
            "rationale": item.rationale,
            "follow_up": item.follow_up,
            "follow_up_reference": item.follow_up_reference,
        },
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        decided = run(form, lambda: services.decide(actor=request.user, item=item, **data))
        if decided:
            messages.success(request, f"Decision recorded for {services.record_label(decided)}.")
            return redirect(detail_url(assessment))
    title = "Change decision" if item.decision else "Record decision"
    return action_page(
        request,
        form,
        title=title,
        crumbs=_crumbs((assessment.label, detail_url(assessment)), (title, None)),
        cancel_url=detail_url(assessment),
        submit=title,
        intro="Affected: the record may not be relied on as it stands; say what is done about "
        "it. Not affected: say why. A decision can be changed until the assessment is concluded; "
        "the audit trail keeps every earlier one.",
        facts=_item_facts(item),
    )


@login_required
@require_http_methods(["GET", "POST"])
def record_hold(request, pk):
    require_role(request.user, services.QUALITY)
    item = _item(pk)
    assessment = item.assessment
    if back := _open_or_back(request, assessment):
        return back
    if refusal := services.hold_refusal(item):
        messages.warning(request, refusal)
        return redirect(detail_url(assessment))
    form = HoldForm(request.POST or None, initial={"expected_revision": item.revision})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        hold = run(form, lambda: services.place_hold(actor=request.user, item=item, **data))
        if hold:
            messages.success(request, f"{hold.identifier} placed on lot {item.lot.number}.")
            return redirect(detail_url(assessment))
    title = "Place hold"
    return action_page(
        request,
        form,
        title=title,
        crumbs=_crumbs((assessment.label, detail_url(assessment)), (title, None)),
        cancel_url=detail_url(assessment),
        submit=title,
        intro="A quality hold on the lot, referenced to this assessment. While it is active the "
        "lot's QC disposition cannot be signed and no certificate is issued or amended for it. "
        "A quality person who did not place it releases it with a signature on the hold's page.",
        facts=_item_facts(item),
        tone="danger",
    )


# Signing ---------------------------------------------------------------------------------------


def _summary(assessment, items):
    facts = [
        ("Assessment", f"{assessment.label} · {assessment.title}"),
        ("Cause", _cause_text(assessment)),
        ("Period of concern", f"{day(assessment.period_from)} to {day(assessment.period_until)}"),
    ]
    affected = [i for i in items if i.decision == DECISION.AFFECTED]
    clear = [i for i in items if i.decision == DECISION.NOT_AFFECTED]
    facts.append(("Records", f"{len(affected)} affected · {len(clear)} not affected"))
    for item in affected[:30]:
        facts.append((f"Affected {item.get_kind_display().lower()}", services.record_label(item)))
    if len(affected) > 30:
        facts.append(("More affected", f"{len(affected) - 30} more, listed on the record"))
    return facts


@login_required
@require_http_methods(["GET", "POST"])
def assessment_conclude(request, pk):
    require_role(request.user, services.QUALITY)
    assessment = _assessment(pk)
    found = services.review(assessment)
    denial = services.conclusion_refusal(assessment, request.user, found)
    form = AssessmentSigningForm(
        request.POST or None, initial={"expected_revision": assessment.revision}
    )
    return sign_page(
        request,
        form,
        title=f"Conclude {assessment.label}",
        identifier=assessment.label,
        meaning="impact_assessed",
        meaning_text=(
            "You conclude the impact assessment on the records and decisions shown. They are "
            "frozen with your signature. Holds placed through it stay until released on their "
            "own pages; withdrawing or amending a certificate, retesting and the manufacturer's "
            "decisions on released material are separate."
        ),
        button="Sign and conclude",
        facts=_summary(assessment, found[0]),
        revision=assessment.revision,
        cancel_url=detail_url(assessment),
        run=lambda d: services.conclude(
            actor=request.user,
            pin=d["pin"],
            assessment=assessment,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"{assessment.label} concluded.",
        success_url=detail_url(assessment),
        denial=denial,
        crumbs=_crumbs((assessment.label, detail_url(assessment)), ("Conclude", None)),
    )


@login_required
@require_http_methods(["GET", "POST"])
def assessment_withdraw(request, pk):
    require_role(request.user, services.QUALITY)
    assessment = _assessment(pk)
    items = services.review(assessment)[0]
    form = AssessmentSigningForm(
        request.POST or None, initial={"expected_revision": assessment.revision}
    )
    return sign_page(
        request,
        form,
        title=f"Withdraw {assessment.label}",
        identifier=assessment.label,
        meaning="withdrawn",
        meaning_text=(
            "You withdraw an impact assessment started in error. It and its records are kept as "
            "recorded and take no more decisions."
        ),
        button="Sign and withdraw",
        facts=_summary(assessment, items),
        revision=assessment.revision,
        cancel_url=detail_url(assessment),
        run=lambda d: services.withdraw(
            actor=request.user,
            pin=d["pin"],
            assessment=assessment,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"{assessment.label} withdrawn; the record is kept.",
        success_url=detail_url(assessment),
        denial=services.withdrawal_refusal(assessment),
        crumbs=_crumbs((assessment.label, detail_url(assessment)), ("Withdraw", None)),
    )
