"""HTTP behaviour for stability pages: queues, filters, role boundaries and signing."""

import pytest
from django.urls import reverse

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
