"""Planning pages: who opens them, the work list's filters, planning and taking tests through the
pages, the workload counts and the reminders of calibrations, pulls and reagent lots."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import AuditEvent
from laboratory.tests.helpers import accept_new_calibration, make_equipment, make_reagent
from planning import services
from planning.models import Plan
from stability.tests.helpers import started_study
from tests.overview_counts import assert_counts_open_their_rows, listed

from .conftest import login, lot_tests, review_identity

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("plain_static")]

READERS = ("analyst", "reviewer", "quality", "auditor", "admin")
PAGES = ("work_list", "workload", "reminders", "targets")


def url(name, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return reverse(f"planning:{name}") + (f"?{query}" if query else "")


@pytest.mark.parametrize("name", READERS)
def test_every_laboratory_reader_opens_the_planning_pages(client, people, name):
    login(client, people[name])
    for page in PAGES:
        assert client.get(url(page)).status_code == 200, page


def test_an_account_without_a_laboratory_role_is_refused(client, django_user_model):
    login(client, django_user_model.objects.create_user("roleless", password="Synthetic-1-pass"))
    for page in PAGES:
        assert client.get(url(page)).status_code == 403, page


@pytest.mark.parametrize("name", ["analyst", "auditor", "admin"])
def test_the_plan_page_is_for_planners_only(client, people, tests_of_lot, name):
    login(client, people[name])
    response = client.get(url("plan", test=tests_of_lot["identity"].pk))
    assert response.status_code == 403
    assert b"Plan selected tests" not in client.get(url("work_list")).content


@pytest.mark.parametrize("name", ["analyst", "reviewer", "auditor", "admin"])
def test_only_quality_changes_targets(client, people, name):
    login(client, people[name])
    assert client.get(url("targets_change")).status_code == 403
    assert client.post(url("targets_change"), {"lot": "5", "reason": "x"}).status_code == 403
    assert b"Change targets" not in client.get(url("targets")).content


def test_quality_changes_the_targets_through_the_page(client, people):
    login(client, people["quality"])
    form = client.get(url("targets_change")).context["form"]
    response = client.post(
        url("targets_change"),
        {
            "expected": form.initial["expected"],
            "lot": "10",
            "stability": "",
            "reassessment": "14",
            "reason": "Synthetic SOP-PLAN-1",
        },
    )
    assert response.status_code == 302
    current = services.current_targets()
    assert (current["lot"].days, current["stability"], current["reassessment"].days) == (
        10,
        None,
        14,
    )
    # The same page posted again is stale: the targets changed after it was opened.
    again = client.post(
        url("targets_change"),
        {"expected": form.initial["expected"], "lot": "9", "reason": "Synthetic"},
    )
    assert again.status_code == 422
    assert "changed after this page was opened" in again.content.decode()
    page = client.get(url("targets")).content.decode()
    assert "Synthetic SOP-PLAN-1" in page and "Reassessment testing" in page


def test_the_work_list_shows_open_work_earliest_due_first(client, people):
    first = lot_tests(people, "SYN-PLAN-A")
    second = lot_tests(people, "SYN-PLAN-B")
    review_identity(people, first["identity"])
    today = timezone.localdate()
    services.plan_tests(
        actor=people["reviewer"],
        token=services.selection_token([second["water"]]),
        due_on=today - timedelta(days=2),
    )
    login(client, people["reviewer"])
    response = client.get(url("work_list"))
    shown = [row["test"].pk for row in response.context["rows"]]
    assert first["identity"].pk not in shown  # reviewed: no more work
    assert shown[0] == second["water"].pk  # overdue, first
    assert "Overdue by 2 days" in response.content.decode()
    assert 'name="test"' in response.content.decode()  # planners select rows


def test_the_work_list_filters_by_due_date_analyst_instrument_state_and_work(client, people):
    tests = lot_tests(people)
    equipment = make_equipment(people, "SYN-PLAN-UV")
    services.plan_tests(
        actor=people["reviewer"],
        token=services.selection_token([tests["identity"]]),
        due_on=timezone.localdate(),
        analyst=people["analyst"],
        equipment=equipment,
    )
    login(client, people["analyst"])

    def codes(**params):
        response = client.get(url("work_list", **params))
        assert response.status_code == 200, params
        return sorted(row["test"].test_code for row in response.context["rows"])

    assert codes() == ["identity", "water"]
    assert codes(analyst="me") == ["identity"]
    assert codes(analyst="none") == ["water"]
    assert codes(analyst=people["analyst"].pk) == ["identity"]
    assert codes(due="today") == ["identity"]
    assert codes(due="none") == ["water"]
    assert codes(equipment=equipment.pk) == ["identity"]
    assert codes(equipment="none") == ["water"]
    assert codes(state="submitted") == []
    assert codes(work="stability") == []
    assert codes(q="wat") == ["water"]
    invalid = client.get(url("work_list", due="someday"))
    assert (
        invalid.status_code == 200 and "These filters cannot be applied" in invalid.content.decode()
    )


def test_a_planner_plans_the_selected_tests_through_the_page(client, people, tests_of_lot):
    identity, water = tests_of_lot["identity"], tests_of_lot["water"]
    login(client, people["quality"])
    page = client.get(url("plan") + f"?test={identity.pk}&test={water.pk}")
    assert page.status_code == 200
    token = page.context["form"].initial["token"]
    day = timezone.localdate() + timedelta(days=4)
    response = client.post(
        url("plan"),
        {"token": token, "due_on": day.isoformat(), "analyst": people["analyst2"].pk},
    )
    assert response.status_code == 302
    assert set(Plan.objects.values_list("due_on", "analyst")) == {(day, people["analyst2"].pk)}
    # Posting the same page again is stale and changes nothing.
    stale = client.post(url("plan"), {"token": token, "no_analyst": "on"})
    assert stale.status_code == 422
    assert "changed after this page was opened" in stale.content.decode()
    assert AuditEvent.objects.filter(action="plan.changed").count() == 2


def test_the_plan_form_refuses_a_value_and_its_removal_together(client, people, tests_of_lot):
    login(client, people["reviewer"])
    token = services.selection_token([tests_of_lot["identity"]])
    response = client.post(
        url("plan"), {"token": token, "due_on": "2026-12-01", "use_target": "on"}
    )
    assert response.status_code == 422
    assert "not both" in response.content.decode()
    assert not Plan.objects.exists()


def test_the_plan_page_explains_a_selection_it_cannot_plan(client, people, tests_of_lot):
    identity = review_identity(people, tests_of_lot["identity"])
    login(client, people["reviewer"])
    nothing = client.get(url("plan"))
    assert nothing.status_code == 409 and "Select the tests to plan" in nothing.content.decode()
    closed = client.get(url("plan", test=identity.pk))
    assert closed.status_code == 409
    assert "only a test that is open or awaiting review" in closed.content.decode()
    assert 'name="token"' not in closed.content.decode()


def test_an_analyst_takes_a_test_from_the_work_list(client, people, tests_of_lot):
    identity = tests_of_lot["identity"]
    login(client, people["analyst"])
    page = client.get(url("work_list", analyst="none")).content.decode()
    assert "Assign to me" in page
    back = url("work_list", analyst="none")
    response = client.post(
        reverse("planning:take", args=[identity.pk]), {"expected_revision": "0", "next": back}
    )
    assert response.status_code == 302 and response["Location"] == back
    assert Plan.objects.get(test=identity).analyst == people["analyst"]
    again = client.post(
        reverse("planning:take", args=[identity.pk]),
        {"expected_revision": "0", "next": back},
        follow=True,
    )
    assert "changed after this page was opened" in again.content.decode()


def test_taking_a_test_never_redirects_off_the_work_list(client, people, tests_of_lot):
    login(client, people["analyst"])
    for target in ("https://example.invalid/planning/", "/accounts/access/", "//example.invalid"):
        response = client.post(
            reverse("planning:take", args=[tests_of_lot["water"].pk]),
            {"expected_revision": "0", "next": target},
        )
        assert response["Location"] == url("work_list")


@pytest.mark.parametrize("name", ["reviewer", "quality", "auditor"])
def test_only_analysts_take_tests_through_the_page(client, people, tests_of_lot, name):
    login(client, people[name])
    response = client.post(
        reverse("planning:take", args=[tests_of_lot["water"].pk]), {"expected_revision": "0"}
    )
    assert response.status_code == 403
    assert "Assign to me" not in client.get(url("work_list")).content.decode()
    assert client.get(reverse("planning:take", args=[tests_of_lot["water"].pk])).status_code == 405


def test_workload_counts_open_the_rows_they_count(client, people):
    tests = lot_tests(people)
    lot_tests(people, "SYN-PLAN-2")
    equipment = make_equipment(people, "SYN-PLAN-HPLC")
    services.plan_tests(
        actor=people["reviewer"],
        token=services.selection_token([tests["identity"], tests["water"]]),
        due_on=timezone.localdate() - timedelta(days=1),
        analyst=people["analyst"],
        equipment=equipment,
    )
    login(client, people["auditor"])
    counts = assert_counts_open_their_rows(client, url("workload"))
    assert counts["Overdue"] == 2
    assert counts["No due date"] == 2
    assert counts["Open, no analyst assigned"] == 2
    response = client.get(url("workload"))
    analyst = next(r for r in response.context["analyst_rows"] if r["name"] == "Synthetic Analyst")
    assert analyst["total"][0] == analyst["overdue"][0] == 2
    assert listed(client.get(analyst["overdue"][1])) == 2
    (row,) = response.context["instrument_rows"]
    assert row["total"][0] == 2 and listed(client.get(row["total"][1])) == 2
    assert row["check"] == ""


def test_workload_warns_when_calibration_runs_out_before_planned_work(client, people):
    tests = lot_tests(people)
    equipment = make_equipment(people, "SYN-PLAN-KF", ready=False, requires_qualification=False)
    accept_new_calibration(people, equipment, days_valid=3)
    services.plan_tests(
        actor=people["reviewer"],
        token=services.selection_token([tests["water"]]),
        due_on=timezone.localdate() + timedelta(days=10),
        equipment=equipment,
    )
    login(client, people["analyst"])
    (row,) = client.get(url("workload")).context["instrument_rows"]
    assert row["check"] == ("Calibration runs out before planned work", "warning")


def test_reminders_list_calibrations_pulls_and_reagents_within_the_window(client, people):
    today = timezone.localdate()
    soon = make_equipment(people, "SYN-REM-BAL", ready=False, requires_qualification=False)
    accept_new_calibration(people, soon, days_valid=10)
    later = make_equipment(people, "SYN-REM-UV", ready=False, requires_qualification=False)
    accept_new_calibration(people, later, days_valid=80)
    make_reagent(people, "SYN-REM-RG1", expiry_days=5)
    make_reagent(people, "SYN-REM-RG2", expiry_days=200)
    make_reagent(people, "SYN-REM-RG3", expiry_days=3, release=False)
    started_study(people)  # pulls due 70 days ago, today and in 80 days (window 5 days)
    login(client, people["analyst"])

    def shown(**params):
        response = client.get(url("reminders", **params))
        assert response.status_code == 200
        return [(r.kind, r.label.split(" · ")[0], r.status) for r in response.context["page_obj"]]

    month = shown()
    assert ("calibration", "SYN-REM-BAL", "Due in 10 days") in month
    assert ("reagent", "SYN-REM-RG1", "Expires in 5 days") in month
    assert not any(label in ("SYN-REM-UV", "SYN-REM-RG2", "SYN-REM-RG3") for _, label, _ in month)
    pulls = [status for kind, _, status in month if kind == "pull"]
    assert any(status.startswith("Overdue: window closed") for status in pulls)
    assert any(status.startswith("Due now, until") for status in pulls)
    assert len(pulls) == 2
    assert [r[0] for r in shown(kind="pull", within=90)].count("pull") == 3
    assert {r[0] for r in shown(kind="calibration")} == {"calibration"}
    dates = [r.on for r in client.get(url("reminders", within=90)).context["page_obj"]]
    assert dates == sorted(dates) and dates[0] < today


def test_reminders_point_to_expired_lots_instead_of_listing_them(client, people, monkeypatch):
    from planning import reminders

    make_reagent(people, "SYN-REM-OLD", expiry_days=5)
    later = timezone.localdate() + timedelta(days=6)
    assert reminders.expired_reagents(later).count() == 1
    assert not [r for r in reminders.reminders(later, 30) if r.kind == "reagent"]
    monkeypatch.setattr(reminders, "expired_reagents", lambda today: reminders.ReagentLot.objects)
    login(client, people["analyst"])
    response = client.get(url("reminders", kind="reagent"))
    assert response.context["expired"] == 1
    assert "past its last day of use" in response.content.decode()
    assert client.get(url("reminders", kind="pull")).context["expired"] == 0
