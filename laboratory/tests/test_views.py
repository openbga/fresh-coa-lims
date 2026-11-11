"""HTTP behaviour: role boundaries, list states, signing pages and refusals."""

import pytest
from django.urls import reverse

from laboratory import services
from laboratory.models import Calibration, Equipment, ReagentLot

from .helpers import (
    PIN,
    accept_new_calibration,
    make_equipment,
    make_reagent,
    make_sample,
    qualify_analyst,
)

pytestmark = pytest.mark.django_db(transaction=True)


def sign_post(client, url, user, revision, *, pin=PIN, username=None, reason="Checked"):
    return client.post(
        url,
        {
            "signature_username": username or user.username,
            "expected_revision": revision,
            "pin": pin,
            "reason": reason,
        },
    )


def test_pages_require_login_and_a_laboratory_role(client, people, django_user_model):
    url = reverse("laboratory:equipment_list")
    assert client.get(url).status_code == 302
    outsider = django_user_model.objects.create_user("outsider", password="password-for-tests")
    client.force_login(outsider)
    assert client.get(url).status_code == 403
    client.force_login(people["auditor"])
    assert client.get(url).status_code == 200
    for name in ("equipment_new", "reagent_new", "qualification_new", "use_new"):
        assert client.get(reverse(f"laboratory:{name}")).status_code == 403, name


def test_list_states_empty_filtered_and_invalid(client, people):
    client.force_login(people["analyst"])
    url = reverse("laboratory:equipment_list")
    page = client.get(url).content.decode()
    assert "No records yet" in page and "New equipment" in page
    make_equipment(people)
    assert "BAL-001" in client.get(url).content.decode()
    filtered = client.get(url, {"q": "nothing-matches"}).content.decode()
    assert "Nothing matches these filters" in filtered and "Clear filters" in filtered
    invalid = client.get(url, {"status": "bogus"})
    assert invalid.status_code == 200 and "cannot be applied" in invalid.content.decode()
    # Unknown sort keys fall back to the default instead of failing or ordering by user input.
    assert client.get(url, {"sort": "password; drop"}).status_code == 200
    assert client.get(url, {"sort": "-due", "per_page": "999"}).status_code == 200


def test_filters_run_over_the_whole_queryset(client, people):
    client.force_login(people["analyst"])
    for number in range(30):
        make_equipment(people, f"E-{number:02d}", ready=False)
    make_equipment(people, "E-READY")
    url = reverse("laboratory:equipment_list")
    body = client.get(url, {"status": "ready"}).content.decode()
    assert "E-READY" in body and "E-00" not in body
    assert "Showing <strong>1–1</strong>" in body
    second_page = client.get(url, {"page": 2}).content.decode()
    assert "E-" in second_page and "Page 2 of 2" in second_page


def test_create_equipment_validates_and_keeps_input(client, people):
    client.force_login(people["analyst"])
    url = reverse("laboratory:equipment_new")
    bad = client.post(url, {"asset_id": "BAL-9", "description": "", "category": "balance"})
    assert bad.status_code == 422
    assert 'value="BAL-9"' in bad.content.decode()
    ok = client.post(
        url,
        {
            "asset_id": "BAL-9",
            "description": "Synthetic",
            "category": "balance",
            "requires_qualification": "on",
            "reason": "Synthetic registration",
        },
    )
    assert ok.status_code == 302 and Equipment.objects.filter(asset_id="BAL-9").exists()
    duplicate = client.post(
        url, {"asset_id": "BAL-9", "description": "Again", "category": "balance", "reason": "Dup"}
    )
    assert duplicate.status_code == 422


def test_signing_page_flow_and_credential_failures(client, people):
    equipment = make_equipment(people, ready=False)
    calibration = accept_new_calibration(people, equipment, accept=False)
    url = reverse("laboratory:calibration_accept", args=[calibration.pk])
    client.force_login(people["reviewer"])
    page = client.get(url)
    assert page.status_code == 200
    html = page.content.decode()
    assert "Signature PIN" in html and "Sign and review" in html and PIN not in html
    assert "revision <strong>1</strong>" in html and "revision 2" in html

    wrong_identity = sign_post(client, url, people["reviewer"], 1, username="someone-else")
    assert wrong_identity.status_code == 422
    assert "own signing username" in wrong_identity.content.decode()
    bad_pin = sign_post(client, url, people["reviewer"], 1, pin="00000000")
    assert bad_pin.status_code == 422
    assert "00000000" not in bad_pin.content.decode()
    stale = sign_post(client, url, people["reviewer"], 7)
    assert stale.status_code == 422 and "Record changed" in stale.content.decode()
    calibration.refresh_from_db()
    assert calibration.state == "recorded"

    done = sign_post(client, url, people["reviewer"], 1)
    assert done.status_code == 302
    calibration.refresh_from_db()
    assert calibration.state == "accepted"
    detail = client.get(
        reverse("laboratory:equipment_detail", args=[equipment.pk])
    ).content.decode()
    assert "Signatures" in detail and "Reviewed" in detail and "History" in detail


def test_self_acceptance_is_denied_without_a_pin_control(client, people):
    equipment = make_equipment(people, ready=False)
    calibration = accept_new_calibration(people, equipment, accept=False)
    people["analyst"].groups.add(people["reviewer"].groups.get())
    client.force_login(people["analyst"])
    url = reverse("laboratory:calibration_accept", args=[calibration.pk])
    denied = client.get(url)
    assert denied.status_code == 403
    html = denied.content.decode()
    assert "cannot accept it" in html and 'type="password"' not in html
    assert sign_post(client, url, people["analyst"], 1).status_code == 403
    calibration.refresh_from_db()
    assert calibration.state == "recorded"


def test_admin_has_no_scientific_authority(client, people):
    equipment = make_equipment(people, ready=False)
    calibration = accept_new_calibration(people, equipment, accept=False)
    client.force_login(people["admin"])
    assert client.get(reverse("laboratory:equipment_list")).status_code == 200
    assert (
        client.get(reverse("laboratory:calibration_accept", args=[calibration.pk])).status_code
        == 403
    )
    assert client.get(reverse("laboratory:equipment_new")).status_code == 403


def test_failed_calibration_message_and_out_of_service_notice(client, people):
    equipment = make_equipment(people)
    client.force_login(people["analyst"])
    response = client.post(
        reverse("laboratory:calibration_new", args=[equipment.pk]),
        {
            "performed_at": "2024-01-02T09:30",
            "due_date": "2099-01-01",
            "outcome": "fail",
            "standard_ref": "CERT",
            "reason": "Out of tolerance",
        },
        follow=True,
    )
    assert "impact assessment" in response.content.decode()
    assert "Out of service" in response.content.decode()
    equipment.refresh_from_db()
    assert equipment.state == "out_of_service"
    assert Calibration.objects.filter(outcome="fail").count() == 1


def test_use_form_blocks_ineligible_and_records_eligible(client, people):
    from quality.models import Sample

    sample = make_sample(people)
    equipment = make_equipment(people)
    reagent = make_reagent(people)
    client.force_login(people["analyst"])
    url = reverse("laboratory:use_new")
    data = {
        "sample_reference": sample.reference,
        "activity": "HPLC-ASSAY",
        "test_code": "assay",
        "equipment": [equipment.pk],
        "reagents": [reagent.pk],
        "reason": "Assay run",
    }
    blocked = client.post(url, data)
    assert blocked.status_code == 422
    assert (
        "Work is blocked" in blocked.content.decode()
        and "qualification" in blocked.content.decode()
    )
    qualify_analyst(people, people["analyst"])
    ok = client.post(url, data)
    assert ok.status_code == 302
    listing = client.get(reverse("laboratory:use_list")).content.decode()
    assert "BAL-001" in listing and "RG-001" in listing
    assert Sample.objects.get() == sample
    missing = client.post(url, {**data, "sample_reference": "NOPE"})
    assert missing.status_code == 422 and "No sample" in missing.content.decode()


def test_overview_counts_link_to_filtered_lists(client, people):
    make_equipment(people)
    stopped = make_equipment(people, "BAL-002")
    services.take_out_of_service(actor=people["analyst"], equipment=stopped, reason="Drift")
    make_reagent(people, release=False)
    client.force_login(people["quality"])
    response = client.get(reverse("laboratory:overview"))
    queues = {queue["label"]: queue for queue in response.context["queues"]}
    awaiting = queues["Reagent lots awaiting release"]
    assert awaiting["count"] == ReagentLot.objects.filter(state="received").count() == 1
    assert awaiting["href"].endswith("?status=received") and awaiting["tone"] == "info"
    assert queues["Equipment out of service"]["count"] == 1
    assert queues["Calibrations awaiting acceptance"]["count"] == 0
    assert queues["Calibrations awaiting acceptance"]["tone"] == "neutral"
    # Each count matches the filtered list it links to.
    for queue in queues.values():
        listed = client.get(queue["href"]).context["page_obj"].paginator.count
        assert listed == queue["count"], queue["label"]


def test_return_to_service_refuses_a_failure_recorded_after_the_page_opened(client, people):
    import re
    from datetime import timedelta

    from django.utils import timezone

    from core.models import ElectronicSignature

    equipment = make_equipment(people)
    accept_new_calibration(people, equipment, outcome="fail", accept=False, performed_hours_ago=0)
    accept_new_calibration(people, equipment, performed_hours_ago=0)
    equipment.refresh_from_db()
    url = reverse("laboratory:equipment_return", args=[equipment.pk])
    client.force_login(people["quality"])
    page = client.get(url).content.decode()
    assert "1 failed calibration(s) and 0 use(s) to assess" in page
    shown = re.search(r'name="assessed" value="([^"]*)"', page)
    assessed = {"assessed": shown.group(1)} if shown else {}
    # A backdated failure (before the latest passing calibration) neither blocks the return nor
    # changes the equipment revision, but it widens what the signature claims was assessed.
    services.record_calibration(
        actor=people["analyst2"],
        equipment=equipment,
        performed_at=timezone.now() - timedelta(hours=48),
        due_date=timezone.localdate(),
        outcome="fail",
        standard_ref="CERT-SYN-2",
        reason="Late entry of an earlier failure",
    )
    equipment.refresh_from_db()
    assert equipment.revision == int(re.search(r'name="expected_revision" value="(\d+)"', page)[1])
    response = client.post(
        url,
        {
            "signature_username": "quality",
            "expected_revision": equipment.revision,
            "pin": PIN,
            "reason": "Assessed the failure shown",
            **assessed,
        },
    )
    assert response.status_code == 422
    assert "changed while you assessed them" in response.content.decode()
    equipment.refresh_from_db()
    assert equipment.state == "out_of_service"
    assert not ElectronicSignature.objects.filter(object_type="laboratory.equipment").exists()
    # A reloaded page carries the current scope and signs.
    page = client.get(url).content.decode()
    assert "2 failed calibration(s)" in page
    fresh = re.search(r'name="assessed" value="([^"]*)"', page).group(1)
    signed = client.post(
        url,
        {
            "signature_username": "quality",
            "expected_revision": equipment.revision,
            "pin": PIN,
            "reason": "Assessed both failures",
            "assessed": fresh,
        },
    )
    assert signed.status_code == 302
    equipment.refresh_from_db()
    assert equipment.state == "in_service"


def test_return_to_service_without_a_scope_is_refused(client, people):
    equipment = make_equipment(people)
    services.take_out_of_service(actor=people["analyst"], equipment=equipment, reason="Check")
    equipment.refresh_from_db()
    client.force_login(people["quality"])
    url = reverse("laboratory:equipment_return", args=[equipment.pk])
    for assessed in (None, "x|y", "1"):
        data = {
            "signature_username": "quality",
            "expected_revision": equipment.revision,
            "pin": PIN,
            "reason": "No impact",
        }
        if assessed is not None:
            data["assessed"] = assessed
        response = client.post(url, data)
        assert response.status_code == 422, assessed
        assert "Reload and reassess" in response.content.decode()
    equipment.refresh_from_db()
    assert equipment.state == "out_of_service"
