"""CoA issue/amend transitions: authorization, locks, stale evidence, atomic rollback, history."""

import hashlib
import json
import shutil
import subprocess

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction

from core.models import AuditEvent, ElectronicSignature
from reporting import evidence as ev
from reporting import render, services
from reporting.models import Report, ReportVersion
from reporting.tests.conftest import PIN, build_lot

pytestmark = pytest.mark.django_db(transaction=True)


def issue(people, lot, actor="quality", **overrides):
    _, digest, _ = services.preview(lot)
    kwargs = {
        "actor": people[actor],
        "pin": PIN,
        "lot": lot,
        "recipient": "Synthetic Customer A",
        "evidence_hash": digest,
        "reason": "Customer shipment certificate",
        "remarks": "Store below 25 °C",
    }
    kwargs.update(overrides)
    return services.issue_report(**kwargs)


def amend(people, report, actor="quality", **overrides):
    report.refresh_from_db()
    _, digest, _ = services.preview(report.lot)
    kwargs = {
        "actor": people[actor],
        "pin": PIN,
        "report": report,
        "expected_version": report.version_count,
        "evidence_hash": digest,
        "reason": "Recipient name corrected",
        "remarks": "Store below 25 °C",
    }
    kwargs.update(overrides)
    return services.amend_report(**kwargs)


def pdf_text(data):
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext (poppler) is not installed")
    out = subprocess.run(
        ["pdftotext", "-layout", "-", "-"], input=data, capture_output=True, check=True
    )
    return out.stdout.decode()


def test_issue_stores_immutable_version_signature_and_audit(people, lot):
    report = issue(people, lot)
    version = report.versions.get()
    assert (report.state, report.version_count, report.revision) == ("issued", 1, 2)
    assert report.number == "CoA-SYN-100-1"
    data = bytes(version.pdf)
    assert data.startswith(b"%PDF-")
    assert hashlib.sha256(data).hexdigest() == version.pdf_sha256 == report.current_pdf_sha256
    assert version.pdf_size == len(data)
    assert (
        version.snapshot_hash == report.current_snapshot_hash == ev.canonical_hash(version.snapshot)
    )
    signature = services.signature_for(version)
    assert signature.meaning == "issued"
    assert signature.signer == people["quality"]
    assert signature.revision == report.revision == version.report_revision
    # The signed content binds the issued bytes and the frozen snapshot.
    assert signature.content["current_pdf_sha256"] == version.pdf_sha256
    assert signature.content["current_snapshot_hash"] == version.snapshot_hash
    assert signature.signed_at == version.issued_at  # one server-selected signing time
    assert ev.iso(signature.signed_at) == version.snapshot["report"]["issued_at"]
    assert signature.audit_event.action == "signed.issued"
    assert signature.audit_event.reason == "Customer shipment certificate"
    assert version.snapshot["report"]["issued_by"] == "Quality Synthetic"
    assert version.snapshot["samples"][0]["results"][0]["value"] == "99.5"


def test_pdf_manifests_content_and_signatures(people, lot):
    version = issue(people, lot).versions.get()
    text = pdf_text(bytes(version.pdf))
    for expected in (
        "Certificate of analysis",
        "CoA-SYN-100-1",
        "SYN-100",
        "Synthetic reference powder",
        "Synthetic Customer A",
        "99.5",
        "98 to 101 mg/g",
        "Conforms",
        "Reviewer Synthetic",
        "QC disposition approved",
        "Quality Synthetic",
        "Certificate issued",
        "Store below 25 °C",
        "not asserted by this certificate",
        "not the manufacturer's batch release",
        "Synthetic demonstration data",
    ):
        assert expected in text, expected
    assert version.evidence_hash in text.replace("\n", "").replace(" ", "")


def test_unicode_units_survive_into_pdf(people):
    lot = build_lot(people, number="SYN-UNI", unit="µg/mL")
    version = issue(people, lot).versions.get()
    assert "µg/mL" in pdf_text(bytes(version.pdf))


def test_multipage_certificate_keeps_header_and_page_numbers(people):
    tests = [f"impurity-{n:02d}" for n in range(60)]
    lot = build_lot(people, number="SYN-LONG", extra_tests=tests)
    version = issue(people, lot).versions.get()
    text = pdf_text(bytes(version.pdf))
    assert "Page 1 of" in text
    assert "Page 2 of" in text
    assert text.count("Independent review") >= 2  # table header repeats on later pages
    assert "impurity-59" in text
    # The final hash is grouped with the technical identifiers, never alone on the last page.
    pages = text.split("\x0c")
    last = [p for p in pages if p.strip()][-1]
    assert "Technical identifiers" in last and version.evidence_hash[:16] in last
    assert "Electronic signatures" in text


def test_pdf_never_includes_pin_or_credentials(people, lot):
    data = bytes(issue(people, lot).versions.get().pdf)
    assert PIN.encode() not in data
    assert b"pbkdf2" not in data


@pytest.mark.parametrize("actor", ["analyst", "reviewer", "auditor", "nobody"])
def test_only_quality_can_issue(people, lot, actor):
    with pytest.raises(PermissionDenied):
        issue(people, lot, actor=actor)
    assert not Report.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()


def test_author_with_quality_role_cannot_issue(people, lot):
    people["analyst"].groups.add(*people["quality"].groups.all())
    with pytest.raises(PermissionDenied, match="authored"):
        issue(people, lot, actor="analyst")
    assert not ReportVersion.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()


def test_unreleased_lot_cannot_be_opened(people):
    lot = build_lot(people, number="SYN-QUAR", release=False)
    with pytest.raises(ValidationError, match="signed QC disposition"):
        issue(people, lot)
    assert not Report.objects.exists()


def test_open_hold_blocks_and_rolls_back(people, lot):
    ev.register_collector(
        "holds", lambda lot: [{"id": "H1", "status": "open", "description": "Investigation 7"}]
    )
    with pytest.raises(ValidationError, match="Open hold: Investigation 7"):
        issue(people, lot, evidence_hash=services.preview(lot)[1])
    report = Report.objects.get()
    assert (report.state, report.version_count, report.revision) == ("draft", 0, 1)
    assert not ReportVersion.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()
    assert not AuditEvent.objects.filter(action="signed.issued").exists()


def test_stale_evidence_is_rejected(people, lot):
    _, reviewed_hash, _ = services.preview(lot)
    # A hold snapshot appears (cleared) between review and signing: evidence changed.
    ev.register_collector("holds", lambda lot: [])
    with pytest.raises(ValidationError, match="evidence changed"):
        issue(people, lot, evidence_hash=reviewed_hash)
    assert not ReportVersion.objects.exists()
    issue(people, lot)  # reviewing the new evidence succeeds
    assert ReportVersion.objects.count() == 1


def test_wrong_pin_fails_but_denial_is_audited(people, lot):
    with pytest.raises(ValidationError, match="not accepted"):
        issue(people, lot, pin="00000000")
    assert AuditEvent.objects.filter(action="signature.denied", actor=people["quality"]).exists()
    assert not ReportVersion.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()


def test_failed_render_rolls_back_release(people, lot, monkeypatch):
    def boom(snapshot, **kwargs):
        raise render.RenderError("font failure")

    monkeypatch.setattr(services, "render_certificate", boom)
    with pytest.raises(ValidationError, match="could not be rendered"):
        issue(people, lot)
    report = Report.objects.get()
    assert (report.state, report.version_count, report.revision) == ("draft", 0, 1)
    assert not ReportVersion.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()
    assert not AuditEvent.objects.filter(action="signed.issued").exists()
    monkeypatch.undo()
    assert issue(people, lot).versions.count() == 1  # the draft head is reused


def test_renderer_refuses_external_resources(people, lot):
    html_snapshot = ev.collect_evidence(lot)
    with pytest.raises(ValueError):
        render._refuse_fetch("file:///etc/passwd")
    assert html_snapshot


def test_cannot_issue_twice_but_series_is_per_recipient(people, lot):
    first = issue(people, lot)
    with pytest.raises(ValidationError, match="already issued"):
        issue(people, lot)
    other = issue(people, lot, recipient="Synthetic Customer B")
    assert other.pk != first.pk
    assert other.number == "CoA-SYN-100-2"
    assert Report.objects.count() == 2


def test_amendment_adds_linked_version_and_preserves_original(people, lot):
    report = issue(people, lot)
    original = report.versions.get()
    original_bytes = bytes(original.pdf)
    amended = amend(people, report, reason="Recipient address corrected")
    assert (amended.version_count, amended.revision) == (2, 3)
    first, second = amended.versions.order_by("number")
    assert second.kind == "amendment" and first.kind == "issue"
    assert second.supersedes_id == first.pk
    assert bytes(first.pdf) == original_bytes
    assert first.pdf_sha256 == original.pdf_sha256 != second.pdf_sha256
    assert services.signature_for(second).meaning == "amended"
    assert services.signature_for(first).meaning == "issued"
    text = pdf_text(bytes(second.pdf))
    assert "Amended certificate" in text or "AMENDED" in text.upper()
    assert "Recipient address corrected" in text
    assert "replaces version 1" in text.lower()
    assert amended.current_pdf_sha256 == second.pdf_sha256


def test_amend_requires_issue_current_version_and_reason(people, lot):
    report = issue(people, lot)
    with pytest.raises(ValidationError, match="changed since you reviewed"):
        amend(people, report, expected_version=0)
    with pytest.raises(ValidationError, match="reason"):
        amend(people, report, reason="   ")
    amend(people, report)
    with pytest.raises(ValidationError, match="changed since you reviewed"):
        amend(people, report, expected_version=1)  # stale: version 2 exists now
    assert ReportVersion.objects.count() == 2


def test_cannot_amend_unissued_report(people, lot):
    draft = services.open_report(actor=people["quality"], lot=lot, recipient="X")
    with pytest.raises(ValidationError, match="Only an issued"):
        amend(people, draft)


def test_amendment_is_gated_like_issue(people, lot):
    report = issue(people, lot)
    ev.register_collector("holds", lambda lot: [{"id": "H", "status": "open"}])
    with pytest.raises(ValidationError, match="Open hold"):
        amend(people, report)
    assert ReportVersion.objects.count() == 1


def test_second_quality_user_may_amend(people, lot):
    report = issue(people, lot)
    assert amend(people, report, actor="quality2").versions.count() == 2


def test_history_is_database_protected(people, lot):
    report = issue(people, lot)
    version = report.versions.get()
    with pytest.raises(DatabaseError), transaction.atomic():
        ReportVersion.objects.filter(pk=version.pk).update(pdf=b"%PDF-forged")
    with pytest.raises(DatabaseError), transaction.atomic():
        ReportVersion.objects.filter(pk=version.pk).delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        Report.objects.filter(pk=report.pk).update(recipient="Someone else")
    with pytest.raises(DatabaseError), transaction.atomic():
        Report.objects.filter(pk=report.pk).update(version_count=0)
    with pytest.raises(DatabaseError), transaction.atomic():
        Report.objects.filter(pk=report.pk).delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        # A head cannot claim a version that does not exist or whose hash differs.
        Report.objects.filter(pk=report.pk).update(
            version_count=2, current_pdf_sha256="0" * 64, current_snapshot_hash="1" * 64
        )
    version.refresh_from_db()
    assert hashlib.sha256(bytes(version.pdf)).hexdigest() == version.pdf_sha256


def test_head_cannot_claim_issue_without_version(people, lot):
    draft = services.open_report(actor=people["quality"], lot=lot, recipient="Y")
    with pytest.raises(DatabaseError), transaction.atomic():
        Report.objects.filter(pk=draft.pk).update(state="issued")


def test_snapshot_is_independent_of_later_rule_text(people, lot):
    """Issued content is the stored snapshot: the audit trail JSON has no mutable references."""
    version = issue(people, lot).versions.get()
    stored = json.loads(json.dumps(version.snapshot))
    assert stored["rules"]["required_tests"] == ["assay"]
    assert stored["disposition"]["meaning"] == "approved"
    assert stored["authors"] == sorted(stored["authors"])


def test_download_requires_role_audits_and_verifies_integrity(people, lot):
    version = issue(people, lot).versions.get()
    with pytest.raises(PermissionDenied):
        services.read_pdf(actor=people["nobody"], version=version)
    data = services.read_pdf(actor=people["auditor"], version=version)
    assert hashlib.sha256(data).hexdigest() == version.pdf_sha256
    event = AuditEvent.objects.get(action="report.downloaded")
    assert event.actor == people["auditor"]
    assert event.after["pdf_sha256"] == version.pdf_sha256
    version.pdf = b"%PDF-tampered"
    with pytest.raises(ValidationError, match="integrity"):
        services.read_pdf(actor=people["auditor"], version=version)
    assert AuditEvent.objects.filter(action="report.downloaded").count() == 1


def test_open_report_is_audited_once(people, lot):
    first = services.open_report(actor=people["quality"], lot=lot, recipient=" A ")
    again = services.open_report(actor=people["quality"], lot=lot, recipient="A")
    assert first.pk == again.pk
    assert AuditEvent.objects.filter(action="report.opened").count() == 1
    assert connection.in_atomic_block is False


def test_write_review_pdfs(people, lot):
    """Visual inspection aid: set OQ_PDF_OUT to a directory to keep sample PDFs."""
    import os
    import pathlib

    out = os.environ.get("OQ_PDF_OUT")
    if not out:
        pytest.skip("OQ_PDF_OUT not set")
    ev.register_collector("holds", lambda lot: [])
    ev.register_collector("specification", lambda lot: {"code": "SYN-SPEC", "revision": 2})
    first = issue(people, lot, evidence_hash=services.preview(lot)[1])
    pathlib.Path(out, "issue.pdf").write_bytes(bytes(first.versions.get().pdf))
    amended = amend(people, first, reason="Recipient wording corrected after customer query")
    pathlib.Path(out, "amend.pdf").write_bytes(bytes(amended.versions.get(number=2).pdf))
    long_lot = build_lot(
        people, number="SYN-LONG", extra_tests=[f"impurity-{n:02d}" for n in range(45)]
    )
    ev.unregister_collector("holds")
    ev.unregister_collector("specification")
    long = issue(people, long_lot)
    pathlib.Path(out, "long.pdf").write_bytes(bytes(long.versions.get().pdf))
