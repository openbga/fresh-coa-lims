"""Evidence collection and release gates, judged on payloads (fixtures and live alike)."""

import copy
from decimal import Decimal

import pytest

from reporting import evidence as ev
from reporting.tests.conftest import build_lot

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def good(people, lot):
    return ev.collect_evidence(lot)


def test_complete_released_lot_has_no_blockers(good):
    assert ev.blockers(good) == []
    assert good["schema"] == ev.SCHEMA
    assert good["sections_supplied"] == []


def test_collection_is_deterministic(lot):
    assert ev.canonical_hash(ev.collect_evidence(lot)) == ev.canonical_hash(
        ev.collect_evidence(lot)
    )


def test_values_are_exact_decimal_text(people):
    lot = build_lot(people, number="SYN-DEC", value="100")
    result = ev.collect_evidence(lot)["samples"][0]["results"][0]
    assert result["value"] == "100"
    assert result["lower_limit"] == "98"
    assert Decimal(result["value"]) == Decimal("100.00000000")


def test_unreleased_lot_is_blocked(people):
    lot = build_lot(people, number="SYN-UNREL", release=False)
    problems = ev.blockers(ev.collect_evidence(lot))
    assert "The lot has no signed QC disposition." in problems
    assert any("no independent signed review" in p for p in problems)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda e: e["samples"][0]["results"].clear(), "No sample results"),
        (lambda e: e["rules"].update(required_tests=["assay", "identity"]), "missing required"),
        (lambda e: e["samples"][0]["results"][0].update(conforms=False), "outside its limits"),
        (lambda e: e["samples"][0]["results"][0].update(review=None), "no independent"),
        (
            lambda e: e["samples"][0]["results"][0]["review"].update(revision=99),
            "does not bind the current result",
        ),
        (
            lambda e: e["samples"][0]["results"][0]["review"].update(
                signer_id=e["samples"][0]["results"][0]["analyst_id"]
            ),
            "own analyst",
        ),
        (lambda e: e.update(disposition=None), "disposition record is missing"),
        (lambda e: e["disposition"].update(revision=99), "does not bind the current lot"),
        (
            lambda e: e["disposition"].update(
                signer_id=e["samples"][0]["results"][0]["analyst_id"]
            ),
            "signed by an analyst",
        ),
        (lambda e: e["holds"].append({"id": "H1", "status": "open"}), "Open hold"),
        (lambda e: e["holds"].append({"id": "H2", "status": "mystery"}), "Open hold"),
    ],
)
def test_each_gate_blocks(good, mutate, expected):
    payload = copy.deepcopy(good)
    mutate(payload)
    assert any(expected in p for p in ev.blockers(payload)), ev.blockers(payload)


def test_cleared_hold_does_not_block(good):
    good["holds"].append({"id": "H1", "status": "closed", "description": "Closed"})
    assert ev.blockers(good) == []


def test_registered_collector_is_frozen_into_evidence(lot):
    ev.register_collector("specification", lambda lot: {"code": "SPEC-1", "revision": 3})
    ev.register_collector("holds", lambda lot: [])
    payload = ev.collect_evidence(lot)
    assert payload["specification"] == {"code": "SPEC-1", "revision": 3}
    assert payload["sections_supplied"] == ["holds", "specification"]


def test_unknown_section_is_refused():
    with pytest.raises(ValueError):
        ev.register_collector("anything", lambda lot: None)


def test_independence_conflict_covers_every_author(people, lot):
    payload = ev.collect_evidence(lot)
    assert ev.independence_conflict(payload, people["analyst"])
    assert not ev.independence_conflict(payload, people["quality2"])


def test_changed_sections():
    assert ev.changed_sections({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 1}) == ["b", "c"]


def native_payload(good):
    """A native-testing payload shaped like quality's frozen disposition evidence."""
    payload = copy.deepcopy(good)
    payload["samples"][0]["results"] = []
    payload["native"] = {
        "assignment_id": 1,
        "assignment_hash": "a" * 64,
        "assignment_verified": True,
        "specification": {"code": "SPEC", "version": 1, "approved_hash": "b" * 64},
        "analytical": {
            "complete": True,
            "blockers": [],
            "author_ids": [payload["authors"][0]],
            "results": [
                {
                    "test_code": "assay",
                    "sample": "S1",
                    "unit": "mg/g",
                    "lower_limit": "98",
                    "upper_limit": None,
                    "reportable": "100.3",
                    "method": {"code": "M1", "revision": 2},
                    "requirement_source": "catalog:SPEC@1:" + "b" * 64,
                    "replicates": [{"replicate": 1, "value": "100.25"}],
                    "review": {"signer": "Reviewer", "signed_at": "2026-11-10T10:00:00+00:00"},
                }
            ],
        },
    }
    return payload


def test_native_evidence_passes_and_blocks(good):
    payload = native_payload(good)
    assert ev.blockers(payload) == []
    broken = native_payload(good)
    broken["native"]["assignment_verified"] = False
    assert any("could not be resolved and verified" in p for p in ev.blockers(broken))
    broken = native_payload(good)
    broken["native"]["analytical"]["results"][0]["review"] = None
    assert any("no independent signed review" in p for p in ev.blockers(broken))
    broken = native_payload(good)
    broken["native"]["analytical"].update(complete=False, blockers=["Missing test"])
    assert any("not complete" in p for p in ev.blockers(broken))
    broken = native_payload(good)
    broken["native"]["analytical"]["results"] = []
    assert any("No reportable native results" in p for p in ev.blockers(broken))
    broken = native_payload(good)
    broken["native"]["analytical"]["author_ids"] = [broken["disposition"]["signer_id"]]
    assert any("author of these results" in p for p in ev.blockers(broken))


def test_native_certificate_renders(people, good):
    from reporting.render import render_certificate
    from reporting.tests.test_services import flat, normalized, pdf_text

    payload = native_payload(good)
    payload["evidence_hash"] = ev.canonical_hash(good)
    payload["report"] = {
        "number": "CoA-N-1",
        "version": 1,
        "kind": "issue",
        "recipient": "",
        "remarks": "",
        "reason": "x",
        "amends_version": None,
        "issued_by": "Quality Synthetic",
        "issued_by_id": 1,
        "issued_at": "2026-11-10T12:00:00Z",
        "lot_revision": 5,
    }
    payload["specification"] = payload["native"]["specification"]
    payload["methods"] = [
        {
            "code": "M1",
            "version": 2,
            "revision_id": 9,
            "document_ref": "SOP-SYN-1 rev 1",
            "suitability_kind": "validation",
            "suitability_ref": "VAL-SYN-1 rev 1",
            "requires_batch": False,
            "qc_checks": [],
            "approved_hash": "c" * 64,
        }
    ]
    data = render_certificate(payload)
    text = pdf_text(data)
    spoken = normalized(text)  # wrapping differs by font; see normalized()
    squashed = flat(text)  # hashes may break anywhere
    for phrase in (
        "100.3 mg/g",
        "no upper limit",
        "M1 r2",
        "SPEC version 1",
        "M1 version 2",
        "controlled document SOP-SYN-1 rev 1",
        "suitability (validation) VAL-SYN-1 rev 1",  # complete type, reference and revision
    ):
        assert phrase in spoken, phrase
    assert "{'code'" not in text and "revision_id" not in text  # no Python dict repr
    assert "VAL-SYN-1rev1" not in spoken  # token boundaries are really checked
    assert "c" * 64 in squashed and "b" * 64 in squashed  # hashes kept, in technical identifiers
    assert len([p for p in text.split("\x0c") if p.strip()]) == 1  # compact certificate: one page
    assert "2026-11-10 10:00:00 UTC" in text


def result_types_payload(good):
    """Native evidence with results published after qualitative/less-than support was added."""
    payload = native_payload(good)
    legacy = payload["native"]["analytical"]["results"][0]
    new = {
        "result_type": "qualitative",
        "unit": "",
        "lower_limit": None,
        "upper_limit": None,
        "lower_inclusive": True,
        "upper_inclusive": True,
        "expected_result": "absent",
        "criterion": "Absent in 25 g",
        "acceptance": "Absent in 25 g (expected: Absent)",
        "mean": None,
        "reportable": "Absent",
    }
    count = {
        "result_type": "count",
        "unit": "CFU/g",
        "lower_limit": None,
        "upper_limit": "1000",
        "lower_inclusive": True,
        "upper_inclusive": False,
        "expected_result": None,
        "criterion": "",
        "acceptance": "less than 1000 CFU/g",
        "mean": None,
        "reportable": "<10; 50",
    }
    payload["native"]["analytical"]["results"] += [
        {
            **legacy,
            **new,
            "test_code": "pathogen",
            "replicates": [
                {"replicate": 1, "value": "Absent", "observed": "No growth"},
                {"replicate": 2, "value": "Absent", "observed": "No growth"},
            ],
        },
        {
            **legacy,
            **count,
            "test_code": "tamc",
            "replicates": [{"replicate": 1, "value": "<10"}, {"replicate": 2, "value": "50"}],
        },
    ]
    return payload


def certificate_row(html, code):
    start = html.index(f'<th scope="row">{code}')
    return " ".join(html[start : html.index("</tr>", start)].split())


def test_certificate_renders_frozen_and_new_evidence(good):
    from django.template.loader import render_to_string

    html = render_to_string("reporting/_certificate.html", {"snapshot": result_types_payload(good)})
    legacy = certificate_row(html, "assay")  # frozen before this change: no acceptance key
    assert "<td>100.25</td>" in legacy
    assert '<td class="text-end">100.3 mg/g</td>' in legacy
    assert "<td>98 to no upper limit mg/g</td>" in legacy
    pathogen = certificate_row(html, "pathogen")
    assert "<td>Absent; Absent</td>" in pathogen
    assert '<td class="text-end">Absent</td>' in pathogen
    assert "<td>Absent in 25 g (expected: Absent)</td>" in pathogen
    tamc = certificate_row(html, "tamc")
    assert "<td>&lt;10; 50</td>" in tamc
    assert '<td class="text-end">&lt;10; 50 CFU/g</td>' in tamc
    assert "<td>less than 1000 CFU/g</td>" in tamc
    assert "None" not in html


def test_certificate_pdf_renders_new_evidence(good):
    from reporting.render import render_certificate
    from reporting.tests.test_services import normalized, pdf_text

    payload = result_types_payload(good)
    payload["evidence_hash"] = ev.canonical_hash(good)
    payload["report"] = {
        "number": "CoA-RT-1",
        "version": 1,
        "kind": "issue",
        "recipient": "",
        "remarks": "",
        "reason": "x",
        "amends_version": None,
        "issued_by": "Quality Synthetic",
        "issued_by_id": 1,
        "issued_at": "2026-11-12T12:00:00Z",
        "lot_revision": 5,
    }
    spoken = normalized(pdf_text(render_certificate(payload)))
    for phrase in ("100.3 mg/g", "no upper limit", "Absent in 25 g", "<10; 50 CFU/g", "less than"):
        assert phrase in spoken, phrase
    assert "None" not in spoken
