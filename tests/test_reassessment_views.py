"""The reassessment of a released lot through its pages: the lot record's panel and start page,
assigning the tests, the conclusion and withdrawal signing pages, the lot list's Dates filter,
the dashboard queues and the pages of a reassessment's test (synthetic data only)."""

import html
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from analytical import services as analytical
from analytical.contracts import resolve_reassessment
from analytical.models import AnalyticalTest, Investigation
from quality import dashboard, dates, reassessment
from quality.models import Reassessment
from tests.test_integrated_journey import PIN
from tests.test_reassessment import (
    begin,
    conclude,
    fresh,
    released_world,
    reviewed,
    submit_all,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(django_user_model):
    return released_world(django_user_model)


def today():
    return timezone.localdate()


def text(response):
    """The page as text, tags and whitespace runs removed."""
    return " ".join(html.unescape(strip_tags(response.content.decode())).split())


def lot_page(client, world):
    return text(client.get(reverse("quality:lot_detail", args=[world["lot"].pk])))


def signed(user, **values):
    return {
        "signature_username": user.username,
        "reason": "Synthetic signature",
        "pin": PIN,
        **values,
    }


def test_an_analyst_starts_a_reassessment_from_the_lot_record(client, world):
    people, lot = world["people"], world["lot"]
    client.force_login(people["reviewer"])
    body = lot_page(client, world)
    assert "Reassessments" in body and "Start reassessment" not in body
    client.force_login(people["analyst"])
    body = lot_page(client, world)
    start = reverse("quality:reassessment_new", args=[lot.pk])
    assert "Start reassessment" in body
    assert (
        f'href="{start}">Start reassessment</a>'
        in client.get(reverse("quality:lot_detail", args=[lot.pk])).content.decode()
    )

    page = text(client.get(start))
    assert "Start reassessment" in page and "Containers sampled" in page
    assert (today() + timedelta(days=10)).isoformat() in page  # the retest date in force
    response = client.post(
        start,
        {
            "sample_reference": "SYN-RA-VIEW-1",
            "sampled_on": today().isoformat(),
            "quantity": "20",
            "quantity_unit": "g",
            "containers": "SYN-C001; bay B2",
            "reason": "Retest date in ten days",
        },
    )
    item = Reassessment.objects.get(lot=lot)
    assert response.status_code == 302 and response.url == reverse(
        "quality:reassessment_detail", args=[item.pk]
    )
    detail = text(client.get(response.url))
    assert f"{item.label} started; assign its tests." in detail
    assert "Assign tests" in detail and "No test assigned." in detail
    assert "Retest date when started" in detail and "SYN-RA-VIEW-1" in detail
    # The lot record lists it, and a second one cannot start while it is open.
    body = lot_page(client, world)
    assert item.label in body and "Start reassessment" not in body
    response = client.get(start)
    assert response.status_code == 302


def test_a_released_lot_without_a_retest_date_says_why_it_is_not_reassessed(
    client, django_user_model
):
    world = released_world(django_user_model, retest_in=None, expiry_in=300)
    client.force_login(world["people"]["analyst"])
    body = lot_page(client, world)
    assert "The lot has no retest date." in body and "Start reassessment" not in body


def test_assigning_tests_shows_the_criteria_in_force_and_refuses_a_stale_page(client, world):
    item = begin(world)
    client.force_login(world["people"]["analyst"])
    url = reverse("quality:reassessment_tests", args=[item.pk])
    page = text(client.get(url))
    assert "Acceptance criteria in force" in page and "Impurity" in page
    assert "synthetic-rt-spec@v1" in page and "/reassess:" in page
    response = client.post(url, {"criteria": "0" * 64, "reason": "Assign"})
    assert response.status_code == 422
    assert analytical.CRITERIA_CHANGED in text(response)
    accepted, _ = resolve_reassessment(item)
    token = analytical.pull_criteria_hash(accepted)
    assert f'value="{token}"' in response.content.decode()  # the page can be sent again
    response = client.post(url, {"criteria": token, "reason": "Assign"})
    assert response.status_code == 302
    assert AnalyticalTest.objects.filter(reassessment=item).count() == 4
    # A reviewer does not assign tests.
    client.force_login(world["people"]["reviewer"])
    assert client.get(url).status_code == 403


def test_a_reassessment_test_names_its_reassessment_not_a_lot_sample(client, world):
    item = begin(world)
    submit_all(world, item)
    test = AnalyticalTest.objects.filter(reassessment=item).first()
    client.force_login(world["people"]["reviewer"])
    body = text(client.get(reverse("analytical:test_detail", args=[test.pk])))
    assert "Reassessment test" in body and f"Reassessment {item.label}" in body
    listed = text(client.get(reverse("analytical:test_list") + f"?q={world['lot'].number}"))
    assert f"reassessment {item.label}" in listed


def test_the_conclusion_is_signed_by_an_independent_quality_person(client, world):
    people = world["people"]
    item = reviewed(world, begin(world, who="author"))
    url = reverse("quality:reassessment_conclude", args=[item.pk])
    client.force_login(people["author"])  # started it
    raw = client.get(reverse("quality:reassessment_detail", args=[item.pk]))
    assert "another quality person concludes it" in text(raw)
    assert f'href="{url}"' not in raw.content.decode()  # not offered to an author
    response = client.get(url)
    assert response.status_code == 403 and reassessment.SELF_CONCLUSION in text(response)
    client.force_login(people["analyst"])  # recorded its results, and holds the quality role
    assert client.get(url).status_code == 403
    client.force_login(people["approver"])
    page = text(client.get(url))
    assert "Sign and conclude" in page and "New retest date" in page and "Conforms" in page
    response = client.post(
        url,
        signed(people["approver"], expected_revision=item.revision, outcome="suitable"),
    )
    assert response.status_code == 422 and "Enter the new retest date." in text(response)
    new_date = today() + timedelta(days=401)
    response = client.post(
        url,
        signed(
            people["approver"],
            expected_revision=item.revision,
            outcome="suitable",
            retest_on=new_date.isoformat(),
        ),
    )
    assert response.status_code == 422 and "expiry date" in text(response)
    new_date = today() + timedelta(days=180)
    response = client.post(
        url,
        signed(
            people["approver"],
            expected_revision=item.revision,
            outcome="suitable",
            retest_on=new_date.isoformat(),
        ),
    )
    assert response.status_code == 302
    assert fresh(item).retest_on == new_date
    detail = text(client.get(reverse("quality:reassessment_detail", args=[item.pk])))
    assert "Suitable" in detail and f"retest date in force is {new_date.isoformat()}" in detail
    body = lot_page(client, world)
    assert f"set by {item.label}" in body and new_date.isoformat() in body
    assert "Retest due" not in body


def test_a_failure_cannot_be_withdrawn_and_ends_the_lot_s_use(client, world):
    people = world["people"]
    item = begin(world)
    for code, (test, _) in submit_all(world, item, impurity="5.50").items():
        if code != "impurity":
            analytical.review_test(
                actor=people["reviewer"],
                pin=PIN,
                test=fresh(test),
                expected_revision=fresh(test).revision,
                reason="Review",
            )
    test = AnalyticalTest.objects.get(reassessment=item, test_code="impurity")
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=fresh(test).revision,
        reason="Review",
    )
    investigation = Investigation.objects.get(test=test)
    analytical.add_entry(
        actor=people["analyst"],
        investigation=investigation,
        kind="assessment",
        text="No laboratory error found",
    )
    investigation.refresh_from_db()
    analytical.conclude(
        actor=people["author"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="confirmed",
        assignable_cause="",
        reason="Confirmed",
    )
    client.force_login(people["approver"])
    detail = text(client.get(reverse("quality:reassessment_detail", args=[item.pk])))
    assert "Out of specification" in detail and "Withdraw" not in detail
    response = client.get(reverse("quality:reassessment_withdraw", args=[item.pk]))
    assert response.status_code == 403 and "not suitable instead" in text(response)
    item = fresh(item)
    response = client.post(
        reverse("quality:reassessment_conclude", args=[item.pk]),
        signed(people["approver"], expected_revision=item.revision, outcome="not_suitable"),
    )
    assert response.status_code == 302
    body = lot_page(client, world)
    assert "Use ended" in body and "A reassessment ended the use of this lot" in body
    assert "Start reassessment" not in body


def test_withdrawal_of_a_reassessment_started_in_error(client, world):
    people = world["people"]
    item = begin(world)
    url = reverse("quality:reassessment_withdraw", args=[item.pk])
    client.force_login(people["reviewer"])
    assert client.get(url).status_code == 403
    client.force_login(people["author"])
    assert "Sign and withdraw" in text(client.get(url))
    response = client.post(url, signed(people["author"], expected_revision=item.revision))
    assert response.status_code == 302 and fresh(item).state == "withdrawn"


def test_the_dates_filter_and_the_dashboard_list_the_same_lots(client, world):
    people, lot = world["people"], world["lot"]
    client.force_login(people["reviewer"])
    lots = reverse("quality:lot_list")

    def listed(key):
        return lot.number in text(client.get(f"{lots}?dates={key}"))

    def counted(label):
        return next(q.count for q in dashboard.gates() if q.label == label)

    assert not listed("reassessing") and counted("Reassessments open") == 0
    item = begin(world)
    assert listed("reassessing") and counted("Reassessments open") == 1
    later = today() + timedelta(days=11)
    original = dates.today
    try:
        dates.today = lambda: later
        assert listed("retest_due") and counted("Retest due") == 1
        conclude(world, reviewed(world, item), "suitable", today() + timedelta(days=200))
        assert not listed("retest_due") and counted("Retest due") == 0
    finally:
        dates.today = original
    assert not listed("use_ended")
    body = text(client.get(f"{lots}?dates=use_ended"))
    assert "Use ended" in body  # the filter is offered


def test_readers_see_a_reassessment_and_only_quality_concludes(client, world):
    item = begin(world)
    detail = reverse("quality:reassessment_detail", args=[item.pk])
    for who in ("reviewer", "analyst", "approver"):
        client.force_login(world["people"][who])
        assert client.get(detail).status_code == 200
    client.force_login(world["people"]["reviewer"])
    assert client.get(reverse("quality:reassessment_conclude", args=[item.pk])).status_code == 403
    assert (
        client.get(reverse("quality:reassessment_new", args=[world["lot"].pk])).status_code == 403
    )
