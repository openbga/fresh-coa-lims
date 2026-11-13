"""Calculated results and bench checks (equipment, reagent lots, analyst qualification)."""

import copy
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.urls import reverse

from analytical import fixtures, services
from analytical.contracts import (
    METHOD_KEYS,
    WorkRefused,
    canonical_hash,
    parse_method,
    parse_requirement,
)
from analytical.fixtures import METHODS, FixtureProvider, requirement_payload
from analytical.models import Observation, QCBatch, QCResult
from core import formulas
from core.models import AuditEvent, ElectronicSignature

from .conftest import PIN, fresh, login, pass_qc

pytestmark = pytest.mark.django_db(transaction=True)

UV = {"sample_abs": "0.500625", "standard_abs": "0.5", "standard_conc": "1.000", "sample_conc": "1"}
FIT = {"equipment_ids": [2], "reagent_ids": [1]}  # in-service spectrometer, released standard


def payload(code="uv_assay", **changes):
    data = requirement_payload(code)
    data.update(changes)
    return data


def calc_payload(**changes):
    data = payload()
    data["method"]["calculation"].update(changes)
    return data


def bench_calls(name):
    return [details for call, details in fixtures.BENCH_LOG if call == name]


@pytest.fixture
def calc(people, make_lot):
    lot, sample = make_lot("SYN-CALC", tests=("uv_assay", "kf_water"))
    created, holds = services.assign_tests(actor=people["analyst"], sample=sample, reason="Go")
    assert holds == []
    return lot, sample, {t.test_code: t for t in created}


def record_uv(people, test, inputs=UV, who="analyst", **kwargs):
    kwargs = {**FIT, **kwargs}
    return services.record_observation(
        actor=people[who], test=test, inputs=dict(inputs), raw_reference="UV-RUN-1", **kwargs
    )


# Parser: legacy payloads unchanged, seven-key methods and calculations ----------------------


def test_legacy_payloads_and_four_key_methods_parse_exactly_as_before():
    for code in ("assay", "tamc", "pathogen"):
        data = requirement_payload(code)
        frozen = copy.deepcopy(data)
        spec = parse_requirement(data)
        assert data == frozen and canonical_hash(data) == canonical_hash(frozen)
        assert set(data["method"]) == METHOD_KEYS
        method = spec.method
        assert (method.requires_equipment, method.requires_reagent, method.calculation) == (
            False,
            False,
            None,
        )
        assert spec.calculation is None
    batch = parse_method(copy.deepcopy(METHODS["SYN-HPLC"]))
    assert batch.requires_batch and [c.code for c in batch.qc_checks] == ["blank", "control"]
    assert (batch.requires_equipment, batch.requires_reagent, batch.calculation) == (
        False,
        False,
        None,
    )


def test_seven_key_method_and_v3_requirement_parse():
    spec = parse_requirement(payload())
    method = spec.method
    assert (method.code, method.revision, method.requires_equipment, method.requires_reagent) == (
        "SYN-UV",
        3,
        True,
        True,
    )
    calculation = spec.calculation
    assert [i.code for i in calculation.inputs] == [
        "sample_abs",
        "standard_abs",
        "standard_conc",
        "sample_conc",
    ]
    assert (calculation.unit, calculation.decimals) == ("% label claim", 2)
    plain = parse_requirement(payload("kf_water"))
    assert plain.calculation is None and plain.method.requires_equipment
    batch = parse_method(copy.deepcopy(METHODS["SYN-LC-BENCH"]))
    assert batch.requires_batch and batch.requires_reagent


def test_method_shape_must_match_the_schema():
    seven = copy.deepcopy(METHODS["SYN-KF-BENCH"])
    for code in ("assay", "tamc"):  # /1 and /2 froze four-key methods
        with pytest.raises(ValidationError, match="keys differ"):
            parse_requirement({**requirement_payload(code), "method": copy.deepcopy(seven)})
    four = copy.deepcopy(METHODS["SYN-KF"])
    with pytest.raises(ValidationError, match="keys differ"):
        parse_requirement(payload("kf_water", method=four))
    for keys in ({"requires_equipment"}, {"calculation", "extra"}):
        method = {**copy.deepcopy(METHODS["SYN-KF"]), **dict.fromkeys(keys, False)}
        with pytest.raises(ValidationError, match="keys differ"):
            parse_method(method)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"formula": "sample_abs / (standard_abs"}, "formula is invalid"),
        ({"formula": "sample_abs ** 2"}, "formula is invalid"),
        ({"formula": ""}, "formula is required"),
        ({"formula": "x" * 501}, "formula is required"),
        ({"formula": "sample_abs / standard_abs * standard_conc"}, "exactly its input codes"),
        (
            {"formula": "sample_abs / standard_abs * standard_conc / sample_conc * unknown"},
            "exactly its input codes",
        ),
        ({"inputs": []}, "1 to 12 inputs"),
        ({"decimals": 9}, "decimals"),
        ({"decimals": True}, "decimals"),
        ({"decimals": "2"}, "decimals"),
        ({"unit": ""}, "Calculation unit"),
        ({"unit": "u" * 41}, "Calculation unit"),
        ({"extra": 1}, "keys differ"),
    ],
)
def test_invalid_calculations_hold(changes, message):
    with pytest.raises(ValidationError, match=message):
        parse_requirement(calc_payload(**changes))


def test_invalid_calculation_inputs_hold():
    def with_inputs(inputs):
        return calc_payload(inputs=inputs)

    good = copy.deepcopy(METHODS["SYN-UV"]["calculation"]["inputs"])
    cases = [
        ([*good, {**good[0]}], "unique"),
        ([{**good[0], "code": "Sample"}, *good[1:]], "code is invalid"),
        ([{**good[0], "name": ""}, *good[1:]], "input name"),
        ([{**good[0], "unit": "u" * 25}, *good[1:]], "input unit"),
        ([{**good[0], "extra": "x"}, *good[1:]], "keys differ"),
        (["sample_abs", *good[1:]], "definition is invalid"),
    ]
    for inputs, message in cases:
        with pytest.raises(ValidationError, match=message):
            parse_requirement(with_inputs(inputs))
    many = [{"code": f"x{n}", "name": f"Input {n}", "unit": "g"} for n in range(13)]
    formula = " + ".join(i["code"] for i in many)
    with pytest.raises(ValidationError, match="1 to 12 inputs"):
        parse_requirement(calc_payload(inputs=many, formula=formula))
    twelve = many[:12]
    spec = parse_requirement(
        calc_payload(inputs=twelve, formula=" + ".join(i["code"] for i in twelve))
    )
    assert len(spec.calculation.inputs) == 12


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"unit": "%"}, "numeric in the calculation's unit"),
        ({"result_type": "count", "reporting_decimals": 0}, "numeric in the calculation's unit"),
        (
            {
                "result_type": "qualitative",
                "unit": "",
                "lower_limit": None,
                "upper_limit": None,
                "expected_result": "conforms",
                "criterion": "Conforms",
                "reporting_decimals": None,
            },
            "numeric in the calculation's unit",
        ),
    ],
)
def test_calculated_line_must_be_numeric_in_the_calculation_unit(changes, message):
    with pytest.raises(ValidationError, match=message):
        parse_requirement(payload(**changes))


def test_calculation_rounds_half_up_at_the_approved_decimals():
    calculation = parse_requirement(payload()).calculation
    value, entered = calculation.compute(UV)
    assert value == Decimal("100.13")  # 100.125: half-up, not half-even
    assert str(value) == "100.13"
    assert [i["value"] for i in entered] == ["0.500625", "0.5", "1.000", "1"]
    assert [i["code"] for i in entered] == [i.code for i in calculation.inputs]
    low, _ = calculation.compute({**UV, "sample_abs": Decimal("0.500624")})
    assert low == Decimal("100.12")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"sample_abs": None}, "Enter Sample absorbance"),
        ({"sample_abs": "  "}, "Enter Sample absorbance"),
        ({"sample_abs": "NaN"}, "finite"),
        ({"sample_abs": Decimal("Infinity")}, "finite"),
        ({"sample_abs": "abc"}, "not a decimal"),
        ({"sample_abs": "0.123456789"}, "more than 8 decimal places"),
        ({"sample_abs": "123456789012345678901"}, "more than 20 digits"),
        ({"standard_abs": "0"}, "divides by zero"),
        ({"other": "1"}, "no input other"),
    ],
)
def test_calculation_input_validation(change, message):
    calculation = parse_requirement(payload()).calculation
    with pytest.raises(ValidationError, match=message):
        calculation.compute({**UV, **change})


def test_too_large_calculated_value_is_refused():
    calculation = parse_requirement(payload()).calculation
    big = {**UV, "sample_abs": "999999999999", "standard_abs": "0.00000001"}
    with pytest.raises(ValidationError, match="too large"):
        calculation.compute(big)


class InvalidCalculationProvider(FixtureProvider):
    def requirements(self, lot):
        return {
            "uv_assay": calc_payload(formula="sample_abs / standard_abs"),
            "kf_water": payload("kf_water", method=copy.deepcopy(METHODS["SYN-KF"])),
        }


def test_invalid_payloads_hold_the_lot(people, make_lot, settings):
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = f"{__name__}.InvalidCalculationProvider"
    _, sample = make_lot("SYN-HOLD", tests=("uv_assay", "kf_water"))
    created, holds = services.assign_tests(actor=people["analyst"], sample=sample, reason="Go")
    assert created == []
    assert any("uv_assay is held" in h and "exactly its input codes" in h for h in holds)
    assert any("kf_water is held" in h and "keys differ" in h for h in holds)


# Calculated observations -------------------------------------------------------------------


def test_calculated_observation_keeps_inputs_formula_and_method(people, calc):
    lot, _, tests = calc
    test = tests["uv_assay"]
    start = (fresh(test).revision, fresh(lot).revision)
    observation = record_uv(people, test)
    assert (observation.value, observation.value_text, observation.unit) == (
        Decimal("100.13"),
        "100.13",
        "% label claim",
    )
    assert observation.inputs == [
        {"code": "sample_abs", "name": "Sample absorbance", "unit": "AU", "value": "0.500625"},
        {"code": "standard_abs", "name": "Standard absorbance", "unit": "AU", "value": "0.5"},
        {
            "code": "standard_conc",
            "name": "Standard concentration",
            "unit": "mg/mL",
            "value": "1.000",
        },
        {"code": "sample_conc", "name": "Sample concentration", "unit": "mg/mL", "value": "1"},
    ]
    assert observation.calculation == {
        "method": "SYN-UV",
        "revision": 3,
        "formula": "sample_abs / standard_abs * standard_conc / sample_conc * 100",
        "unit": "% label claim",
        "decimals": 2,
    }
    assert [e["asset_id"] for e in observation.eligibility["equipment"]] == ["SYN-UV-01"]
    assert observation.equipment_used == ["SYN-UV-01"]
    assert observation.reagents_used == ["SYN-RS-001"]
    assert (fresh(test).revision, fresh(lot).revision) == (start[0] + 1, start[1] + 1)
    event = AuditEvent.objects.get(action="observation.recorded")
    assert event.after["inputs"] == observation.inputs
    assert event.after["calculation"] == observation.calculation
    assert event.after["eligibility"] == observation.eligibility
    assert [call for call, _ in fixtures.BENCH_LOG] == ["lock_actor", "authorize"]
    (authorized,) = bench_calls("authorize")
    assert authorized == {
        "method_code": "SYN-UV",
        "test_code": "uv_assay",
        "context_type": "analytical.analyticaltest",
        "context_id": test.pk,
        "equipment_ids": [2],
        "reagent_ids": [1],
        "reason": f"Replicate 1 of {test.label} uv_assay",
    }


def test_invalid_inputs_store_nothing(people, calc):
    lot, _, tests = calc
    test = tests["uv_assay"]
    revisions = (fresh(test).revision, fresh(lot).revision)
    for change, message in [
        ({"sample_abs": None}, "Enter Sample absorbance"),
        ({"sample_abs": Decimal("NaN")}, "finite"),
        ({"sample_abs": "0.123456789"}, "decimal places"),
        ({"standard_abs": "0"}, "divides by zero"),
    ]:
        with pytest.raises(ValidationError, match=message):
            record_uv(people, test, inputs={**UV, **change})
    with pytest.raises(ValidationError, match="enter the inputs, not the value"):
        record_uv(people, test, value=Decimal("100"))
    with pytest.raises(ValidationError, match="cannot be reported as less than"):
        record_uv(people, test, qualifier="<")
    with pytest.raises(ValidationError, match="no calculation"):
        services.record_observation(
            actor=people["analyst"],
            test=tests["kf_water"],
            value=Decimal("0.1"),
            inputs={"x": "1"},
            raw_reference="KF-1",
            equipment_ids=[1],
        )
    assert not Observation.objects.exists()
    assert (fresh(test).revision, fresh(lot).revision) == revisions
    assert not AuditEvent.objects.filter(action="observation.recorded").exists()
    assert bench_calls("authorize") == []  # refused before the bench is asked


def test_correction_reenters_inputs_and_keeps_the_original(people, calc):
    _, _, tests = calc
    test = tests["uv_assay"]
    original = record_uv(people, test)
    correction = services.correct_observation(
        actor=people["analyst2"],
        observation=original,
        inputs={**UV, "sample_abs": "0.4990"},
        raw_reference="UV-RUN-1 p2",
        reason="Transcription error in sample absorbance",
        **FIT,
    )
    assert correction.value == Decimal("99.80") and correction.supersedes_id == original.pk
    assert correction.inputs[0]["value"] == "0.4990"
    kept = Observation.objects.get(pk=original.pk)
    assert kept.inputs[0]["value"] == "0.500625" and kept.value == Decimal("100.13")
    event = AuditEvent.objects.get(action="observation.corrected")
    assert event.before["inputs"] == kept.inputs and event.after["inputs"] == correction.inputs
    assert event.after["calculation"]["formula"] == kept.calculation["formula"]
    with pytest.raises(ValidationError, match="Enter Standard absorbance"):
        services.correct_observation(
            actor=people["analyst2"],
            observation=correction,
            inputs={k: v for k, v in UV.items() if k != "standard_abs"},
            raw_reference="x",
            reason="Partial re-entry",
            **FIT,
        )


def test_submit_and_review_recompute_calculated_observations(people, calc, monkeypatch):
    _, _, tests = calc
    test = tests["uv_assay"]
    record_uv(people, test)
    record_uv(people, test, inputs={**UV, "sample_abs": "0.4990"})
    real = formulas.calculate

    def drifted(expression, values, decimals):
        return real(expression, values, decimals) + Decimal("0.01")

    monkeypatch.setattr(formulas, "calculate", drifted)
    test = fresh(test)
    with pytest.raises(ValidationError, match="Calculated result changed; correct"):
        services.submit_test(
            actor=people["analyst"], test=test, expected_revision=test.revision, reason="Done"
        )
    assert fresh(test).state == "open"
    monkeypatch.setattr(formulas, "calculate", real)
    submitted, investigation = services.submit_test(
        actor=people["analyst"], test=test, expected_revision=test.revision, reason="Done"
    )
    assert investigation is None and submitted.reportable_display == "100.0"
    monkeypatch.setattr(formulas, "calculate", drifted)
    with pytest.raises(ValidationError, match="Calculated result changed; return"):
        services.review_test(
            actor=people["reviewer"],
            pin=PIN,
            test=fresh(test),
            expected_revision=fresh(test).revision,
            reason="Checked",
        )
    assert fresh(test).state == "submitted"
    assert not ElectronicSignature.objects.filter(object_id=str(test.pk)).exists()
    monkeypatch.setattr(formulas, "calculate", real)
    reviewed = services.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=fresh(test),
        expected_revision=fresh(test).revision,
        reason="Checked",
    )
    assert reviewed.state == "reviewed"


def test_required_equipment_and_reagents_are_refused_before_the_bench(people, calc):
    _, _, tests = calc
    with pytest.raises(ValidationError, match="requires at least one instrument") as raised:
        record_uv(people, tests["uv_assay"], equipment_ids=[], reagent_ids=[1])
    assert set(raised.value.error_dict) == {"equipment_ids"}
    with pytest.raises(ValidationError, match="reagent or standard lot") as raised:
        record_uv(people, tests["uv_assay"], equipment_ids=[2], reagent_ids=[])
    assert set(raised.value.error_dict) == {"reagent_ids"}
    assert not Observation.objects.exists() and bench_calls("authorize") == []
    # kf_water requires equipment only.
    observation = services.record_observation(
        actor=people["analyst"],
        test=tests["kf_water"],
        value=Decimal("0.12"),
        raw_reference="KF-1",
        equipment_ids=["1"],
    )
    assert observation.equipment_used == ["SYN-BAL-01"] and observation.reagents_used == []
    assert (observation.inputs, observation.calculation) == ([], {})
    with pytest.raises(ValidationError, match="Unknown equipment"):
        record_uv(people, tests["uv_assay"], equipment_ids=["x"])


def test_work_refused_rolls_back_and_is_audited_outside_the_transaction(people, calc):
    lot, _, tests = calc
    test = tests["uv_assay"]
    revisions = (fresh(test).revision, fresh(lot).revision)
    with pytest.raises(WorkRefused) as raised:
        record_uv(people, test, equipment_ids=[2, 3], reagent_ids=[2])
    assert raised.value.messages == [
        "SYN-UV-02: Equipment is out of service.",
        "SYN-RS-002: Lot is expired.",
    ]
    assert not Observation.objects.exists()
    assert (fresh(test).revision, fresh(lot).revision) == revisions
    assert not AuditEvent.objects.filter(action="observation.recorded").exists()
    (refusal,) = bench_calls("record_refusal")
    assert refusal["in_transaction"] is False
    assert (refusal["context_type"], refusal["context_id"], refusal["test_code"]) == (
        "analytical.analyticaltest",
        test.pk,
        "uv_assay",
    )
    assert refusal["refusals"] == raised.value.refusals
    # Correction by an unqualified analyst: refused, original untouched, refusal audited.
    original = record_uv(people, test)
    fixtures.UNQUALIFIED.add("analyst2")
    with pytest.raises(WorkRefused, match="No approved, current qualification"):
        services.correct_observation(
            actor=people["analyst2"],
            observation=original,
            inputs=UV,
            raw_reference="x",
            reason="Recheck",
            **FIT,
        )
    assert Observation.objects.filter(test=test).count() == 1
    assert len(bench_calls("record_refusal")) == 2
    assert bench_calls("record_refusal")[1]["reason"] == "Recheck"


def test_entries_are_held_without_a_configured_bench(people, calc, batch, settings):
    _, _, tests = calc
    for value in ("", None):
        if value is None:
            del settings.ANALYTICAL_BENCH
        else:
            settings.ANALYTICAL_BENCH = value
        with pytest.raises(ValidationError, match="No bench check is configured"):
            record_uv(people, tests["uv_assay"])
        with pytest.raises(ValidationError, match="No bench check is configured"):
            services.record_qc(
                actor=people["analyst2"],
                batch=batch,
                check_code="blank",
                value=Decimal("0.01"),
                raw_reference="RUN-1",
            )
    assert not Observation.objects.exists() and not QCResult.objects.exists()


# Batch QC ----------------------------------------------------------------------------------


def test_batch_qc_checks_the_analyst_and_freezes_evidence(people, batch):
    fixtures.UNQUALIFIED.add("analyst2")
    revision = fresh(batch).revision
    with pytest.raises(WorkRefused, match="analyst2: No approved, current qualification"):
        services.record_qc(
            actor=people["analyst2"],
            batch=batch,
            check_code="blank",
            value=Decimal("0.01"),
            raw_reference="RUN-1",
        )
    assert not QCResult.objects.exists() and fresh(batch).revision == revision
    (refusal,) = bench_calls("record_refusal")
    assert (refusal["context_type"], refusal["context_id"]) == ("analytical.qcbatch", batch.pk)
    assert (refusal["method_code"], refusal["test_code"]) == ("SYN-HPLC", "blank")
    assert refusal["in_transaction"] is False
    fixtures.UNQUALIFIED.clear()
    pass_qc(people, batch)
    result = QCResult.objects.get(check_code="blank")
    assert result.eligibility["user"] == people["analyst2"].pk
    assert result.eligibility["activity"] == "SYN-HPLC"
    event = AuditEvent.objects.filter(action="qc.recorded").first()
    assert event.after["eligibility"] == result.eligibility
    fixtures.UNQUALIFIED.add("analyst")
    with pytest.raises(WorkRefused):
        services.correct_qc(
            actor=people["analyst"],
            qc_result=result,
            value=Decimal("0.02"),
            raw_reference="RUN-1",
            reason="Typo",
        )
    assert QCResult.objects.count() == 2
    fixtures.UNQUALIFIED.clear()
    correction = services.correct_qc(
        actor=people["analyst"],
        qc_result=result,
        value=Decimal("0.02"),
        raw_reference="RUN-1",
        reason="Typo",
        equipment_ids=[1],
    )
    assert correction.equipment_used == ["SYN-BAL-01"]
    event = AuditEvent.objects.get(action="qc.corrected")
    assert event.after["eligibility"] == correction.eligibility


def test_batch_method_resource_requirements(people):
    batch = services.create_batch(
        actor=people["analyst"], number="SYN-B-LC", method_code="SYN-LC-BENCH", reason="Run"
    )
    with pytest.raises(ValidationError, match="requires at least one instrument"):
        services.record_qc(
            actor=people["analyst"],
            batch=batch,
            check_code="control",
            value=Decimal("100"),
            raw_reference="LC-1",
            reagent_ids=[1],
        )
    with pytest.raises(WorkRefused, match="SYN-UV-02"):
        services.record_qc(
            actor=people["analyst"],
            batch=batch,
            check_code="control",
            value=Decimal("100"),
            raw_reference="LC-1",
            equipment_ids=[3],
            reagent_ids=[1],
        )
    assert not QCResult.objects.exists()
    result = services.record_qc(
        actor=people["analyst"],
        batch=batch,
        check_code="control",
        value=Decimal("100"),
        raw_reference="LC-1",
        equipment_ids=[2],
        reagent_ids=[1],
    )
    assert (result.equipment_used, result.reagents_used) == (["SYN-UV-01"], ["SYN-RS-001"])
    (_, authorized) = bench_calls("authorize")  # the missing-instrument entry never reached it
    assert authorized["context_type"] == "analytical.qcbatch"
    assert authorized["reason"] == "QC check control of batch SYN-B-LC"


# Database guards ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "shape",
    [
        {"inputs": [{"code": "a", "value": "1"}]},  # inputs without the calculation
        {"calculation": {"formula": "a"}},  # calculation without inputs
        {"inputs": [{"code": "a"}], "calculation": {"formula": "a"}, "qualifier": "<"},
    ],
)
def test_database_refuses_inputs_without_calculation(people, calc, shape):
    _, _, tests = calc
    with pytest.raises(IntegrityError), transaction.atomic():
        Observation.objects.create(
            test=tests["uv_assay"],
            replicate=1,
            value=Decimal("1"),
            value_text="1",
            unit="% label claim",
            raw_reference="x",
            recorded_by=people["analyst"],
            **shape,
        )


def test_new_evidence_columns_are_immutable(people, calc, batch):
    _, _, tests = calc
    observation = record_uv(people, tests["uv_assay"])
    pass_qc(people, batch)
    result = QCResult.objects.first()
    for action in [
        lambda: Observation.objects.filter(pk=observation.pk).update(inputs=[]),
        lambda: Observation.objects.filter(pk=observation.pk).update(calculation={}),
        lambda: Observation.objects.filter(pk=observation.pk).update(eligibility={}),
        lambda: QCResult.objects.filter(pk=result.pk).update(eligibility={"user": 1}),
        lambda: QCResult.objects.filter(pk=result.pk).delete(),
    ]:
        with pytest.raises(DatabaseError), transaction.atomic():
            action()


# Pages -------------------------------------------------------------------------------------


@pytest.fixture
def pages(plain_static):
    return None


def test_calculated_entry_form_and_test_page(client, people, calc, pages):
    _, _, tests = calc
    test = tests["uv_assay"]
    login(client, people["analyst"])
    url = reverse("analytical:observation_new", args=[test.pk])
    body = client.get(url).content.decode()
    assert "Sample absorbance (AU)" in body and "Standard concentration (mg/mL)" in body
    assert 'name="value"' not in body and 'name="less_than"' not in body
    assert 'name="equipment_ids"' in body and 'name="reagent_ids"' in body
    assert "SYN-UV-02 UV spectrometer · out of service" in body
    assert "rounded half-up to 2 decimal places" in body
    form = {f"input_{k}": v for k, v in UV.items()} | {"raw_reference": "UV-RUN-1"}
    response = client.post(url, {**form, "reagent_ids": "1"})
    assert response.status_code == 422 and "Select the instrument used" in response.content.decode()
    response = client.post(url, {**form, "equipment_ids": ["2", "3"], "reagent_ids": "1"})
    body = response.content.decode()
    assert response.status_code == 422 and not Observation.objects.exists()
    assert 'id="id_equipment_ids_error"' in body
    assert "Refused: SYN-UV-02: Equipment is out of service." in body
    fixtures.UNQUALIFIED.add("analyst")
    body = client.post(url, {**form, "equipment_ids": "2", "reagent_ids": "1"}).content.decode()
    assert "Refused: analyst: No approved, current qualification" in body
    fixtures.UNQUALIFIED.clear()
    response = client.post(url, {**form, "sample_abs": "x", "equipment_ids": "2"})
    assert response.status_code == 422
    response = client.post(
        url, {**form, "input_standard_abs": "0", "equipment_ids": "2", "reagent_ids": "1"}
    )
    assert response.status_code == 422 and "divides by zero" in response.content.decode()
    response = client.post(url, {**form, "equipment_ids": "2", "reagent_ids": "1"})
    assert response.status_code == 302
    observation = Observation.objects.get()
    assert observation.value_text == "100.13" and observation.inputs[2]["value"] == "1.000"
    body = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    for text in [
        "Calculated value (% label claim)",
        "100.13",
        'Sample absorbance: <span class="vr-nowrap">0.500625 AU</span>',
        "sample_abs / standard_abs * standard_conc / sample_conc * 100",
        "SYN-UV revision 3; rounded half-up to 2 decimal places in % label claim",
        "SYN-UV-01",
        "SYN-RS-001",
    ]:
        assert text in body, text
    correct = reverse("analytical:observation_correct", args=[observation.pk])
    body = client.get(correct).content.decode()
    assert "Inputs being corrected" in body and "Sample absorbance 0.500625 AU" in body
    response = client.post(
        correct,
        {
            **form,
            "input_sample_abs": "0.4990",
            "equipment_ids": "2",
            "reagent_ids": "1",
            "reason": "Typo",
        },
    )
    assert response.status_code == 302
    assert Observation.objects.get(supersedes=observation).value_text == "99.80"


def test_entry_pages_are_held_without_a_bench(client, people, calc, batch, settings, pages):
    _, _, tests = calc
    settings.ANALYTICAL_BENCH = ""
    login(client, people["analyst"])
    for url, back in [
        (
            reverse("analytical:observation_new", args=[tests["kf_water"].pk]),
            reverse("analytical:test_detail", args=[tests["kf_water"].pk]),
        ),
        (
            reverse("analytical:qc_record", args=[batch.pk, "blank"]),
            reverse("analytical:batch_detail", args=[batch.pk]),
        ),
    ]:
        response = client.get(url)
        assert response.status_code == 302 and response.url == back
        assert "results are held" in client.get(back).content.decode()


def test_qc_pages_offer_resources_and_show_them(client, people, pages):
    batch = services.create_batch(
        actor=people["analyst"], number="SYN-B-LC", method_code="SYN-LC-BENCH", reason="Run"
    )
    login(client, people["analyst"])
    url = reverse("analytical:qc_record", args=[batch.pk, "control"])
    body = client.get(url).content.decode()
    assert 'name="equipment_ids"' in body and 'name="reagent_ids"' in body
    response = client.post(
        url, {"value": "100.0", "raw_reference": "LC-1", "equipment_ids": "3", "reagent_ids": "1"}
    )
    assert response.status_code == 422
    assert "Refused: SYN-UV-02: Equipment is out of service." in response.content.decode()
    response = client.post(
        url, {"value": "100.0", "raw_reference": "LC-1", "equipment_ids": "1", "reagent_ids": "1"}
    )
    assert response.status_code == 302
    result = QCResult.objects.get()
    body = client.get(reverse("analytical:batch_detail", args=[batch.pk])).content.decode()
    assert "Equipment and lots" in body and "SYN-BAL-01" in body and "SYN-RS-001" in body
    assert "requires each QC entry to record the equipment used and the reagent" in body
    correct = reverse("analytical:qc_correct", args=[result.pk])
    assert 'name="equipment_ids"' in client.get(correct).content.decode()
    response = client.post(
        correct,
        {
            "value": "99.0",
            "raw_reference": "LC-1",
            "equipment_ids": "2",
            "reagent_ids": "1",
            "reason": "Typo",
        },
    )
    assert response.status_code == 302
    body = client.get(reverse("analytical:batch_detail", args=[batch.pk])).content.decode()
    assert "equipment SYN-UV-01; lots SYN-RS-001" in body


def test_rows_written_before_this_change_still_display(client, people, assigned, batch, pages):
    _, _, tests = assigned
    test = tests["identity"]
    legacy = [
        {},
        {"user": people["analyst"].pk, "activity": "SYN-IR", "qualification": 7},
        {"policy": "synthetic-test-fixture", "user": people["analyst"].pk, "activity": "SYN-IR"},
        {"equipment": "not a list", "reagents": [None, {"id": 4}]},
    ]
    Observation.objects.create(
        test=test,
        replicate=1,
        value=Decimal("1.00"),
        value_text="1.00",
        unit="ratio",
        raw_reference="NB-OLD",
        eligibility=legacy[1],
        recorded_by=people["analyst"],
    )
    for n, evidence in enumerate(legacy):
        QCResult.objects.create(
            batch=batch,
            check_code="blank" if n == 0 else "control",
            value=Decimal("0.01"),
            value_text="0.01",
            unit="%",
            raw_reference="RUN-OLD",
            eligibility=evidence,
            recorded_by=people["analyst2"],
            supersedes=QCResult.objects.filter(check_code="control").last() if n > 1 else None,
        )
    login(client, people["auditor"])
    body = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert "1.00" in body and "Not recorded" in body and "How it was calculated" not in body
    body = client.get(reverse("analytical:batch_detail", args=[batch.pk])).content.decode()
    assert "Not recorded" in body and "#4" in body
    assert QCBatch.objects.get(pk=batch.pk).qc_status()[0] == "failed"
