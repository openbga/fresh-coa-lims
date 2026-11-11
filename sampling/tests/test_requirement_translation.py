"""Frozen catalog/sampling requirements, translated, parse with the analytical contract or hold."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from analytical.contracts import parse_method, parse_requirement
from catalog import services as catalog
from catalog.services import ApplicabilityHold
from catalog.tests.factories import (
    approve,
    approved_rules,
    material,
    numeric_line,
    qualitative_line,
    specification,
    window,
)
from quality.services import receive_lot
from sampling import services

from .test_services import plan_revision

pytestmark = pytest.mark.django_db(transaction=True)


def batch_method(people):
    start, end = window()
    _, revision = catalog.create_method(
        actor=people["author"],
        code="hplc-b",
        title="Batch HPLC",
        technique="HPLC",
        document_ref="SOP-SYN rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN",
        requires_batch=True,
        effective_from=start,
        effective_until=end,
        reason="Synthetic",
    )
    catalog.add_qc_check(
        actor=people["author"],
        revision=revision,
        reason="QC",
        code="blank",
        name="Blank",
        unit="%",
        upper_limit=Decimal("0.05"),
    )
    return approve(revision, people["approver"]).method


@pytest.fixture
def lot_with_requirements(people):
    mat = material(people["author"])
    hplc = batch_method(people)
    ident = approve(
        catalog.create_method(
            actor=people["author"],
            code="ftir-b",
            title="FTIR",
            technique="FTIR",
            document_ref="SOP rev 1",
            suitability_kind="validation",
            suitability_ref="VAL",
            effective_from=window()[0],
            effective_until=window()[1],
            reason="Synthetic",
        )[1],
        people["approver"],
    ).method
    _, spec = specification(people["author"], mat)
    qualitative_line(people["author"], spec, ident, code="identity")
    numeric_line(
        people["author"],
        spec,
        hplc,
        code="assay",
        reporting_decimals=1,
        replicates=2,
        max_retests=1,
    )
    numeric_line(
        people["author"],
        spec,
        hplc,
        code="impurity",
        low=None,
        high="0.5",
        upper_inclusive=False,
        reporting_decimals=2,
    )
    numeric_line(people["author"], spec, hplc, code="exact", reporting_decimals=None)
    numeric_line(people["author"], spec, hplc, code="info", reporting_decimals=1, required=False)
    approve(spec, people["approver"])
    approve(plan_revision(people["author"], mat), people["approver"])
    lot = receive_lot(
        actor=people["analyst"],
        number="SYN-B-1",
        material=mat.name,
        rules=approved_rules(people["author"]),
        reason="Synthetic",
    )
    services.assign_requirements(
        actor=people["analyst"], lot=lot, material=mat, stage="incoming", reason="Assign"
    )
    return lot


def test_supported_tests_parse_and_unsupported_hold(people, lot_with_requirements):
    payloads = services.test_requirements(lot_with_requirements)
    assert set(payloads) == {"identity", "assay", "impurity", "exact"}  # info-only excluded
    assay = parse_requirement(payloads["assay"])
    assert (assay.replicates, assay.reporting_decimals, assay.max_retests) == (2, 1, 1)
    assert assay.lower == Decimal("98") and assay.upper == Decimal("102")
    assert assay.method.requires_batch and assay.method.qc_checks[0].code == "blank"
    assert payloads["assay"]["source"].startswith("catalog:spec-api@v1#rev")
    assert parse_requirement(payloads["exact"]).reporting_decimals is None  # exact comparison
    for code, reason in [("identity", "numeric"), ("impurity", "inclusive")]:
        with pytest.raises(ValidationError, match=reason):
            parse_requirement(payloads[code])


def test_batch_methods_parse_in_analytical_contract(people):
    batch_method(people)
    [method] = catalog.batch_method_requirements()
    parsed = parse_method(method)
    assert parsed.requires_batch and parsed.revision == 1


def test_unassigned_lot_holds(people):
    lot = receive_lot(
        actor=people["analyst"],
        number="SYN-B-2",
        material="x",
        rules=approved_rules(people["author"]),
        reason="Synthetic",
    )
    with pytest.raises(ApplicabilityHold):
        services.test_requirements(lot)


def test_source_changes_with_reassignment(people, lot_with_requirements):
    before = services.test_requirements(lot_with_requirements)["assay"]["source"]
    assignment = services.current_assignment(lot_with_requirements)
    services.assign_requirements(
        actor=people["analyst"],
        lot=lot_with_requirements,
        material=assignment.material,
        stage="incoming",
        reason="Reassign",
    )
    after = services.test_requirements(lot_with_requirements)["assay"]["source"]
    assert before != after  # each frozen assignment has its own hash (resolved_at differs)
