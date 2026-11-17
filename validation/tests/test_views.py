"""The validation pages: who sees what, the signing pages, uploads, downloads and the evidence
check of a restored copy."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from catalog.models import MethodRevision
from catalog.tests.factories import PIN, approve, method_revision
from core import recovery
from core.models import ElectronicSignature
from validation import services
from validation.models import Rehearsal, RehearsalFile, UseAcceptance

pytestmark = pytest.mark.django_db(transaction=True)

LISTS = ["validation:use_list", "validation:rehearsal_list"]


def login(client, user):
    client.force_login(user)
    return client


def recorded_use(people, actor=None):
    return services.record_use_acceptance(
        actor=actor or people["author"],
        title="Synthetic QC release testing",
        intended_use="Release testing of synthetic incoming materials.",
        method_codes=["ftir-identity", "hplc-assay"],
        process_owner=people["author"],
        system_owner=people["admin"],
        validation_ref="VAL-SYN-001 rev 1",
        reason="Synthetic validation completed",
    )


def accepted_use(people):
    acceptance = recorded_use(people)
    return services.accept_use(
        actor=people["approver"],
        pin=PIN,
        acceptance=acceptance,
        expected_revision=acceptance.revision,
        reason="Validation report reviewed",
        token=services.acceptance_token(
            acceptance, services.configuration_in_force(), services.running_release(), None
        ),
    )


def recorded_rehearsal(actor, **changes):
    data = {
        "kind": "recovery",
        "title": "Synthetic restore",
        "performed_on": timezone.localdate(),
        "release": "abc1234",
        "environment": "Isolated synthetic copy",
        "procedure_ref": "SOP-SYN-IT-007 rev 2",
        "acceptance_criteria": "Restore check passes.",
        "outcome": "met",
        "observations": "Every check passed.",
        "reason": "Synthetic rehearsal",
    }
    data.update(changes)
    return services.record_rehearsal(actor=actor, **data)


@pytest.mark.parametrize("name", LISTS)
@pytest.mark.parametrize("role", ["analyst", "reviewer", "auditor", "admin", "author"])
def test_lists_are_readable_by_working_roles(client, people, name, role):
    response = login(client, people[role]).get(reverse(name))
    assert response.status_code == 200
    body = response.content.decode()
    assert "vr-empty" in body and "Rehearsals" in body and "Intended use" in body
    new = "New intended use" if name == "validation:use_list" else "New rehearsal"
    can_add = role == "author" or (role == "admin" and name == "validation:rehearsal_list")
    assert (new in body) is can_add


@pytest.mark.parametrize("name", LISTS)
def test_lists_are_refused_without_a_role(client, name):
    outsider = get_user_model().objects.create_user("outsider", password="x-synthetic-91")
    assert login(client, outsider).get(reverse(name)).status_code == 403


def test_recording_the_intended_use_through_the_page(client, people, configured):
    url = reverse("validation:use_new")
    assert login(client, people["analyst"]).get(url).status_code == 403
    client = login(client, people["author"])
    page = client.get(url)
    body = page.content.decode()
    assert page.status_code == 200
    assert "ftir-identity" in body and "hplc-assay" in body and "Supported assays" in body
    data = {
        "title": "Synthetic QC release testing",
        "intended_use": "Release testing.",
        "method_codes": ["hplc-assay"],
        "process_owner": people["author"].pk,
        "system_owner": people["admin"].pk,
        "validation_ref": "VAL-SYN-001 rev 1",
        "reason": "Synthetic validation completed",
    }
    missing = client.post(url, data | {"method_codes": []})
    assert missing.status_code == 422 and not UseAcceptance.objects.exists()
    response = client.post(url, data)
    created = UseAcceptance.objects.get()
    assert response.status_code == 302 and response.url == reverse(
        "validation:use_detail", args=[created.pk]
    )
    assert created.method_codes == ["hplc-assay"]


def test_intended_use_record_and_acceptance_pages(client, people, configured):
    acceptance = recorded_use(people)
    detail = reverse("validation:use_detail", args=[acceptance.pk])
    accept_url = reverse("validation:use_accept", args=[acceptance.pk])
    body = login(client, people["author"]).get(detail).content.decode()
    assert "Approved configuration in force now" in body and "Awaiting acceptance" in body
    assert accept_url not in body  # the recorder does not accept
    assert reverse("validation:use_withdraw", args=[acceptance.pk]) in body
    denied = client.get(accept_url)
    assert denied.status_code == 403 and services.SELF_ACCEPTANCE in denied.content.decode()
    client = login(client, people["approver"])
    assert accept_url in client.get(detail).content.decode()
    page = client.get(accept_url)
    body = page.content.decode()
    assert page.status_code == 200 and "Sign and accept" in body
    assert "ftir-identity v1" in body and "Supersedes" in body
    token = page.context["form"].initial["token"]
    data = {
        "reason": "Validation report reviewed",
        "signature_username": people["approver"].username,
        "pin": PIN,
        "expected_revision": acceptance.revision,
        "token": token,
    }
    # A method version approved after the page opened makes the page stale.
    hplc = MethodRevision.objects.get(method__code="hplc-assay").method
    approve(method_revision(people["author"], method=hplc), people["approver"])
    stale = client.post(accept_url, data)
    assert stale.status_code == 422
    assert "changed since this page was opened" in stale.content.decode()
    fresh = client.get(accept_url).context["form"].initial["token"]
    response = client.post(accept_url, data | {"token": fresh})
    assert response.status_code == 302
    acceptance.refresh_from_db()
    assert acceptance.state == "accepted"
    body = client.get(detail).content.decode()
    assert "Changes since acceptance" in body and "Approved configuration frozen" in body
    assert "None: every approved version in force is the one the acceptance froze." in body


def test_changes_since_acceptance_are_shown_on_the_list_and_the_record(
    client, people, configured, monkeypatch
):
    monkeypatch.setenv("SOURCE_REVISION", "abc1234")
    acceptance = accepted_use(people)
    client = login(client, people["analyst"])
    listing = client.get(reverse("validation:use_list")).content.decode()
    assert "Current acceptance" in listing and acceptance.label in listing
    approve(method_revision(people["author"], code="kf-water"), people["approver"])
    monkeypatch.setenv("SOURCE_REVISION", "def5678")
    listing = client.get(reverse("validation:use_list")).content.decode()
    assert "Changed since acceptance" in listing
    assert "1 change to the configuration and another release" in listing
    body = client.get(reverse("validation:use_detail", args=[acceptance.pk])).content.decode()
    assert "Newly in force" in body and "kf-water" in body
    assert "The running release (def5678) is not the accepted one (abc1234)." in body
    assert reverse("validation:use_withdraw", args=[acceptance.pk]) not in body


def test_withdrawing_the_intended_use_page(client, people, configured):
    acceptance = recorded_use(people)
    url = reverse("validation:use_withdraw", args=[acceptance.pk])
    assert login(client, people["admin"]).get(url).status_code == 403
    client = login(client, people["approver"])
    assert client.get(url).status_code == 200
    assert client.post(url, {"expected_revision": 1, "reason": ""}).status_code == 422
    response = client.post(url, {"expected_revision": 1, "reason": "Wrong owner"})
    assert response.status_code == 302
    acceptance.refresh_from_db()
    assert acceptance.state == "withdrawn"
    again = client.get(url)
    assert again.status_code == 302  # nothing left to withdraw


def test_rehearsal_pages_from_recording_to_acceptance(client, people):
    client = login(client, people["admin"])
    new = reverse("validation:rehearsal_new")
    form = client.get(new)
    assert form.status_code == 200 and "Record rehearsal" in form.content.decode()
    data = {
        "kind": "upgrade",
        "title": "Synthetic upgrade rehearsal",
        "performed_on": timezone.localdate().isoformat(),
        "release": "0.2.0",
        "environment": "Synthetic copy",
        "procedure_ref": "SOP-SYN-IT-009 rev 1",
        "acceptance_criteria": "Migrations apply; record counts unchanged.",
        "outcome": "met",
        "observations": "Applied in 3 minutes; counts unchanged.",
        "reason": "Synthetic rehearsal",
    }
    missing = client.post(new, data)
    assert missing.status_code == 422 and "release before it" in missing.content.decode()
    response = client.post(new, data | {"previous_release": "0.1.0"})
    rehearsal = Rehearsal.objects.get()
    detail = reverse("validation:rehearsal_detail", args=[rehearsal.pk])
    assert response.status_code == 302 and response.url == detail
    body = client.get(detail).content.decode()
    assert "Evidence needed" in body and "Release before" in body
    attach_url = reverse("validation:rehearsal_file_new", args=[rehearsal.pk])
    assert attach_url in body
    upload = SimpleUploadedFile("counts.csv", b"table,before,after\nlots,4,4\n")
    attached = client.post(attach_url, {"file": upload, "description": "Row counts"})
    assert attached.status_code == 302
    stored = RehearsalFile.objects.get()
    download = client.get(reverse("validation:rehearsal_file", args=[stored.pk]))
    assert download.status_code == 200
    assert download["Content-Disposition"] == 'attachment; filename="counts.csv"'
    assert download["X-Content-Type-Options"] == "nosniff"
    assert download.content == b"table,before,after\nlots,4,4\n"
    accept_url = reverse("validation:rehearsal_accept", args=[rehearsal.pk])
    assert client.get(accept_url).status_code == 403  # admin is not quality
    client = login(client, people["author"])
    assert client.get(attach_url).status_code == 302  # only the recorder attaches
    page = client.get(accept_url)
    assert page.status_code == 200 and stored.sha256 in page.content.decode()
    rehearsal.refresh_from_db()
    response = client.post(
        accept_url,
        {
            "reason": "Evidence reviewed",
            "signature_username": people["author"].username,
            "pin": PIN,
            "expected_revision": rehearsal.revision,
        },
    )
    assert response.status_code == 302
    assert ElectronicSignature.objects.filter(object_type="validation.rehearsal").count() == 1
    body = client.get(detail).content.decode()
    assert "Accepted: criteria met" in body and accept_url not in body


def test_rehearsal_downloads_and_pages_are_refused_without_a_role(client, people):
    rehearsal = recorded_rehearsal(people["admin"])
    stored = services.attach_rehearsal_file(
        actor=people["admin"],
        rehearsal=rehearsal,
        upload=SimpleUploadedFile("r.json", b"{}"),
        description="Report",
    )
    outsider = get_user_model().objects.create_user("outsider", password="x-synthetic-91")
    client = login(client, outsider)
    for url in (
        reverse("validation:rehearsal_detail", args=[rehearsal.pk]),
        reverse("validation:rehearsal_file", args=[stored.pk]),
        reverse("validation:rehearsal_file", args=[stored.pk + 1000]),
    ):
        assert client.get(url).status_code == 403
    client = login(client, people["analyst"])
    assert client.get(reverse("validation:rehearsal_new")).status_code == 403
    assert (
        client.get(reverse("validation:rehearsal_withdraw", args=[rehearsal.pk])).status_code == 403
    )
    other = get_user_model().objects.get(username="admin-a")
    assert other == people["admin"]


def test_restore_check_covers_rehearsal_evidence(people):
    rehearsal = recorded_rehearsal(people["admin"])
    stored = services.attach_rehearsal_file(
        actor=people["admin"],
        rehearsal=rehearsal,
        upload=SimpleUploadedFile("r.json", b'{"result": "passed"}'),
        description="Report",
    )
    check = recovery.check_raw_files()
    assert check["status"] == recovery.PASSED
    assert "1 rehearsal evidence files" in check["summary"]
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE validation_rehearsalfile DISABLE TRIGGER USER")
        try:
            RehearsalFile.objects.filter(pk=stored.pk).update(content=b'{"result": "failed"}')
        finally:
            cursor.execute("ALTER TABLE validation_rehearsalfile ENABLE TRIGGER USER")
    check = recovery.check_raw_files()
    assert check["status"] == recovery.FAILED
    assert check["problems"][0].startswith(f"Evidence file {stored.pk} of rehearsal")
