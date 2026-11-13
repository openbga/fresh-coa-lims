"""Resource flags and calculations of method versions: services, guards, approval and payloads."""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.urls import reverse

from catalog import services
from catalog.models import MethodCalculationInput, MethodRevision
from catalog.units import INPUT_UNITS, RESULT_UNITS
from core.models import AuditEvent

from .factories import (
    approve,
    material,
    method_revision,
    numeric_line,
    qualitative_line,
    specification,
    window,
)

pytestmark = pytest.mark.django_db(transaction=True)

FORMULA = "(peak_area * standard_mass) / (standard_area * sample_mass) * 100"
INPUTS = [
    ("peak_area", "Sample peak area", "peak area"),
    ("standard_area", "Standard peak area", "peak area"),
    ("standard_mass", "Standard mass", "mg"),
    ("sample_mass", "Sample mass", "mg"),
]


def new_method(actor, code="hplc-calc", **extra):
    start, end = window()
    return services.create_method(
        actor=actor,
        code=code,
        title=f"Synthetic {code}",
        technique="HPLC-UV",
        document_ref="SOP-SYN rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN",
        effective_from=start,
        effective_until=end,
        reason="Synthetic",
        **extra,
    )[1]


def add_inputs(actor, revision, inputs=INPUTS):
    for code, name, unit in inputs:
        services.add_calculation_input(
            actor=actor, revision=revision, reason="Input", code=code, name=name, unit=unit
        )


def calculated(actor, code="hplc-calc", **extra):
    revision = new_method(actor, code=code, **extra)
    add_inputs(actor, revision)
    services.set_calculation(
        actor=actor, revision=revision, reason="Formula", formula=FORMULA, unit="%", decimals=2
    )
    revision.refresh_from_db()
    return revision


CALCULATION = {
    "formula": FORMULA,
    "inputs": [{"code": c, "name": n, "unit": u} for c, n, u in INPUTS],
    "unit": "%",
    "decimals": 2,
}


def test_input_units_extend_result_and_quantity_units():
    units = [unit for unit, _ in INPUT_UNITS]
    assert len(units) == len(set(units))
    assert {unit for unit, _ in RESULT_UNITS} <= set(units)
    assert {"mg", "mL", "µL", "µg", "mol/L", "peak area", "AU", "factor"} <= set(units)


def test_flags_are_set_at_creation_and_frozen_with_the_version(people):
    revision = new_method(people["author"], requires_equipment=True, requires_reagent=True)
    assert (revision.requires_equipment, revision.requires_reagent) == (True, True)
    approved = approve(revision, people["approver"])
    assert approved.approved_content["requires_equipment"] is True
    assert approved.approved_content["requires_reagent"] is True
    assert approved.approved_content["calculation"] is None
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodRevision.objects.filter(pk=approved.pk).update(requires_equipment=False)
    draft = new_method(people["author"], code="flags-draft", requires_equipment=True)
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodRevision.objects.filter(pk=draft.pk).update(requires_equipment=False)


def test_new_version_copies_flags_inputs_and_calculation(people):
    first = calculated(people["author"], requires_equipment=True)
    approve(first, people["approver"])
    nxt = method_revision(people["author"], code="hplc-calc", method=first.method)
    assert nxt.requires_equipment is True and nxt.requires_reagent is False
    assert nxt.calculation() == CALCULATION
    assert nxt.calculation_inputs.count() == 4
    assert [i.pk for i in nxt.calculation_inputs.all()] != [
        i.pk for i in first.calculation_inputs.all()
    ]
    off = services.new_method_revision(
        actor=people["author"],
        method=first.method,
        technique="HPLC",
        document_ref="SOP rev 2",
        suitability_kind="validation",
        suitability_ref="VAL",
        effective_from=nxt.effective_until,
        effective_until=nxt.effective_until + (nxt.effective_until - nxt.effective_from),
        reason="Flags off",
        requires_equipment=False,
    )
    assert off.requires_equipment is False


def test_calculation_services_update_revision_and_audit(people):
    revision = new_method(people["author"])
    start = revision.revision
    item = services.add_calculation_input(
        actor=people["author"],
        revision=revision,
        reason="Add input",
        code="peak_area",
        name="Peak area",
        unit="peak area",
    )
    event = AuditEvent.objects.get(action="method_revision.calculation_input_added")
    assert event.after == {"code": "peak_area", "name": "Peak area", "unit": "peak area"}
    assert event.reason == "Add input"
    services.set_calculation(
        actor=people["author"],
        revision=revision,
        reason="Formula",
        formula="peak_area*2",
        unit="mg/g",
        decimals=3,
    )
    event = AuditEvent.objects.get(action="method_revision.calculation_set")
    assert event.before["formula"] == "" and event.after["formula"] == "peak_area*2"
    services.set_calculation(
        actor=people["author"],
        revision=revision,
        reason="Change",
        formula="peak_area * 3",
        unit="mg/g",
        decimals=1,
    )
    changed = AuditEvent.objects.filter(action="method_revision.calculation_set").last()
    assert changed.before["formula"] == "peak_area*2" and changed.after["decimals"] == 1
    services.remove_calculation_input(actor=people["author"], item=item, reason="Wrong input")
    removed = AuditEvent.objects.get(action="method_revision.calculation_input_removed")
    assert removed.before["code"] == "peak_area"
    revision.refresh_from_db()
    assert revision.revision == start + 4
    services.clear_calculation(actor=people["author"], revision=revision, reason="Not needed")
    revision.refresh_from_db()
    assert revision.calculation() is None
    assert AuditEvent.objects.filter(action="method_revision.calculation_cleared").count() == 1
    with pytest.raises(ValidationError, match="no calculation"):
        services.clear_calculation(actor=people["author"], revision=revision, reason="Again")


def test_clear_removes_the_inputs(people):
    revision = calculated(people["author"])
    services.clear_calculation(actor=people["author"], revision=revision, reason="Drop it")
    assert not MethodCalculationInput.objects.filter(method_revision=revision).exists()
    cleared = AuditEvent.objects.get(action="method_revision.calculation_cleared")
    assert len(cleared.before["inputs"]) == 4


@pytest.mark.parametrize("role", ["analyst", "reviewer", "admin", "auditor"])
def test_calculation_services_need_the_quality_role(people, role):
    revision = calculated(people["author"])
    item = revision.calculation_inputs.first()
    before = AuditEvent.objects.count()
    calls = [
        lambda: services.add_calculation_input(
            actor=people[role], revision=revision, reason="x", code="extra", name="E", unit="mg"
        ),
        lambda: services.remove_calculation_input(actor=people[role], item=item, reason="x"),
        lambda: services.set_calculation(
            actor=people[role], revision=revision, reason="x", formula="a", unit="%", decimals=1
        ),
        lambda: services.clear_calculation(actor=people[role], revision=revision, reason="x"),
    ]
    for call in calls:
        with pytest.raises(PermissionDenied):
            call()
    assert AuditEvent.objects.count() == before
    assert revision.calculation_inputs.count() == 4


def test_reason_is_required(people):
    revision = new_method(people["author"])
    with pytest.raises(ValidationError, match="reason"):
        services.add_calculation_input(
            actor=people["author"], revision=revision, reason=" ", code="a", name="A", unit="mg"
        )
    with pytest.raises(ValidationError, match="reason"):
        services.set_calculation(
            actor=people["author"], revision=revision, reason="", formula="a", unit="%", decimals=1
        )


def test_approved_and_withdrawn_versions_refuse_changes_in_the_service(people):
    approved = approve(calculated(people["author"]), people["approver"])
    item = approved.calculation_inputs.first()
    withdrawn = new_method(people["author"], code="withdrawn-calc")
    services.withdraw_revision(
        actor=people["author"],
        revision=withdrawn,
        expected_revision=withdrawn.revision,
        reason="Not needed",
    )
    for version in (approved, withdrawn):
        for call in (
            lambda v=version: services.add_calculation_input(
                actor=people["author"], revision=v, reason="x", code="late", name="L", unit="mg"
            ),
            lambda v=version: services.set_calculation(
                actor=people["author"], revision=v, reason="x", formula="a", unit="%", decimals=1
            ),
            lambda v=version: services.clear_calculation(
                actor=people["author"], revision=v, reason="x"
            ),
        ):
            with pytest.raises(ValidationError, match="draft"):
                call()
    with pytest.raises(ValidationError, match="draft"):
        services.remove_calculation_input(actor=people["author"], item=item, reason="x")
    assert approved.calculation_inputs.count() == 4


def test_approved_calculation_is_frozen_in_the_database(people):
    approved = approve(calculated(people["author"]), people["approver"])
    item = approved.calculation_inputs.first()
    operations = [
        lambda: MethodRevision.objects.filter(pk=approved.pk).update(calculation_formula="a"),
        lambda: MethodRevision.objects.filter(pk=approved.pk).update(calculation_unit="mg/g"),
        lambda: MethodRevision.objects.filter(pk=approved.pk).update(calculation_decimals=5),
        lambda: MethodCalculationInput.objects.filter(pk=item.pk).update(unit="mg"),
        lambda: MethodCalculationInput.objects.filter(pk=item.pk).delete(),
        lambda: MethodCalculationInput.objects.create(
            method_revision=approved,
            code="late",
            name="Late",
            unit="mg",
            created_by=item.created_by,
        ),
    ]
    for operation in operations:
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()
    approved.refresh_from_db()
    assert approved.calculation_formula == FORMULA
    assert approved.calculation_inputs.count() == 4
    assert approved.approved_content["calculation"] == CALCULATION


def test_withdrawn_draft_inputs_are_frozen_in_the_database(people):
    revision = calculated(people["author"])
    item = revision.calculation_inputs.first()
    services.withdraw_revision(
        actor=people["author"],
        revision=revision,
        expected_revision=revision.revision,
        reason="Not needed",
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodCalculationInput.objects.filter(pk=item.pk).update(name="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodRevision.objects.filter(pk=revision.pk).update(calculation_formula="a")


def test_draft_allows_only_the_calculation_columns_to_change(people):
    revision = new_method(people["author"])
    MethodRevision.objects.filter(pk=revision.pk).update(
        calculation_formula="a", calculation_unit="%", calculation_decimals=1
    )
    for field, value in (("technique", "changed"), ("requires_reagent", True)):
        with pytest.raises(DatabaseError), transaction.atomic():
            MethodRevision.objects.filter(pk=revision.pk).update(**{field: value})
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodRevision.objects.filter(pk=revision.pk).update(calculation_decimals=9)


def test_database_limits_inputs_to_twelve_and_unique_codes(people):
    revision = new_method(people["author"])
    for number in range(12):
        services.add_calculation_input(
            actor=people["author"],
            revision=revision,
            reason="x",
            code=f"v{number}",
            name=f"Value {number}",
            unit="mg",
        )
    with pytest.raises(ValidationError, match="at most 12"):
        services.add_calculation_input(
            actor=people["author"], revision=revision, reason="x", code="v13", name="V", unit="mg"
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodCalculationInput.objects.create(
            method_revision=revision, code="v13", name="V", unit="mg", created_by=people["author"]
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodCalculationInput.objects.create(
            method_revision=revision, code="v0", name="V", unit="mg", created_by=people["author"]
        )


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"code": "Peak Area"}, "code"),
        ({"code": "1area"}, "code"),
        ({"code": "peak_area"}, "code"),
        ({"code": "x" * 41}, "code"),
        ({"unit": "furlong"}, "unit"),
        ({"name": ""}, "name"),
        ({"name": "n" * 161}, "name"),
    ],
)
def test_input_validation(people, fields, field):
    revision = new_method(people["author"])
    add_inputs(people["author"], revision, [("peak_area", "Peak area", "peak area")])
    data = {"code": "other", "name": "Other", "unit": "mg", **fields}
    with pytest.raises(ValidationError) as caught:
        services.add_calculation_input(
            actor=people["author"], revision=revision, reason="x", **data
        )
    assert field in caught.value.message_dict
    assert revision.calculation_inputs.count() == 1


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"formula": ""}, "formula"),
        ({"formula": "a +"}, "formula"),
        ({"formula": "sqrt(a)"}, "formula"),
        ({"formula": "a" + " + a" * 200}, "formula"),
        ({"unit": "furlong"}, "unit"),
        ({"unit": "mg"}, "unit"),
        ({"decimals": 9}, "decimals"),
        ({"decimals": -1}, "decimals"),
        ({"decimals": None}, "decimals"),
    ],
)
def test_set_calculation_validation(people, fields, field):
    revision = new_method(people["author"])
    data = {"formula": "a * 2", "unit": "%", "decimals": 2, **fields}
    with pytest.raises(ValidationError) as caught:
        services.set_calculation(actor=people["author"], revision=revision, reason="x", **data)
    assert field in caught.value.message_dict
    revision.refresh_from_db()
    assert revision.calculation() is None


def test_valid_calculation_is_approved_and_frozen_in_the_content(people):
    approved = approve(calculated(people["author"]), people["approver"])
    assert approved.approved_content["calculation"] == CALCULATION
    assert approved.approved_content["requires_equipment"] is False
    assert approved.approved_hash == services.digest(approved.approved_content)


def approval_error(people, revision):
    with pytest.raises(ValidationError) as caught:
        approve(revision, people["approver"])
    revision.refresh_from_db()
    assert revision.status == "draft"
    return " ".join(caught.value.messages)


def test_formula_names_must_be_exactly_the_input_codes(people):
    revision = calculated(people["author"])
    services.set_calculation(
        actor=people["author"],
        revision=revision,
        reason="Typo",
        formula=FORMULA.replace("sample_mass", "sample_weight"),
        unit="%",
        decimals=2,
    )
    message = approval_error(people, revision)
    assert "sample_weight" in message and "not inputs" in message
    assert "sample_mass" in message and "not used" in message


def test_input_not_used_by_the_formula_blocks_approval(people):
    revision = calculated(people["author"])
    add_inputs(people["author"], revision, [("dilution", "Dilution", "factor")])
    assert "dilution" in approval_error(people, revision)


@pytest.mark.parametrize("step", ["inputs only", "formula only", "no decimals", "no unit"])
def test_half_defined_calculation_blocks_approval(people, step):
    revision = new_method(people["author"], code=f"half-{step.replace(' ', '-')}")
    if step == "inputs only":
        add_inputs(people["author"], revision, INPUTS[:1])
        expected = "Set the formula"
    elif step == "formula only":
        services.set_calculation(
            actor=people["author"], revision=revision, reason="x", formula="a", unit="%", decimals=1
        )
        expected = "1 to 12 inputs"
    else:
        add_inputs(people["author"], revision, INPUTS[:1])
        services.set_calculation(
            actor=people["author"],
            revision=revision,
            reason="x",
            formula="peak_area",
            unit="%",
            decimals=1,
        )
        column = "calculation_decimals" if step == "no decimals" else "calculation_unit"
        MethodRevision.objects.filter(pk=revision.pk).update(
            **{column: None if step == "no decimals" else ""}
        )
        expected = "number of decimals" if step == "no decimals" else "unit of the calculated"
    assert expected in approval_error(people, revision)


def test_invalid_stored_formula_blocks_approval(people):
    revision = calculated(people["author"])
    MethodRevision.objects.filter(pk=revision.pk).update(calculation_formula="peak_area +")
    assert "formula is not valid" in approval_error(people, revision)


def test_method_without_calculation_is_unaffected(people):
    approved = approve(new_method(people["author"], code="plain-calc"), people["approver"])
    assert approved.approved_content["calculation"] is None


# Specification lines against a calculation -----------------------------------------------------


def calc_spec(people, **line):
    method = approve(calculated(people["author"]), people["approver"]).method
    _, revision = specification(people["author"], material(people["author"]))
    return revision, method, line


def test_specification_line_must_match_the_calculation_unit(people):
    revision, method, _ = calc_spec(people)
    numeric_line(people["author"], revision, method, unit="mg/g")
    with pytest.raises(ValidationError, match="calculates its result in %"):
        approve(revision, people["approver"])
    revision.refresh_from_db()
    assert revision.status == "draft"


def test_specification_line_must_be_numeric_for_a_calculation(people):
    revision, method, _ = calc_spec(people)
    qualitative_line(people["author"], revision, method)
    with pytest.raises(ValidationError, match="numeric with the unit %"):
        approve(revision, people["approver"])


def test_specification_line_with_matching_unit_is_approved(people):
    revision, method, _ = calc_spec(people)
    numeric_line(people["author"], revision, method, unit="%")
    assert approve(revision, people["approver"]).status == "approved"


def test_specification_checks_the_method_version_effective_at_its_start(people):
    first = approve(calculated(people["author"]), people["approver"])
    late_start, late_end = window(400, 800)
    later = services.new_method_revision(
        actor=people["author"],
        method=first.method,
        technique="HPLC",
        document_ref="SOP rev 2",
        suitability_kind="validation",
        suitability_ref="VAL",
        effective_from=late_start,
        effective_until=late_end,
        reason="Later",
    )
    services.set_calculation(
        actor=people["author"],
        revision=later,
        reason="New unit",
        formula=FORMULA,
        unit="mg/g",
        decimals=2,
    )
    approve(later, people["approver"])
    _, revision = specification(people["author"], material(people["author"]))
    numeric_line(people["author"], revision, first.method, unit="%")
    assert approve(revision, people["approver"]).status == "approved"


def test_specification_without_calculation_keeps_any_unit(people):
    plain = approve(method_revision(people["author"], code="plain-line"), people["approver"])
    _, revision = specification(people["author"], material(people["author"], code="syn-plain"))
    numeric_line(people["author"], revision, plain.method, unit="mg/g")
    assert approve(revision, people["approver"]).status == "approved"


# Payloads --------------------------------------------------------------------------------------

QC = [{"code": "blank", "name": "Blank", "unit": "%", "lower_limit": None, "upper_limit": "0.05"}]


def legacy_revision(**content):
    """An approved version frozen before this change: its content lacks the new keys."""
    return SimpleNamespace(
        pk=7,
        method=SimpleNamespace(code="syn-hplc"),
        version=2,
        document_ref="SOP rev 1",
        suitability_kind="validation",
        suitability_ref="VAL",
        approved_hash="a" * 64,
        approved_content={"requires_batch": True, "qc_checks": QC, **content},
    )


LEGACY_PAYLOAD = {
    "revision_id": 7,
    "code": "syn-hplc",
    "version": 2,
    "document_ref": "SOP rev 1",
    "suitability_kind": "validation",
    "suitability_ref": "VAL",
    "requires_batch": True,
    "qc_checks": QC,
    "requires_equipment": False,
    "requires_reagent": False,
    "calculation": None,
    "approved_hash": "a" * 64,
}
FOUR_KEYS = {"code": "syn-hplc", "revision": 2, "requires_batch": True, "qc_checks": QC}


def test_payload_of_content_approved_before_this_change_has_defaults():
    payload = services._method_payload(legacy_revision())
    assert payload == LEGACY_PAYLOAD
    shape = services.method_requirement(payload)
    assert shape == FOUR_KEYS
    assert json.dumps(shape, sort_keys=True) == json.dumps(FOUR_KEYS, sort_keys=True)


def test_method_requirement_of_an_older_payload_without_the_keys_is_the_four_keys():
    old = {
        k: v
        for k, v in LEGACY_PAYLOAD.items()
        if k not in {"requires_equipment", "requires_reagent", "calculation"}
    }
    assert services.method_requirement(old) == FOUR_KEYS


@pytest.mark.parametrize(
    "extra",
    [
        {"requires_equipment": True},
        {"requires_reagent": True},
        {"calculation": CALCULATION},
        {"requires_equipment": True, "requires_reagent": True, "calculation": CALCULATION},
    ],
)
def test_method_requirement_has_seven_keys_with_a_flag_or_calculation(extra):
    shape = services.method_requirement({**LEGACY_PAYLOAD, **extra})
    assert list(shape) == [
        "code",
        "revision",
        "requires_batch",
        "qc_checks",
        "requires_equipment",
        "requires_reagent",
        "calculation",
    ]
    assert shape["requires_equipment"] is extra.get("requires_equipment", False)
    assert shape["requires_reagent"] is extra.get("requires_reagent", False)
    assert shape["calculation"] == extra.get("calculation")


LINE = {
    "code": "assay",
    "name": "Assay",
    "position": 1,
    "result_type": "numeric",
    "unit": "%",
    "lower_limit": "98",
    "lower_inclusive": True,
    "upper_limit": "102",
    "upper_inclusive": True,
    "reporting_decimals": 1,
    "expected_text": "",
    "expected_result": "",
    "required": True,
    "replicates": 1,
    "replicate_limits": True,
    "max_retests": 0,
}
SOURCE = "catalog:spec-api@v1#rev7/lot-req:0123456789abcdef"


def test_requirement_schemas_follow_the_method_shape():
    four = services.test_requirement({**LINE, "method": LEGACY_PAYLOAD}, SOURCE)
    assert four["schema"] == "oq.test-requirement/1" and list(four["method"]) == list(FOUR_KEYS)
    strict = services.test_requirement(
        {**LINE, "upper_inclusive": False, "method": LEGACY_PAYLOAD}, SOURCE
    )
    assert strict["schema"] == "oq.test-requirement/2" and list(strict["method"]) == list(FOUR_KEYS)
    seven = {**LEGACY_PAYLOAD, "calculation": CALCULATION, "requires_reagent": True}
    inclusive = services.test_requirement({**LINE, "method": seven}, SOURCE)
    other = services.test_requirement({**LINE, "upper_inclusive": False, "method": seven}, SOURCE)
    assert inclusive["schema"] == other["schema"] == "oq.test-requirement/3"
    assert inclusive["method"] == other["method"] == services.method_requirement(seven)
    v2 = services.test_requirement(
        {**LINE, "method": LEGACY_PAYLOAD, "upper_inclusive": False}, SOURCE
    )
    assert {k for k in other if k != "schema"} == {k for k in v2 if k != "schema"}
    assert inclusive["lower_inclusive"] is True
    assert inclusive["upper_limit"] == "102" and inclusive["expected_result"] is None


def test_catalog_payloads_carry_the_new_keys_through_resolution(people):
    calc = (
        approve(calculated(people["author"], requires_batch=True), people["approver"])
        if False
        else None
    )
    assert calc is None
    revision = new_method(
        people["author"], code="batch-calc", requires_batch=True, requires_equipment=True
    )
    services.add_qc_check(
        actor=people["author"],
        revision=revision,
        reason="QC",
        code="blank",
        name="Blank",
        unit="%",
        upper_limit=Decimal("0.05"),
    )
    add_inputs(people["author"], revision, INPUTS)
    services.set_calculation(
        actor=people["author"], revision=revision, reason="F", formula=FORMULA, unit="%", decimals=2
    )
    plain = approve(method_revision(people["author"], code="plain-batch"), people["approver"])
    approve(revision, people["approver"])
    [payload] = services.effective_batch_methods()
    assert payload["requires_equipment"] is True and payload["calculation"] == CALCULATION
    [shape] = services.batch_method_requirements()
    assert shape["calculation"] == CALCULATION and shape["requires_equipment"] is True
    assert shape["requires_reagent"] is False
    assert plain.method.code not in {m["code"] for m in services.batch_method_requirements()}


def test_resolved_requirements_use_v3_only_for_a_calculated_method(people):
    mat = material(people["author"])
    calc = approve(calculated(people["author"]), people["approver"])
    plain = approve(method_revision(people["author"], code="plain-ident"), people["approver"])
    _, revision = specification(people["author"], mat)
    numeric_line(people["author"], revision, calc.method, code="assay", unit="%")
    numeric_line(people["author"], revision, plain.method, code="water", unit="%")
    approve(revision, people["approver"])
    resolved = services.resolve_requirements(material=mat, stage="incoming")
    schemas = {}
    for test in resolved["tests"]:
        schemas[test["code"]] = services.test_requirement(test, "catalog:x")["schema"]
    assert schemas == {"assay": "oq.test-requirement/3", "water": "oq.test-requirement/1"}
    [assay] = [t for t in resolved["tests"] if t["code"] == "assay"]
    assert assay["method"]["calculation"] == CALCULATION


# Pages -----------------------------------------------------------------------------------------


def test_pages_set_the_calculation_and_inputs(client, people):
    revision = new_method(people["author"], code="web-calc", requires_reagent=True)
    client.force_login(people["author"])
    detail_url = reverse("catalog:method", args=[revision.method_id])
    detail = client.get(detail_url).content.decode()
    assert "No calculation" in detail and "Recorded with every result" in detail
    new_input = reverse("catalog:calculation_input_new", args=[revision.pk])
    assert new_input in detail
    data = {"code": "peak_area", "name": "Peak area", "unit": "peak area", "reason": "Input"}
    assert client.post(new_input, {**data, "code": "Peak"}).status_code == 422
    assert client.post(new_input, data).status_code == 302
    assert client.post(new_input, data).status_code == 422  # duplicate code
    setter = reverse("catalog:calculation_set", args=[revision.pk])
    body = {"formula": "peak_area * 2", "unit": "mg/g", "decimals": "2", "reason": "Formula"}
    assert client.post(setter, {**body, "formula": "peak_area *"}).status_code == 422
    assert client.post(setter, {**body, "decimals": "9"}).status_code == 422
    assert client.post(setter, body).status_code == 302
    revision.refresh_from_db()
    assert revision.calculation_formula == "peak_area * 2"
    detail = client.get(detail_url).content.decode()
    assert "peak_area * 2" in detail and "mg/g, 2 decimals" in detail
    assert client.get(setter).context["form"].initial["formula"] == "peak_area * 2"
    item = revision.calculation_inputs.get()
    remove = reverse("catalog:calculation_input_remove", args=[revision.pk, item.pk])
    stale = {"reason": "Wrong", "expected_revision": revision.revision - 1}
    assert client.post(remove, stale).status_code == 422
    assert client.post(remove, {**stale, "expected_revision": revision.revision}).status_code == 302
    clear = reverse("catalog:calculation_clear", args=[revision.pk])
    revision.refresh_from_db()
    assert (
        client.post(clear, {"reason": "Drop", "expected_revision": revision.revision}).status_code
        == 302
    )
    revision.refresh_from_db()
    assert revision.calculation() is None


def test_pages_refuse_other_roles_and_frozen_versions(client, people):
    approved = approve(calculated(people["author"], code="web-frozen"), people["approver"])
    item = approved.calculation_inputs.first()
    urls = [
        reverse("catalog:calculation_set", args=[approved.pk]),
        reverse("catalog:calculation_clear", args=[approved.pk]),
        reverse("catalog:calculation_input_new", args=[approved.pk]),
        reverse("catalog:calculation_input_remove", args=[approved.pk, item.pk]),
    ]
    client.force_login(people["author"])
    for url in urls:
        assert client.get(url).status_code == 302
        assert client.post(url, {"reason": "x"}).status_code == 302
    detail = client.get(reverse("catalog:method", args=[approved.method_id])).content.decode()
    assert not [url for url in urls if f'href="{url}"' in detail]
    assert "(peak_area * standard_mass)" in detail
    draft = new_method(people["author"], code="web-denied")
    for role in ("analyst", "reviewer", "admin", "auditor"):
        client.force_login(people[role])
        for name in ("calculation_set", "calculation_clear", "calculation_input_new"):
            url = reverse(f"catalog:{name}", args=[draft.pk])
            assert client.get(url).status_code == 403
            assert client.post(url, {"reason": "x"}).status_code == 403


def test_method_forms_set_the_flags_and_version_form_prefills(client, people):
    start, end = window()
    client.force_login(people["author"])
    data = {
        "code": "flag-web",
        "title": "Flags",
        "technique": "HPLC",
        "document_ref": "SOP rev 1",
        "suitability_kind": "validation",
        "suitability_ref": "VAL",
        "effective_from": start.strftime("%Y-%m-%dT%H:%M"),
        "effective_until": end.strftime("%Y-%m-%dT%H:%M"),
        "reason": "New",
        "requires_equipment": "on",
    }
    assert client.post(reverse("catalog:method_new"), data).status_code == 302
    revision = MethodRevision.objects.get(method__code="flag-web")
    assert (revision.requires_equipment, revision.requires_reagent) == (True, False)
    page = client.get(reverse("catalog:method_version_new", args=[revision.method_id]))
    assert page.context["form"].initial == {"requires_equipment": True, "requires_reagent": False}
    client.force_login(people["approver"])
    detail = client.get(reverse("catalog:method_approve", args=[revision.pk])).content.decode()
    assert "Instrument" in detail and "Calculation" in detail
