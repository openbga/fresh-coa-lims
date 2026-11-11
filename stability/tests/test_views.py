"""HTTP behaviour for stability pages: queues, filters, role boundaries and signing."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from core.models import AuditEvent
from stability import services
from stability.models import Hold, Pull

from .helpers import PIN, approved_protocol, make_lot, started_study

pytestmark = pytest.mark.django_db(transaction=True)


def sign_post(client, url, user, revision, **extra):
    data = {
        "signature_username": user.username,
        "expected_revision": revision,
        "pin": PIN,
        "reason": "Checked",
    }
    data.update(extra)
    return client.post(url, data)


def test_pull_queue_filters_match_window_boundaries(client, people):
    study = started_study(people)  # pulls due at day 30 (overdue), 100 (due now), 180 (upcoming)
    client.force_login(people["analyst"])
    url = reverse("stability:pull_list")
    expected = {"overdue": "30 days", "due": "100 days", "upcoming": "180 days"}
    for key, label in expected.items():
        body = client.get(url, {"status": key}).content.decode()
        assert label in body, key
        for other_key, other in expected.items():
            if other_key != key:
                assert other not in body, (key, other)
        assert "Showing <strong>1–1</strong>" in body
    assert study.pulls.count() == 3
    assert client.get(url, {"status": "bogus"}).status_code == 200
    assert client.get(url, {"sort": "-due"}).status_code == 200


def test_overview_counts_and_role_boundaries(client, people):
    started_study(people)
    client.force_login(people["auditor"])
    html = client.get(reverse("stability:overview")).content.decode()
    assert "Pulls overdue" in html and "?status=overdue" in html
    for name in ("protocol_new", "study_new", "reserve_new", "hold_new"):
        assert client.get(reverse(f"stability:{name}")).status_code == 403, name
    client.force_login(people["admin"])
    assert client.get(reverse("stability:study_list")).status_code == 200
    assert client.get(reverse("stability:hold_new")).status_code == 403


def test_empty_and_filtered_empty_states(client, people):
    client.force_login(people["quality"])
    url = reverse("stability:protocol_list")
    assert "No records yet" in client.get(url).content.decode()
    approved_protocol(people)
    assert "Nothing matches these filters" in client.get(url, {"q": "zzz"}).content.decode()


def test_protocol_approval_page_flow(client, people):
    protocol = services.create_protocol(
        actor=people["analyst"],
        code="P1",
        title="T",
        product="X",
        document_ref="D",
        document_url="",
        test_profile_ref="",
        basis="B",
        reason="Draft",
    )
    condition = services.add_condition(
        actor=people["analyst"],
        protocol=protocol,
        label="C",
        setpoint="S",
        temperature_c=None,
        humidity_pct=None,
        reason="Add",
    )
    services.add_timepoint(
        actor=people["analyst"],
        protocol=protocol,
        condition=condition,
        label="1m",
        interval_days=30,
        window_days=2,
        test_codes=["assay"],
        reason="Add",
    )
    protocol.refresh_from_db()
    url = reverse("stability:protocol_approve", args=[protocol.pk])
    people["analyst"].groups.add(people["quality"].groups.get())
    client.force_login(people["analyst"])
    denied = client.get(url)
    assert denied.status_code == 403 and 'type="password"' not in denied.content.decode()
    client.force_login(people["quality"])
    page = client.get(url).content.decode()
    assert "Sign and approve" in page and "Signature PIN" in page and "Signing username" in page
    wrong = sign_post(client, url, people["quality"], protocol.revision, signature_username="other")
    assert wrong.status_code == 422
    bad_pin = sign_post(client, url, people["quality"], protocol.revision, pin="11111111")
    assert bad_pin.status_code == 422 and "11111111" not in bad_pin.content.decode()
    ok = sign_post(client, url, people["quality"], protocol.revision)
    assert ok.status_code == 302
    detail = client.get(reverse("stability:protocol_detail", args=[protocol.pk])).content.decode()
    assert "Approved" in detail and "Signatures" in detail and "approved" in detail


def test_hold_flow_and_release_denials(client, people):
    lot = make_lot(people)
    client.force_login(people["reviewer"])
    url = reverse("stability:hold_new")
    bad = client.post(url, {"lot": lot.pk, "kind": "legal", "reason": ""})
    assert bad.status_code == 422
    created = client.post(url, {"lot": lot.pk, "kind": "legal", "reason": "Matter 7"})
    hold = Hold.objects.get()
    assert created.status_code == 302 and hold.placed_by == people["reviewer"]
    detail = reverse("stability:hold_detail", args=[hold.pk])
    assert "QC disposition and disposal" in client.get(detail).content.decode()
    release = reverse("stability:hold_release", args=[hold.pk])
    assert client.get(release).status_code == 403  # reviewers hold no quality authority
    people["reviewer"].groups.add(people["quality"].groups.get())
    placed_by_self = client.get(release)
    assert placed_by_self.status_code == 403 and "cannot release" in placed_by_self.content.decode()
    client.force_login(people["quality"])
    assert sign_post(client, release, people["quality"], hold.revision).status_code == 302
    hold.refresh_from_db()
    assert hold.state == "released"


def test_pull_recording_form_enforces_window_and_preserves_input(client, people):
    study = started_study(people)
    pull = study.pulls.get(timepoint__interval_days=30)
    client.force_login(people["analyst"])
    url = reverse("stability:pull_record", args=[pull.pk])
    data = {
        "pulled_on": pull.due_date.isoformat(),
        "quantity": "5",
        "quantity_unit": "g",
        "storage_location": "Synthetic shelf",
        "reason": "Pull",
    }
    from django.utils import timezone

    late = client.post(url, {**data, "pulled_on": timezone.localdate().isoformat()})
    assert late.status_code == 422
    assert "outside its window" in late.content.decode()
    assert 'value="Synthetic shelf"' in late.content.decode()
    assert client.post(url, data).status_code == 302
    pull.refresh_from_db()
    assert pull.state == Pull.State.PULLED


def test_reserve_and_obligation_pages(client, people):
    lot = make_lot(people)
    client.force_login(people["analyst"])
    created = client.post(
        reverse("stability:reserve_new"),
        {
            "identifier": "RES-9",
            "lot": lot.pk,
            "container_description": "Package",
            "storage_location": "Cabinet",
            "quantity": "25",
            "test_quantity": "10",
            "quantity_unit": "g",
            "minimum_multiple": "2",
            "retained_on": "2026-01-02",
            "reason": "Reserve",
        },
    )
    assert created.status_code == 302
    from stability.models import ReserveSample

    reserve = ReserveSample.objects.get()
    detail = reverse("stability:reserve_detail", args=[reserve.pk])
    page = client.get(detail).content.decode()
    assert "applicability is unresolved" in page and "Disposal readiness" in page
    add = client.post(
        reverse("stability:obligation_new") + f"?reserve={reserve.pk}",
        {
            "anchor_kind": "last_distribution",
            "offset_months": "24",
            "basis": "Basis",
            "reason": "Unknown anchor",
        },
    )
    assert add.status_code == 302
    assert "Set anchor" in client.get(detail).content.decode()


# --- Follow-up regressions -------------------------------------------------------------------


def test_chamber_choices_list_only_equipment_fit_now_and_the_save_still_checks(client, people):
    from laboratory.models import Equipment
    from laboratory.services import take_out_of_service
    from laboratory.tests.helpers import make_equipment

    study = started_study(people)
    pull = study.pulls.get(timepoint__interval_days=100)
    fit = make_equipment(people, "CH-FIT")
    make_equipment(people, "CH-UNCAL", ready=False)
    client.force_login(people["analyst"])
    url = reverse("stability:pull_record", args=[pull.pk])
    page = client.get(url).content.decode()
    assert "CH-FIT" in page and "CH-UNCAL" not in page
    data = {
        "pulled_on": timezone.localdate().isoformat(),
        "quantity": "5",
        "quantity_unit": "g",
        "storage_location": "Shelf",
        "chamber": fit.pk,
        "reason": "Pull",
    }
    # Fitness changes after the form was opened: the submitted choice is refused, nothing saved.
    take_out_of_service(actor=people["reviewer"], equipment=fit, reason="Drift found")
    assert Equipment.objects.get(pk=fit.pk).state == "out_of_service"
    refused = client.post(url, data)
    assert refused.status_code == 422
    pull.refresh_from_db()
    assert pull.state == Pull.State.SCHEDULED and pull.chamber_id is None


def test_condition_and_timepoint_pages_confirm_success(client, people):
    protocol = services.create_protocol(
        actor=people["analyst"],
        code="MSG",
        title="T",
        product="X",
        document_ref="D",
        document_url="",
        test_profile_ref="",
        basis="B",
        reason="Draft",
    )
    client.force_login(people["analyst"])
    added = client.post(
        reverse("stability:condition_new", args=[protocol.pk]),
        {"label": "Long-term", "setpoint": "S", "reason": "Add"},
        follow=True,
    )
    assert "Condition added to the draft protocol." in added.content.decode()
    condition = protocol.conditions.get()
    timepoint = client.post(
        reverse("stability:timepoint_new", args=[protocol.pk]),
        {
            "condition": condition.pk,
            "label": "1m",
            "interval_days": 30,
            "window_days": 2,
            "test_codes": "identity",
            "reason": "Add",
        },
        follow=True,
    )
    assert "Timepoint added to the draft protocol." in timepoint.content.decode()


def test_hold_on_a_released_lot_is_intentional_and_leaves_the_lot_row_untouched(client, people):
    from quality.models import Lot
    from stability import gates

    lot = make_lot(people)
    Lot.objects.filter(pk=lot.pk).update(state="released")
    released = Lot.objects.get(pk=lot.pk)
    client.force_login(people["quality"])
    created = client.post(
        reverse("stability:hold_new"),
        {
            "lot": lot.pk,
            "kind": "regulatory",
            "reference": "REV-1",
            "reason": "Post-release review",
        },
    )
    assert created.status_code == 302
    hold = Hold.objects.get()
    after = Lot.objects.get(pk=lot.pk)
    # The released lot (and the evidence frozen at release) is not rewritten by the hold.
    assert (after.state, after.revision) == (released.state, released.revision)
    assert gates.lot_blockers(after) and "Post-release review" in gates.lot_blockers(after)[0]
    assert gates.lot_hold_evidence(after)["holds"][0]["state"] == "active"
    page = client.get(reverse("stability:hold_detail", args=[hold.pk])).content.decode()
    assert "QC disposition and disposal" in page
    release = reverse("stability:hold_release", args=[hold.pk])
    people["quality2"].groups.add(people["quality"].groups.get())
    client.force_login(people["quality2"])
    assert sign_post(client, release, people["quality2"], hold.revision).status_code == 302
    final = Lot.objects.get(pk=lot.pk)
    assert (final.state, final.revision) == (released.state, released.revision)
    assert not gates.lot_blockers(final)


def test_time_zero_must_not_be_in_the_future_but_released_and_historical_lots_are_fine(
    client, people
):
    from django.db import DatabaseError, transaction

    from quality.models import Lot
    from stability.models import Study

    lot = make_lot(people)
    Lot.objects.filter(pk=lot.pk).update(state="released")
    released = Lot.objects.get(pk=lot.pk)
    protocol = approved_protocol(people)
    today = timezone.localdate()

    def start(identifier, start_date, lot_row=released):
        return services.start_study(
            actor=people["analyst"],
            identifier=identifier,
            protocol=protocol,
            lot=lot_row,
            container_closure=identifier,
            start_date=start_date,
            reason="Study start",
        )

    with pytest.raises(ValidationError, match="cannot be in the future"):
        start("STB-FUTURE", today + timedelta(days=1))
    assert not Study.objects.filter(identifier="STB-FUTURE").exists()
    assert not AuditEvent.objects.filter(action="study.started").exists()
    # Today and historical time zero (even before the lot reached the laboratory) are accepted,
    # on a released lot: neither lot state nor receipt date is compared.
    todays = start("STB-TODAY", today)
    historical = start("STB-HISTORY", today - timedelta(days=900))
    assert {p.due_date for p in todays.pulls.all()} == {
        today + timedelta(days=d) for d in (30, 100, 180)
    }
    assert historical.state == "active"
    for change in (
        lambda: Study.objects.filter(pk=todays.pk).update(start_date=today - timedelta(days=5)),
        lambda: todays.pulls.update(due_date=today),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            change()
    # The page gives the same feedback and keeps the other entries.
    client.force_login(people["analyst"])
    data = {
        "identifier": "STB-FORM",
        "protocol": protocol.pk,
        "lot": lot.pk,
        "container_closure": "Form container",
        "start_date": (today + timedelta(days=2)).isoformat(),
        "reason": "Planned",
    }
    refused = client.post(reverse("stability:study_new"), data)
    assert refused.status_code == 422
    body = refused.content.decode()
    assert "cannot be in the future" in body and 'value="Form container"' in body
    ok = client.post(reverse("stability:study_new"), {**data, "start_date": today.isoformat()})
    assert ok.status_code == 302 and Study.objects.filter(identifier="STB-FORM").exists()
