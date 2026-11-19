"""Proficiency testing pages: the list and its filters, planning through the form, recording
results and the report, signing the review and closing the follow-up through the web forms, what
each role is offered, the method page, the methods list and the reminders. Synthetic data."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog import proficiency
from catalog.models import ProficiencyParticipation
from core.models import ElectronicSignature

from .factories import PIN, method_revision, person
from .test_proficiency import follow_up, plan, ready, report, result, review

pytestmark = pytest.mark.django_db(transaction=True)


def login(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def method(people):
    return method_revision(people["author"]).method


def detail(item):
    return reverse("catalog:proficiency_detail", args=[item.pk])


def signing(item, **overrides):
    item.refresh_from_db()
    data = {
        "reason": "Outcome reviewed",
        "pin": PIN,
        "expected_revision": item.revision,
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("role", ["analyst", "reviewer", "author", "admin", "auditor"])
def test_every_laboratory_role_reads_the_list_and_the_record(client, people, method, role):
    item = plan(people["author"], method)
    login(client, people[role])
    listed = client.get(reverse("catalog:proficiency_list"))
    assert listed.status_code == 200 and item.identifier in listed.text
    assert ("New participation" in listed.text) == (role == "author")
    page = client.get(detail(item))
    assert page.status_code == 200 and "Synthetic PT Provider" in page.text


def test_the_list_filters_by_state(client, people, method):
    today = timezone.localdate()
    planned = plan(people["author"], method, round_ref="Round A")
    overdue = plan(people["author"], method, round_ref="Round B", results_due=today - timedelta(1))
    waiting = plan(people["author"], method, round_ref="Round C")
    report(people["analyst"], waiting)
    login(client, people["reviewer"])
    url = reverse("catalog:proficiency_list")
    for status, wanted in (
        ("planned", planned),
        ("overdue", overdue),
        ("reported", waiting),
    ):
        text = client.get(url, {"status": status}).text
        others = {planned, overdue, waiting} - {wanted}
        assert wanted.identifier in text
        assert all(f">{other.identifier}<" not in text for other in others), status


def test_quality_plans_through_the_form(client, people, method):
    login(client, people["author"])
    url = reverse("catalog:proficiency_new")
    assert client.get(url, {"method": method.pk}).status_code == 200
    data = {
        "method": method.pk,
        "kind": "comparison",
        "provider": "Synthetic Laboratory B",
        "provider_accreditation": "",
        "scheme": "",
        "round_ref": "Bilateral 2026",
        "test_item": "Split sample of a synthetic lot",
        "results_due": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "reason": "Annual plan",
    }
    response = client.post(url, data)
    item = ProficiencyParticipation.objects.get()
    assert response.status_code == 302 and response.url == detail(item)
    assert item.kind == "comparison" and item.planned_by == people["author"]


@pytest.mark.parametrize("role", ["analyst", "reviewer", "admin", "auditor"])
def test_others_cannot_open_the_plan_form(client, people, role):
    login(client, people[role])
    assert client.get(reverse("catalog:proficiency_new")).status_code == 403


def test_a_result_is_recorded_through_the_form(client, people, method):
    item = plan(people["author"], method)
    login(client, people["analyst"])
    url = reverse("catalog:proficiency_result_new", args=[item.pk])
    data = {
        "expected_revision": item.revision,
        "measurand": "Synthetic API assay",
        "unit": "%",
        "reported_value": "101.9",
        "assigned_value": "99.0",
        "score_kind": "z",
        "score": "2.6",
        "outcome": "",
        "performed_by": people["analyst"].pk,
        "note": "",
        "reason": "From the report",
    }
    refused = client.post(url, {**data, "outcome": "satisfactory"})
    assert refused.status_code == 422 and "follows from the score" in refused.text
    response = client.post(url, data)
    assert response.status_code == 302
    line = item.results.get()
    assert line.outcome == "questionable"
    page = client.get(detail(item))
    assert "z = 2.6" in page.text and "Questionable" in page.text


def test_the_review_is_signed_through_the_form(client, people, method):
    item = ready(people, method, score="-3.2")
    url = reverse("catalog:proficiency_review", args=[item.pk])
    login(client, people["analyst"])
    assert client.get(url).status_code == 403
    login(client, people["approver"])
    page = client.get(url)
    assert page.status_code == 200 and "Unsatisfactory" in page.text
    refused = client.post(
        url,
        signing(item, conclusion="Bias", signature_username="qa-approver", follow_up=""),
    )
    assert refused.status_code == 422 and "corrective follow-up" in refused.text
    done = client.post(
        url,
        signing(item, conclusion="Bias", signature_username="qa-approver", follow_up="on"),
    )
    assert done.status_code == 302
    item.refresh_from_db()
    assert item.state == "follow_up" and item.outcome == "unsatisfactory"


def test_a_data_author_is_told_before_any_pin(client, people, method):
    dual = people["dual"]
    item = plan(people["author"], method)
    result(dual, item, people["analyst"])
    report(people["analyst"], item)
    login(client, dual)
    page = client.get(detail(item))
    assert proficiency.INDEPENDENT in page.text
    assert reverse("catalog:proficiency_review", args=[item.pk]) not in page.text
    signing_page = client.get(reverse("catalog:proficiency_review", args=[item.pk]))
    assert signing_page.status_code == 403 and 'name="pin"' not in signing_page.text


def test_the_record_offers_each_role_its_next_step(client, people, method):
    item = ready(people, method)
    review_url = reverse("catalog:proficiency_review", args=[item.pk])
    login(client, people["analyst"])
    text = client.get(detail(item)).text
    assert "Record result" in text and review_url not in text
    login(client, people["approver"])
    text = client.get(detail(item)).text
    assert review_url in text and "Change plan" in text
    login(client, people["auditor"])
    text = client.get(detail(item)).text
    assert "Record result" not in text and review_url not in text


def test_follow_up_and_closure_through_the_forms(client, people, method):
    closer = person("qa-closer", "quality")
    item = review(people["approver"], ready(people, method, score="3.3"), follow_up=True)
    login(client, people["approver"])
    url = reverse("catalog:proficiency_follow_up", args=[item.pk])
    data = {
        "expected_revision": item.revision,
        "cause": "Shoulder peak",
        "actions": "Integration revised",
        "reported_results": "None affected",
        "impact_assessment": "",
        "quality_reference": "CAPA-SYN-1",
        "effectiveness": "Repeat z = 0.3",
        "reason": "Follow-up",
    }
    assert client.post(url, data).status_code == 302
    close_url = reverse("catalog:proficiency_close", args=[item.pk])
    assert client.get(close_url).status_code == 403
    login(client, closer)
    assert client.get(detail(item)).text.count(close_url) >= 1
    done = client.post(close_url, signing(item, signature_username="qa-closer"))
    assert done.status_code == 302
    item.refresh_from_db()
    assert item.state == "closed"
    assert ElectronicSignature.objects.filter(meaning="closed", signer=closer).exists()


def test_a_closed_participation_offers_no_change(client, people, method):
    item = review(people["approver"], ready(people, method))
    login(client, people["analyst"])
    response = client.get(reverse("catalog:proficiency_result_new", args=[item.pk]))
    assert response.status_code == 302 and response.url == detail(item)
    login(client, people["author"])
    text = client.get(detail(item)).text
    assert "Change plan" not in text and "Satisfactory" in text


def test_cancel_through_the_form(client, people, method):
    item = plan(people["author"], method)
    login(client, people["approver"])
    url = reverse("catalog:proficiency_cancel", args=[item.pk])
    response = client.post(url, {"expected_revision": item.revision, "reason": "No round"})
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.state == "cancelled"


def test_method_page_and_methods_list_show_the_plan(client, people, method):
    done = review(people["approver"], ready(people, method, score="2.2"))
    planned = plan(people["author"], method, round_ref="Round 2027-1")
    login(client, people["reviewer"])
    page = client.get(reverse("catalog:method", args=[method.pk]))
    assert done.identifier in page.text and planned.identifier in page.text
    listed = client.get(reverse("catalog:methods"))
    assert "Questionable" in listed.text
    assert "Next due" in listed.text and planned.results_due.isoformat() in listed.text


def test_reminders_list_results_due_and_overdue(client, people, method):
    today = timezone.localdate()
    soon = plan(people["author"], method, round_ref="Soon", results_due=today + timedelta(5))
    late = plan(people["author"], method, round_ref="Late", results_due=today - timedelta(2))
    later = plan(people["author"], method, round_ref="Later", results_due=today + timedelta(200))
    reported = plan(people["author"], method, round_ref="Sent", results_due=today)
    report(people["analyst"], reported)
    follow = review(people["approver"], ready(people, method, score="3.1"), follow_up=True)
    follow_up(people["approver"], follow)
    login(client, people["analyst"])
    text = client.get(reverse("planning:reminders"), {"kind": "proficiency"}).text
    assert soon.identifier in text and late.identifier in text
    assert "Overdue by 2 days" in text and "Due in 5 days" in text
    for absent in (later, reported, follow):
        assert f"{absent.identifier} ·" not in text


def test_a_method_page_lists_its_own_participations_only(client, people, method):
    other = method_revision(people["author"], code="hplc-assay-2").method
    mine = plan(people["author"], method, round_ref="Mine")
    theirs = plan(people["author"], other, round_ref="Theirs")
    login(client, people["auditor"])
    page = client.get(reverse("catalog:method", args=[method.pk])).text
    assert f"{reverse('catalog:proficiency_list')}?method={method.pk}" in page
    text = client.get(reverse("catalog:proficiency_list"), {"method": method.pk}).text
    assert f">{mine.identifier}<" in text and f">{theirs.identifier}<" not in text
    # The text search matches codes that contain it; the method filter does not.
    searched = client.get(reverse("catalog:proficiency_list"), {"q": method.code}).text
    assert f">{theirs.identifier}<" in searched
