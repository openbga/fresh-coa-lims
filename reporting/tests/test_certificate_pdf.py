"""The issued certificate PDF: every regulated element prints, statuses carry text and a glyph,
the renderer loads only its own font and icons, and issued bytes are never re-rendered.

The payloads below are synthetic frozen snapshots that fill every branch of
reporting/_certificate.html. .local/evidence/reports/checklist.md lists the same elements.
"""

import copy
import hashlib
import os
import pathlib
import re
import shutil
import subprocess

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from reporting import render, services
from reporting.tests.test_services import flat, issue, normalized

H = {"spec": "b" * 64, "spec2": "d" * 64, "method": "c" * 64, "assign": "a" * 64, "ev": "e" * 64}
REPORT = {
    "number": "CoA-SYN-900-1",
    "version": 2,
    "kind": "amendment",
    "recipient": "Synthetic Customer B",
    "remarks": "Synthetic remark line one\nSynthetic remark line two",
    "reason": "Synthetic amendment reason",
    "amends_version": 1,
    "issued_by": "Quality Synthetic",
    "issued_by_id": 1,
    "issued_at": "2026-11-12T12:00:00Z",
    "lot_revision": 7,
}
COMMON = {
    "evidence_hash": H["ev"],
    "lot": {
        "number": "SYN-900",
        "material": "Synthetic reference powder",
        "state": "released",
        "received_at": "2026-11-01T08:00:00Z",
        "received_by": "Analyst Synthetic",
    },
    "disposition": {
        "signer_name": "Disposition Synthetic",
        "signed_at": "2026-11-11T09:30:00Z",
        "revision": 6,
    },
    "rules": {
        "code": "RS-SYN",
        "version": 3,
        "revision": 4,
        "segment": "supplements",
        "effective_from": "2026-01-01T00:00:00Z",
        "effective_until": "2027-01-01T00:00:00Z",
        "required_tests": ["assay", "identity"],
    },
    "methods": [
        {
            "code": "M1",
            "version": 2,
            "document_ref": "SOP-SYN-1 rev 1",
            "suitability_kind": "validation",
            "suitability_ref": "VAL-SYN-1 rev 1",
            "requires_batch": True,
            "qc_checks": [{"kind": "blank"}, {"kind": "standard"}],
            "approved_hash": H["method"],
        },
        "Legacy method text M0",
    ],
    "sections_supplied": ["holds"],
    "holds": [
        {"id": "HOLD-SYN-1", "description": "Synthetic hold description", "status": "cleared"}
    ],
    "corrections": [{"description": "Synthetic correction description"}],
    "report": REPORT,
}


def native_full():
    """Native testing: additional rules, two specifications, a requirement decision, a contract
    laboratory result, an unreviewed result, supplier results (accepted and not), investigations."""
    review = {"signer": "Reviewer Synthetic", "signed_at": "2026-11-10T10:00:00Z", "revision": 3}
    base = {
        "sample": "S1",
        "unit": "mg/g",
        "lower_limit": "98",
        "upper_limit": None,
        "reportable": "100.3",
        "method": {"code": "M1", "revision": 2},
        "requirement_source": "catalog:SPEC@1:" + H["spec"],
        "replicates": [{"replicate": 1, "value": "100.25"}, {"replicate": 2, "value": "100.35"}],
        "review": review,
    }
    supplier = {
        "test_code": "heavy-metals",
        "name": "Heavy metals",
        "label": "SRA-7",
        "unit": "ppm",
        "stated": {
            "result": "<5",
            "wording": "Complies",
            "method": "Supplier method SM-1",
            "limits": "NMT 10 ppm",
        },
        "criterion": "not more than 10 ppm",
        "certificate": {"number": "SUP-COA-77", "issued_on": "2026-10-20", "issued_by": "Synth Co"},
        "supplier": {"name": "Synthetic Ingredients Supply", "location": "Synthville"},
        "qualification": {"label": "SQ-3", "evidence_ref": "AUDIT-SYN-2026"},
        "requirement_source": "catalog:SPEC2@4:" + H["spec2"],
        "signature": {
            "signer": "Reviewer Synthetic",
            "signed_at": "2026-11-09T08:00:00Z",
            "revision": 2,
        },
    }
    payload = copy.deepcopy(COMMON)
    payload["samples"] = []
    payload["specification"] = {}
    payload["native"] = {
        "assignment_hash": H["assign"],
        "additional_rules": [
            {"code": "RS-EU", "version": 1, "segment": "supplements", "required_tests": ["lead"]}
        ],
        "specifications": [
            {"code": "SPEC", "version": 1, "scope": "material", "approved_hash": H["spec"]},
            {"code": "SPEC2", "version": 4, "scope": "market EU", "approved_hash": H["spec2"]},
        ],
        "decisions": [
            {
                "code": "assay",
                "differs": ["SPEC2 v4"],
                "applies": {
                    "specification": "SPEC v1",
                    "scopes": ["material"],
                    "requirement": "98 to no upper limit mg/g",
                },
                "not_applied": [
                    {
                        "specification": "SPEC2 v4",
                        "scopes": ["market EU"],
                        "requirement": "99 to 101 mg/g",
                    }
                ],
                "decided": {
                    "by": "Quality Synthetic",
                    "at": "2026-11-05T11:00:00Z",
                    "with": "replacement",
                    "reason": "Synthetic decision reason.",
                    "carried": {"by": "Quality Second", "at": "2026-11-06T11:00:00Z"},
                },
            }
        ],
        "analytical": {
            "results": [
                {**base, "test_code": "assay", "name": "Assay (HPLC)"},
                {
                    **base,
                    "test_code": "identity",
                    "name": "Identity",
                    "unit": "",
                    "lower_limit": None,
                    "acceptance": "Conforms to reference (expected: Conforms)",
                    "reportable": "Conforms",
                    "replicates": [{"replicate": 1, "value": "Conforms"}],
                    "contract_laboratory": {
                        "name": "Synthetic Contract Lab",
                        "location": "Testtown",
                        "report_number": "CL-SYN-55",
                        "report_date": "2026-11-08",
                    },
                },
                {**base, "test_code": "water", "name": "Water", "review": None, "upper_limit": "5"},
            ],
            "supplier_results": [
                supplier,
                {**supplier, "test_code": "arsenic", "name": "Arsenic", "signature": None},
            ],
            "investigations": [
                {
                    "investigation": "INV-SYN-4",
                    "trigger": "OOS water",
                    "outcome": "Laboratory error confirmed",
                    "conclusion": {
                        "signer": "Quality Synthetic",
                        "signed_at": "2026-11-07T15:00:00Z",
                    },
                },
                {"investigation": "INV-SYN-5", "trigger": "Atypical assay", "outcome": ""},
            ],
        },
    }
    return payload


def foundation_full():
    """Manual foundation results: a conforming reviewed result and an out-of-limits unreviewed
    one, with a frozen specification given as sections, and an issue (not an amendment)."""
    payload = copy.deepcopy(COMMON)
    payload["report"] = {
        **REPORT,
        "kind": "issue",
        "version": 1,
        "amends_version": None,
        "recipient": "",
    }
    payload["specification"] = {"appearance": "White powder", "assay": "98 to 101 mg/g"}
    payload["samples"] = [
        {
            "reference": "SYN-900-S1",
            "collected_at": "2026-11-02T07:00:00Z",
            "results": [
                {
                    "test_code": "assay",
                    "value": "99.5",
                    "unit": "mg/g",
                    "lower_limit": "98",
                    "upper_limit": "101",
                    "conforms": True,
                    "analyst": "Analyst Synthetic",
                    "review": {
                        "signer_name": "Reviewer Synthetic",
                        "signed_at": "2026-11-03T10:00:00Z",
                        "revision": 2,
                    },
                },
                {
                    "test_code": "water",
                    "value": "6.1",
                    "unit": "%",
                    "lower_limit": "0",
                    "upper_limit": "5",
                    "conforms": False,
                    "analyst": "Analyst Synthetic",
                    "review": None,
                },
            ],
        }
    ]
    payload["sections_supplied"] = []
    payload["holds"] = []
    payload["corrections"] = []
    return payload


NATIVE_PHRASES = (
    # Identity and amendment
    "Certificate of analysis · CoA-SYN-900-1 version 2",
    "CoA-SYN-900-1 · version 2 · lot SYN-900",
    "Amended certificate. Replaces version 1; the earlier version remains on record.",
    "Reason for amendment: Synthetic amendment reason",
    # Material and lot
    "LOT NUMBER SYN-900",
    "Synthetic reference powder",
    "ISSUED TO Synthetic Customer B",
    "2026-11-01 08:00:00 UTC by Analyst Synthetic",
    # Decision
    "Laboratory QC disposition: approved (lot state released), signed by Disposition Synthetic on "
    "2026-11-11 09:30:00 UTC, binding lot record revision 6.",
    "This certificate reports the laboratory QC disposition and test results only. It is not the "
    "manufacturer's batch release or qualified-person certification.",
    # Rules, specifications, methods
    "RS-SYN version 3 (record revision 4), segment supplements",
    "2026-01-01 00:00:00 UTC to 2027-01-01 00:00:00 UTC",
    "REQUIRED TESTS assay, identity",
    "RS-EU version 1, segment supplements · requires lead",
    "SPEC version 1 (scope material)",
    "SPEC2 version 4 (scope market EU)",
    "M1 version 2 · controlled document SOP-SYN-1 rev 1 · suitability (validation) VAL-SYN-1 rev 1 "
    "· batch QC required (2 checks)",
    "Legacy method text M0",
    # Requirement decisions
    "The specifications that apply to this lot state a test differently.",
    "assay (stated differently in SPEC2 v4): SPEC v1 (material) applies, 98 to no upper limit "
    "mg/g. Not applied: SPEC2 v4 (market EU), 99 to 101 mg/g.",
    "Decided by Quality Synthetic on 2026-11-05 11:00:00 UTC",
    "with the replacement of the lot's requirements: Synthetic decision reason.",
    "Carried unchanged by the replacement of the lot's requirements signed by Quality Second on",
    # Native results
    "Assay (HPLC)",
    "M1 r2",
    "100.25; 100.35",
    "100.3 mg/g",
    "98 to no upper limit mg/g",
    "Conforms to reference (expected: Conforms)",
    "Tested by contract laboratory Synthetic Contract Lab, Testtown. Report CL-SYN-55 dated "
    "2026-11-08.",
    "Not reviewed",
    # Supplier results
    "Results accepted from the supplier's certificate of analysis.",
    "This laboratory did not perform these tests.",
    "<5 ppm",
    "Stated as: Complies",
    "Supplier method SM-1",
    "Limits stated: NMT 10 ppm",
    "not more than 10 ppm",
    "SUP-COA-77 dated 2026-10-20, issued by Synth Co",
    "Supplier Synthetic Ingredients Supply, Synthville. Qualification SQ-3:",
    "Not accepted",
    # Holds, investigations, corrections, remarks
    "Synthetic hold description · cleared",
    "Investigations linked to this lot:",
    "INV-SYN-4 · OOS water · Laboratory error confirmed · concluded by Quality Synthetic",
    "INV-SYN-5 · Atypical assay · outcome not recorded",
    "Correction: Synthetic correction description",
    "REMARKS",
    "Synthetic remark line one",
    "Synthetic remark line two",
    # Signatures, bound revisions
    "ELECTRONIC SIGNATURES",
    "Test S1 assay reviewed",
    "Test record revision 3",
    "Supplier result heavy-metals accepted in place of a test",
    "Acceptance SRA-7 revision 2",
    "QC disposition approved",
    "Lot revision 6",
    "Certificate amended",
    "Certificate version 2",
    # Technical identifiers
    "TECHNICAL IDENTIFIERS",
    "ASSIGNMENT HASH",
    "REQUIREMENT SOURCE",
    "EVIDENCE SHA-256",
    # Every page
    "Page 1 of",
    "Synthetic demonstration data. This document has no regulatory or commercial standing.",
    "OpenBGA QM LIMS",
)
FOUNDATION_PHRASES = (
    "Certificate of analysis · CoA-SYN-900-1 version 1",
    "Certificate issued",
    "Certificate version 1",
    "appearance: White powder; assay: 98 to 101 mg/g",
    "Sample SYN-900-S1 · collected 2026-11-02 07:00:00 UTC",
    "99.5",
    "98 to 101 mg/g",
    "Conforms",
    "Out of limits",
    "Not reviewed",
    "Reviewer Synthetic",
    "Result SYN-900-S1 assay reviewed",
    "Result revision 2",
    "A hold snapshot was not available to this system; hold status is not asserted by this "
    "certificate.",
    "EVIDENCE SHA-256",
)


def pdf_text(data):
    """Text in reading order (pdftotext -raw): a table cell's wrapped lines stay together, where
    -layout interleaves them with the neighbouring columns. Pages are separated by form feeds."""
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext (poppler) is not installed")
    out = subprocess.run(
        ["pdftotext", "-raw", "-", "-"], input=data, capture_output=True, check=True
    )
    return out.stdout.decode()


def rendered(payload, synthetic_notice=True):
    return pdf_text(render.render_certificate(payload, synthetic_notice=synthetic_notice))


@pytest.mark.parametrize(
    ("payload", "phrases"),
    [(native_full, NATIVE_PHRASES), (foundation_full, FOUNDATION_PHRASES)],
    ids=["native", "foundation"],
)
def test_every_regulated_element_prints(payload, phrases):
    """Labels, table heads and section titles print in capitals (the Line label case), so the
    phrases name them as printed."""
    text = rendered(payload())
    spoken = normalized(text)  # wrapping differs by font; see normalized()
    for phrase in phrases:
        assert phrase in spoken, phrase
    squashed = flat(text)
    if payload is native_full:  # identifiers may break after a hyphen
        assert "QualificationSQ-3:AUDIT-SYN-2026." in flat(text)
    native = payload is native_full
    for digest in (H["ev"], H["method"]) + ((H["spec"], H["spec2"], H["assign"]) if native else ()):
        assert digest in squashed
    assert "None" not in spoken and "{'" not in text


def test_every_page_carries_identity_and_no_result_row_splits():
    payload = foundation_full()
    row = payload["samples"][0]["results"][0]
    payload["samples"][0]["results"] = [
        {**row, "test_code": f"impurity-{n:02d}"} for n in range(70)
    ]
    pages = [page for page in rendered(payload).split("\x0c") if page.strip()]
    assert len(pages) >= 3
    for number, page in enumerate(pages, 1):
        spoken = normalized(page)
        assert "OpenBGA QM LIMS" in spoken, number
        assert "CoA-SYN-900-1 · version 1 · lot SYN-900" in spoken, number
        assert f"Page {number} of {len(pages)}" in spoken, number
        codes = len(re.findall(r"impurity-\d\d 99\.5 ", spoken))  # result rows, not signatures
        if codes:  # the table head repeats, and each row prints whole on one page
            assert "INDEPENDENT REVIEW" in spoken, number
            assert spoken.count("Conforms") == codes, number
            assert spoken.count("Reviewer Synthetic") >= codes, number


def test_status_prints_text_and_glyph():
    """Black and white safe: each status prints its words and a black glyph for its recorded tone,
    and the renderer loads its own font and glyphs only."""
    html = render_to_string("reporting/pdf/certificate.html", {"snapshot": foundation_full()})
    for words, tone in (
        ("Conforms", "success"),
        ("Out of limits", "danger"),
        ("Not reviewed", "warning"),
    ):
        assert f'data-tone="{tone}">{words}</span>' in html
    data, served = render.write_pdf(html)
    assert served == {
        render.FONT_URL,
        *(f"{render.ICON_URL}{name}" for name in render.TONE_ICONS.values()),
    }
    assert data.startswith(b"%PDF-")
    for name in render.TONE_ICONS.values():
        glyph = render.resources()[f"{render.ICON_URL}{name}"][0]
        assert glyph.startswith(b"<svg") and b'fill="#000"' in glyph and b"<path" in glyph


def test_missing_font_fails_the_render(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "_font_path", lambda: tmp_path / "absent.woff2")
    with pytest.raises(render.RenderError, match="font"):
        render.render_certificate(foundation_full())


@pytest.mark.django_db(transaction=True)
def test_issued_bytes_are_served_unchanged_after_restyle(people, lot, client, monkeypatch):
    """An issued certificate is its stored bytes. One issued before a restyle (here: bytes the
    old renderer would have produced) downloads byte for byte, and nothing renders it again."""
    legacy = b"%PDF-1.7\n% synthetic certificate rendered before the Line restyle\n%%EOF\n"
    monkeypatch.setattr(services, "render_certificate", lambda *args, **kwargs: legacy)
    report = issue(people, lot)
    version = report.versions.get()
    assert bytes(version.pdf) == legacy

    def refuse(*args, **kwargs):
        raise AssertionError("an issued certificate was rendered again")

    monkeypatch.setattr(services, "render_certificate", refuse)
    monkeypatch.setattr(render, "render_certificate", refuse)
    monkeypatch.setattr(render, "write_pdf", refuse)
    client.force_login(people["auditor"])
    response = client.get(reverse("reporting:pdf", args=[report.pk, version.number]))
    assert response.status_code == 200
    assert response.content == legacy
    assert hashlib.sha256(response.content).hexdigest() == version.pdf_sha256
    for name, args in (("detail", [report.pk]), ("version", [report.pk, version.number])):
        assert client.get(reverse(f"reporting:{name}", args=args)).status_code == 200


def test_no_synthetic_notice_when_switched_off():
    assert "Synthetic demonstration data" not in rendered(foundation_full(), synthetic_notice=False)


def test_write_certificate_review_pdfs():
    """Visual inspection aid: set OQ_PDF_OUT to a directory to keep the full sample PDFs."""
    out = os.environ.get("OQ_PDF_OUT")
    if not out:
        pytest.skip("OQ_PDF_OUT not set")
    for name, payload in (("native-full", native_full), ("foundation-full", foundation_full)):
        pathlib.Path(out, f"{name}.pdf").write_bytes(render.render_certificate(payload()))
