"""Certificates for a customer or a market from the same lot, and each result judged against
every specification that applies to the lot.

A lot assigned under the general scope and a market scope whose specification states the assay
differently is released against the statement quality chose. Its certificate states how every
result compares with each specification, and a certificate issued for one scope reports that
scope's tests and limits only and is refused unless each result meets them.

Uses the production adapters and service-created approvals only (synthetic data).
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from analytical.contracts import Reading
from catalog import services as catalog
from catalog.models import SpecificationRevision
from core.models import AuditEvent, ElectronicSignature
from reporting import conformity
from reporting import services as reporting
from reporting.models import Report
from tests.test_integrated_journey import PIN, approve, dispose
from tests.test_requirement_applicability import (
    ASSAY,
    READINGS,
    TIGHT,
    WATER,
    assign,
    complete,
    decide,
    lot_of,
    overlay,
    sample_and_tests,
)
from tests.test_result_types_journey import build_world, record, review, submit

pytestmark = pytest.mark.django_db(transaction=True)

MARKET = "eu-market"


@pytest.fixture
def world(django_user_model):
    return build_world(django_user_model, with_assay=True)


def released(world, *lines, choice=MARKET, readings=None):
    """The lot under the general scope and the market scope (whose specification states
    ``lines``), decided for ``choice`` where they differ, tested and released."""
    overlay(world, MARKET, *lines)
    held = assign(world, "general", MARKET)
    if held.status == "hold":
        decide(world, choices={"assay": choice})
    merged = {**READINGS, **(readings or {})}
    for code, test in sample_and_tests(world).items():
        record(world, test, merged[code])
        submit(world, test)
        review(world, test)
    lot = dispose(world, world["people"]["approver"])
    assert lot.state == "released"
    return lot


def statements(evidence, code):
    (row,) = [r for r in evidence["native"]["conformity"] if r["test_code"] == code]
    return {s["scope"]: s for s in row["statements"]}


def issue(world, lot, scope="", recipient="Synthetic customer EU", who="author"):
    evidence, digest, blockers = reporting.preview(lot, scope)
    assert blockers == [], blockers
    return reporting.issue_report(
        actor=world["people"][who],
        pin=PIN,
        lot=lot,
        recipient=recipient,
        evidence_hash=digest,
        reason="Synthetic customer certificate",
        scope=scope,
    )


def flat(snapshot):
    return " ".join(render_to_string("reporting/_certificate.html", {"snapshot": snapshot}).split())


# Each result judged against every specification ----------------------------------------------


def test_each_result_is_judged_against_every_specification_that_states_its_test(world):
    lot = released(world, TIGHT)
    evidence, _, blockers = reporting.preview(lot)
    assert blockers == []
    assay = statements(evidence, "assay")
    assert assay["general"] == {
        "scope": "general",
        "specification": "synthetic-rt-spec version 1",
        "revision_id": assay["general"]["revision_id"],
        "applied": False,
        "required": True,
        "requirement": "98 – 102 % · rounded to 2 decimals",
        "result": "99.60 %",
        "outcome": conformity.CONFORMS,
        "reason": "",
    }
    assert assay[MARKET]["applied"] is True and assay[MARKET]["outcome"] == conformity.CONFORMS
    assert assay[MARKET]["requirement"] == "99 – 101 % · rounded to 2 decimals"
    # A test only the general specification states is judged against it alone.
    impurity = statements(evidence, "impurity")
    assert set(impurity) == {"general"} and impurity["general"]["applied"] is True
    identity = statements(evidence, "identity")["general"]
    assert identity["result"] == "Conforms" and identity["outcome"] == conformity.CONFORMS
    assert {row["origin"] for row in evidence["native"]["conformity"]} == {"laboratory"}


def test_a_result_that_meets_the_applied_statement_can_fail_another_specification(world):
    lot = released(world, TIGHT, choice="general", readings={"assay": "98.50"})
    evidence, _, blockers = reporting.preview(lot)
    assert blockers == [], "the general certificate states it; it does not refuse it"
    assay = statements(evidence, "assay")
    assert assay["general"]["applied"] and assay["general"]["outcome"] == conformity.CONFORMS
    assert assay[MARKET]["outcome"] == conformity.FAILS
    assert assay[MARKET]["result"] == "98.50 %"
    report = issue(world, lot, recipient="Synthetic general recipient")
    text = flat(report.versions.get(number=1).snapshot)
    assert "Conformity with each specification" in text
    assert "synthetic-rt-eu-market version 1 (eu-market)" in text
    assert "Does not conform" in text and "Measurement uncertainty is not taken" in text
    # A certificate for the market is refused: the result does not meet its specification.
    _, _, refused = reporting.preview(lot, MARKET)
    assert refused == [
        "SYN-RT-S001 assay: the result 98.50 % does not meet synthetic-rt-eu-market version 1 "
        "(eu-market), 99 – 101 % · rounded to 2 decimals."
    ]


def test_a_specification_rounds_the_result_to_its_own_precision(world):
    lot = released(world, {**TIGHT, "reporting_decimals": 1}, choice="general")
    assay = statements(reporting.preview(lot)[0], "assay")
    assert assay["general"]["result"] == "99.60 %"
    assert assay[MARKET]["result"] == "99.6 %" and assay[MARKET]["outcome"] == conformity.CONFORMS
    assert assay[MARKET]["requirement"] == "99 – 101 % · rounded to 1 decimals"


def test_a_limit_that_excludes_its_boundary_is_judged_as_stated(world):
    lot = released(
        world,
        {**TIGHT, "lower_limit": Decimal("99.60"), "lower_inclusive": False},
        choice="general",
    )
    assay = statements(reporting.preview(lot)[0], "assay")[MARKET]
    assert assay["outcome"] == conformity.FAILS
    assert assay["requirement"].startswith("> 99.6 and ≤ 101 %")


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"unit": "mg/g"}, "it states the result in mg/g; the result is in %"),
        ({"replicates": 2}, "it states 2 replicates; 1 was recorded"),
        (
            {
                "result_type": "count",
                "unit": "%",
                "lower_limit": Decimal("99"),
                "upper_limit": Decimal("101"),
            },
            "it states the result as a count; the result is a number",
        ),
    ],
)
def test_a_statement_that_cannot_be_compared_is_not_judged_and_says_why(world, change, reason):
    lot = released(world, {**TIGHT, **change}, choice="general")
    assay = statements(reporting.preview(lot)[0], "assay")[MARKET]
    assert assay["outcome"] == conformity.NOT_JUDGED
    assert assay["reason"] == reason
    assert assay["result"] == "99.60 %"
    _, _, refused = reporting.preview(lot, MARKET)
    assert refused == [
        f"SYN-RT-S001 assay: the result cannot be judged against synthetic-rt-eu-market "
        f"version 1 (eu-market): {reason}."
    ]


def test_a_statement_of_another_method_is_not_judged(world):
    start, end = timezone.now() - timedelta(days=1), timezone.now() + timedelta(days=365)
    other, revision = catalog.create_method(
        actor=world["people"]["author"],
        code="synthetic-rt-other",
        title="Synthetic other method",
        technique="Titration",
        document_ref="SOP-SYN-OTHER rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-OTHER rev 1",
        requires_batch=False,
        effective_from=start,
        effective_until=end,
        reason="Synthetic other method",
    )
    approve(revision, world["people"]["approver"])
    _, spec = catalog.create_specification(
        actor=world["people"]["author"],
        code=f"synthetic-rt-{MARKET}",
        title="Synthetic market specification",
        material=world["material"],
        stage="incoming",
        scope=MARKET,
        basis="Synthetic overlay limits",
        effective_from=start,
        effective_until=end,
        reason="Synthetic overlay",
    )
    catalog.add_test_line(
        actor=world["people"]["author"],
        revision=spec,
        reason="Synthetic line",
        method=other,
        **{**ASSAY, "required": True, "replicates": 1, "max_retests": 0},
    )
    approve(spec, world["people"]["approver"])
    assert assign(world, "general", MARKET).status == "hold"
    decide(world, choices={"assay": "general"})
    complete(world, sample_and_tests(world))
    lot = dispose(world, world["people"]["approver"])
    assay = statements(reporting.preview(lot)[0], "assay")[MARKET]
    assert assay["outcome"] == conformity.NOT_JUDGED
    assert assay["reason"] == (
        "it states method synthetic-rt-other; the result was obtained with method "
        "synthetic-rt-method version 1"
    )


def test_a_statement_for_information_states_no_conformity(world):
    lot = released(world, {**TIGHT, "required": False}, choice="general")
    assay = statements(reporting.preview(lot)[0], "assay")[MARKET]
    assert assay["outcome"] == conformity.INFORMATION and assay["required"] is False
    assert assay["result"] == "99.60 %"


def test_a_lot_under_one_specification_keeps_the_evidence_it_always_had(world):
    assign(world)
    complete(world, sample_and_tests(world))
    lot = dispose(world, world["people"]["approver"])
    evidence, _, _ = reporting.preview(lot)
    assert "conformity" not in evidence["native"]
    assert conformity.scopes(evidence) == {}
    _, _, refused = reporting.preview(lot, "general")
    assert refused == [
        "The lot's requirements name no specification for scope general; a certificate for it "
        "cannot be issued."
    ]
    text = flat(issue(world, lot, recipient="Synthetic recipient").versions.get().snapshot)
    assert "Conformity with each specification" not in text and "Certificate for" not in text


def test_a_specification_whose_approved_content_changed_is_not_judged(world):
    lot = released(world, TIGHT)
    revision_id = statements(reporting.preview(lot)[0], "assay")[MARKET]["revision_id"]
    # The guard refuses a change to approved content; a payload naming another hash is what an
    # altered record would look like to the certificate.
    with pytest.raises(DatabaseError), transaction.atomic():
        SpecificationRevision.objects.filter(pk=revision_id).update(approved_hash="0" * 64)
    lines = conformity._approved_lines(
        [{"revision_id": revision_id, "approved_hash": "f" * 64, "code": "x", "version": 1}]
    )
    assert lines == {revision_id: None}


# A certificate for one scope ------------------------------------------------------------------


def test_quality_issues_a_certificate_for_a_customer_scope_with_its_tests_and_limits(world):
    lot = released(world, TIGHT, WATER)
    evidence, _, _ = reporting.preview(lot)
    assert list(conformity.scopes(evidence)) == ["general", MARKET]
    report = issue(world, lot, scope=MARKET)
    assert report.scope == MARKET and report.state == "issued"
    version = report.versions.get(number=1)
    assert version.snapshot["report"]["scope"] == MARKET
    assert version.pdf_sha256 and bytes(version.pdf).startswith(b"%PDF-")
    opened = AuditEvent.objects.get(action="report.opened", object_id=str(report.pk))
    assert opened.after["scope"] == MARKET
    view = conformity.scope_view(version.snapshot, MARKET)
    assert [row["result"]["test_code"] for row in view["results"]] == ["assay", "water"]
    assert [m["code"] for m in view["methods"]] == ["synthetic-rt-method"]
    text = flat(version.snapshot)
    assert "Certificate for</dt><dd>Scope eu-market" in text.replace("> <", "><")
    assert "This certificate is issued for scope eu-market." in text
    assert "synthetic-rt-eu-market version 1 (scope eu-market)" in text
    assert "99 – 101 % · rounded to 2 decimals" in text
    # It names no other scope, specification or decision, and lists only its own tests.
    for absent in ("synthetic-rt-spec", "general)", "Not applied", "Decided by", "impurity"):
        assert absent not in text, absent
    assert "Test SYN-RT-S001 identity reviewed" not in text
    assert "Test SYN-RT-S001 assay reviewed" in text


def test_a_certificate_for_the_general_scope_reports_its_statement(world):
    lot = released(world, TIGHT)
    report = issue(world, lot, scope="general", recipient="Synthetic general customer")
    view = conformity.scope_view(report.versions.get().snapshot, "general")
    assay = next(r for r in view["results"] if r["result"]["test_code"] == "assay")
    assert assay["statement"]["requirement"] == "98 – 102 % · rounded to 2 decimals"
    assert not assay["statement"]["applied"]


def test_a_scope_the_lot_does_not_have_is_refused(world):
    lot = released(world, TIGHT)
    message = "The lot's requirements name no specification for scope us-market"
    with pytest.raises(ValidationError, match=message):
        reporting.issue_report(
            actor=world["people"]["author"],
            pin=PIN,
            lot=lot,
            recipient="Synthetic",
            evidence_hash=reporting.preview(lot)[1],
            reason="Synthetic",
            scope="us-market",
        )
    assert not Report.objects.exists(), "a refused issue leaves no numbered head behind"


def test_a_scope_certificate_is_refused_when_a_result_fails_its_specification(world):
    lot = released(world, TIGHT, choice="general", readings={"assay": "98.50"})
    with pytest.raises(ValidationError, match="does not meet synthetic-rt-eu-market"):
        reporting.issue_report(
            actor=world["people"]["author"],
            pin=PIN,
            lot=lot,
            recipient="Synthetic customer EU",
            evidence_hash=reporting.preview(lot, MARKET)[1],
            reason="Synthetic",
            scope=MARKET,
        )
    assert not Report.objects.exists()
    assert not ElectronicSignature.objects.filter(meaning="issued").exists()
    # The general certificate of the same lot is issued, and says so.
    assert issue(world, lot, recipient="Synthetic general").scope == ""


def test_independence_and_role_still_apply_to_a_scope_certificate(world, django_user_model):
    lot = released(world, TIGHT)
    digest = reporting.preview(lot, MARKET)[1]
    # The analyst recorded the lot's data, and holds the quality role too.
    with pytest.raises(PermissionDenied):
        reporting.issue_report(
            actor=world["people"]["analyst"],
            pin=PIN,
            lot=lot,
            recipient="Synthetic",
            evidence_hash=digest,
            reason="Synthetic",
            scope=MARKET,
        )
    with pytest.raises(PermissionDenied):
        reporting.issue_report(
            actor=world["people"]["reviewer"],
            pin=PIN,
            lot=lot,
            recipient="Synthetic",
            evidence_hash=digest,
            reason="Synthetic",
            scope=MARKET,
        )
    with pytest.raises(ValidationError, match="evidence changed"):
        reporting.issue_report(
            actor=world["people"]["author"],
            pin=PIN,
            lot=lot,
            recipient="Synthetic",
            evidence_hash="0" * 64,
            reason="Synthetic",
            scope=MARKET,
        )
    assert not Report.objects.exists()


def test_the_scope_of_a_certificate_never_changes(world):
    lot = released(world, TIGHT)
    report = issue(world, lot, scope=MARKET)
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        Report.objects.filter(pk=report.pk).update(scope="general")
    # The same recipient's open certificate is amended, not reissued for another scope.
    with pytest.raises(ValidationError, match="already open for this recipient"):
        issue(world, lot, scope="general")
    amended = reporting.amend_report(
        actor=world["people"]["author"],
        pin=PIN,
        report=report,
        expected_version=1,
        evidence_hash=reporting.preview(lot, MARKET)[1],
        reason="Synthetic wording amendment",
    )
    second = amended.versions.get(number=2)
    assert amended.scope == MARKET and second.snapshot["report"]["scope"] == MARKET
    assert conformity.scope_view(second.snapshot, MARKET) is not None


def test_a_withdrawn_scope_certificate_leaves_room_for_another_scope(world):
    lot = released(world, TIGHT)
    report = issue(world, lot, scope=MARKET)
    reporting.withdraw_report(
        actor=world["people"]["author"],
        pin=PIN,
        report=report,
        expected_revision=Report.objects.get(pk=report.pk).revision,
        reason="Synthetic: issued for the wrong scope",
    )
    again = issue(world, lot_of(world), scope="general")
    assert again.number != report.number and again.scope == "general"


# The judgement itself, on frozen values -------------------------------------------------------


def _line(**changes):
    return {
        "code": "assay",
        "name": "Assay",
        "method": "synthetic-m",
        "result_type": "numeric",
        "unit": "%",
        "lower_limit": "99",
        "upper_limit": "101",
        "lower_inclusive": True,
        "upper_inclusive": True,
        "reporting_decimals": 1,
        "expected_text": "",
        "expected_result": "",
        "required": True,
        "replicates": 1,
        "replicate_limits": True,
        "max_retests": 0,
        **changes,
    }


FROZEN = {
    "result_type": "numeric",
    "unit": "%",
    "method": {
        "revision_id": 1,
        "code": "synthetic-m",
        "version": 1,
        "document_ref": "SOP",
        "suitability_kind": "validation",
        "suitability_ref": "VAL",
        "requires_batch": False,
        "qc_checks": [],
        "requires_equipment": False,
        "requires_reagent": False,
        "calculation": None,
        "approved_hash": "a" * 64,
    },
}
SPEC = {"scope": MARKET, "code": "synthetic-s", "version": 2, "revision_id": 9}


def _stated(value, qualifier="", outcome=""):
    return SimpleNamespace(
        value=None if value is None else Decimal(value),
        qualifier=qualifier,
        outcome=outcome,
        value_text=f"{qualifier}{value}",
        conforms=True,
    )


@pytest.mark.parametrize(
    ("value", "qualifier", "outcome"),
    [
        ("100.04", "", conformity.CONFORMS),
        ("98.96", "", conformity.FAILS),  # a supplier's result is never rounded first
        ("101", "", conformity.CONFORMS),
        ("10", "<", conformity.FAILS),  # a less-than result cannot meet a lower limit
    ],
)
def test_a_suppliers_result_is_compared_exactly_as_stated(value, qualifier, outcome):
    line = _line()
    statement = conformity._statement(SPEC, line, applied=False)
    judged = conformity._judge_stated(
        _stated(value, qualifier), FROZEN, statement, line, SPEC, applied=False
    )
    assert judged["outcome"] == outcome, judged


def test_a_suppliers_result_of_another_method_is_still_judged():
    line = _line(method="another-method")
    statement = conformity._statement(SPEC, line, applied=False)
    judged = conformity._judge_stated(_stated("100"), FROZEN, statement, line, SPEC, False)
    assert judged["outcome"] == conformity.CONFORMS


def test_laboratory_readings_are_evaluated_as_testing_evaluates_them():
    readings = [Reading(value=Decimal("98.96")), Reading(value=Decimal("99.06"))]
    test = SimpleNamespace(
        current_observations=lambda: [SimpleNamespace(reading=r) for r in readings],
        reportable_display="99.01",
        spec=None,
    )
    line = _line(replicates=2, replicate_limits=True)
    statement = conformity._statement(SPEC, line, applied=False)
    judged = conformity._judge_test(test, FROZEN, statement, line, SPEC, applied=False)
    # The mean 99.01 rounds to 99.0 and meets 99 – 101, but one replicate does not.
    assert (judged["outcome"], judged["result"]) == (conformity.FAILS, "99.0 %")
    line = _line(replicates=2, replicate_limits=False)
    judged = conformity._judge_test(test, FROZEN, statement, line, SPEC, applied=False)
    assert judged["outcome"] == conformity.CONFORMS


def _evidence(rows, specs=None):
    specs = specs or [
        {"scope": "general", "code": "g", "version": 1, "revision_id": 1, "approved_hash": "h"},
        {"scope": MARKET, "code": "m", "version": 1, "revision_id": 2, "approved_hash": "h"},
    ]
    return {
        "native": {
            "specifications": specs,
            "conformity": rows,
            "analytical": {"results": [], "supplier_results": []},
        },
        "methods": [],
    }


def test_a_test_the_scope_requires_and_the_lot_did_not_test_refuses_its_certificate():
    statement = {
        "scope": MARKET,
        "specification": "m version 1",
        "required": True,
        "requirement": "≤ 0.5 %",
        "result": "",
        "outcome": conformity.NOT_TESTED,
        "reason": "the requirement applied to this lot states it for information only",
    }
    rows = [{"origin": "none", "test_code": "water", "statements": [statement]}]
    assert conformity.scope_blockers(_evidence(rows), MARKET) == [
        "water: m version 1 (eu-market) requires it and the lot has no result for it; the "
        "requirement applied to this lot states it for information only."
    ]
    assert conformity.scope_blockers(_evidence(rows), "") == []
    assert conformity.scope_view(_evidence(rows), "general")["results"] == []


def test_a_suppliers_accepted_result_is_judged_against_every_specification(django_user_model):
    from tests.test_supplier_certificates import certify, sample_and_test, stated
    from tests.test_supplier_reliance import (
        RELIED,
        accept,
        build_reliance_world,
        fully_stated,
        propose,
        qualify,
    )

    world = build_reliance_world(django_user_model)
    overlay(world, MARKET, TIGHT)
    assert assign(world, "general", MARKET).status == "hold"
    decide(world, choices={"assay": "general"})
    qualify(world)
    results = fully_stated(
        assay=stated("assay", "98.50", method="Supplier HPLC-07", limits="98.0 - 102.0 %")
    )
    certificate = certify(world, results, lot=world["lot"])
    for code in RELIED:
        accept(world, propose(world, certificate, code))
    sample_and_test(world)
    lot = dispose(world, world["people"]["approver"])
    evidence, _, blockers = reporting.preview(lot)
    assert blockers == []
    (row,) = [r for r in evidence["native"]["conformity"] if r["test_code"] == "assay"]
    assert row["origin"] == "supplier" and row["sample"] is None
    found = {s["scope"]: s for s in row["statements"]}
    assert (found["general"]["applied"], found["general"]["outcome"]) == (True, "conforms")
    assert found[MARKET]["outcome"] == conformity.FAILS
    assert found[MARKET]["result"] == "98.50 %"
    assert reporting.preview(lot, MARKET)[2] == [
        "assay (supplier's result): the result 98.50 % does not meet synthetic-rt-eu-market "
        "version 1 (eu-market), 99 – 101 % · rounded to 2 decimals."
    ]
    report = issue(world, lot, scope="general", recipient="Synthetic general customer")
    view = conformity.scope_view(report.versions.get().snapshot, "general")
    assert {r["result"]["test_code"] for r in view["supplier_results"]} == set(RELIED)
    assert [r["result"]["test_code"] for r in view["results"]] == ["identity"]
    text = flat(report.versions.get().snapshot)
    assert "Results accepted from the supplier's certificate of analysis." in text
    assert "Supplier result assay accepted in place of a test" in text
