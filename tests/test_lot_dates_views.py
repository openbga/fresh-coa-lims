"""Expiry and retest dates through the pages: recording and correcting them, the lot record,
the lot list's columns and Dates filter, the rule sets page and the disposition page."""

import html
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from quality import dates
from quality.models import LotDates
from tests.receipts import on_site_receipt
from tests.test_lot_dates import BASIS, dated_rules, put
from tests.test_lot_receipt import approved_rules, receive, release, staff

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def people(django_user_model):
    return staff(django_user_model)


@pytest.fixture
def lot(people):
    return receive(people, approved_rules(people), on_site_receipt())


def today():
    return timezone.localdate()


def page(client, lot):
    return client.get(reverse("quality:lot_dates", args=[lot.pk]))


def posted(**changes):
    return {
        "expiry_on": (today() + timedelta(days=365)).isoformat(),
        "retest_on": (today() + timedelta(days=180)).isoformat(),
        "basis": BASIS,
        "current": "",
        "reason": "Synthetic dates from the supplier certificate",
    } | changes


def text(response):
    return " ".join(html.unescape(response.content.decode()).split())


def test_an_analyst_records_the_dates_from_the_lot_record(client, people, lot):
    client.force_login(people["analyst"])
    detail = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "Expiry and retest dates" in detail and "No expiry or retest date is recorded." in detail
    assert f'href="{reverse("quality:lot_dates", args=[lot.pk])}">Record dates</a>' in detail

    body = text(page(client, lot))
    assert "Record expiry and retest dates" in body
    assert "The lot's rule sets require no dates; record them where they apply." in body
    for label in ("Expiry date", "Retest date", "Basis", "Reason"):
        assert label in body
    response = client.post(reverse("quality:lot_dates", args=[lot.pk]), posted())
    assert response.status_code == 302
    assert response.url == reverse("quality:lot_detail", args=[lot.pk])
    record = LotDates.objects.get(lot=lot)
    assert record.retest_on == today() + timedelta(days=180) and record.basis == BASIS

    detail = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "Dates recorded." in detail
    assert (today() + timedelta(days=180)).isoformat() in detail and BASIS in detail
    assert ">Correct dates</a>" in detail and "Dates history" in detail


def test_a_correction_shows_the_dates_in_force_and_refuses_a_stale_page(client, people, lot):
    first = put(people, lot, retest_on=today() + timedelta(days=30))
    client.force_login(people["quality"])
    body = text(page(client, lot))
    assert "Correct expiry and retest dates" in body and "Reason for correction" in body
    assert f'value="{(today() + timedelta(days=30)).isoformat()}"' in body
    assert f'name="current" value="{first.pk}"' in body
    # Someone else corrects the dates while this page is open.
    put(people, lot, expected=first.pk, retest_on=today() + timedelta(days=60))
    response = client.post(
        reverse("quality:lot_dates", args=[lot.pk]), posted(current=str(first.pk))
    )
    assert response.status_code == 422
    assert "changed after this page was opened" in text(response)
    assert LotDates.objects.filter(lot=lot).count() == 2


def test_inconsistent_dates_are_shown_beside_their_field(client, people, lot):
    client.force_login(people["analyst"])
    response = client.post(
        reverse("quality:lot_dates", args=[lot.pk]),
        posted(retest_on=(today() + timedelta(days=400)).isoformat()),
    )
    assert response.status_code == 422
    assert "The retest date cannot be after the expiry date." in text(response)
    assert not LotDates.objects.exists()


@pytest.mark.parametrize("role", ["reviewer", "auditor", "admin"])
def test_other_roles_see_the_dates_but_cannot_record_them(client, people, lot, role):
    put(people, lot, expiry_on=today() + timedelta(days=10))
    client.force_login(people[role])
    assert page(client, lot).status_code == 403
    assert client.post(reverse("quality:lot_dates", args=[lot.pk]), posted()).status_code == 403
    detail = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert (today() + timedelta(days=10)).isoformat() in detail
    assert ">Correct dates</a>" not in detail and ">Record dates</a>" not in detail


def test_a_released_lot_takes_no_dates(client, people, lot, settings):
    release(people, lot, settings)
    client.force_login(people["analyst"])
    response = page(client, lot)
    assert response.status_code == 302
    assert response.url == reverse("quality:lot_detail", args=[lot.pk])
    detail = text(client.get(response.url))
    assert dates.NOT_QUARANTINED in detail and ">Record dates</a>" not in detail


def test_the_dates_page_names_what_the_rule_set_requires(client, people):
    lot = receive(people, dated_rules(people, "expiry"), on_site_receipt())
    client.force_login(people["analyst"])
    assert "synthetic-dated v1 requires an expiry date." in text(page(client, lot))
    detail = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "requires an expiry date." in detail
    assert "Rule set synthetic-dated v1 requires an expiry date for the lot." in detail


def test_the_lot_list_shows_and_filters_lots_by_their_dates(client, people, lot):
    rules = lot.rules
    put(people, lot, retest_on=today())
    expired = receive(people, rules, on_site_receipt(), number="SYN-R-EXP")
    put(people, expired, expiry_on=today() - timedelta(days=1))
    soon = receive(people, rules, on_site_receipt(), number="SYN-R-SOON")
    put(people, soon, expiry_on=today() + timedelta(days=dates.SOON_DAYS))
    later = receive(people, rules, on_site_receipt(), number="SYN-R-LATER")
    put(people, later, retest_on=today() + timedelta(days=dates.SOON_DAYS + 1))
    receive(people, rules, on_site_receipt(), number="SYN-R-NONE")
    client.force_login(people["auditor"])
    url = reverse("quality:lot_list")
    body = text(client.get(url))
    assert "Retest date" in body and "Expiry date" in body and "Retest due" in body
    assert "Expired" in body

    def listed(value):
        content = client.get(url, {"dates": value}).content.decode()
        return {n for n in ("SYN-R-001", "SYN-R-EXP", "SYN-R-SOON", "SYN-R-LATER") if n in content}

    assert listed("retest_due") == {"SYN-R-001"}
    assert listed("expired") == {"SYN-R-EXP"}
    assert listed("soon") == {"SYN-R-SOON"}
    assert listed("") == {"SYN-R-001", "SYN-R-EXP", "SYN-R-SOON", "SYN-R-LATER"}


def test_the_lot_record_and_the_disposition_page_show_the_dates(client, people, lot):
    put(people, lot, expiry_on=today() + timedelta(days=60), retest_on=today())
    client.force_login(people["quality"])
    detail = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "Retest due" in detail
    assert "has been reached. A lot is not released on or after its retest date" in detail
    sign = text(client.get(reverse("quality:disposition", args=[lot.pk])))
    assert "The release freezes the lot's expiry date" in sign and BASIS in sign


def test_the_rule_sets_page_shows_which_dates_a_rule_set_requires(client, people):
    dated_rules(people, "expiry_and_retest")
    client.force_login(people["quality"])
    body = text(client.get(reverse("core:rules")))
    assert "A lot is released with an expiry date and a retest date" in body
    assert "material_dates" in body  # the policy field's help names the key


def test_an_unknown_dates_value_is_ignored_and_the_status_still_applies(
    client, people, lot, settings
):
    released = receive(people, lot.rules, on_site_receipt(), number="SYN-R-REL")
    release(people, released, settings)
    client.force_login(people["auditor"])
    body = client.get(
        reverse("quality:lot_list"), {"state": "released", "dates": "someday"}
    ).content.decode()
    assert "SYN-R-REL" in body and "SYN-R-001" not in body


def test_the_rejection_and_cancellation_pages_show_the_dates_they_freeze(client, people, lot):
    put(people, lot, expiry_on=today() + timedelta(days=60), retest_on=today() + timedelta(days=30))
    client.force_login(people["quality"])
    for name in ("quality:lot_reject", "quality:lot_cancel"):
        body = text(client.get(reverse(name, args=[lot.pk])))
        assert "Expiry and retest dates" in body, name
        expiry = (today() + timedelta(days=60)).isoformat()
        retest = (today() + timedelta(days=30)).isoformat()
        assert f'Expiry date <time datetime="{expiry}">{expiry}</time>' in body, name
        assert f'Retest date <time datetime="{retest}">{retest}</time>' in body, name
        assert BASIS in body, name
    other = receive(people, lot.rules, on_site_receipt(), number="SYN-R-NODATES")
    assert "None recorded" in text(client.get(reverse("quality:lot_reject", args=[other.pk])))
