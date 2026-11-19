"""Reminders of qualifications that reach their last valid day: the window, renewals that follow,
revoked, expired and future qualifications, instruments as well as people, and the page."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from laboratory import services
from laboratory.tests.helpers import PIN, make_equipment
from planning import reminders

from .conftest import login

pytestmark = pytest.mark.django_db(transaction=True)


def qualify(
    people,
    *,
    user=None,
    equipment=None,
    activity="HPLC-ASSAY",
    work="perform",
    approve=True,
    **dates,
):
    today = timezone.localdate()
    values = {
        "valid_from": today - timedelta(days=100),
        "valid_until": today + timedelta(days=10),
        **dates,
    }
    record = services.record_qualification(
        actor=people["reviewer"],
        user=user,
        equipment=equipment,
        activity=activity,
        evidence_ref="QUAL-SYN",
        reason="Synthetic evidence",
        **({"work": work} if user else {}),
        **values,
    )
    if not approve:
        return record
    return services.approve_qualification(
        actor=people["quality"],
        pin=PIN,
        qualification=record,
        expected_revision=record.revision,
        reason="Independent approval",
    )


def labels(today, within=30):
    return [r.label for r in reminders.reminders(today, within, "qualification")]


def test_a_qualification_reaching_its_last_valid_day_in_the_window_is_reminded(people):
    today = timezone.localdate()
    soon = qualify(people, user=people["analyst"])
    last_day = qualify(people, user=people["analyst2"], valid_until=today)
    far = qualify(people, user=people["analyst"], activity="GC", valid_until=today + timedelta(60))
    found = {r.label: r for r in reminders.reminders(today, 30)}
    assert found[f"QUAL-{soon.pk} · HPLC-ASSAY"].status == "Expires in 10 days"
    assert found[f"QUAL-{soon.pk} · HPLC-ASSAY"].tone == "neutral"
    assert found[f"QUAL-{last_day.pk} · HPLC-ASSAY"].status == "Last valid day today"
    assert found[f"QUAL-{last_day.pk} · HPLC-ASSAY"].tone == "warning"
    assert found[f"QUAL-{soon.pk} · HPLC-ASSAY"].href == reverse(
        "laboratory:qualification_detail", args=[soon.pk]
    )
    assert "performing the work" in found[f"QUAL-{soon.pk} · HPLC-ASSAY"].detail
    assert f"QUAL-{far.pk} · GC" not in found
    assert f"QUAL-{far.pk} · GC" in labels(today, within=60)


def test_an_approved_renewal_that_takes_over_removes_the_reminder(people):
    today = timezone.localdate()
    ending = qualify(people, user=people["analyst"])
    assert labels(today) == [f"QUAL-{ending.pk} · HPLC-ASSAY"]
    # A renewal awaiting approval does not count, nor one that leaves a gap.
    qualify(
        people,
        user=people["analyst"],
        valid_from=today + timedelta(days=11),
        valid_until=today + timedelta(days=400),
        approve=False,
    )
    gap = qualify(
        people,
        user=people["analyst"],
        valid_from=today + timedelta(days=12),
        valid_until=today + timedelta(days=400),
    )
    assert labels(today) == [f"QUAL-{ending.pk} · HPLC-ASSAY"]
    # Another person's or another work's renewal does not count either.
    qualify(people, user=people["analyst2"], valid_until=today + timedelta(days=400))
    qualify(people, user=people["analyst"], work="review", valid_until=today + timedelta(400))
    assert f"QUAL-{ending.pk} · HPLC-ASSAY" in labels(today)
    # Revoking the gapped one changes nothing; an approved renewal from the next day does.
    services.revoke_qualification(
        actor=people["quality"],
        pin=PIN,
        qualification=gap,
        expected_revision=gap.revision,
        reason="Recorded with the wrong dates",
    )
    qualify(
        people,
        user=people["analyst"],
        activity="hplc-assay",
        valid_from=today + timedelta(days=11),
        valid_until=today + timedelta(days=400),
    )
    assert f"QUAL-{ending.pk} · HPLC-ASSAY" not in labels(today)


def test_revoked_expired_and_future_qualifications_are_not_reminded(people):
    today = timezone.localdate()
    revoked = qualify(people, user=people["analyst"])
    services.revoke_qualification(
        actor=people["quality"],
        pin=PIN,
        qualification=revoked,
        expected_revision=revoked.revision,
        reason="Withdrawn",
    )
    old = qualify(people, user=people["analyst"], activity="OLD")
    qualify(
        people,
        user=people["analyst"],
        activity="LATER",
        valid_from=today + timedelta(days=1),
        valid_until=today + timedelta(days=5),
    )
    qualify(people, user=people["analyst2"], activity="WAITING", approve=False)
    assert labels(today) == [f"QUAL-{old.pk} · OLD"]
    # Once past its last valid day it is expired, not reminded of (the list shows it).
    assert labels(today + timedelta(days=11), within=90) == []


def test_an_instruments_qualification_and_its_renewal(people):
    today = timezone.localdate()
    balance = make_equipment(people, "SYN-REM-QUAL", ready=False)
    other = make_equipment(people, "SYN-REM-QUAL-2", ready=False)
    ending = qualify(people, equipment=balance, activity="PQ")
    reminder = next(r for r in reminders.reminders(today, 30) if r.kind == "qualification")
    assert reminder.label == f"QUAL-{ending.pk} · PQ"
    assert reminder.detail.startswith("SYN-REM-QUAL, intended use")
    qualify(people, equipment=other, activity="PQ", valid_until=today + timedelta(days=400))
    assert labels(today) == [f"QUAL-{ending.pk} · PQ"]
    qualify(people, equipment=balance, activity="PQ", valid_until=today + timedelta(days=400))
    assert labels(today) == []


def test_the_reminders_page_lists_and_filters_qualifications(client, people):
    soon = qualify(people, user=people["analyst"])
    login(client, people["auditor"])
    response = client.get(reverse("planning:reminders"), {"kind": "qualification"})
    assert response.status_code == 200
    rows = list(response.context["page_obj"])
    assert [(r.kind_label, r.label) for r in rows] == [
        ("Qualification", f"QUAL-{soon.pk} · HPLC-ASSAY")
    ]
    html = response.content.decode()
    assert reverse("laboratory:qualification_detail", args=[soon.pk]) in html
    assert "qualifications of people and instruments" in html
    response = client.get(reverse("planning:reminders"), {"kind": "reagent"})
    assert not [r for r in response.context["page_obj"] if r.kind == "qualification"]


def test_people_no_longer_active_and_equipment_out_of_service_are_not_reminded_of(people):
    today = timezone.localdate()
    leaving = qualify(people, user=people["analyst2"])
    stopped = make_equipment(people, "SYN-REM-STOPPED", ready=False)
    instrument = qualify(people, equipment=stopped, activity="PQ")
    assert set(labels(today)) == {f"QUAL-{leaving.pk} · HPLC-ASSAY", f"QUAL-{instrument.pk} · PQ"}
    people["analyst2"].is_active = False
    people["analyst2"].save()
    services.take_out_of_service(actor=people["analyst"], equipment=stopped, reason="Drift")
    assert labels(today) == []
