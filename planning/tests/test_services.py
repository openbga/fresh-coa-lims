"""Planning rules on PostgreSQL: due dates from targets and plans, who plans, stale and closed
tests, the append-only history of targets and the audit of every change."""

import datetime
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from analytical import services as analytical
from analytical.models import AnalyticalTest
from core.models import AuditEvent
from laboratory.models import Equipment
from laboratory.tests.helpers import make_equipment
from planning import services
from planning.models import Plan, Target, Work

from .conftest import fresh, lot_tests, review_identity

pytestmark = pytest.mark.django_db(transaction=True)


def targets(people, actor="quality", reason="Synthetic SOP-PLAN-1", **days):
    current = services.current_targets()
    expected = {work: (t.pk if t else None) for work, t in current.items()}
    values = {work: (t.days if t else None) for work, t in current.items()}
    values.update(days)
    return services.set_targets(actor=people[actor], days=values, expected=expected, reason=reason)


def due_of(test):
    return services.with_due(AnalyticalTest.objects.filter(pk=test.pk)).get()


def token(*tests):
    return services.selection_token(list(tests))


def plan(people, *tests, actor="reviewer", **changes):
    return services.plan_tests(actor=people[actor], token=token(*tests), **changes)


# --- Due dates -------------------------------------------------------------------------------


def test_without_a_target_or_a_plan_a_test_has_no_due_date(people, tests_of_lot):
    assert due_of(tests_of_lot["identity"]).due is None


def test_a_test_is_due_by_the_target_in_force_when_it_was_assigned(people):
    targets(people, lot=5, stability=20)
    test = lot_tests(people)["identity"]
    found = due_of(test)
    assigned = timezone.localdate(test.created_at)
    assert found.assigned_on == assigned
    assert found.target_days == 5  # the lot target, not the stability one
    assert found.due == assigned + timedelta(days=5)


def test_the_day_assigned_is_the_local_day_of_the_deployment(people, settings):
    """A test assigned at 12:00 UTC is assigned the next calendar day in Auckland (UTC+13 in
    November): its due date counts from that local day."""
    settings.TIME_ZONE = "Pacific/Auckland"
    utc = datetime.UTC
    moment = datetime.datetime.combine(
        timezone.now().astimezone(utc).date() - timedelta(days=1), datetime.time(12), utc
    )
    with mock.patch("django.utils.timezone.now", return_value=moment - timedelta(hours=1)):
        targets(people, lot=3)  # in force before the test is assigned
    test = lot_tests(people, assigned_at=moment)["identity"]
    assert test.created_at == moment
    found = due_of(test)
    assert found.assigned_on == moment.date() + timedelta(days=1)
    assert found.due == moment.date() + timedelta(days=4)
    tests = services.with_due(AnalyticalTest.objects.filter(pk=test.pk))
    local_today = timezone.localdate()
    expected = "today" if found.due == local_today else None
    assert services.due_filter(tests, "today", local_today).exists() == (expected == "today")


def test_a_later_target_does_not_move_a_test_already_assigned(people):
    targets(people, lot=5)
    test = lot_tests(people)["identity"]
    targets(people, lot=2)
    assert due_of(test).target_days == 5
    later = lot_tests(people, "SYN-PLAN-2")["identity"]
    assert due_of(later).target_days == 2


def test_a_target_removed_leaves_later_tests_without_a_due_date(people):
    targets(people, lot=5)
    targets(people, lot=None)
    assert due_of(lot_tests(people)["identity"]).due is None


def test_a_planned_date_wins_over_the_target_and_can_be_given_back(people):
    targets(people, lot=5)
    test = lot_tests(people)["identity"]
    day = timezone.localdate() + timedelta(days=1)
    plan(people, test, due_on=day)
    assert due_of(test).due == day
    plan(people, test, due_on=None)
    assert due_of(test).due == timezone.localdate(test.created_at) + timedelta(days=5)


@pytest.mark.parametrize(
    ("offset", "key", "label", "tone"),
    [
        (-3, "overdue", "Overdue by 3 days", "danger"),
        (-1, "overdue", "Overdue by 1 day", "danger"),
        (0, "today", "Due today", "warning"),
        (2, "week", "Due in 2 days", "warning"),
        (7, "week", "Due in 7 days", "warning"),
        (8, "later", "Due in 8 days", "neutral"),
    ],
)
def test_due_filters_and_labels_agree(people, tests_of_lot, offset, key, label, tone):
    today = timezone.localdate()
    test = tests_of_lot["identity"]
    plan(people, test, due_on=today + timedelta(days=offset))
    tests = services.with_due(AnalyticalTest.objects.filter(pk=test.pk))
    for other, _ in services.DUE_CHOICES:
        assert services.due_filter(tests, other, today).exists() == (other == key)
    assert services.due_status(today + timedelta(days=offset), today) == (label, tone)
    assert services.due_status(None, today) == ("No due date", "neutral")


# --- Turnaround targets ----------------------------------------------------------------------


def test_only_quality_sets_targets(people):
    for name in ("analyst", "reviewer", "auditor", "admin"):
        with pytest.raises(PermissionDenied):
            targets(people, actor=name, lot=5)
    assert not Target.objects.exists()


def test_setting_targets_adds_rows_only_for_the_kinds_changed_and_audits_each(people):
    targets(people, lot=5, stability=30)
    added = targets(people, lot=5, stability=21)
    assert [(t.work, t.days) for t in added] == [(Work.STABILITY, 21)]
    event = AuditEvent.objects.get(action="turnaround_target.set", after__days=21)
    assert event.before == {"work": "stability", "days": 30}
    assert event.after == {"work": "stability", "days": 21}
    assert event.reason == "Synthetic SOP-PLAN-1"
    assert event.actor == people["quality"]


def test_a_change_that_changes_nothing_is_refused(people):
    targets(people, lot=5)
    with pytest.raises(ValidationError, match="Nothing changed"):
        targets(people, lot=5)


def test_targets_changed_after_the_page_opened_are_refused(people):
    seen = {work: None for work in Work.values}
    targets(people, actor="quality2", lot=4)
    with pytest.raises(ValidationError, match="changed after this page was opened"):
        services.set_targets(
            actor=people["quality"], days={"lot": 9}, expected=seen, reason="Synthetic"
        )
    assert services.current_targets()["lot"].days == 4


@pytest.mark.parametrize("days", [0, 366])
def test_a_target_outside_one_to_365_days_is_refused(people, days):
    with pytest.raises(ValidationError, match="from 1 to 365 days"):
        targets(people, lot=days)
    with transaction.atomic(), pytest.raises(IntegrityError):
        Target.objects.create(work="lot", days=days, set_by=people["quality"])


def test_targets_are_append_only(people):
    (target,) = targets(people, lot=5)
    for statement in (
        "UPDATE planning_target SET days = 6 WHERE id = %s",
        "DELETE FROM planning_target WHERE id = %s",
    ):
        with transaction.atomic(), pytest.raises(DatabaseError, match="append-only"):
            with connection.cursor() as cursor:
                cursor.execute(statement, [target.pk])
    assert fresh(target).days == 5


# --- Planning tests --------------------------------------------------------------------------


def test_planners_set_due_date_analyst_and_instrument_with_an_audited_change(people, tests_of_lot):
    equipment = make_equipment(people, "SYN-PLAN-BAL")
    day = timezone.localdate() + timedelta(days=3)
    identity, water = tests_of_lot["identity"], tests_of_lot["water"]
    changed = plan(
        people,
        identity,
        water,
        actor="quality",
        due_on=day,
        analyst=people["analyst2"],
        equipment=equipment,
        reason="Synthetic week plan",
    )
    assert len(changed) == 2
    stored = Plan.objects.get(test=identity)
    assert (stored.due_on, stored.analyst, stored.equipment) == (day, people["analyst2"], equipment)
    assert (stored.revision, stored.changed_by) == (1, people["quality"])
    event = AuditEvent.objects.filter(action="plan.changed", object_id=str(stored.pk)).get()
    assert event.before == {"due_on": None, "analyst": None, "equipment": None}
    assert event.after == {
        "due_on": day.isoformat(),
        "analyst": "analyst2",
        "equipment": "SYN-PLAN-BAL",
    }
    assert event.reason == "Synthetic week plan"
    # Fields not given keep each test's own value.
    plan(people, identity, analyst=people["analyst"])
    stored = fresh(stored)
    assert (stored.due_on, stored.analyst, stored.equipment) == (day, people["analyst"], equipment)


@pytest.mark.parametrize("name", ["analyst", "auditor", "admin"])
def test_only_reviewers_and_quality_plan(people, tests_of_lot, name):
    with pytest.raises(PermissionDenied):
        plan(people, tests_of_lot["identity"], actor=name, due_on=timezone.localdate())
    assert not Plan.objects.exists()


def test_a_plan_changed_after_the_page_opened_is_refused_as_a_whole(people, tests_of_lot):
    identity, water = tests_of_lot["identity"], tests_of_lot["water"]
    seen = token(identity, water)
    plan(people, water, actor="reviewer2", analyst=people["analyst"])
    with pytest.raises(ValidationError, match=f"plan of {water.label} changed"):
        services.plan_tests(actor=people["reviewer"], token=seen, analyst=people["analyst2"])
    assert Plan.objects.get(test=water).analyst == people["analyst"]
    assert not Plan.objects.filter(test=identity).exists()  # the whole change rolled back
    assert AuditEvent.objects.filter(action="plan.changed").count() == 1


def test_a_test_that_takes_no_more_work_is_not_planned(people, tests_of_lot):
    identity = review_identity(people, tests_of_lot["identity"])
    with pytest.raises(ValidationError, match="only a test that is open or awaiting review"):
        plan(people, identity, tests_of_lot["water"], due_on=timezone.localdate())
    assert not Plan.objects.exists()


def test_the_database_refuses_a_plan_change_once_the_test_is_closed(people, tests_of_lot):
    identity = tests_of_lot["identity"]
    plan(people, identity, analyst=people["analyst"])
    review_identity(people, identity)
    stored = Plan.objects.get(test=identity)
    with transaction.atomic(), pytest.raises(DatabaseError, match="open or awaiting review"):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE planning_plan SET due_on = CURRENT_DATE, revision = revision + 1 "
                "WHERE id = %s",
                [stored.pk],
            )
    with transaction.atomic(), pytest.raises(DatabaseError, match="cannot be deleted"):
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM planning_plan WHERE id = %s", [stored.pk])


def test_the_database_keeps_a_plan_with_its_test_and_its_revision_moving(people, tests_of_lot):
    identity, water = tests_of_lot["identity"], tests_of_lot["water"]
    plan(people, identity, analyst=people["analyst"])
    stored = Plan.objects.get(test=identity)
    for statement, message in (
        ("UPDATE planning_plan SET test_id = %s, revision = revision + 1 WHERE id = %s", "stays"),
        ("UPDATE planning_plan SET due_on = CURRENT_DATE WHERE id = %s", "advances"),
    ):
        args = [water.pk, stored.pk] if "test_id" in statement else [stored.pk]
        with transaction.atomic(), pytest.raises(DatabaseError, match=message):
            with connection.cursor() as cursor:
                cursor.execute(statement, args)


def test_only_an_active_analyst_and_equipment_in_service_are_planned(people, tests_of_lot):
    test = tests_of_lot["identity"]
    with pytest.raises(ValidationError, match="not an active analyst"):
        plan(people, test, analyst=people["reviewer2"])
    people["analyst2"].is_active = False
    people["analyst2"].save()
    with pytest.raises(ValidationError, match="not an active analyst"):
        plan(people, test, analyst=people["analyst2"])
    equipment = make_equipment(people, "SYN-PLAN-OOS")
    Equipment.objects.filter(pk=equipment.pk).update(state="out_of_service", revision=2)
    with pytest.raises(ValidationError, match="out of service"):
        plan(people, test, equipment=fresh(equipment))
    assert not Plan.objects.filter(revision__gt=0).exists()


def test_a_plan_that_changes_nothing_is_refused(people, tests_of_lot):
    test = tests_of_lot["identity"]
    with pytest.raises(ValidationError, match="Choose what to change"):
        services.plan_tests(actor=people["reviewer"], token=token(test))
    plan(people, test, analyst=people["analyst"])
    with pytest.raises(ValidationError, match="Nothing changed"):
        plan(people, test, analyst=people["analyst"])


@pytest.mark.parametrize("text", ["", "x", "1:a", "1:0,2"])
def test_an_unreadable_selection_is_refused(people, text):
    with pytest.raises(ValidationError):
        services.plan_tests(actor=people["reviewer"], token=text, due_on=None)


def test_at_most_a_hundred_tests_are_planned_at_once(people):
    text = ",".join(f"{n}:0" for n in range(1, services.MAX_SELECTED + 2))
    with pytest.raises(ValidationError, match="at most 100"):
        services.plan_tests(actor=people["reviewer"], token=text, due_on=None)


# --- Taking a test ---------------------------------------------------------------------------


def test_an_analyst_takes_an_unassigned_open_test(people, tests_of_lot):
    test = tests_of_lot["identity"]
    taken = services.take_test(actor=people["analyst"], test=test, expected_revision=0)
    assert taken.analyst == people["analyst"]
    event = AuditEvent.objects.get(action="plan.taken")
    assert event.after["analyst"] == "analyst"
    with pytest.raises(ValidationError, match="changed after this page was opened"):
        services.take_test(actor=people["analyst2"], test=test, expected_revision=0)
    with pytest.raises(ValidationError, match="already assigned to analyst"):
        services.take_test(actor=people["analyst2"], test=test, expected_revision=1)


def test_a_test_awaiting_review_or_closed_is_not_taken(people, tests_of_lot):
    water = tests_of_lot["water"]
    analytical.record_observation(
        actor=people["analyst"], test=water, value=Decimal("0.5"), raw_reference="NB-PLAN p2"
    )
    water = fresh(water)
    analytical.submit_test(
        actor=people["analyst"], test=water, expected_revision=water.revision, reason="Complete"
    )
    with pytest.raises(ValidationError, match="is awaiting review: it takes no analyst now"):
        services.take_test(actor=people["analyst2"], test=water, expected_revision=0)
    identity = review_identity(people, tests_of_lot["identity"])
    with pytest.raises(ValidationError, match="open or awaiting review"):
        services.take_test(actor=people["analyst"], test=identity, expected_revision=0)
    assert not Plan.objects.filter(analyst__isnull=False).exists()


def test_one_person_with_both_roles_plans_and_takes(people, tests_of_lot):
    both = people["planner_analyst"]
    identity, water = tests_of_lot["identity"], tests_of_lot["water"]
    services.plan_tests(actor=both, token=token(identity), analyst=people["analyst2"])
    services.take_test(actor=both, test=water, expected_revision=0)
    assert set(Plan.objects.values_list("test_id", "analyst__username")) == {
        (identity.pk, "analyst2"),
        (water.pk, "planner_analyst"),
    }


@pytest.mark.parametrize("name", ["reviewer", "quality", "auditor", "admin"])
def test_only_analysts_take_tests(people, tests_of_lot, name):
    with pytest.raises(PermissionDenied):
        services.take_test(actor=people[name], test=tests_of_lot["identity"], expected_revision=0)


def test_open_work_counts_tests_open_and_awaiting_review_only(people, tests_of_lot):
    review_identity(people, tests_of_lot["identity"])
    assert list(services.open_work().values_list("test_code", flat=True)) == ["water"]
