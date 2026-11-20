"""Pages of shelf-life evaluations (HTTP only; the rules are in ``stability.services``, the reading
of results and the figures in ``stability.shelf_life`` and ``stability.regression``)."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from catalog.units import plain
from core.services import require_role
from laboratory.ui import (
    access,
    action,
    cell,
    form_page,
    list_page,
    make_filter,
    paginate,
    person,
    record_page,
    refused,
    roles_of,
    run_form,
    section,
    sign_page,
    status,
    when,
)

from . import plot, regression, services, shelf_life
from .forms import (
    ShelfLifeChangeForm,
    ShelfLifeConcludeForm,
    ShelfLifeForm,
    ShelfLifeStudyForm,
    ShelfLifeWithdrawForm,
    evaluable_studies,
)
from .models import ShelfLifeEvaluation

HOME = "Stability and retention"
LIST = "Shelf-life evaluations"
QUALITY = "quality"
STATE = ShelfLifeEvaluation.State
DIRECTION = ShelfLifeEvaluation.Direction
STATUS_FILTER = [
    ("draft", "Draft"),
    ("concluded", "Concluded"),
    ("withdrawn", "Withdrawn"),
]
MODEL_TEXT = {
    regression.Model.POOLED: "Pooled: one line for all studies",
    regression.Model.COMMON_SLOPE: "A common slope, each study's own intercept",
    regression.Model.SEPARATE: "Each study's own slope and intercept",
    regression.Model.SINGLE: "One study",
}
WHAT_IT_IS = (
    "A shelf-life evaluation fits the results of one test at one storage condition, from the "
    "studies of one protocol and container closure, against months on stability, and finds "
    "where the 95 % confidence limit of the mean meets the acceptance criterion (ICH Q1E)."
)


def _crumbs(*trail):
    return [
        (HOME, reverse("stability:overview")),
        (LIST, reverse("stability:shelf_life_list")),
        *trail,
    ]


def detail_url(evaluation):
    return reverse("stability:shelf_life_detail", args=[evaluation.pk])


def _quality(user):
    return QUALITY in roles_of(user)


def state_cell(evaluation):
    if evaluation.state == STATE.DRAFT:
        return status("Draft", "progress")
    if evaluation.state == STATE.WITHDRAWN:
        return status("Withdrawn", "neutral")
    if evaluation.outcome == ShelfLifeEvaluation.Outcome.SUPPORTED:
        return status(f"Concluded · {evaluation.shelf_life_months} months", "success")
    return status("Concluded · none supported", "warning")


def criterion_text(evaluation):
    lower, upper, unit = evaluation.lower_limit, evaluation.upper_limit, evaluation.unit
    if lower is not None and upper is not None:
        return f"{plain(lower)} to {plain(upper)} {unit}"
    if lower is not None:
        return f"Not less than {plain(lower)} {unit}"
    return f"Not more than {plain(upper)} {unit}"


def months_text(value):
    return "" if value is None else f"{plain(value)} months"


def _evaluation(pk):
    return get_object_or_404(
        ShelfLifeEvaluation.objects.select_related("specification", "drafted_by"), pk=pk
    )


def result_for(evaluation):
    """What the page shows: a concluded evaluation from its frozen content, any other from the
    record as it stands."""
    if evaluation.state == STATE.CONCLUDED:
        return shelf_life.replay(evaluation.content)
    return shelf_life.of(evaluation)


# List ---------------------------------------------------------------------------------------


@login_required
def shelf_life_list(request):
    access(request.user)
    form, data = make_filter(request, STATUS_FILTER)
    queryset = ShelfLifeEvaluation.objects.annotate(studies=Count("study_links"))
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(protocol_code__icontains=q)
            | Q(product__icontains=q)
            | Q(test_code__icontains=q)
            | Q(name__icontains=q)
            | Q(condition__icontains=q)
        )
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {"drafted": ["drafted_at"], "protocol": ["protocol_code", "condition", "test_code"]},
        "-drafted",
    )
    rows = [
        [
            cell(evaluation.identifier, detail_url(evaluation), sub=evaluation.name),
            cell(evaluation.protocol_code, code=True, sub=evaluation.product),
            evaluation.condition,
            cell(str(evaluation.studies), numeric=True),
            state_cell(evaluation),
            when(evaluation.drafted_at),
        ]
        for evaluation in page
    ]
    return list_page(
        request,
        title=LIST,
        intro=WHAT_IT_IS,
        noun="evaluations",
        columns=[
            ("Evaluation", None, False),
            ("Protocol", "protocol", False),
            ("Storage condition", None, False),
            ("Studies", None, True, "low"),
            ("State", None, False),
            ("Drafted", "drafted", False, "low"),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "evaluation", "href": reverse("stability:shelf_life_new")}
        if _quality(request.user)
        else None,
        empty_body="Quality drafts an evaluation from a study whose pulls are tested in the "
        "system.",
    )


# New ----------------------------------------------------------------------------------------


def _study_from_query(request):
    value = request.GET.get("study", "")
    if not value.isascii() or not value.isdigit() or len(value) > 19:
        return None
    return evaluable_studies().filter(pk=value).first()


@login_required
@require_http_methods(["GET", "POST"])
def shelf_life_new(request):
    require_role(request.user, QUALITY)
    study = _study_from_query(request)
    back = (
        reverse("stability:study_detail", args=[study.pk])
        if study
        else reverse("stability:shelf_life_list")
    )
    crumbs = _crumbs(("New evaluation", None))
    if study is None:
        form = ShelfLifeStudyForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            chosen = form.cleaned_data["study"]
            return redirect(f"{reverse('stability:shelf_life_new')}?study={chosen.pk}")
        return form_page(
            request,
            form,
            title="New evaluation",
            crumbs=crumbs,
            submit="Continue",
            cancel_url=back,
            intro=WHAT_IT_IS + " Choose a study first: its protocol names the conditions and "
            "tests.",
        )
    protocol = study.protocol
    _, lines = services.shelf_life_lines(protocol)
    conditions = list(protocol.conditions.order_by("pk").values_list("label", flat=True))
    form = ShelfLifeForm(request.POST or None, conditions=conditions, lines=lines)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        evaluation, _ = run_form(
            request,
            form,
            lambda: services.draft_shelf_life(
                actor=request.user,
                study=study,
                condition=values["condition"],
                test_code=values["test_code"],
                direction=values["direction"],
                purpose=values["purpose"],
                reason=values["reason"],
            ),
        )
        if evaluation:
            messages.success(
                request,
                f"{evaluation.identifier} drafted with every study of {protocol.code} in this "
                "container closure.",
            )
            return redirect(detail_url(evaluation))
    intro = (
        f"For the studies of {protocol.code} ({protocol.product}) in "
        f"{study.container_closure}, all of them to begin with. "
    )
    if not lines:
        intro += (
            "The protocol's specification in force states no numeric or count test with a "
            "limit for the tests it names, so nothing can be evaluated."
        )
    else:
        intro += "The acceptance criterion is the one the specification in force states now."
    return form_page(
        request,
        form,
        title="New evaluation",
        crumbs=crumbs,
        submit="Draft evaluation",
        cancel_url=back,
        intro=intro,
    )


# Detail -------------------------------------------------------------------------------------


def _test_cell(point):
    test = point.test
    if isinstance(test, shelf_life.FrozenTest):
        return cell(f"T-{test.pk}", reverse("analytical:test_detail", args=[test.pk]))
    return cell(test.label, reverse("analytical:test_detail", args=[test.pk]))


def _result_cell(point, unit):
    text = f"{point.text} {unit}"
    if point.conforms:
        return cell(text, numeric=True)
    return cell(text, numeric=True, tone="danger", sub="Outside the acceptance criterion")


def _study_cell(study):
    if isinstance(study, shelf_life.FrozenStudy):
        return cell(study.identifier, sub=f"Lot {study.lot.number}")
    return cell(
        study.identifier,
        reverse("stability:study_detail", args=[study.pk]),
        sub=f"Lot {study.lot.number}",
    )


def _f_test_row(label, test):
    """A poolability test as the figures hold it (strings), or None when it was not made."""
    if test is None:
        return [label, "", "", "", "Not tested: the slopes differ"]
    verdict = "Rejected: they differ" if test["rejected"] else "Not rejected"
    return [
        label,
        cell(test["f"] or "", numeric=True),
        cell(f"{test['df1']}, {test['df2']}", numeric=True),
        cell(test["p"], numeric=True),
        verdict,
    ]


def _earliest(crossings):
    found = [Decimal(months) for months in crossings.values() if months is not None]
    return min(found) if found else None


def _figures_sections(evaluation, result, figures):
    """The tables of the page. ``figures`` are the rounded figures: those the conclusion froze
    for a concluded evaluation, those of the record now for a draft (None when nothing was
    fitted)."""
    unit = evaluation.unit
    sections = []
    if figures and figures["slopes"] is not None:
        sections.append(
            section(
                "Poolability of the studies",
                [
                    ("Hypothesis", False),
                    ("F", True),
                    ("Degrees of freedom", True, "low"),
                    ("p", True),
                    (f"At {figures['significance']}", False),
                ],
                [
                    _f_test_row("Equal slopes", figures["slopes"]),
                    _f_test_row("Equal intercepts, given equal slopes", figures["intercepts"]),
                ],
                "",
                note="Analysis of covariance with time as the covariate, each test at the 0.25 "
                "significance level (ICH Q1E). The intercepts are tested under the common-slope "
                "model, with its mean square error.",
            )
        )
    rows = []
    shown = {item["study"]: item for item in (figures["batches"] if figures else [])}
    for batch in result.batches:
        item = shown.get(batch.study.identifier) if batch.fitted else None
        if item is None:
            rows.append(
                [
                    _study_cell(batch.study),
                    cell(str(len(batch.points)), numeric=True),
                    "",
                    "",
                    "",
                    cell(batch.reason, muted=True, wrap=True),
                ]
            )
            continue
        earliest = _earliest(item["crossings"])
        rows.append(
            [
                _study_cell(batch.study),
                cell(str(item["results"]), numeric=True),
                cell(item["own_slope"], numeric=True),
                cell(item["slope"], numeric=True),
                cell(item["intercept"], numeric=True),
                months_text(plain(earliest))
                if earliest is not None
                else f"Not reached within {figures['horizon']} months",
            ]
        )
    sections.append(
        section(
            "Studies",
            [
                ("Study", False),
                ("Results", True),
                (f"Own slope ({unit} per month)", True, "low"),
                ("Slope used", True),
                (f"Intercept used ({unit})", True, "medium"),
                ("Limit meets the criterion", False),
            ],
            rows,
            "No study.",
            note="The slope and intercept each study's mean line has under the model chosen; "
            "its own slope is that of its results alone. When the studies are not pooled the "
            "shortest time applies to all.",
        )
    )
    points = sorted(result.points, key=lambda p: (str(p.study.identifier), p.days, p.test.pk))
    sections.append(
        section(
            "Results",
            [
                ("Study", False),
                ("Time point", False),
                ("Months", True),
                ("Condition", False, "low"),
                ("Result", True),
                ("Test", False, "medium"),
            ],
            [
                [
                    _study_cell(point.study),
                    point.pull.timepoint.label,
                    cell(f"{regression.round_half_up(point.months, 2):f}", numeric=True),
                    point.condition,
                    _result_cell(point, unit),
                    _test_cell(point),
                ]
                for point in points
            ],
            "No result of this test at this condition yet.",
            note="The results reported on accepted pulls tested in the system. Months on "
            "stability are the time point's interval in days divided by 365.25 / 12.",
        )
    )
    if result.unused:
        sections.append(
            section(
                "Not used",
                [("Study", False), ("Pull", False), ("Why", False)],
                [
                    [
                        _study_cell(item.study),
                        cell(
                            item.pull.timepoint.label
                            if item.pull.timepoint
                            else f"Pull {item.pull.pk}",
                            reverse("stability:pull_detail", args=[item.pull.pk]),
                        ),
                        item.reason,
                    ]
                    for item in result.unused
                ],
                "",
            )
        )
    return sections


def _estimate_fact(result, figures):
    if figures is None:
        return cell("Not worked out", muted=True, sub=result.problem)
    if figures["estimate_months"] is None:
        return f"Not reached within {figures['horizon']} months"
    return cell(
        months_text(figures["estimate_months"]),
        sub=f"{MODEL_TEXT[figures['model']]}; t = {figures['t']} on {figures['df']} degrees "
        "of freedom",
    )


def shown_figures(evaluation, result):
    """The figures a page shows: those the conclusion froze, or those of the record now."""
    if evaluation.state == STATE.CONCLUDED:
        return evaluation.content["figures"]
    return shelf_life.figures(result)


def _notices(evaluation, result):
    texts = []
    tone = "info"
    if evaluation.state == STATE.WITHDRAWN:
        return {
            "tone": "neutral",
            "label": "Withdrawn",
            "text": "This draft was withdrawn and will not be concluded. Its results are shown "
            "as the record stands now.",
        }
    if evaluation.state == STATE.CONCLUDED:
        if shelf_life.figures(result) != evaluation.content["figures"]:
            return {
                "tone": "info",
                "label": "As signed",
                "text": "The details and tables show the figures the conclusion froze. The "
                "drawing is worked out again from the frozen results by this release's "
                "statistics, which now give other figures.",
            }
        return None
    if result.analysis is not None:
        if len(result.fitted) < shelf_life.ADVISED_BATCHES:
            texts.append(
                f"{len(result.fitted)} stud{'y is' if len(result.fitted) == 1 else 'ies are'} "
                "fitted; ICH Q1E evaluates the data of at least three batches."
            )
            tone = "warning"
        estimate = result.estimate.months
        covered = result.covered_months
        if estimate is None or estimate > covered:
            texts.append(
                f"The estimate lies beyond the {plain(regression.round_half_up(covered, 1))} "
                "months the data cover. ICH Q1E limits how far a shelf life may be extrapolated "
                "beyond them, and an extrapolated shelf life needs supporting data."
            )
            tone = "warning"
    if not texts:
        return None
    return {"tone": tone, "label": "Before concluding", "text": " ".join(texts)}


def _actions(user, evaluation, result):
    if evaluation.state != STATE.DRAFT or not _quality(user):
        return []
    base = [evaluation.pk]
    denial = services.shelf_life_denial(user, evaluation, result)
    return [
        action("Change", reverse("stability:shelf_life_change", args=base)),
        action("Withdraw", reverse("stability:shelf_life_withdraw", args=base), more=True),
        refused(denial)
        if denial
        else action("Conclude", reverse("stability:shelf_life_conclude", args=base), True),
    ]


@login_required
def shelf_life_detail(request, pk):
    access(request.user)
    evaluation = _evaluation(pk)
    result = result_for(evaluation)
    concluded = evaluation.state == STATE.CONCLUDED
    caption = (
        "As concluded: the results and figures the signature froze."
        if concluded
        else "As the record stands now."
    )
    drawing = plot.geometry(evaluation, result, caption=caption)
    figures = shown_figures(evaluation, result)
    facts = [
        ("Protocol", cell(evaluation.protocol_code, code=True, sub=evaluation.product)),
        ("Container closure", evaluation.container_closure),
        ("Storage condition", evaluation.condition),
        ("Test", cell(evaluation.name, sub=evaluation.test_code)),
        (
            "Acceptance criterion",
            cell(
                criterion_text(evaluation),
                sub=f"{evaluation.specification.code} v{evaluation.specification_version}",
            ),
        ),
        ("Expected change", evaluation.get_direction_display()),
        ("Estimated shelf life", _estimate_fact(result, figures)),
        (
            "Data cover",
            months_text(figures["covered_months"]) if figures else "No result fitted yet",
        ),
    ]
    if concluded:
        facts += [
            (
                "Outcome",
                cell(
                    evaluation.get_outcome_display(),
                    sub=months_text(evaluation.shelf_life_months),
                ),
            ),
            ("Conclusion", cell(evaluation.conclusion, wrap=True)),
            ("Concluded", when(evaluation.concluded_at)),
        ]
    facts += [
        ("Purpose", cell(evaluation.purpose, wrap=True)),
        ("Drafted by", person(evaluation.drafted_by)),
    ]
    return record_page(
        request,
        identifier=evaluation.identifier,
        title=evaluation.title,
        crumbs=_crumbs((evaluation.identifier, None)),
        state=state_cell(evaluation),
        facts=facts,
        meta=[("Record revision", evaluation.revision)],
        actions=_actions(request.user, evaluation, result),
        notice=_notices(evaluation, result),
        sections=_figures_sections(evaluation, result, figures),
        related=[evaluation],
        template="stability/shelf_life_detail.html",
        extra={
            "drawing": drawing,
            "drawing_note": "Results appear here once pulls of these studies with this test are "
            "tested in the system and accepted.",
        },
    )


# Change, withdraw, conclude -----------------------------------------------------------------


def _draft_or_back(request, evaluation):
    if evaluation.state != STATE.DRAFT:
        messages.warning(
            request,
            f"{evaluation.identifier} is {evaluation.get_state_display().lower()}: it no longer "
            "changes.",
        )
        return redirect(detail_url(evaluation))
    return None


@login_required
@require_http_methods(["GET", "POST"])
def shelf_life_change(request, pk):
    require_role(request.user, QUALITY)
    evaluation = _evaluation(pk)
    if back := _draft_or_back(request, evaluation):
        return back
    detail = detail_url(evaluation)
    studies = list(shelf_life.studies_of(evaluation.protocol_code, evaluation.container_closure))
    linked = list(evaluation.study_links.values_list("study_id", flat=True))
    form = ShelfLifeChangeForm(
        request.POST or None,
        studies=studies,
        initial={
            "expected_revision": evaluation.revision,
            "studies": linked,
            "direction": evaluation.direction,
            "purpose": evaluation.purpose,
        },
    )
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        done, _ = run_form(
            request,
            form,
            lambda: services.change_shelf_life(
                actor=request.user,
                evaluation=evaluation,
                expected_revision=values["expected_revision"],
                reason=values["reason"],
                studies=values["studies"],
                direction=values["direction"],
                purpose=values["purpose"],
            ),
        )
        if done:
            messages.success(request, f"{evaluation.identifier} changed.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Change {evaluation.identifier}",
        crumbs=_crumbs((evaluation.identifier, detail), ("Change", None)),
        submit="Save changes",
        cancel_url=detail,
        intro="The studies of the protocol in this container closure. The test, condition and "
        "acceptance criterion are fixed; a draft of another needs a new evaluation. Whoever "
        "changes a draft cannot conclude it.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def shelf_life_withdraw(request, pk):
    require_role(request.user, QUALITY)
    evaluation = _evaluation(pk)
    if back := _draft_or_back(request, evaluation):
        return back
    detail = detail_url(evaluation)
    form = ShelfLifeWithdrawForm(
        request.POST or None, initial={"expected_revision": evaluation.revision}
    )
    if request.method == "POST" and form.is_valid():
        done, _ = run_form(
            request,
            form,
            lambda: services.withdraw_shelf_life(
                actor=request.user,
                evaluation=evaluation,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
            ),
        )
        if done:
            messages.success(request, f"{evaluation.identifier} withdrawn.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Withdraw {evaluation.identifier}",
        crumbs=_crumbs((evaluation.identifier, detail), ("Withdraw", None)),
        submit="Withdraw draft",
        cancel_url=detail,
        intro="A withdrawn draft is never concluded and stays in the record. A new evaluation "
        "of the same test and condition can then be drafted.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def shelf_life_conclude(request, pk):
    require_role(request.user, QUALITY)
    evaluation = _evaluation(pk)
    detail = detail_url(evaluation)
    result = shelf_life.of(evaluation)
    form = ShelfLifeConcludeForm(
        request.POST or None,
        initial={
            "expected_revision": evaluation.revision,
            "data_hash": shelf_life.data_digest(evaluation, result),
        },
    )
    figures = shelf_life.figures(result)
    longest = result.longest_supported
    if not longest:
        most = "None: no shelf life is supported"
    elif result.estimate.months is None:
        most = cell(
            months_text(longest),
            sub="The search horizon: the confidence limit does not meet the criterion within "
            "it. Any shelf life beyond the data is an extrapolation.",
        )
    else:
        most = cell(months_text(longest), sub="The estimate rounded down to whole months.")
    facts = [
        ("Test", f"{evaluation.name} · {evaluation.condition}"),
        ("Acceptance criterion", criterion_text(evaluation)),
        ("Studies fitted", str(len(result.fitted))),
        ("Estimated shelf life", _estimate_fact(result, figures)),
        ("Longest you can record", most),
        ("Data cover", months_text(figures["covered_months"]) if figures else ""),
    ]
    if notice := _notices(evaluation, result):
        facts.append((notice["label"], cell(notice["text"], wrap=True)))
    return sign_page(
        request,
        form,
        title=f"Conclude evaluation · {evaluation.identifier}",
        identifier=evaluation.identifier,
        meaning="concluded",
        meaning_text="You conclude what shelf life these data support. Your signature freezes "
        "the results, the figures worked out from them and the shelf life you record.",
        button="Sign and conclude",
        facts=facts,
        revision=evaluation.revision,
        cancel_url=detail,
        run=lambda d: services.conclude_shelf_life(
            actor=request.user,
            pin=d["pin"],
            evaluation=evaluation,
            expected_revision=d["expected_revision"],
            data_hash=d["data_hash"],
            reason=d["reason"],
            outcome=d["outcome"],
            shelf_life_months=d["shelf_life_months"],
            conclusion=d["conclusion"],
        ),
        success=f"{evaluation.identifier} concluded.",
        success_url=detail,
        denial=services.shelf_life_denial(request.user, evaluation, result),
        crumbs=_crumbs((evaluation.identifier, detail), ("Conclude evaluation", None)),
    )


# The studies' side ----------------------------------------------------------------------------


def study_section(study):
    """The evaluations that use ``study``, for its page."""
    evaluations = ShelfLifeEvaluation.objects.filter(study_links__study=study).order_by(
        "-drafted_at", "-pk"
    )
    return section(
        "Shelf-life evaluations",
        [("Evaluation", False), ("Storage condition", False), ("State", False)],
        [
            [
                cell(evaluation.identifier, detail_url(evaluation), sub=evaluation.name),
                evaluation.condition,
                state_cell(evaluation),
            ]
            for evaluation in evaluations
        ],
        "No evaluation uses this study yet.",
    )


def study_action(user, study):
    """The study page's action to evaluate the shelf life, for quality, or None."""
    if not _quality(user) or study.protocol.specification_id is None:
        return None
    return action(
        "Evaluate shelf life",
        f"{reverse('stability:shelf_life_new')}?study={study.pk}",
        more=True,
    )


def drafts_count():
    return ShelfLifeEvaluation.objects.filter(state=STATE.DRAFT).count()
