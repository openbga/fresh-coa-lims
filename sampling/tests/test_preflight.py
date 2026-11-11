"""Action pages explain why they cannot be used on GET; role checks precede record lookups."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from catalog.tests.factories import method_revision
from quality.models import Lot
from sampling import services

from .test_gate import assess, short
from .test_services import assign, plan_revision, ready, sample  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
MISSING = 987654


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


@pytest.mark.parametrize(
    "name",
    [
        "catalog:specification_approve",
        "catalog:specification_withdraw",
        "catalog:method_approve",
        "catalog:method_withdraw",
        "sampling:plan_approve",
        "sampling:plan_withdraw",
    ],
)
def test_role_checked_before_lookup(client, people, name):
    existing = method_revision(people["author"]).pk
    for role in ("analyst", "reviewer", "admin", "auditor"):
        client.force_login(people[role])
        for pk in (existing, MISSING):
            assert client.get(reverse(name, args=[pk])).status_code == 403, (role, pk)
            assert client.post(reverse(name, args=[pk]), {}).status_code == 403, (role, pk)
    client.force_login(people["approver"])
    assert client.get(reverse(name, args=[MISSING])).status_code == 404


def test_sampling_new_prechecks_state_and_holds(client, people, ready):  # noqa: F811
    client.force_login(people["analyst"])
    url = reverse("sampling:sampling_new", args=[ready["lot"].pk])
    response = client.get(url)
    assert response.status_code == 302
    assert messages_of(response) == ["Assign approved requirements before recording sampling."]
    assign(people, ready, scope="eu-market")
    response = client.get(url)
    assert response.status_code == 302
    assert messages_of(response)[-1].startswith("Applicability hold: No specification exists")
    assign(people, ready)
    assert client.get(url).status_code == 200
    Lot.objects.filter(pk=ready["lot"].pk).update(state="released")
    response = client.get(url)
    assert response.status_code == 302
    assert messages_of(response)[-1] == "Only quarantined lots accept new samples."
    assert services.sampling_blocker(Lot.objects.get(pk=ready["lot"].pk))
    body = client.get(reverse("sampling:lot", args=[ready["lot"].pk])).content.decode()
    assert url not in body


def test_correction_and_assessment_prechecks(client, people, ready):  # noqa: F811
    assign(people, ready)
    record = short(people, ready)
    assess(people, record)
    client.force_login(people["approver"])
    response = client.get(reverse("sampling:deviation_assess", args=[record.pk]))
    assert response.status_code == 302
    assert messages_of(response) == ["This deviation has already been assessed."]
    client.force_login(people["analyst"])
    correct = reverse("sampling:sampling_correct", args=[record.pk])
    assert client.get(correct).status_code == 200
    Lot.objects.filter(pk=ready["lot"].pk).update(state="released")
    response = client.get(correct)
    assert response.status_code == 302
    assert messages_of(response) == ["Sampling for a dispositioned lot cannot be corrected here."]


def test_assessment_of_corrected_record_redirects(client, people, ready):  # noqa: F811
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    assign(people, ready)
    record = short(people, ready)
    services.correct_sampling(
        actor=people["analyst"],
        record=record,
        reason="Fix",
        sampled_at=timezone.now() - timedelta(minutes=1),
        containers_total=9,
        containers_sampled=4,
        container_ids="C1, C2, C3, C4",
        quantity=Decimal("60"),
        quantity_unit="g",
        location="Booth",
    )
    client.force_login(people["approver"])
    response = client.get(reverse("sampling:deviation_assess", args=[record.pk]))
    assert response.status_code == 302
    assert messages_of(response) == ["This record was corrected; assess the latest record instead."]
    response = client.get(reverse("sampling:sampling_correct", args=[record.pk]))
    assert response.status_code == 403  # quality is not an analyst: role first
    client.force_login(people["analyst"])
    response = client.get(reverse("sampling:sampling_correct", args=[record.pk]))
    assert messages_of(response) == [
        "This record was already corrected. Correct the latest record."
    ]


def test_sampling_new_uses_one_assignment_snapshot(client, people, ready, monkeypatch):  # noqa: F811
    """Regression: a reassignment to HOLD between the check and the form must not 500."""
    assign(people, ready)
    client.force_login(people["analyst"])
    url = reverse("sampling:sampling_new", args=[ready["lot"].pk])
    real = services.current_assignment
    calls = []

    def racing(lot):
        snapshot = real(lot)
        first = not calls
        calls.append(snapshot)
        if first:
            # After the page's first read, another user reassigns the lot to a hold.
            services.assign_requirements(
                actor=people["author"],
                lot=lot,
                material=ready["material"],
                stage="incoming",
                scope="eu-market",
                reason="Concurrent change",
            )
        return snapshot

    monkeypatch.setattr(services, "current_assignment", racing)
    response = client.get(url)
    assert response.status_code == 200  # rendered from the ready snapshot, no crash
    assert len(calls) == 2  # the page's single read + the concurrent reassignment's own read
    monkeypatch.setattr(services, "current_assignment", real)
    response = client.get(url)  # the next request sees the hold and redirects
    assert response.status_code == 302
    assert messages_of(response)[-1].startswith("Applicability hold:")
    post = client.post(url, {"reference": "SYN-RACE", "reason": "x"})
    assert post.status_code == 302  # current hold redirects before any form or write
    assert not services.SamplingRecord.objects.exists()
