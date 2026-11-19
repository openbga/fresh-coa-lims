"""Turnaround and right-first-time figures: what counts as a return, a correction and a repeat,
turnaround and timeliness against the due date, the period by the local day of the review, who
reads the figures, every count matching the list it opens, and the CSV export."""

import csv
import io
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from analytical import services as analytical
from analytical.models import AnalyticalTest
from laboratory.tests.helpers import PIN
from planning import figures, services, views
from planning.models import Work
from tests.overview_counts import assert_counts_open_their_rows, listed

from .conftest import fresh, login, lot_tests

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("plain_static")]


def url(name, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return reverse(f"planning:{name}") + (f"?{query}" if query else "")


def record(people, test, value, who="analyst"):
    analytical.record_observation(
        actor=people[who], test=fresh(test), value=Decimal(value), raw_reference="NB-FIG p1"
    )
    return fresh(test)


def submit(people, test, who="analyst"):
    test = fresh(test)
    return analytical.submit_test(
        actor=people[who], test=test, expected_revision=test.revision, reason="Complete"
    )


def review(people, test, who="reviewer", at=None):
    test = fresh(test)
    with mock.patch("django.utils.timezone.now", return_value=at or timezone.now()):
        analytical.review_test(
            actor=people[who],
            pin=PIN,
            test=test,
            expected_revision=test.revision,
            reason="Raw data checked",
        )
    return fresh(test)


def done(people, test, value="1.00", who="analyst", at=None):
    """Record, submit and review a test, right first time."""
    record(people, test, value, who=who)
    submit(people, test, who=who)
    return review(people, test, at=at)


def set_target(people, days, work="lot"):
    with mock.patch("django.utils.timezone.now", return_value=timezone.now() - timedelta(days=400)):
        services.set_targets(
            actor=people["quality"],
            days={work: days},
            expected={w: None for w in Work.values},
            reason="Synthetic SOP-FIG-1",
        )


def csv_rows(response):
    assert response.streaming
    return list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))


def row_of(test, start=None, end=None):
    today = timezone.localdate()
    tests = figures.reviewed_tests(start or today - timedelta(days=60), end or today)
    return tests.get(pk=test.pk)


def test_a_test_reviewed_without_rework_is_right_first_time_and_on_time(people):
    set_target(people, 10)
    assigned = timezone.now() - timedelta(days=3)
    tests = lot_tests(people, "SYN-FIG-1", assigned_at=assigned)
    done(people, tests["identity"])
    row = row_of(tests["identity"])
    assert row.turnaround == 3
    assert row.due == timezone.localdate(assigned) + timedelta(days=10)
    assert row.timeliness == figures.ON_TIME
    assert (row.returns, row.corrections, row.is_repeat, row.repeated) == (0, 0, False, False)
    assert row.first_time is True
    assert (row.work, row.material, row.method) == ("lot", "Synthetic powder", "SYN-IR")
    # A test not yet reviewed is not counted.
    assert not figures.reviewed_tests(timezone.localdate(), timezone.localdate()).filter(
        pk=tests["water"].pk
    )


def test_returns_corrections_and_lateness_are_counted(people):
    set_target(people, 2)
    tests = lot_tests(people, "SYN-FIG-2", assigned_at=timezone.now() - timedelta(days=5))
    returned, corrected = tests["identity"], tests["water"]
    record(people, returned, "1.00")
    submit(people, returned)
    test = fresh(returned)
    analytical.return_test(
        actor=people["reviewer"], test=test, expected_revision=test.revision, reason="Units"
    )
    submit(people, returned)
    review(people, returned)
    record(people, corrected, "0.20")
    analytical.correct_observation(
        actor=people["analyst"],
        observation=fresh(corrected).observations.get(),
        value=Decimal("0.21"),
        raw_reference="NB-FIG p2",
        reason="Transcription",
    )
    submit(people, corrected)
    review(people, corrected)
    first, second = row_of(returned), row_of(corrected)
    assert (first.returns, first.corrections, first.first_time) == (1, 0, False)
    assert (second.returns, second.corrections, second.first_time) == (0, 1, False)
    assert first.timeliness == second.timeliness == figures.LATE
    assert first.turnaround == 5
    totals = figures.totals(figures.reviewed_tests(*figures.default_period(timezone.localdate())))
    assert (totals["reviewed"], totals["returned"], totals["corrected"], totals["late"]) == (
        2,
        1,
        1,
        2,
    )
    assert totals["first_time"] == 0 and totals["with_due"] == 2 and totals["no_due"] == 0


def test_a_planner_date_wins_and_no_date_is_its_own_figure(people):
    tests = lot_tests(people, "SYN-FIG-3", assigned_at=timezone.now() - timedelta(days=4))
    tomorrow = timezone.localdate() + timedelta(days=1)
    services.plan_tests(
        actor=people["reviewer"],
        token=services.selection_token([tests["identity"]]),
        due_on=tomorrow,
    )
    done(people, tests["identity"])
    done(people, tests["water"], value="0.20")
    planned, unplanned = row_of(tests["identity"]), row_of(tests["water"])
    assert (planned.due, planned.timeliness) == (tomorrow, figures.ON_TIME)
    assert (unplanned.due, unplanned.timeliness) == (None, figures.NO_DUE)
    totals = figures.totals(figures.reviewed_tests(*figures.default_period(timezone.localdate())))
    assert (totals["with_due"], totals["on_time"], totals["no_due"]) == (1, 1, 1)


def test_an_invalidated_oos_result_and_its_retest_are_both_repeats(people):
    tests = lot_tests(people, "SYN-FIG-4")
    original = record(people, tests["identity"], "1.30")
    submitted, investigation = submit(people, original)
    assert submitted.conforms is False
    review(people, original)
    analytical.add_entry(
        actor=people["analyst"],
        investigation=investigation,
        kind="assessment",
        text="Dilution flask used the wrong volume",
    )
    investigation = fresh(investigation)
    analytical.authorize_retest(
        actor=people["quality"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        kind="retest",
        reason="One retest of the same sample",
    )
    retest = AnalyticalTest.objects.get(parent=original)
    done(people, retest, value="1.01", who="analyst2")
    investigation = fresh(investigation)
    analytical.conclude(
        actor=people["quality2"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="invalidated",
        assignable_cause="Dilution error documented",
        reason="Independent conclusion",
    )
    first, second = row_of(original), row_of(retest)
    assert fresh(original).state == "invalidated"  # still counted: its review was signed
    assert (first.repeated, first.is_repeat, first.invalidated, first.conforms) == (
        True,
        False,
        True,
        False,
    )
    assert (second.repeated, second.is_repeat, second.invalidated) == (False, True, False)
    assert not first.first_time and not second.first_time
    totals = figures.totals(figures.reviewed_tests(*figures.default_period(timezone.localdate())))
    assert (totals["reviewed"], totals["repeat"], totals["oos"], totals["invalidated"]) == (
        2,
        2,
        1,
        1,
    )
    by_analyst = {
        row["key"]: row["reviewed"]
        for row in figures.by_group(
            figures.reviewed_tests(*figures.default_period(timezone.localdate())), "analyst"
        )
    }
    assert by_analyst == {people["analyst"].pk: 1, people["analyst2"].pk: 1}


def test_the_repeat_of_a_test_not_completed_is_not_right_first_time(people):
    tests = lot_tests(people, "SYN-FIG-5")
    stopped = fresh(tests["identity"])
    analytical.record_not_completed(
        actor=people["quality"],
        pin=PIN,
        test=stopped,
        expected_revision=stopped.revision,
        cause=AnalyticalTest.NotCompletedCause.SAMPLE,
        reason="Synthetic: the sample was spilt",
        repeat="same",
    )
    repeat = AnalyticalTest.objects.get(parent=stopped)
    assert repeat.kind == "repeat"
    done(people, repeat)
    row = row_of(repeat)
    assert (row.is_repeat, row.first_time) == (True, False)
    # The test not completed was never reviewed and is not counted.
    assert not figures.reviewed_tests(*figures.default_period(timezone.localdate())).filter(
        pk=stopped.pk
    )


def test_a_repeat_under_replaced_requirements_is_not_a_repeat(people):
    tests = lot_tests(people, "SYN-FIG-6")
    done(people, tests["identity"])
    child = AnalyticalTest.objects.create(
        lot=tests["identity"].lot,
        sample=tests["identity"].sample,
        test_code="identity",
        requirement=tests["identity"].requirement,
        requirement_hash=tests["identity"].requirement_hash,
        kind=AnalyticalTest.Kind.REVISED,
        parent=tests["identity"],
        created_by=people["quality"],
    )
    done(people, child)
    assert row_of(tests["identity"]).first_time is True
    assert row_of(child).first_time is True


def test_the_period_is_the_local_day_of_the_review(people, settings):
    settings.TIME_ZONE = "Pacific/Auckland"
    timezone.activate("Pacific/Auckland")
    try:
        tests = lot_tests(people, "SYN-FIG-7")
        local_today = timezone.localdate()
        # Signed at 23:30 local time yesterday: 10:30 or 11:30 UTC, a UTC day that is also
        # "yesterday" there; the period of today alone must not count it.
        late_evening = timezone.make_aware(
            timezone.datetime.combine(local_today - timedelta(days=1), timezone.datetime.min.time())
        ) + timedelta(hours=23, minutes=30)
        done(people, tests["identity"], at=late_evening)
        assert not figures.reviewed_tests(local_today, local_today).exists()
        row = figures.reviewed_tests(local_today - timedelta(days=1), local_today).get()
        assert row.reviewed_on == local_today - timedelta(days=1)
    finally:
        timezone.deactivate()


def test_the_median_and_the_ninth_decile(people):
    set_target(people, 30)
    for n, days in enumerate((1, 2, 4, 9)):
        tests = lot_tests(
            people,
            f"SYN-FIG-M{n}",
            codes=("identity",),
            assigned_at=timezone.now() - timedelta(days=days),
        )
        done(people, tests["identity"])
    totals = figures.totals(figures.reviewed_tests(*figures.default_period(timezone.localdate())))
    assert totals["median"] == Decimal("3.0")  # between 2 and 4
    assert totals["ninth"] == 9
    assert figures.share(1, 3) == Decimal("33") and figures.share(2, 3) == Decimal("67")
    assert figures.share(1, 0) is None


@pytest.mark.parametrize("name", ["reviewer", "quality", "auditor", "admin"])
def test_reviewers_quality_auditors_and_admins_read_the_figures(client, people, name):
    login(client, people[name])
    assert client.get(url("figures")).status_code == 200
    assert client.get(url("reviewed")).status_code == 200
    assert b'href="/planning/figures/"' in client.get(url("work_list")).content


def test_analysts_do_not_see_the_figures(client, people, django_user_model):
    login(client, people["analyst"])
    assert client.get(url("figures")).status_code == 403
    assert client.get(url("reviewed")).status_code == 403
    assert client.get(url("reviewed", export="csv")).status_code == 403
    page = client.get(url("work_list")).content
    assert b"/planning/figures/" not in page
    assert b"Turnaround targets" in page
    login(client, django_user_model.objects.create_user("roleless", password="Synthetic-1-pass"))
    assert client.get(url("figures")).status_code == 403


def test_every_count_opens_its_tests(client, people):
    set_target(people, 2)
    old = lot_tests(people, "SYN-FIG-8", assigned_at=timezone.now() - timedelta(days=6))
    done(people, old["identity"])
    record(people, old["water"], "0.20")
    submit(people, old["water"])
    test = fresh(old["water"])
    analytical.return_test(
        actor=people["reviewer"], test=test, expected_revision=test.revision, reason="Units"
    )
    submit(people, old["water"])
    review(people, old["water"])
    new = lot_tests(people, "SYN-FIG-9", codes=("identity",))
    done(people, new["identity"], who="analyst2")
    login(client, people["reviewer"])
    counts = assert_counts_open_their_rows(client, url("figures"))
    assert counts["Reviewed"] == 3
    assert counts["Reviewed late"] == 2 and counts["Reviewed on time"] == 1
    assert counts["Returned for correction"] == 1 and counts["Right first time"] == 2
    response = client.get(url("figures"))
    assert response.context["first_time_share"] == "67%"
    for group in ("work", "material", "method", "analyst", "month"):
        rows = client.get(url("figures", by=group)).context["group_rows"]
        assert sum(row["reviewed"][0] for row in rows) == 3, group
        for row in rows:
            for key in views.COUNTS:
                count, link = row[key]
                response = client.get(link)
                assert response.context["invalid"] is None, (group, key, link)
                assert listed(response) == count, (group, key, link)
    for row in client.get(url("figures")).context["summary"]:
        assert client.get(row["href"]).context["invalid"] is None, row["href"]


def test_the_period_is_validated(client, people):
    login(client, people["quality"])
    today = timezone.localdate()
    backwards = client.get(url("figures", start=today, end=today - timedelta(days=1)))
    assert backwards.context["totals"] is None
    assert b"The period ends before it starts." in backwards.content
    too_long = client.get(url("reviewed", start=today - timedelta(days=366), end=today))
    assert b"at most 366 days" in too_long.content
    assert (
        client.get(url("reviewed", start=today - timedelta(days=365), end=today)).status_code == 200
    )
    empty = client.get(url("figures"))
    assert b"No test was reviewed in this period" in empty.content
    # Extreme or partial dates never fail the page.
    for params in (
        {"start": "9999-12-31"},
        {"end": "0001-01-05"},
        {"start": "9999-12-20", "end": "9999-12-31"},
        {"start": "1899-12-31", "end": "1900-01-01"},
    ):
        for page in ("figures", "reviewed"):
            response = client.get(url(page, **params))
            assert response.status_code == 200, (page, params)
            assert b"Enter a date from 1900-01-01 to 9998-12-31." in response.content
    future = client.get(url("figures", start=today + timedelta(days=10)))
    assert (future.context["start"], future.context["end"]) == (today + timedelta(days=10),) * 2
    only_from = client.get(url("figures", start=today - timedelta(days=100)))
    assert only_from.context["end"] == today - timedelta(days=71)
    only_to = client.get(url("figures", end=today - timedelta(days=10)))
    assert only_to.context["start"] == today - timedelta(days=39)
    wrong = client.get(url("figures", by="colour", work="mining"))
    assert wrong.context["totals"] is None and b"The figures cannot be shown" in wrong.content
    # An invalid filter never exports: the list shows the error instead.
    refused = client.get(url("reviewed", export="csv", start=today, end=today - timedelta(days=1)))
    assert refused["Content-Type"].startswith("text/html")
    assert b"The period ends before it starts." in refused.content


def test_the_reviewed_list_filters_and_searches(client, people):
    tests = lot_tests(people, "SYN-FIG-10")
    done(people, tests["identity"])
    record(people, tests["water"], "0.20")
    submit(people, tests["water"])
    test = fresh(tests["water"])
    analytical.return_test(
        actor=people["reviewer"], test=test, expected_revision=test.revision, reason="Units"
    )
    submit(people, tests["water"])
    review(people, tests["water"])
    login(client, people["auditor"])
    assert listed(client.get(url("reviewed"))) == 2
    assert listed(client.get(url("reviewed", first_time="yes"))) == 1
    assert listed(client.get(url("reviewed", first_time="no"))) == 1
    assert listed(client.get(url("reviewed", method="SYN-KF"))) == 1
    assert listed(client.get(url("reviewed", q="SYN-FIG-10"))) == 2
    assert listed(client.get(url("reviewed", q="nothing-like-this"))) == 0
    page = client.get(url("reviewed", first_time="returned")).content.decode()
    assert "Not right first time" in page and "Returned" in page


def test_the_csv_lists_the_filtered_tests_and_escapes_formulas(client, people):
    tests = lot_tests(people, "SYN-FIG-11", material="=SUM(A1:A2)")
    done(people, tests["identity"])
    login(client, people["quality"])
    response = client.get(url("reviewed", export="csv"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    rows = csv_rows(response)
    header, body = rows[0], rows[1:]
    assert header[0] == "Test" and "Right first time" in header
    assert len(body) == 1
    line = dict(zip(header, body[0], strict=True))
    assert line["Material"] == "'=SUM(A1:A2)"
    assert line["Test"] == tests["identity"].label and line["Right first time"] == "yes"
    assert line["Analyst"] == "analyst" and line["Due from"] == ""
    reviewed_at = timezone.datetime.fromisoformat(line["Reviewed at"])
    assert reviewed_at.utcoffset() == timezone.localtime().utcoffset()
    filtered = client.get(url("reviewed", export="csv", first_time="no"))
    assert len(csv_rows(filtered)) == 1


def test_a_stability_test_counts_as_stability_work_of_its_study_lot(people):
    from stability.tests.helpers import assign, pulled, reviewed, specified_study

    study, _ = specified_study(people)
    (test,) = assign(people, pulled(people, study))
    reviewed(people, test)
    row = row_of(test)
    assert (row.work, row.material) == ("stability", study.lot.material)
    assert row.method == "syn-shelf-assay" and row.first_time is True
    totals = figures.by_group(
        figures.reviewed_tests(*figures.default_period(timezone.localdate())), "work"
    )
    assert [(group["key"], group["reviewed"]) for group in totals] == [("stability", 1)]


def test_a_month_row_opens_its_part_of_the_period(client, people, settings):
    """A period across a month boundary: each month's counts open the tests of that month."""
    tests = lot_tests(people, "SYN-FIG-12", assigned_at=timezone.now() - timedelta(days=50))
    today = timezone.localdate()
    first_of_month = today.replace(day=1)
    before = timezone.make_aware(
        timezone.datetime.combine(first_of_month - timedelta(days=1), timezone.datetime.min.time())
    ) + timedelta(hours=12)
    done(people, tests["identity"], at=before)
    done(people, tests["water"], value="0.20")
    login(client, people["quality"])
    start = first_of_month - timedelta(days=5)
    response = client.get(url("figures", by="month", start=start, end=today))
    rows = response.context["group_rows"]
    assert [row["reviewed"][0] for row in rows] == [1, 1]
    assert [row["name"] for row in rows] == [
        (first_of_month - timedelta(days=1)).strftime("%B %Y"),
        today.strftime("%B %Y"),
    ]
    earlier = client.get(rows[0]["reviewed"][1])
    assert (earlier.context["start"], earlier.context["end"]) == (
        start,
        first_of_month - timedelta(days=1),
    )
    assert [r["test"].pk for r in earlier.context["rows"]] == [tests["identity"].pk]


def test_a_filter_value_outside_the_period_lists_nothing(client, people):
    tests = lot_tests(people, "SYN-FIG-13", codes=("identity",))
    done(people, tests["identity"])
    login(client, people["reviewer"])
    response = client.get(url("reviewed", method="SYN-NOT-IN-PERIOD", material="Nothing"))
    assert response.context["invalid"] is None and listed(response) == 0
    choices = dict(response.context["filters"].fields["method"].choices)
    assert "SYN-IR" in choices and "SYN-KF" not in choices  # only the period's methods
    assert listed(client.get(url("reviewed", analyst="none"))) == 0


def test_the_list_reads_a_page_of_tests_in_a_fixed_number_of_queries(
    client, people, django_assert_max_num_queries
):
    for n in range(3):
        tests = lot_tests(people, f"SYN-FIG-Q{n}")
        done(people, tests["identity"])
        done(people, tests["water"], value="0.20")
    login(client, people["reviewer"])
    client.get(url("reviewed"))  # warm the session and preference caches
    with django_assert_max_num_queries(20):
        response = client.get(url("reviewed"))
    assert listed(response) == 6
    with django_assert_max_num_queries(20):
        client.get(url("figures", by="analyst"))
