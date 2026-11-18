"""Impact assessments through their pages: the list and its filter, starting one from the record
that failed, the record page with its sections and actions, adding and deciding records,
placing a hold, the conclusion and withdrawal signing pages, the lot record's panel and the
dashboard queue (synthetic data only)."""

import html
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from impact.models import Assessment, Item
from quality import dashboard
from tests.test_impact_assessment import begin, decide_all, fresh, released, reviewed_world, used
from tests.test_integrated_journey import PIN

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(django_user_model):
    world = reviewed_world(django_user_model)
    used(world, world["tests"]["impurity"], world["balance"])
    return world


def today():
    return timezone.localdate()


def text(response):
    return " ".join(html.unescape(strip_tags(response.content.decode())).split())


def signed(user, **values):
    return {
        "signature_username": user.username,
        "reason": "Synthetic signature",
        "pin": PIN,
        **values,
    }


def test_quality_starts_an_assessment_from_the_equipment_page(client, world):
    people, balance = world["people"], world["balance"]
    equipment = reverse("laboratory:equipment_detail", args=[balance.pk])
    start = reverse("impact:new") + f"?equipment={balance.pk}"
    client.force_login(people["reviewer"])
    assert start not in client.get(equipment).content.decode().replace("&amp;", "&")
    assert client.get(reverse("impact:new")).status_code == 403
    client.force_login(people["author"])
    assert start in client.get(equipment).content.decode().replace("&amp;", "&")
    page = client.get(start)
    assert page.status_code == 200
    assert f'value="{balance.pk}" selected' in page.content.decode()
    response = client.post(
        reverse("impact:new"),
        {
            "cause": "equipment",
            "equipment": balance.pk,
            "title": "Balance out of tolerance",
            "description": "Synthetic weekly check failed",
            "found_on": today().isoformat(),
            "period_from": (today() - timedelta(days=3)).isoformat(),
            "period_until": today().isoformat(),
            "quality_reference": "DEV-SYN-7",
        },
    )
    assessment = Assessment.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("impact:detail", args=[assessment.pk])
    assert assessment.items.count() == 2  # the test and its lot
    # A refused start keeps the values and says why, beside the field.
    response = client.post(
        reverse("impact:new"),
        {
            "cause": "supplier",
            "title": "Supplier problem",
            "description": "Synthetic",
            "found_on": today().isoformat(),
            "period_from": today().isoformat(),
            "period_until": today().isoformat(),
        },
    )
    assert response.status_code == 422
    assert "Choose the record that failed." in text(response)


def test_the_record_page_shows_each_kind_and_the_next_step(client, world):
    world = released(world)
    people = world["people"]
    assessment = begin(world)
    detail = reverse("impact:detail", args=[assessment.pk])
    client.force_login(people["auditor"] if "auditor" in people else people["reviewer"])
    body = text(client.get(detail))
    assert "Tests" in body and "Lots" in body and "Certificates" in body
    assert "Record decision" not in body and "Conclude" not in body
    assert "3 record(s) have no decision yet." in body
    client.force_login(people["author"])
    body = text(client.get(detail))
    assert "Record decision" in body and "Place hold" in body and "Add record" in body
    assert "another quality person concludes it" in body
    item = assessment.items.get(kind=Item.Kind.TEST)
    decide = reverse("impact:decide", args=[item.pk])
    response = client.post(
        decide,
        {
            "expected_revision": item.revision,
            "decision": "affected",
            "rationale": "Synthetic: weighed on the failed balance",
            "follow_up": "",
        },
    )
    assert response.status_code == 422 and "Say what is done about it." in text(response)
    response = client.post(
        decide,
        {
            "expected_revision": item.revision,
            "decision": "affected",
            "rationale": "Synthetic: weighed on the failed balance",
            "follow_up": "Retest under an investigation",
            "follow_up_reference": "INV-SYN-1",
        },
    )
    assert response.status_code == 302
    assert fresh(item).decision == "affected"
    lot_item = assessment.items.get(kind=Item.Kind.LOT)
    response = client.post(
        reverse("impact:hold", args=[lot_item.pk]),
        {"expected_revision": lot_item.revision, "reason": "Synthetic: hold until assessed"},
    )
    assert response.status_code == 302
    hold = fresh(lot_item).hold
    body = text(client.get(detail))
    assert hold.identifier in body
    # The lot record names the assessment, the decision on the lot and the hold.
    lot_page = text(client.get(reverse("quality:lot_detail", args=[world["lot"].pk])))
    assert assessment.label in lot_page and hold.identifier in lot_page
    # The approver, who did none of it, concludes once every record is decided.
    decide_all(world, assessment)
    client.force_login(people["approver"])
    conclude = reverse("impact:conclude", args=[assessment.pk])
    assert f'href="{conclude}"' in client.get(detail).content.decode()
    page = client.get(conclude)
    assert page.status_code == 200 and "Sign and conclude" in text(page)
    response = client.post(
        conclude, signed(people["approver"], expected_revision=fresh(assessment).revision)
    )
    assert response.status_code == 302
    assert fresh(assessment).state == Assessment.State.CONCLUDED
    body = text(client.get(detail))
    assert "Concluded" in body and "Record decision" not in body


def test_the_conclusion_page_refuses_its_authors_before_any_pin(client, world):
    people = world["people"]
    assessment = begin(world)
    decide_all(world, assessment)
    client.force_login(people["author"])
    response = client.get(reverse("impact:conclude", args=[assessment.pk]))
    assert response.status_code == 403
    assert "Another quality person concludes it." in text(response)
    assert 'name="pin"' not in response.content.decode()


def test_records_are_added_and_found_again_through_their_pages(client, world):
    world = released(world)
    people = world["people"]
    assessment = begin(world, cause="other", equipment=None)
    client.force_login(people["author"])
    add = reverse("impact:add", args=[assessment.pk])
    response = client.post(
        add,
        {
            "expected_revision": assessment.revision,
            "kind": "lot",
            "identifier": "SYN-NOT-A-LOT",
            "reason": "Synthetic",
        },
    )
    assert response.status_code == 422 and "No lot is called SYN-NOT-A-LOT." in text(response)
    response = client.post(
        add,
        {
            "expected_revision": assessment.revision,
            "kind": "lot",
            "identifier": world["lot"].number,
            "reason": "Synthetic: the diluent was used for it",
        },
    )
    assert response.status_code == 302
    detail = text(client.get(reverse("impact:detail", args=[assessment.pk])))
    assert "New records found" in detail and "Find affected records" in detail
    find = reverse("impact:find", args=[assessment.pk])
    page = text(client.get(find))
    assert "Issued for lot" in page and "Add 1 record(s)" in page
    response = client.post(find, {"expected_revision": fresh(assessment).revision})
    assert response.status_code == 302
    assert fresh(assessment).items.filter(kind="certificate").count() == 1


def test_the_list_filters_and_the_dashboard_counts_open_assessments(client, world):
    people = world["people"]
    open_one = begin(world, title="Open synthetic problem")
    closed = begin(world, cause="other", equipment=None, title="Closed synthetic problem")
    from tests.test_impact_assessment import conclude

    conclude(world, closed)
    client.force_login(people["reviewer"])
    listing = text(client.get(reverse("impact:list")))
    assert open_one.label in listing and closed.label in listing
    filtered = text(client.get(reverse("impact:list") + "?status=open"))
    assert open_one.label in filtered and closed.label not in filtered
    searched = text(client.get(reverse("impact:list") + f"?q={closed.label}"))
    assert closed.label in searched and open_one.label not in searched
    (gate,) = [q for q in dashboard.gates() if q.label == "Impact assessments open"]
    assert gate.count == 1 and gate.url.endswith("?status=open")


def test_withdrawal_page_waits_for_the_hold(client, world):
    people = world["people"]
    assessment = begin(world)
    lot_item = assessment.items.get(kind=Item.Kind.LOT)
    client.force_login(people["author"])
    client.post(
        reverse("impact:hold", args=[lot_item.pk]),
        {"expected_revision": lot_item.revision, "reason": "Synthetic hold"},
    )
    response = client.get(reverse("impact:withdraw", args=[assessment.pk]))
    assert response.status_code == 403 and "is active" in text(response)
