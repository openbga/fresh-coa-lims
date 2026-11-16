"""Export of a lot's complete record: contents, consistency, integrity checks and boundaries."""

import hashlib
import io
import json
import threading
import zipfile
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections, transaction
from django.urls import reverse

from analytical import rawdata
from analytical import services as analytical
from core.audit import record_event
from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import review_audit, set_pin
from quality import services as quality
from quality.models import Lot
from reporting import lot_record
from reporting import services as reporting
from reporting.render import RenderError
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import (  # noqa: F401 - the fixture is used by name
    PASSWORD,
    PIN,
    assign_and_sample,
    dispose,
    integrated,
)

pytestmark = pytest.mark.django_db(transaction=True)
RAW = b"synthetic balance printout\r\nweight 1.00012 g\r\n"
PURPOSE = "Synthetic inspection request INS-SYN-001"


def person(django_user_model, name, *roles):
    user = django_user_model.objects.create_user(
        username=f"synthetic_{name}", password=PASSWORD, first_name="Synthetic", last_name=name
    )
    user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


@pytest.fixture
def released(integrated, django_user_model):  # noqa: F811
    """The integrated journey to an issued certificate, with a raw-data file and a review of
    part of the lot's audit trail. A second lot exists that must never appear in the export."""
    data, people = integrated, integrated["people"]
    people["auditor"] = person(django_user_model, "auditor", "auditor")
    people["admin"] = person(django_user_model, "admin", "admin")
    sample = assign_and_sample(data)
    tests, holds = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign frozen required tests"
    )
    assert holds == [] and len(tests) == 1
    test = tests[0]
    analytical.record_observation(
        actor=people["analyst"],
        test=test,
        value=Decimal("100.250"),
        raw_reference="RAW-SYN-001 rev 1",
        reason="Synthetic original observation",
    )
    test.refresh_from_db()
    raw = rawdata.attach_raw_file(
        actor=people["analyst"],
        test=test,
        upload=SimpleUploadedFile("../balance\\printout 1.txt", RAW, content_type="text/plain"),
        description="Synthetic balance printout",
    )
    test.refresh_from_db()
    test, _ = analytical.submit_test(
        actor=people["analyst"],
        test=test,
        expected_revision=test.revision,
        reason="Submit synthetic observation",
    )
    test = analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent original-data review",
    )
    lot = dispose(data, people["approver"])
    _, evidence_hash, blockers = reporting.preview(lot)
    assert blockers == []
    report = reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    reviewed = list(
        AuditEvent.objects.filter(object_type="quality.lot", object_id=str(lot.pk)).exclude(
            actor=people["auditor"]
        )
    )
    review = review_audit(
        actor=people["auditor"],
        event_ids=[e.pk for e in reviewed],
        conclusion="Synthetic review of the lot's events",
    )
    other = quality.receive_lot(
        actor=people["receiver"],
        number="SYN-OTHER-001",
        material=data["material"].name,
        rules=data["lot"].rules,
        reason="Another synthetic lot",
        receipt=on_site_receipt(),
    )
    return {
        **data,
        "lot": lot,
        "test": test,
        "raw": raw,
        "report": report,
        "review": review,
        "other": other,
    }


def unpack(package):
    data = package.file.read()
    package.file.close()
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()
    folder = names[0].split("/", 1)[0]
    assert all(name.startswith(folder + "/") for name in names)
    members = {name.split("/", 1)[1]: archive.read(name) for name in names}
    return data, folder, members


def export(data, actor=None, purpose=PURPOSE):
    actor = actor or data["people"]["auditor"]
    return lot_record.export_lot_record(actor=actor, lot_pk=data["lot"].pk, purpose=purpose)


def section(record, key):
    return next((s for s in record["sections"] if s["key"] == key), None)


def test_package_holds_the_complete_record_with_files_signatures_and_audit_trail(released):
    lot, people = released["lot"], released["people"]
    before = (
        Lot.objects.filter(pk=lot.pk).values().get(),
        ElectronicSignature.objects.count(),
        AuditEvent.objects.count(),
    )
    package = export(released)
    data, folder, members = unpack(package)

    assert folder.startswith("SYN-INTEGRATED-001-record-") and folder.endswith("Z")
    assert package.filename == folder + ".zip"
    assert {"record.pdf", "record.json", "manifest.json", "SHA256SUMS"} <= set(members)
    assert members["record.pdf"].startswith(b"%PDF-")
    # Every file in the folder is listed with its SHA-256, in the format sha256sum checks.
    listed = dict(
        reversed(line.split("  ", 1)) for line in members["SHA256SUMS"].decode().splitlines()
    )
    assert set(listed) == set(members) - {"SHA256SUMS"}
    for name, digest in listed.items():
        assert hashlib.sha256(members[name]).hexdigest() == digest

    # Stored files are copied byte for byte, under names that stay inside the folder.
    raw, version = released["raw"], released["report"].versions.get(number=1)
    raw_path = f"files/raw-data/test-{released['test'].pk}/{raw.pk}-printout 1.txt"
    assert members[raw_path] == RAW
    certificate = members[f"files/certificates/{released['report'].number}-v1.pdf"]
    assert certificate == bytes(version.pdf)

    record = json.loads(members["record.json"])
    assert record["schema"] == "oq.lot-record/1"
    assert record["export"]["purpose"] == PURPOSE
    assert record["export"]["exported_by"]["username"] == "synthetic_auditor"
    assert record["export"]["lot"] == {
        "id": lot.pk,
        "number": "SYN-INTEGRATED-001",
        "material": lot.material,
        "state": "released",
        "revision": before[0]["revision"],
    }
    for key in (
        "lot",
        "receipts",
        "assignments",
        "samples",
        "sampling_records",
        "tests",
        "observations",
        "raw_files",
        "reports",
        "report_versions",
    ):
        assert section(record, key)["records"], key
    for label in (
        "core.ruleset",
        "catalog.material",
        "catalog.specificationrevision",
        "sampling.samplingplanrevision",
    ):
        assert section(record, label.replace(".", "_"))["part"] == "referenced", label
    # Exact values, as recorded, and stored files named by their place in the package.
    observation = section(record, "observations")["records"][0]["fields"]
    assert (observation["value"], observation["value_text"]) == ("100.25000000", "100.250")
    assert section(record, "raw_files")["records"][0]["fields"]["content"]["path"] == raw_path
    assert record["types"]["analytical.observation"]["fields"]
    # Nothing of the other lot.
    lot_ids = [r["id"] for r in section(record, "lot")["records"]]
    assert lot_ids == [lot.pk]
    text = members["record.json"].decode()
    assert "SYN-OTHER-001" not in text
    lots = {
        e["fields"]["object_id"]
        for e in record["audit_trail"]
        if e["fields"]["object_type"] == "quality.lot"
    }
    assert lots == {str(lot.pk)}

    # Signatures: disposition, review and issue on the lot's records, and the approvals of the
    # configuration they name.
    signed = {(s["fields"]["object_type"], s["fields"]["meaning"]) for s in record["signatures"]}
    assert ("quality.lot", "approved") in signed
    assert ("analytical.analyticaltest", "reviewed") in signed
    assert ("reporting.report", "issued") in signed
    assert any(t == "catalog.specificationrevision" for t, _ in signed)
    # The audit trail holds every event on the lot's records, and the review that covered some.
    expected = set(
        AuditEvent.objects.filter(object_type="quality.lot", object_id=str(lot.pk))
        .exclude(action=lot_record.EXPORT_ACTION)
        .values_list("pk", flat=True)
    ) | set(
        AuditEvent.objects.filter(
            object_type="analytical.analyticaltest", object_id=str(released["test"].pk)
        ).values_list("pk", flat=True)
    )
    exported = {e["id"] for e in record["audit_trail"]}
    assert {str(pk) for pk in expected} <= exported
    review = record["audit_reviews"][0]
    assert review["fields"]["conclusion"] == "Synthetic review of the lot's events"
    assert review["events_in_this_record"]
    # Every stored checksum and hash was recomputed and matched.
    kinds = {c["check"] for c in record["checks"]}
    assert {
        "signature content",
        "raw-data file",
        "certificate file",
        "certificate content",
        "requirement assignment",
        "approved content",
    } <= kinds
    assert all(c["outcome"] == "intact" for c in record["checks"])
    # People are named by username and name only; no credential ever leaves.
    assert all(set(p) == {"id", "username", "name"} for p in record["people"])
    for user in people.values():
        user.refresh_from_db()
        assert user.password not in text
        assert PINCredential.objects.get(user=user).encoded not in text
    assert PIN not in text and PASSWORD not in text

    manifest = json.loads(members["manifest.json"])
    assert manifest["export"]["id"] == package.export_id
    assert manifest["summary"]["checks_differ"] == 0

    # Exporting changed nothing but adding its own audit event, which names the package.
    assert Lot.objects.filter(pk=lot.pk).values().get() == before[0]
    assert ElectronicSignature.objects.count() == before[1]
    assert AuditEvent.objects.count() == before[2] + 1
    event = AuditEvent.objects.get(action=lot_record.EXPORT_ACTION)
    assert (event.object_type, event.object_id) == ("quality.lot", str(lot.pk))
    assert event.actor == people["auditor"] and event.reason == PURPOSE
    assert event.after["package_sha256"] == hashlib.sha256(data).hexdigest()
    assert event.after["package_size"] == len(data)
    assert event.after["export_id"] == package.export_id
    assert event.after["record_json_sha256"] == listed["record.json"]
    assert event.after["lot_revision"] == before[0]["revision"]


def test_a_later_export_lists_the_earlier_one(released):
    unpack(export(released))
    _, _, members = unpack(export(released, actor=released["people"]["admin"]))
    record = json.loads(members["record.json"])
    exports = [e for e in record["audit_trail"] if e["fields"]["action"] == "lot.record_exported"]
    assert len(exports) == 1 and exports[0]["fields"]["reason"] == PURPOSE


def test_record_is_read_in_one_read_only_snapshot(released, monkeypatch):
    """A change committed while the export reads is not in the package."""
    lot, people = released["lot"], released["people"]
    seen = {}
    original = lot_record._checks

    def write_meanwhile():
        try:
            with transaction.atomic():
                record_event(
                    actor=people["receiver"],
                    action="synthetic.meanwhile",
                    obj=Lot.objects.get(pk=lot.pk),
                    reason="Written while the export reads",
                )
        finally:
            connections.close_all()

    def checks_after_a_write(*args, **kwargs):
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_isolation")
            seen["isolation"] = cursor.fetchone()[0]
            cursor.execute("SHOW transaction_read_only")
            seen["read_only"] = cursor.fetchone()[0]
        writer = threading.Thread(target=write_meanwhile)
        writer.start()
        writer.join()
        return original(*args, **kwargs)

    monkeypatch.setattr(lot_record, "_checks", checks_after_a_write)
    _, _, members = unpack(export(released))
    assert seen == {"isolation": "repeatable read", "read_only": "on"}
    assert AuditEvent.objects.filter(action="synthetic.meanwhile").exists()
    record = json.loads(members["record.json"])
    assert all(e["fields"]["action"] != "synthetic.meanwhile" for e in record["audit_trail"])


def test_a_file_that_no_longer_matches_its_checksum_is_copied_and_reported(released):
    raw = released["raw"]
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE analytical_rawdatafile DISABLE TRIGGER analytical_append_only")
        try:
            cursor.execute(
                "UPDATE analytical_rawdatafile SET content = %s WHERE id = %s",
                [b"altered behind the application", raw.pk],
            )
        finally:
            cursor.execute(
                "ALTER TABLE analytical_rawdatafile ENABLE TRIGGER analytical_append_only"
            )
    package = export(released)
    _, _, members = unpack(package)
    record = json.loads(members["record.json"])
    differs = [c for c in record["checks"] if c["outcome"] != "intact"]
    assert [(c["check"], c["record"]) for c in differs] == [
        ("raw-data file", f"analytical.rawdatafile:{raw.pk}")
    ]
    assert differs[0]["stored"].startswith(raw.sha256)
    assert package.summary["checks_differ"] == 1
    path = record["files"][0]["path"]
    assert members[path] == b"altered behind the application"
    event = AuditEvent.objects.get(action=lot_record.EXPORT_ACTION)
    assert event.after["checks_differ"] == 1


def test_signature_whose_content_no_longer_matches_is_reported(released):
    signature = ElectronicSignature.objects.get(object_type="quality.lot", meaning="approved")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger"
            " WHERE tgrelid = 'core_electronicsignature'::regclass AND NOT tgisinternal"
        )
        triggers = [row[0] for row in cursor.fetchall()]
        for name in triggers:
            cursor.execute(f"ALTER TABLE core_electronicsignature DISABLE TRIGGER {name}")
        try:
            cursor.execute(
                'UPDATE core_electronicsignature SET content = content || \'{"state": "x"}\''
                "::jsonb WHERE id = %s",
                [signature.pk],
            )
        finally:
            for name in triggers:
                cursor.execute(f"ALTER TABLE core_electronicsignature ENABLE TRIGGER {name}")
    _, _, members = unpack(export(released))
    record = json.loads(members["record.json"])
    differs = [c["record"] for c in record["checks"] if c["outcome"] != "intact"]
    assert differs == [f"core.electronicsignature:{signature.pk}"]


def test_a_render_failure_records_nothing(released, monkeypatch):
    def fail(*args, **kwargs):
        raise RenderError("synthetic renderer failure")

    monkeypatch.setattr(lot_record, "render_record_pdf", fail)
    with pytest.raises(RenderError):
        export(released)
    assert not AuditEvent.objects.filter(action=lot_record.EXPORT_ACTION).exists()


@pytest.mark.parametrize("purpose", ["", "   ", "x" * 501])
def test_purpose_is_required_and_bounded(released, purpose):
    with pytest.raises(lot_record.ExportError):
        export(released, purpose=purpose)
    assert not AuditEvent.objects.filter(action=lot_record.EXPORT_ACTION).exists()


@pytest.mark.parametrize("role", ["analyst", "reviewer"])
def test_roles_without_the_audit_trail_cannot_export(released, django_user_model, role):
    actor = person(django_user_model, f"only_{role}", role)
    with pytest.raises(PermissionDenied):
        export(released, actor=actor)
    actor.is_active = False
    actor.save()
    auditor = released["people"]["auditor"]
    auditor.is_active = False
    auditor.save()
    with pytest.raises(PermissionDenied):
        export(released, actor=auditor)
    assert not AuditEvent.objects.filter(action=lot_record.EXPORT_ACTION).exists()


def test_a_lot_just_received_exports_its_receipt(integrated, django_user_model):  # noqa: F811
    auditor = person(django_user_model, "auditor", "auditor")
    package = lot_record.export_lot_record(
        actor=auditor, lot_pk=integrated["lot"].pk, purpose=PURPOSE
    )
    _, _, members = unpack(package)
    record = json.loads(members["record.json"])
    assert [s["key"] for s in record["sections"] if s["part"] == "lot"] == ["lot", "receipts"]
    assert record["files"] == [] and record["signatures"]  # the rule set approval
    assert members["record.pdf"].startswith(b"%PDF-")


def test_names_in_the_package_never_leave_its_folder():
    assert lot_record.safe_name("../../etc/passwd", "x") == "passwd"
    assert lot_record.safe_name("..\\..\\boot.ini", "x") == "boot.ini"
    assert lot_record.safe_name("...", "fallback") == "fallback"
    assert lot_record.safe_name("LOT/2026:01*", "x") == "2026_01"
    assert lot_record.safe_name("a\x00b\nc", "x") == "a_b_c"


# Page ---------------------------------------------------------------------------------------


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)


def test_page_offers_the_export_to_audit_roles_and_downloads_the_package(client, released):
    lot, people = released["lot"], released["people"]
    url = reverse("quality:lot_record", args=[lot.pk])
    for name in ("analyst", "reviewer", "receiver"):
        if {"quality", "auditor", "admin"} & set(
            people[name].groups.values_list("name", flat=True)
        ):
            continue
        login(client, people[name])
        assert url not in client.get(reverse("quality:lot_detail", args=[lot.pk])).content.decode()
        assert client.get(url).status_code == 403
        assert client.post(url, {"purpose": PURPOSE}).status_code == 403
    for name in ("auditor", "admin", "approver"):
        login(client, people[name])
        assert url in client.get(reverse("quality:lot_detail", args=[lot.pk])).content.decode()
        page = client.get(url)
        assert page.status_code == 200
        assert b"Download the record" in page.content and b"data-vr-download" in page.content
    login(client, people["auditor"])
    refused = client.post(url, {"purpose": "  "})
    assert refused.status_code == 422
    assert not AuditEvent.objects.filter(action=lot_record.EXPORT_ACTION).exists()
    response = client.post(url, {"purpose": PURPOSE})
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "no-store" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "attachment" in response["Content-Disposition"]
    assert "SYN-INTEGRATED-001-record-" in response["Content-Disposition"]
    data = b"".join(response.streaming_content)
    assert int(response["Content-Length"]) == len(data)
    event = AuditEvent.objects.get(action=lot_record.EXPORT_ACTION)
    assert event.after["package_sha256"] == hashlib.sha256(data).hexdigest()
    assert zipfile.ZipFile(io.BytesIO(data)).testzip() is None


def test_page_reports_a_render_failure(client, released, monkeypatch):
    def fail(*args, **kwargs):
        raise RenderError("synthetic renderer failure")

    monkeypatch.setattr(lot_record, "render_record_pdf", fail)
    login(client, released["people"]["auditor"])
    response = client.post(
        reverse("quality:lot_record", args=[released["lot"].pk]), {"purpose": PURPOSE}
    )
    assert response.status_code == 422
    assert b"The record could not be exported: synthetic renderer failure" in response.content
    assert not AuditEvent.objects.filter(action=lot_record.EXPORT_ACTION).exists()


def test_page_needs_sign_in_and_an_existing_lot(client, released):
    url = reverse("quality:lot_record", args=[released["lot"].pk])
    assert client.get(url).status_code == 302
    login(client, released["people"]["auditor"])
    assert client.get(reverse("quality:lot_record", args=[999999])).status_code == 404
