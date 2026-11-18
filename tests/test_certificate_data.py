"""Certificate data beside the PDF, and the PDF written as an archival, accessible document.

Each issued version stores its certificate's data in a machine-readable form (JSON, schema
``oq.certificate-data/1``), embeds exactly those bytes in its PDF as an associated file, prints
their SHA-256, and offers them for download beside the PDF. The data states what the printed
certificate states: a certificate for one scope of the lot names no other scope. The PDF is
written as tagged PDF/A-3a and declares PDF/UA-1 too. A version issued before keeps its PDF as
issued and has no data.

Uses a lot under two specifications (the general scope and a market), released through the
production services (synthetic data). The PDF's structure is read with poppler's tools, as CI
installs them.
"""

import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
import zlib

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.urls import reverse

from core.models import AuditEvent, ElectronicSignature
from reporting import certificate_data, lot_record, services
from reporting.models import ReportVersion
from reporting.render import PDF_FORMAT
from tests.test_backup_restore_checks import triggers_disabled
from tests.test_customer_certificates import MARKET, TIGHT, issue, released
from tests.test_integrated_journey import PIN
from tests.test_result_types_journey import build_world

pytestmark = pytest.mark.django_db(transaction=True)

# Internal record numbers and working fields of the snapshot that the certificate does not print.
INTERNAL_KEYS = {
    "id",
    "issued_by_id",
    "signer_id",
    "author_ids",
    "revision_id",
    "assignment_id",
    "eligibility",
    "requirement_hash",
    "content_hash",
    "approval",
    "approval_evidence",
    "stated_lot",
}


@pytest.fixture
def world(django_user_model):
    return build_world(django_user_model, with_assay=True)


@pytest.fixture
def lot(world):
    return released(world, TIGHT)


def tool(name):
    if not shutil.which(name):
        pytest.skip(f"{name} (poppler) is not installed")
    return name


def run(*args, data):
    return subprocess.run(args, input=data, capture_output=True, check=True).stdout


def attachments(pdf, tmp_path):
    """{name: bytes} of the files embedded in a PDF (pdfdetach)."""
    path = tmp_path / "certificate.pdf"
    path.write_bytes(pdf)
    out = tmp_path / "attached"
    out.mkdir()
    subprocess.run([tool("pdfdetach"), "-saveall", "-o", str(out), str(path)], check=True)
    return {item.name: item.read_bytes() for item in out.iterdir()}


def pdf_objects(pdf):
    """The PDF's objects as text, object streams decompressed (where the file keeps them)."""
    parts = [pdf]
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            parts.append(zlib.decompress(stream))
        except zlib.error:
            continue
    return b"\n".join(parts)


def keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from keys(item)


def legacy_issue(world, lot, monkeypatch, **kwargs):
    """A version as issued before certificate data existed: no data and no declared format."""
    create = ReportVersion.objects.create

    def without_data(**fields):
        for name in ("data", "data_sha256", "pdf_format"):
            fields.pop(name)
        return create(**fields)

    monkeypatch.setattr(ReportVersion.objects, "create", without_data)
    report = issue(world, lot, **kwargs)
    monkeypatch.undo()
    return report


# The data, stored and embedded ----------------------------------------------------------------


def test_an_issued_version_stores_its_data_and_embeds_the_same_bytes(world, lot, tmp_path):
    report = issue(world, lot, recipient="Synthetic general recipient")
    version = report.versions.get()
    data = bytes(version.data)
    assert version.data_sha256 == hashlib.sha256(data).hexdigest()
    assert version.pdf_format == PDF_FORMAT == "PDF/A-3a, PDF/UA-1"
    # It is the data of this certificate, built from the snapshot it is signed over.
    assert data == certificate_data.encode(certificate_data.build(version.snapshot, synthetic=True))
    payload = json.loads(data)
    assert payload["schema"] == "oq.certificate-data/1"
    assert payload["certificate"] == {
        "number": report.number,
        "version": 1,
        "kind": "issue",
        "amends_version": None,
        "amendment_reason": None,
        "recipient": "Synthetic general recipient",
        "scope": None,
        "issued_by": "Synthetic Author",
        "issued_at": version.snapshot["report"]["issued_at"],
        "remarks": None,
        "statement": certificate_data.STATEMENT,
        "synthetic_data": True,
        "notice": certificate_data.SYNTHETIC_NOTICE,
    }
    # The PDF carries the same bytes; its printed text is unchanged (new printed wording waits
    # for the owner's approval).
    assert attachments(bytes(version.pdf), tmp_path) == {certificate_data.FILENAME: data}
    printed = run(tool("pdftotext"), "-raw", "-", "-", data=bytes(version.pdf)).decode()
    assert "certificate-data" not in printed and "CERTIFICATE DATA" not in printed


def test_the_data_states_results_exactly_and_no_internal_numbers(world, lot):
    version = issue(world, lot, recipient="Synthetic general recipient").versions.get()
    payload = json.loads(bytes(version.data))
    assert not INTERNAL_KEYS & set(keys(payload))
    (assay,) = [r for r in payload["results"] if r["test"] == "assay"]
    assert assay["replicates"] == ["99.60"] and assay["reportable"] == "99.60"
    assert assay["unit"] == "%"
    assert assay["limits"] == {
        "acceptance": "99 to 101 %",
        "lower": "99",
        "lower_inclusive": True,
        "upper": "101",
        "upper_inclusive": True,
    }
    assert assay["review"]["signer"] == "Synthetic Reviewer"
    assert "conformity" not in assay  # stated per specification below, as the PDF prints it
    # The conformity of each result with each specification, and the decision between them.
    (row,) = [r for r in payload["conformity"] if r["test"] == "assay"]
    assert {(s["scope"], s["outcome"]) for s in row["statements"]} == {
        ("general", "conforms"),
        (MARKET, "conforms"),
    }
    (decision,) = payload["requirement_decisions"]
    assert decision["test"] == "assay" and decision["decided"]["by"] == "Synthetic Approver"
    assert payload["decision_rule"].startswith("Each result is compared with the limits")
    assert {s["scope"] for s in payload["specifications"]} == {"general", MARKET}
    meanings = [s["meaning"] for s in payload["signatures"]]
    assert meanings[-2:] == ["QC disposition approved", "Certificate issued"]
    assert payload["identifiers"]["evidence_sha256"] == version.evidence_hash
    # Moments as printed: UTC to the second, also where the frozen record keeps microseconds.
    moments = [assay["review"]["signed_at"], payload["certificate"]["issued_at"]]
    moments += [s["signed_at"] for s in payload["signatures"]]
    moments += [payload["lot"]["received_at"], payload["disposition"]["signed_at"]]
    moments += [payload["rules"]["effective_from"], decision["decided"]["at"]]
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", m) for m in moments), moments
    assert payload["lot"]["number"] == lot.number and payload["disposition"]["decision"] == (
        "approved"
    )


def test_a_scope_certificates_data_names_no_other_scope(world, lot):
    version = issue(world, lot, scope=MARKET).versions.get()
    data = bytes(version.data)
    payload = json.loads(data)
    assert payload["certificate"]["scope"] == MARKET
    assert [s["scope"] for s in payload["specifications"]] == [MARKET]
    # Nothing of the general specification or of the decision between the two.
    assert b"general" not in data and b"synthetic-rt-spec version" not in data
    assert payload["rules"]["required_tests"] is None and payload["additional_rules"] == []
    assert payload["requirement_decisions"] == [] and payload["conformity"] == []
    assert payload["identifiers"]["requirement_sources"] == []
    (assay,) = [r for r in payload["results"] if r["test"] == "assay"]
    # The result and requirement of the scope's specification; the released ones may be
    # another specification's.
    assert assay["reportable"] is None and assay["limits"] is None
    assert assay["conformity"] == {
        "specification": "synthetic-rt-eu-market version 1",
        "scope": MARKET,
        "requirement": "99 – 101 % · rounded to 2 decimals",
        "result": "99.60 %",
        "outcome": "conforms",
        "reason": None,
    }
    assert not INTERNAL_KEYS & set(keys(payload))


def test_a_scope_certificate_does_not_say_which_specification_governed(world, lot):
    """The assay was released against the market's statement; the general customer's data
    reports the general statement and does not say that it was not the one applied."""
    payload = json.loads(bytes(issue(world, lot, scope="general").versions.get().data))
    assert b"eu-market" not in json.dumps(payload).encode()
    for item in payload["results"] + payload["supplier_results"]:
        assert set(item["conformity"]) == {
            "specification",
            "scope",
            "requirement",
            "result",
            "outcome",
            "reason",
        }
    (assay,) = [r for r in payload["results"] if r["test"] == "assay"]
    assert assay["conformity"]["requirement"] == "98 – 102 % · rounded to 2 decimals"
    assert assay["reportable"] is None and assay["limits"] is None


def scoped_supplier_snapshot():
    """A certificate for the scope ``eu`` of a lot whose supplier result was accepted under the
    general specification; the market's statement states no requirement text."""
    general = {
        "scope": "general",
        "specification": "SPEC-GEN version 1",
        "applied": True,
        "requirement": "NMT 10 ppm",
        "result": "<5 ppm",
        "outcome": "conforms",
        "reason": "",
    }
    market = {**general, "scope": "eu", "specification": "SPEC-EU version 1", "applied": False}
    market.update(requirement="", outcome="information")
    supplier = {
        "acceptance": 7,
        "label": "SRA-7",
        "test_code": "lead",
        "name": "Lead",
        "unit": "ppm",
        "criterion": "NMT 10 ppm (general)",
        "stated": {"result": "<5", "method": "SM-1", "limits": "NMT 10 ppm"},
        "certificate": {"number": "SUP-1", "issued_on": "2026-11-01", "issued_by": "Synth Co"},
        "supplier": {"code": "SUP-SYN", "name": "Synthetic supplier", "location": "Synthville"},
        "qualification": {"id": 3, "label": "SQ-3", "evidence_ref": "AUDIT-SYN"},
        "signature": {"id": 9, "signer": "Reviewer", "signed_at": "2026-11-17T08:00:00.5+00:00"},
    }
    return {
        "evidence_hash": "e" * 64,
        "report": {
            "number": "CoA-SYN-1-1",
            "version": 1,
            "kind": "issue",
            "scope": "eu",
            "issued_by": "Quality Synthetic",
            "issued_at": "2026-11-18T10:00:00Z",
        },
        "native": {
            "specifications": [
                {"code": "SPEC-GEN", "version": 1, "scope": "general", "approved_hash": "a" * 64},
                {"code": "SPEC-EU", "version": 1, "scope": "eu", "approved_hash": "b" * 64},
            ],
            "conformity": [
                {
                    "test": None,
                    "test_code": "lead",
                    "origin": "supplier",
                    "acceptance": 7,
                    "statements": [general, market],
                }
            ],
            "analytical": {"results": [], "supplier_results": [supplier]},
        },
    }


def test_a_scope_certificates_supplier_result_states_only_the_scopes_statement():
    data = certificate_data.encode(certificate_data.build(scoped_supplier_snapshot()))
    payload = json.loads(data)
    (lead,) = payload["supplier_results"]
    assert lead["specification"] is None  # the market states none; the general one is not used
    assert b"general" not in data and b"SPEC-GEN" not in data
    assert "applied" not in lead["conformity"]
    assert lead["supplier"] == {"name": "Synthetic supplier", "location": "Synthville"}
    assert lead["qualification"] == {"label": "SQ-3", "evidence_ref": "AUDIT-SYN"}
    assert lead["accepted"]["signed_at"] == "2026-11-17T08:00:00Z"
    assert not INTERNAL_KEYS & set(keys(payload))


def test_an_amendment_carries_its_own_data(world, lot, tmp_path):
    report = issue(world, lot, recipient="Synthetic general recipient")
    _, digest, _ = services.preview(lot)
    services.amend_report(
        actor=world["people"]["author"],
        pin=PIN,
        report=report,
        expected_version=1,
        evidence_hash=digest,
        reason="Synthetic corrected recipient address",
        remarks="Synthetic remark",
    )
    first, second = report.versions.order_by("number")
    payload = json.loads(bytes(second.data))
    assert payload["certificate"]["kind"] == "amendment"
    assert payload["certificate"]["amends_version"] == 1
    assert payload["certificate"]["amendment_reason"] == "Synthetic corrected recipient address"
    assert payload["certificate"]["remarks"] == "Synthetic remark"
    assert payload["signatures"][-1]["meaning"] == "Certificate amended"
    assert first.data_sha256 != second.data_sha256
    assert attachments(bytes(second.pdf), tmp_path)[certificate_data.FILENAME] == bytes(second.data)


def test_a_failure_to_build_the_data_issues_nothing(world, lot, monkeypatch):
    def broken(*args, **kwargs):
        raise KeyError("synthetic failure")

    monkeypatch.setattr(certificate_data, "build", broken)
    with pytest.raises(ValidationError, match="could not be rendered"):
        issue(world, lot)
    assert not ReportVersion.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()
    assert not AuditEvent.objects.filter(
        action__startswith="signed.", object_type="reporting.report"
    ).exists()


def test_the_synthetic_notice_follows_the_setting(world, lot, settings):
    settings.REPORT_SYNTHETIC_DATA_NOTICE = False
    payload = json.loads(bytes(issue(world, lot).versions.get().data))
    assert payload["certificate"]["synthetic_data"] is False
    assert payload["certificate"]["notice"] is None


# The archival, accessible PDF -----------------------------------------------------------------


def test_the_pdf_is_tagged_and_declares_pdf_a_3a_and_pdf_ua_1(world, lot):
    pdf = bytes(issue(world, lot, scope=MARKET).versions.get().pdf)
    info = run(tool("pdfinfo"), "-", data=pdf).decode()
    assert re.search(r"^Tagged:\s+yes$", info, re.M)
    assert re.search(r"^PDF version:\s+1\.7$", info, re.M)
    meta = run("pdfinfo", "-meta", "-", data=pdf).decode()
    assert 'pdfaid:part="3"' in meta and 'pdfaid:conformance="A"' in meta
    assert 'pdfuaid:part="1"' in meta
    # PDF/A-3 accepts the PDF/UA namespace only when declared as an extension schema.
    assert (
        "<pdfaSchema:namespaceURI>http://www.aiim.org/pdfua/ns/id/</pdfaSchema:namespaceURI>"
        in (meta)
    )
    assert meta.count("<rdf:RDF") == 1  # one RDF: the identification is where readers look
    objects = pdf_objects(pdf)
    assert re.search(rb"/AFRelationship\s*/Data", objects)
    assert re.search(rb"/OutputIntents", objects) and re.search(rb"/Lang", objects)
    assert re.search(rb"/DisplayDocTitle\s+true", objects)
    # Headings start at H1 and skip no level (PDF/UA-1 7.4.2).
    struct = run("pdfinfo", "-struct", "-", data=pdf).decode()
    levels = [int(n) for n in re.findall(r"^\s*H([1-6]) ", struct, re.M)]
    assert levels[0] == 1
    assert all(b - a <= 1 for a, b in zip(levels, levels[1:], strict=False))


def test_the_screen_keeps_its_headings_under_the_page_title(world, lot, client):
    report = issue(world, lot)
    client.force_login(world["people"]["reviewer"])
    page = client.get(reverse("reporting:version", args=[report.pk, 1])).content.decode()
    assert '<h2 class="card-title" id="cert-title">' in page
    assert '<h3 class="h6 fw-bold mt-4">Results</h3>' in page
    assert '<h1 class="card-title"' not in page


# Download beside the PDF ----------------------------------------------------------------------


def test_readers_download_the_data_and_each_download_is_audited(world, lot, client):
    report = issue(world, lot)
    version = report.versions.get()
    url = reverse("reporting:data", args=[report.pk, 1])
    for name in ("reviewer", "author"):
        client.force_login(world["people"][name])
        response = client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json; charset=utf-8"
        assert response["Content-Disposition"] == f'attachment; filename="{report.number}-v1.json"'
        assert response["Cache-Control"] == "no-store, private"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response.content == bytes(version.data)
    events = AuditEvent.objects.filter(action="report.data_downloaded", object_id=str(report.pk))
    assert events.count() == 2
    assert events.first().after == {"version": 1, "data_sha256": version.data_sha256}


def test_the_pages_offer_the_data_beside_the_pdf(world, lot, client):
    report = issue(world, lot)
    version = report.versions.get()
    client.force_login(world["people"]["reviewer"])
    url = reverse("reporting:data", args=[report.pk, 1])
    page = client.get(reverse("reporting:version", args=[report.pk, 1])).content.decode()
    assert f'href="{url}"' in page and "Download data" in page
    assert version.data_sha256 in page and PDF_FORMAT in page
    detail = client.get(reverse("reporting:detail", args=[report.pk])).content.decode()
    assert f'href="{url}"' in detail


def test_without_a_reading_role_the_data_is_refused_and_nothing_is_recorded(
    world, lot, client, django_user_model
):
    report = issue(world, lot)
    outsider = django_user_model.objects.create_user("synthetic_outsider", password="x" * 20)
    with pytest.raises(PermissionDenied):
        services.read_data(actor=outsider, version=report.versions.get())
    client.force_login(outsider)
    assert client.get(reverse("reporting:data", args=[report.pk, 1])).status_code == 403
    assert client.get(reverse("reporting:data", args=[report.pk + 99, 1])).status_code == 403
    client.logout()
    response = client.get(reverse("reporting:data", args=[report.pk, 1]))
    assert response.status_code == 302 and "/accounts/login/" in response["Location"]
    assert not AuditEvent.objects.filter(action="report.data_downloaded").exists()


def test_data_that_fails_its_checksum_is_not_served(world, lot, client):
    report = issue(world, lot)
    version = report.versions.get()
    version.data = bytes(version.data).replace(b"99.60", b"99.70")
    with pytest.raises(ValidationError, match="failed its integrity check"):
        services.read_data(actor=world["people"]["reviewer"], version=version)
    # Altered in the database (its guard switched off, as in a tampered copy): the page says so.
    with triggers_disabled("reporting_reportversion"):
        ReportVersion.objects.filter(pk=version.pk).update(data=version.data)
    client.force_login(world["people"]["reviewer"])
    response = client.get(reverse("reporting:data", args=[report.pk, 1]), follow=True)
    assert response.redirect_chain[0][0] == reverse("reporting:version", args=[report.pk, 1])
    assert "The stored certificate data failed its integrity check." in response.content.decode()
    assert not AuditEvent.objects.filter(action="report.data_downloaded").exists()


# Versions issued before -----------------------------------------------------------------------


def test_a_version_issued_before_has_no_data_and_keeps_its_pdf(world, lot, client, monkeypatch):
    report = legacy_issue(world, lot, monkeypatch)
    version = report.versions.get()
    assert version.data is None and version.data_sha256 == "" and version.pdf_format == ""
    with pytest.raises(ValidationError, match="issued before certificate data was produced"):
        services.read_data(actor=world["people"]["reviewer"], version=version)
    client.force_login(world["people"]["reviewer"])
    url = reverse("reporting:data", args=[report.pk, 1])
    response = client.get(url, follow=True)
    assert response.redirect_chain[0][0] == reverse("reporting:version", args=[report.pk, 1])
    page = response.content.decode()
    assert "issued before certificate data was produced" in page
    assert f'href="{url}"' not in page
    assert "Not declared (issued before certificates were written as archival PDF)" in page
    detail = client.get(reverse("reporting:detail", args=[report.pk])).content.decode()
    assert f'href="{url}"' not in detail
    assert client.get(reverse("reporting:pdf", args=[report.pk, 1])).content == bytes(version.pdf)
    assert not AuditEvent.objects.filter(action="report.data_downloaded").exists()


# Integrity of the stored data -----------------------------------------------------------------


def test_issued_data_cannot_be_changed_or_removed(world, lot):
    version = issue(world, lot).versions.get()
    for statement, args in (
        ("UPDATE reporting_reportversion SET data = %s WHERE id = %s", [b"{}", version.pk]),
        ("UPDATE reporting_reportversion SET data = NULL, data_sha256 = '' WHERE id = %s", None),
        ("UPDATE reporting_reportversion SET pdf_format = '' WHERE id = %s", None),
    ):
        with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(statement, args or [version.pk])
    version.refresh_from_db()
    assert hashlib.sha256(bytes(version.data)).hexdigest() == version.data_sha256


def test_data_and_its_checksum_are_stored_together(world, lot):
    version = issue(world, lot).versions.get()
    base = {
        field.attname: getattr(version, field.attname)
        for field in ReportVersion._meta.concrete_fields
        if field.name not in ("id", "number", "report_revision", "supersedes")
    }
    for broken in (
        {"data": b"{}", "data_sha256": ""},
        {"data": None, "data_sha256": "a" * 64},
        {"data": b"{}", "data_sha256": "a" * 64, "pdf_format": ""},
        {"data": None, "data_sha256": ""},  # declares the archival format without its data
    ):
        with pytest.raises(IntegrityError, match="reportversion_data"), transaction.atomic():
            ReportVersion.objects.create(**{**base, **broken, "number": 9, "report_revision": 99})


# The lot's complete record --------------------------------------------------------------------


def test_the_lot_record_keeps_each_data_file_and_checks_it(world, lot, monkeypatch):
    with_data = issue(world, lot, recipient="Synthetic general recipient")
    without = legacy_issue(world, lot, monkeypatch, recipient="Synthetic earlier recipient")
    package = lot_record.export_lot_record(
        actor=world["people"]["author"], lot_pk=lot.pk, purpose="Synthetic inspection request"
    )
    archive = zipfile.ZipFile(io.BytesIO(package.file.read()))
    names = archive.namelist()
    version = with_data.versions.get()
    (data_name,) = [n for n in names if n.endswith(f"{with_data.number}-v1-data.json")]
    assert archive.read(data_name) == bytes(version.data)
    assert any(n.endswith(f"{with_data.number}-v1.pdf") for n in names)
    assert any(n.endswith(f"{without.number}-v1.pdf") for n in names)
    assert not any(n.endswith(f"{without.number}-v1-data.json") for n in names)
    (record_name,) = [n for n in names if n.endswith("/record.json")]
    record = json.loads(archive.read(record_name))
    checks = [c for c in record["checks"] if c["check"] == "certificate data file"]
    assert [(c["describes"], c["outcome"]) for c in checks] == [(str(version), "intact")]
    assert lot_record.summarize(lot)["files"] == 3  # two PDFs and one data file
