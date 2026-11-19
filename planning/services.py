"""Planning rules: who plans, what a test's due date is, and the audited changes of a plan or a
turnaround target. Planning changes no test and authorizes no work."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DateField, F, OuterRef, Q, Subquery, When
from django.db.models.expressions import CombinedExpression
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from analytical.models import AnalyticalTest
from core.audit import record_event
from core.services import require_role
from laboratory.models import Equipment
from laboratory.services import lock_account

from .models import MAX_TARGET_DAYS, Plan, Target, Work

READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
# Who plans tests: due dates, analysts and instruments. An analyst takes an unassigned test.
PLANNERS = ("reviewer", "quality")
TAKERS = ("analyst",)
TARGET_SETTERS = ("quality",)
# Who reads the turnaround and right-first-time figures: they name each analyst, so they are
# for the people who review and oversee the work, and admins, who read every laboratory area
# (a product choice; see docs/product.md). Analysts do not see their colleagues' figures.
FIGURE_READERS = ("reviewer", "quality", "auditor", "admin")
# A test takes work until it is reviewed, invalidated, superseded or recorded as not completed.
PLANNABLE = (AnalyticalTest.State.OPEN, AnalyticalTest.State.SUBMITTED)
MAX_SELECTED = 100  # tests planned at once: one page of the work list at its largest
SOON_DAYS = 7  # "due within a week"

STALE = (
    "The plan of {test} changed after this page was opened. Open the work list again to see "
    "the current plan."
)


def analysts():
    """Active accounts holding the analyst role: the people a test can be assigned to."""
    return (
        get_user_model()
        .objects.filter(is_active=True, groups__name="analyst")
        .distinct()
        .order_by("username")
    )


def assignable(assigned_ids=()):
    """The active analysts and anyone else open tests are still assigned to (an account that
    lost the role or was deactivated after the assignment), for filters and the workload."""
    ids = set(assigned_ids or ()) - {None}
    if not assigned_ids:
        ids = set(
            Plan.objects.filter(test__state__in=PLANNABLE, analyst__isnull=False).values_list(
                "analyst", flat=True
            )
        )
    return (
        get_user_model()
        .objects.filter(Q(pk__in=analysts().values("pk")) | Q(pk__in=ids))
        .order_by("username")
    )


def instruments():
    """Equipment in service: what a test can be planned on."""
    return Equipment.objects.filter(state=Equipment.State.IN_SERVICE).order_by("asset_id")


WORK_SUBJECT = {
    Work.LOT: Q(lot__isnull=False),
    Work.STABILITY: Q(pull__isnull=False),
    Work.REASSESSMENT: Q(reassessment__isnull=False),
}


def _target_days(work):
    """The days of the target for ``work`` in force when the outer test was assigned."""
    return Subquery(
        Target.objects.filter(work=work, set_at__lte=OuterRef("created_at"))
        .order_by("-set_at", "-id")
        .values("days")[:1]
    )


def with_due(tests):
    """Annotate tests with ``assigned_on`` (the local day the test was assigned), ``target_days``
    (the target in force then for its kind of work), ``target_due`` and ``due``: the planner's
    date, else the target's. Everything is SQL, so the work list filters, sorts and pages the
    whole queryset."""
    days = Case(
        *(When(subject, then=_target_days(work)) for work, subject in WORK_SUBJECT.items()),
    )
    return tests.annotate(
        assigned_on=TruncDate("created_at", tzinfo=timezone.get_current_timezone()),
        target_days=days,
        # PostgreSQL: date + integer is the date that many days later.
        target_due=CombinedExpression(
            F("assigned_on"), "+", F("target_days"), output_field=DateField()
        ),
        due=Coalesce(F("plan__due_on"), F("target_due"), output_field=DateField()),
    )


def open_work():
    """Every test that still takes work, with its due date and plan."""
    return with_due(
        AnalyticalTest.objects.filter(state__in=PLANNABLE).select_related(
            "lot",
            "sample",
            "pull__study__lot",
            "pull__timepoint__condition",
            "reassessment__lot",
            "plan__analyst",
            "plan__equipment",
        )
    )


DUE_CHOICES = [
    ("overdue", "Overdue"),
    ("today", "Due today"),
    ("week", f"Due in the next {SOON_DAYS} days"),
    ("later", f"Due after {SOON_DAYS} days"),
    ("none", "No due date"),
]


def due_filter(tests, key, today):
    """The tests of one due filter; ``tests`` carries ``due`` (with_due)."""
    match key:
        case "overdue":
            return tests.filter(due__lt=today)
        case "today":
            return tests.filter(due=today)
        case "week":
            return tests.filter(due__gt=today, due__lte=today + timedelta(days=SOON_DAYS))
        case "later":
            return tests.filter(due__gt=today + timedelta(days=SOON_DAYS))
        case "none":
            return tests.filter(due__isnull=True)
    return tests


def due_status(due, today):
    """(label, tone) of a due date for display: overdue in red, due within a week in amber."""
    if due is None:
        return "No due date", "neutral"
    days = (due - today).days
    if days < 0:
        late = -days
        return f"Overdue by {late} day{'s' if late != 1 else ''}", "danger"
    if days == 0:
        return "Due today", "warning"
    return (
        f"Due in {days} day{'s' if days != 1 else ''}",
        "warning" if days <= SOON_DAYS else "neutral",
    )


def current_targets():
    """{work: the Target in force now, or None}, in the order of Work."""
    found = {work: None for work in Work.values}
    for target in Target.objects.select_related("set_by").order_by("work", "-set_at", "-id"):
        if found.get(target.work) is None and target.work in found:
            found[target.work] = target
    return found


def _lock_targets():
    """Serialize changes of the turnaround targets (one setting per kind of work)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(681260)")


@transaction.atomic
def set_targets(*, actor, days, expected, reason=""):
    """Set the turnaround target of each kind of work in ``days`` ({work: days or None}).

    ``expected`` is {work: id of the target the page showed, or None}: a target changed meanwhile
    refuses the whole change. A kind whose target stays the same adds nothing."""
    require_role(actor, *TARGET_SETTERS)
    lock_account(actor)
    _lock_targets()
    current = current_targets()
    if {work: (t.pk if t else None) for work, t in current.items()} != expected:
        raise ValidationError(
            "The turnaround targets changed after this page was opened. Open it again to see "
            "the targets in force."
        )
    added = []
    for work, value in days.items():
        if work not in current:
            raise ValidationError("Unknown kind of work.")
        if value is not None and not 1 <= value <= MAX_TARGET_DAYS:
            raise ValidationError(f"A target is from 1 to {MAX_TARGET_DAYS} days.")
        before = current[work].days if current[work] else None
        if value == before:
            continue
        target = Target.objects.create(work=work, days=value, reason=reason, set_by=actor)
        record_event(
            actor=actor,
            action="turnaround_target.set",
            obj=target,
            before={"work": work, "days": before},
            after={"work": work, "days": value},
            reason=reason,
        )
        added.append(target)
    if not added:
        raise ValidationError("Nothing changed: every target is already as entered.")
    return added


def selection_token(tests):
    """What a page showed of the tests it plans: "id:plan revision" for each, in id order."""
    revisions = dict(Plan.objects.filter(test__in=tests).values_list("test_id", "revision"))
    return ",".join(f"{t.pk}:{revisions.get(t.pk, 0)}" for t in sorted(tests, key=lambda t: t.pk))


def parse_token(token):
    """{test id: plan revision} from selection_token; ValidationError when malformed."""
    try:
        pairs = [part.split(":") for part in token.split(",") if part]
        selected = {int(test): int(revision) for test, revision in pairs}
    except ValueError:
        raise ValidationError("The selection of tests is not readable.") from None
    if not selected:
        raise ValidationError("Select at least one test to plan.")
    if len(selected) > MAX_SELECTED:
        raise ValidationError(f"Plan at most {MAX_SELECTED} tests at once.")
    return selected


def _refuse_closed(tests, test_ids):
    if len(tests) != len(set(test_ids)):
        raise ValidationError("A selected test no longer exists.")
    for test in tests:
        if test.state not in PLANNABLE:
            raise ValidationError(
                f"{test.label} is {test.get_state_display().lower()}: only a test that is open or "
                "awaiting review is planned."
            )
    return tests


def plannable(test_ids):
    """The selected tests that still take work, or the refusal naming one that does not (for
    the page; the change rechecks under the locks)."""
    return _refuse_closed(
        list(AnalyticalTest.objects.filter(pk__in=test_ids).order_by("pk")), test_ids
    )


def _plans(selected):
    """The plan rows of the selected tests, created when missing and locked in test order; the
    revision each page saw is compared under the lock.

    The tests are locked first (FOR NO KEY UPDATE, in id order, as testing locks several tests),
    so a review or invalidation signed meanwhile either commits before and is refused here, or
    waits until the plan is saved."""
    tests = list(
        AnalyticalTest.objects.select_for_update(no_key=True).filter(pk__in=selected).order_by("pk")
    )
    _refuse_closed(tests, selected)
    Plan.objects.bulk_create([Plan(test=t) for t in tests], ignore_conflicts=True)
    plans = list(
        Plan.objects.select_for_update(of=("self",))
        .filter(test_id__in=selected)
        .select_related("test", "analyst", "equipment")
        .order_by("test_id")
    )
    for plan in plans:
        if plan.revision != selected[plan.test_id]:
            raise ValidationError(STALE.format(test=plan.test.label))
    return plans


def _record(plan):
    return {
        "due_on": plan.due_on.isoformat() if plan.due_on else None,
        "analyst": plan.analyst.get_username() if plan.analyst else None,
        "equipment": plan.equipment.asset_id if plan.equipment else None,
    }


def _save(plan, actor, before, reason, action):
    after = _record(plan)
    if after == before:
        return False
    plan.changed_by = actor
    plan.changed_at = timezone.now()
    plan.revision += 1
    plan.save()
    record_event(actor=actor, action=action, obj=plan, before=before, after=after, reason=reason)
    return True


KEEP = object()  # a field the planner leaves as each test has it


def _check_analyst(analyst):
    if analyst is not None and not analysts().filter(pk=analyst.pk).exists():
        raise ValidationError(f"{analyst.get_username()} is not an active analyst.")


def _check_instrument(equipment):
    if equipment is not None and equipment.state != Equipment.State.IN_SERVICE:
        raise ValidationError(f"{equipment.asset_id} is out of service.")


@transaction.atomic
def plan_tests(*, actor, token, due_on=KEEP, analyst=KEEP, equipment=KEEP, reason=""):
    """Plan the tests the page showed (``token``): each field given (None clears it) is set on
    every one; KEEP leaves it as each test has it. Refused as a whole when any test no longer
    takes work or its plan changed after the page was opened. Returns the plans changed."""
    require_role(actor, *PLANNERS)
    if due_on is KEEP and analyst is KEEP and equipment is KEEP:
        raise ValidationError("Choose what to change: a due date, an analyst or an instrument.")
    selected = parse_token(token)
    if analyst is not KEEP:
        _check_analyst(analyst)
    if equipment is not KEEP:
        _check_instrument(equipment)
    lock_account(actor)
    changed = []
    for plan in _plans(selected):
        before = _record(plan)
        if due_on is not KEEP:
            plan.due_on = due_on
        if analyst is not KEEP:
            plan.analyst = analyst
        if equipment is not KEEP:
            plan.equipment = equipment
        if _save(plan, actor, before, reason, "plan.changed"):
            changed.append(plan)
    if not changed:
        raise ValidationError("Nothing changed: every selected test is already planned so.")
    return changed


@transaction.atomic
def take_test(*, actor, test, expected_revision):
    """An analyst takes an open test that nobody is assigned to."""
    require_role(actor, *TAKERS)
    _check_analyst(actor)
    lock_account(actor)
    (plan,) = _plans({test.pk: expected_revision})
    if plan.test.state != AnalyticalTest.State.OPEN:
        raise ValidationError(f"{plan.test.label} is awaiting review: it takes no analyst now.")
    if plan.analyst_id is not None:
        raise ValidationError(
            f"{plan.test.label} is already assigned to {plan.analyst.get_username()}."
        )
    before = _record(plan)
    plan.analyst = actor
    _save(plan, actor, before, "", "plan.taken")
    return plan
