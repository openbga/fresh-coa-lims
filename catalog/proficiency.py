"""Participation in proficiency testing schemes and other interlaboratory comparisons.

Quality plans a participation for a method with the day its results are due. An analyst, a
reviewer or a quality person records the laboratory's report (the method version used, the day
the item arrived and the day results were sent, where the original records are kept, the
provider's report) and each result with the score the provider gave it. The outcome of each
result follows from its score (``outcome_of``); the participation's outcome is the worst of
them. A quality person who recorded none of the report or results and performed none of them
reviews the outcome with a signature that freezes it: the participation is closed, or stays
open for corrective follow-up, which is required when a result is unsatisfactory. Quality
records the follow-up, and a quality person who did not record it, nor the report or results,
closes it with a signature. A participation that does not take place is cancelled while it holds
no result. The database refuses any other change (migration 0011).

What a laboratory must take part in, how often, which scores and criteria it relies on, and
what follows an outcome are its own decisions; the score criteria are the conventional ones of
ISO 13528, and a provider that evaluates otherwise is recorded by its own evaluation.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from core.audit import record_event, snapshot
from core.models import AuditEvent
from core.services import require_role, sign_transition
from laboratory.services import lock_account

from .models import (
    Z_LIKE_SCORES,
    MethodRevision,
    ProficiencyOutcome,
    ProficiencyParticipation,
    ProficiencyResult,
    RevisionStatus,
)

PLANNER = "quality"
RECORDERS = ("analyst", "reviewer", "quality")
REVIEWER = "quality"
MAX_RESULTS = 30
STATE = ProficiencyParticipation.State
OUTCOME = ProficiencyOutcome
SCORE = ProficiencyResult.ScoreKind

PLAN_FIELDS = (
    "kind",
    "provider",
    "provider_accreditation",
    "scheme",
    "round_ref",
    "test_item",
    "results_due",
)
REPORT_FIELDS = (
    "method_version",
    "received_on",
    "reported_on",
    "data_ref",
    "report_ref",
    "report_on",
    "report_url",
)
FOLLOW_UP_FIELDS = (
    "cause",
    "actions",
    "reported_results",
    "impact_assessment",
    "quality_reference",
    "effectiveness",
)
# Audit actions that make their actor an author of the participation's data: whoever recorded
# the report, added or removed a result, or changed the plan once a result or the report was
# recorded (the review freezes the plan with them) cannot review the outcome or close its
# follow-up.
DATA_ACTIONS = (
    "participation.plan_corrected",
    "participation.report_recorded",
    "participation.result_added",
    "participation.result_removed",
)
FOLLOW_UP_ACTION = "participation.follow_up_recorded"

INDEPENDENT = (
    "You recorded or performed results or the report of this participation; another quality "
    "person reviews it."
)
INDEPENDENT_CLOSE = (
    "You recorded its follow-up, or results or the report of this participation; another "
    "quality person closes it."
)
UNSATISFACTORY_NEEDS_FOLLOW_UP = "An unsatisfactory result needs corrective follow-up."
ORDER = (OUTCOME.UNSATISFACTORY, OUTCOME.QUESTIONABLE, OUTCOME.SATISFACTORY)


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _locked(participation, expected_revision, *states):
    """The participation under lock. Callers lock the actor's account first."""
    locked = ProficiencyParticipation.objects.select_for_update().get(pk=participation.pk)
    if locked.state not in states:
        raise ValidationError(_state_refusal(locked, states))
    if expected_revision is not None and locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before saving.")
    return locked


def _state_refusal(item, states):
    if states == (STATE.OPEN,) and item.state == STATE.FOLLOW_UP:
        return (
            f"{item.identifier} is reviewed: its plan, report and results no longer change; its "
            "corrective follow-up is open."
        )
    if states == (STATE.OPEN,):
        return f"{item.identifier} is {item.get_state_display().lower()}: it no longer changes."
    if states == (STATE.FOLLOW_UP,):
        return f"{item.identifier} has no corrective follow-up open."
    return f"{item.identifier} is {item.get_state_display().lower()}."


def _bump(locked):
    locked.revision += 1
    locked.save(update_fields=["revision"])


def _past(errors, name, value, label):
    if value and value > timezone.localdate():
        errors[name] = f"{label} cannot be in the future."


# Outcomes -----------------------------------------------------------------------------------


def outcome_of(score_kind, score):
    """The outcome of a score by the conventional criteria of ISO 13528: a z, z′ or ζ score
    is satisfactory up to 2 in absolute value, questionable above 2 and below 3, unsatisfactory
    from 3; an En number is satisfactory up to 1 and unsatisfactory above it. None for a result
    without a score, whose outcome is the provider's evaluation."""
    if score_kind == SCORE.NONE or score is None:
        return None
    size = abs(Decimal(score))
    if score_kind in Z_LIKE_SCORES:
        if size <= 2:
            return OUTCOME.SATISFACTORY
        return OUTCOME.QUESTIONABLE if size < 3 else OUTCOME.UNSATISFACTORY
    if score_kind == SCORE.EN:
        return OUTCOME.SATISFACTORY if size <= 1 else OUTCOME.UNSATISFACTORY
    raise ValidationError({"score_kind": "Choose the kind of score."})


def overall_outcome(results):
    """The participation's outcome: the worst outcome of its results; not evaluated when no
    result was evaluated."""
    outcomes = {result.outcome for result in results}
    return next((outcome for outcome in ORDER if outcome in outcomes), OUTCOME.NOT_EVALUATED)


# Planning -----------------------------------------------------------------------------------


def _plan_values(values):
    unknown = set(values) - set(PLAN_FIELDS)
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}.")
    data = {name: _strip(values.get(name)) for name in PLAN_FIELDS}
    for name in PLAN_FIELDS:
        if data[name] is None and name != "results_due":
            data[name] = ""
    if data["kind"] not in ProficiencyParticipation.Kind.values:
        raise ValidationError({"kind": "Choose the kind of comparison."})
    if not data["results_due"]:
        raise ValidationError({"results_due": "State the day results are due."})
    return data


@transaction.atomic
def plan_participation(*, actor, method, reason, **values):
    """Plan the laboratory's participation in one round for ``method``."""
    require_role(actor, PLANNER)
    _require_reason(reason)
    lock_account(actor)
    item = ProficiencyParticipation(method=method, planned_by=actor, **_plan_values(values))
    item.full_clean()
    item.save()
    record_event(
        actor=actor,
        action="participation.planned",
        obj=item,
        after=snapshot(item),
        reason=reason,
    )
    return item


@transaction.atomic
def change_plan(*, actor, participation, expected_revision, reason, **values):
    """Change the plan of an open participation (its provider, round, item or due day). Once a
    result or the report is recorded the change is a correction of what the review will freeze,
    and whoever makes it cannot review the outcome."""
    require_role(actor, PLANNER)
    _require_reason(reason)
    lock_account(actor)
    locked = _locked(participation, expected_revision, STATE.OPEN)
    action = "participation.plan_corrected" if has_data(locked) else "participation.plan_changed"
    return _change(locked, actor, _plan_values(values), action, reason)


def has_data(item):
    """Whether a result or the day results were reported is recorded."""
    return bool(item.reported_on) or item.results.exists()


def _change(locked, actor, data, action, reason):
    if all(getattr(locked, name) == value for name, value in data.items()):
        raise ValidationError("Nothing was changed.")
    before = snapshot(locked)
    for name, value in data.items():
        setattr(locked, name, value)
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor, action=action, obj=locked, before=before, after=snapshot(locked), reason=reason
    )
    return locked


@transaction.atomic
def cancel_participation(*, actor, participation, expected_revision, reason):
    """Cancel a participation that will not take place, while it holds no result. It stays in
    the record with the reason."""
    require_role(actor, PLANNER)
    _require_reason(reason)
    lock_account(actor)
    locked = _locked(participation, expected_revision, STATE.OPEN)
    if locked.results.exists():
        raise ValidationError(
            "Results are recorded: review the participation instead. A round the provider did "
            "not evaluate is recorded as not evaluated."
        )
    before = snapshot(locked)
    locked.state = STATE.CANCELLED
    locked.cancelled_at = timezone.now()
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="participation.cancelled",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


# The laboratory's report and results --------------------------------------------------------


def version_choices(method):
    """The approved versions of ``method``, newest first: the versions a result can have been
    obtained with."""
    return MethodRevision.objects.filter(method=method, status=RevisionStatus.APPROVED).order_by(
        "-version"
    )


def _report_values(locked, values):
    unknown = set(values) - set(REPORT_FIELDS)
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}.")
    data = {name: _strip(values.get(name)) for name in REPORT_FIELDS}
    for name in ("data_ref", "report_ref", "report_url"):
        data[name] = data[name] or ""
    errors = {}
    version = data["method_version"]
    if version is not None and not version_choices(locked.method).filter(pk=version.pk).exists():
        errors["method_version"] = "Choose an approved version of this method."
    _past(errors, "received_on", data["received_on"], "The day the item was received")
    _past(errors, "reported_on", data["reported_on"], "The day results were reported")
    _past(errors, "report_on", data["report_on"], "The report's date")
    received, reported = data["received_on"], data["reported_on"]
    if received and reported and reported < received and "reported_on" not in errors:
        errors["reported_on"] = "Results cannot be reported before the item was received."
    if data["report_on"] and not reported and "report_on" not in errors:
        errors["reported_on"] = "State the day results were reported before the report's date."
    elif data["report_on"] and reported and data["report_on"] < reported:
        errors.setdefault(
            "report_on", "The provider's report cannot be dated before results were reported."
        )
    if errors:
        raise ValidationError(errors)
    return data


@transaction.atomic
def record_report(*, actor, participation, expected_revision, reason, **values):
    """Record or change the laboratory's report of an open participation. Whoever does cannot
    review it."""
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    lock_account(actor)
    locked = _locked(participation, expected_revision, STATE.OPEN)
    data = _report_values(locked, values)
    return _change(locked, actor, data, "participation.report_recorded", reason)


def performers():
    """Active accounts holding the analyst role: the people who perform an analysis."""
    return (
        get_user_model()
        .objects.filter(is_active=True, groups__name="analyst")
        .distinct()
        .order_by("username")
    )


@transaction.atomic
def add_result(
    *,
    actor,
    participation,
    reason,
    measurand,
    reported_value,
    score_kind,
    performed_by,
    expected_revision,
    unit="",
    assigned_value="",
    score=None,
    outcome="",
    note="",
):
    """Add one result of an open participation. With a score its outcome follows from the
    score; without one it is the provider's evaluation, chosen."""
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    lock_account(actor)
    locked = _locked(participation, expected_revision, STATE.OPEN)
    if locked.results.count() >= MAX_RESULTS:
        raise ValidationError(f"A participation has at most {MAX_RESULTS} results.")
    if not performers().filter(pk=performed_by.pk).exists():
        raise ValidationError({"performed_by": "Choose an active analyst."})
    errors = {}
    if score_kind not in SCORE.values:
        errors["score_kind"] = "Choose the kind of score."
    elif score_kind == SCORE.NONE:
        if score is not None:
            errors["score"] = "A result without a score has no score value."
        if outcome not in OUTCOME.values:
            errors["outcome"] = "Choose the provider's evaluation."
    elif score is None:
        errors["score"] = "Enter the score the provider gave."
    else:
        derived = outcome_of(score_kind, score)
        if outcome and outcome != derived:
            errors["outcome"] = (
                f"A {SCORE(score_kind).label} of {score} is {OUTCOME(derived).label.lower()}."
            )
        outcome = derived
    if errors:
        raise ValidationError(errors)
    item = ProficiencyResult(
        participation=locked,
        measurand=(measurand or "").strip(),
        unit=(unit or "").strip(),
        reported_value=(reported_value or "").strip(),
        assigned_value=(assigned_value or "").strip(),
        score_kind=score_kind,
        score=score,
        outcome=outcome,
        performed_by=performed_by,
        note=(note or "").strip(),
        created_by=actor,
    )
    item.full_clean()
    item.save()
    _bump(locked)
    record_event(
        actor=actor,
        action="participation.result_added",
        obj=locked,
        after=item.content(),
        reason=reason,
    )
    return item


@transaction.atomic
def remove_result(*, actor, item, reason, expected_revision):
    require_role(actor, *RECORDERS)
    _require_reason(reason)
    lock_account(actor)
    locked = _locked(item.participation, expected_revision, STATE.OPEN)
    item = ProficiencyResult.objects.select_for_update().get(pk=item.pk, participation=locked)
    before = item.content()
    item.delete()
    _bump(locked)
    record_event(
        actor=actor,
        action="participation.result_removed",
        obj=locked,
        before=before,
        reason=reason,
    )
    return locked


# Review -------------------------------------------------------------------------------------


def _actors(item, actions):
    return set(
        AuditEvent.objects.filter(
            object_type=item._meta.label_lower, object_id=str(item.pk), action__in=actions
        ).values_list("actor_id", flat=True)
    )


def data_authors(item):
    """Who recorded the report or results, or performed a result: they do not review the
    outcome or close its follow-up. Planning a participation is not authorship."""
    performed = set(item.results.values_list("performed_by_id", flat=True))
    return performed | _actors(item, DATA_ACTIONS)


def follow_up_authors(item):
    return _actors(item, (FOLLOW_UP_ACTION,))


def review_problems(item):
    """What keeps an open participation from being reviewed, in the words of the page; empty
    when ready."""
    problems = []
    if not item.results.exists():
        problems.append("Record the laboratory's results with the provider's scores.")
    if not item.reported_on:
        problems.append("Record the day the results were reported.")
    if not item.data_ref:
        problems.append("Record where the laboratory's original records are kept.")
    if not item.report_ref or not item.report_on:
        problems.append("Record the provider's report and its date.")
    return problems


def review_denial(actor, item):
    """Why ``actor`` cannot review ``item`` now, or "". Signing checks it again under lock."""
    if item.state != STATE.OPEN:
        return _state_refusal(item, (STATE.OPEN,))
    if actor.pk in data_authors(item):
        return INDEPENDENT
    if problems := review_problems(item):
        return "Not ready for review. " + " ".join(problems)
    return ""


def frozen_review(item):
    from .services import digest

    results = list(item.results.select_related("performed_by"))
    content = {
        "schema": "oq.proficiency/1",
        **item.details(),
        "results": [result.content() for result in results],
        "outcome": item.outcome,
        "review_conclusion": item.review_conclusion,
        "follow_up_required": item.follow_up_required,
    }
    return content, digest(content)


@sensitive_variables("pin")
def review_participation(
    *, actor, pin, participation, expected_revision, reason, conclusion, follow_up
):
    """Sign the review of the outcome. The participation is then closed, or stays open for
    corrective follow-up, which an unsatisfactory result requires."""

    def apply(locked):
        if locked.state != STATE.OPEN:
            raise ValidationError(_state_refusal(locked, (STATE.OPEN,)))
        if actor.pk in data_authors(locked):
            raise PermissionDenied(INDEPENDENT)
        if problems := review_problems(locked):
            raise ValidationError(problems)
        if not (conclusion or "").strip():
            raise ValidationError({"conclusion": "State the review of the outcome."})
        outcome = overall_outcome(locked.results.all())
        if outcome == OUTCOME.UNSATISFACTORY and not follow_up:
            raise ValidationError({"follow_up": UNSATISFACTORY_NEEDS_FOLLOW_UP})
        locked.outcome = outcome
        locked.review_conclusion = conclusion.strip()
        locked.follow_up_required = bool(follow_up)
        locked.review_content, locked.review_hash = frozen_review(locked)
        locked.reviewed_at = locked._signing_timestamp
        if follow_up:
            locked.state = STATE.FOLLOW_UP
        else:
            locked.state = STATE.CLOSED
            locked.closed_at = locked._signing_timestamp

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=participation,
        expected_revision=expected_revision,
        meaning="reviewed",
        reason=reason,
        permission=REVIEWER,
        apply=apply,
    )


# Corrective follow-up -----------------------------------------------------------------------


def assessment_refusal(assessment):
    """Why the follow-up cannot be closed on ``assessment`` (an impact assessment), or None."""
    if assessment is None:
        return None
    if assessment.state == "withdrawn":
        return f"{assessment.label} was withdrawn: link another impact assessment or none."
    if assessment.state != "concluded":
        return f"{assessment.label} is still open: conclude it before closing the follow-up."
    return None


@transaction.atomic
def record_follow_up(*, actor, participation, expected_revision, reason, **values):
    """Record or change the corrective follow-up of a reviewed participation. Whoever does
    cannot close it."""
    require_role(actor, REVIEWER)
    _require_reason(reason)
    lock_account(actor)
    locked = _locked(participation, expected_revision, STATE.FOLLOW_UP)
    unknown = set(values) - set(FOLLOW_UP_FIELDS)
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}.")
    data = {name: _strip(values.get(name)) for name in FOLLOW_UP_FIELDS}
    for name in FOLLOW_UP_FIELDS:
        if data[name] is None and name != "impact_assessment":
            data[name] = ""
    if data["impact_assessment"] is not None and data["impact_assessment"].state == "withdrawn":
        raise ValidationError(
            {"impact_assessment": f"{data['impact_assessment'].label} was withdrawn."}
        )
    return _change(locked, actor, data, FOLLOW_UP_ACTION, reason)


def close_problems(item):
    problems = []
    for name, text in (
        ("cause", "Record the cause found."),
        ("actions", "Record the corrective actions."),
        ("reported_results", "Record whether results already reported could be affected."),
        ("effectiveness", "Record how the actions were shown to work."),
    ):
        if not getattr(item, name).strip():
            problems.append(text)
    if refusal := assessment_refusal(item.impact_assessment):
        problems.append(refusal)
    return problems


def close_denial(actor, item):
    if item.state != STATE.FOLLOW_UP:
        return _state_refusal(item, (STATE.FOLLOW_UP,))
    if actor.pk in data_authors(item) | follow_up_authors(item):
        return INDEPENDENT_CLOSE
    if problems := close_problems(item):
        return "Not ready to close. " + " ".join(problems)
    return ""


def frozen_follow_up(item):
    from .services import digest

    assessment = item.impact_assessment
    content = {
        "schema": "oq.proficiency-follow-up/1",
        "identifier": item.identifier,
        "review_hash": item.review_hash,
        "cause": item.cause,
        "actions": item.actions,
        "reported_results": item.reported_results,
        "impact_assessment": {"id": assessment.pk, "label": assessment.label}
        if assessment
        else None,
        "quality_reference": item.quality_reference,
        "effectiveness": item.effectiveness,
    }
    return content, digest(content)


@sensitive_variables("pin")
def close_follow_up(*, actor, pin, participation, expected_revision, reason):
    """Sign the corrective follow-up as complete, freezing it. The signer is a quality person
    who recorded none of the follow-up, report or results."""
    from impact.models import Assessment

    def lock_assessment():
        # The impact assessment named is read under lock, so a withdrawal signed meanwhile
        # waits for the closure or the closure for it.
        current = ProficiencyParticipation.objects.filter(pk=participation.pk).values_list(
            "impact_assessment", flat=True
        )
        list(Assessment.objects.select_for_update(no_key=True).filter(pk__in=current))

    def apply(locked):
        if locked.state != STATE.FOLLOW_UP:
            raise ValidationError(_state_refusal(locked, (STATE.FOLLOW_UP,)))
        if actor.pk in data_authors(locked) | follow_up_authors(locked):
            raise PermissionDenied(INDEPENDENT_CLOSE)
        if problems := close_problems(locked):
            raise ValidationError(problems)
        locked.close_content, locked.close_hash = frozen_follow_up(locked)
        locked.state = STATE.CLOSED
        locked.closed_at = locked._signing_timestamp

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=participation,
        expected_revision=expected_revision,
        meaning="closed",
        reason=reason,
        permission=REVIEWER,
        apply=apply,
        prepare=lock_assessment,
    )


# Reading ------------------------------------------------------------------------------------


def display_state(item, today=None):
    """(label, tone) of a participation as the pages show it: an open one is planned, overdue
    (its results due day passed without a report) or awaiting review."""
    today = today or timezone.localdate()
    if item.state == STATE.OPEN:
        if item.reported_on:
            return "Results reported", "progress"
        if item.results_due < today:
            return "Results overdue", "danger"
        return "Planned", "neutral"
    tone = {STATE.FOLLOW_UP: "warning", STATE.CLOSED: "success", STATE.CANCELLED: "neutral"}
    return item.get_state_display(), tone[item.state]


OUTCOME_TONES = {
    OUTCOME.SATISFACTORY: "success",
    OUTCOME.QUESTIONABLE: "warning",
    OUTCOME.UNSATISFACTORY: "danger",
    OUTCOME.NOT_EVALUATED: "neutral",
}


def assessment_choices():
    """The impact assessments a follow-up can name: any not withdrawn."""
    from impact.models import Assessment

    return Assessment.objects.exclude(state="withdrawn")
