from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from core.models import AuditEvent, AuditReview
from core.services import review_audit

pytestmark = pytest.mark.django_db


@pytest.fixture
def audit_data(client, django_user_model):
    reviewer = django_user_model.objects.create_user("audit-reviewer")
    reviewer.groups.add(Group.objects.get_or_create(name="auditor")[0])
    author = django_user_model.objects.create_user("record-author")
    outsider = django_user_model.objects.create_user("outsider")
    events = [
        AuditEvent.objects.create(
            actor=author,
            action="result.recorded",
            object_type="quality.result",
            object_id=str(index),
            reason=f"Observation {index}",
            after={"value": index},
        )
        for index in range(55)
    ]
    own = AuditEvent.objects.create(
        actor=reviewer,
        action="pin.changed",
        object_type="accounts.user",
        object_id=str(reviewer.pk),
        reason="Self credential event",
    )
    client.force_login(reviewer)
    return reviewer, author, outsider, events, own


def test_filters_dates_pagination_and_export_scope(client, audit_data):
    _, author, _, events, _ = audit_data
    today = timezone.localdate().isoformat()
    query = {
        "actor": author.pk,
        "action": "result.recorded",
        "date_from": today,
        "date_to": today,
        "object_type": "quality.result",
    }
    response = client.get("/audit/", query)
    assert response.status_code == 200
    assert response.context["page"].paginator.count == 55
    body = response.content.decode()
    assert "Next" in body
    assert "date_from=" in body and "action=result.recorded" in body
    response = client.get("/audit/", {**query, "page": 2})
    assert len(response.context["page"]) == 5
    response = client.get("/audit/", {**query, "object_id": events[0].object_id, "export": "csv"})
    assert response["Content-Type"] == "text/csv"
    assert str(events[0].pk) in response.content.decode()
    assert str(events[1].pk) not in response.content.decode()
    future = (timezone.localdate() + timedelta(days=1)).isoformat()
    response = client.get("/audit/", {"date_from": future})
    assert response.context["page"].paginator.count == 0


def test_precise_selection_records_history_and_preserves_filters(client, audit_data):
    reviewer, author, _, events, _ = audit_data
    selected = events[-1]
    query = f"?actor={author.pk}&action=result.recorded&page=1"
    response = client.post(
        "/audit/" + query,
        {
            "events": [str(selected.pk)],
            "conclusion": "Checked source and corrected values.",
        },
    )
    assert response.status_code == 302
    assert "actor=" in response.url and "action=result.recorded" in response.url
    review = AuditReview.objects.get()
    assert list(review.events.all()) == [selected]
    assert review.reviewer == reviewer
    response = client.get(response.url)
    assert b"Reviewed" in response.content
    assert b"Checked source and corrected values." in response.content
    review_audit(actor=reviewer, event_ids=[str(selected.pk)], conclusion="Follow-up completed.")
    response = client.get("/audit/" + query)
    assert b"Follow-up completed." in response.content
    assert b"Checked source and corrected values." in response.content


@pytest.mark.parametrize("kind", ["own", "invalid", "missing", "off_page", "duplicate", "empty"])
def test_invalid_selection_preserves_conclusion_without_500(client, audit_data, kind):
    _, _, _, events, own = audit_data
    choices = {
        "own": [str(own.pk)],
        "invalid": ["not-a-uuid"],
        "missing": [str(uuid4())],
        "off_page": [str(events[0].pk)],
        "duplicate": [str(events[-1].pk)] * 2,
        "empty": [],
    }
    response = client.post(
        "/audit/",
        {
            "events": choices[kind],
            "conclusion": "Keep this review narrative.",
        },
    )
    assert response.status_code == 422
    assert b"Keep this review narrative." in response.content
    assert not AuditReview.objects.exists()
    assert b"Your own event cannot be reviewed" in response.content


def test_invalid_filters_and_denied_users(client, audit_data):
    _, _, outsider, events, _ = audit_data
    for query in [
        {"date_from": "invalid"},
        {"actor": "invalid"},
        {"date_from": "2026-11-11", "date_to": "2026-11-10"},
        {"action": "unknown", "export": "csv"},
    ]:
        response = client.get("/audit/", query)
        assert response.status_code == 422
        assert response["Content-Type"].startswith("text/html")
    client.force_login(outsider)
    assert client.get("/audit/").status_code == 403
    response = client.post("/audit/", {"events": [str(events[-1].pk)], "conclusion": "No"})
    assert response.status_code == 403
    assert not AuditReview.objects.exists()


def test_filters_limit_post_selection(client, audit_data):
    _, _, _, events, _ = audit_data
    response = client.post(
        "/audit/?action=pin.changed",
        {
            "events": [str(events[-1].pk)],
            "conclusion": "Do not accept hidden event.",
        },
    )
    assert response.status_code == 422
    assert not AuditReview.objects.exists()
