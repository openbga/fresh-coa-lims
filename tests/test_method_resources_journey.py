"""Suitable resources across apps: a method version approved with the instruments and lots
suitable for it -> a test frozen to that version -> the production bench offers and accepts only
what it lists, beside the calibration, release and expiry checks; tests frozen to an earlier
version keep its rule. Production requirement adapter and bench bridge; synthetic data only."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from analytical import services as analytical
from analytical.contracts import WorkRefused
from analytical.models import Observation
from catalog import services as catalog
from core.models import AuditEvent
from laboratory import services as laboratory
from tests.test_calculation_bench_journey import (
    REPLICATES,
    assign_water,
    build_world,
    calibrate,
    record,
)
from tests.test_integrated_journey import PIN, approve

pytestmark = pytest.mark.django_db(transaction=True)


def balance(people):
    item = laboratory.register_equipment(
        actor=people["analyst"],
        asset_id="SYN-BAL-09",
        description="Synthetic balance",
        category="Balance",
        location="Synthetic laboratory",
        requires_qualification=False,
        reason="Synthetic equipment",
    )
    calibrate(people, item)
    return item


def second_version(data, *, method_qualified=False, balance=False):
    """Version 2 of the titration method, listing the titrator (by its category) and the titrant
    as required, approved now; it takes over from version 1."""
    author = data["people"]["author"]
    revision = catalog.new_method_revision(
        actor=author,
        method=data["method"],
        technique="Titration",
        document_ref="SOP-SYN-KF rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-KF rev 1",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=365),
        reason="List the suitable instrument and titrant",
    )
    lines = [
        ("instrument", "TITRATOR", method_qualified, True),
        ("reagent", "synthetic titrant", False, True),
    ]
    if balance:
        lines.append(("instrument", "balance", False, False))
    for kind, name, qualified, required in lines:
        catalog.add_method_resource(
            actor=author,
            revision=revision,
            kind=kind,
            name=name,
            method_qualified=qualified,
            required=required,
            reason="Validated with it",
        )
    return approve(revision, data["people"]["approver"])


@pytest.fixture
def world(django_user_model):
    data = build_world(django_user_model)
    data["balance"] = balance(data["people"])
    return data


def blocked():
    return AuditEvent.objects.filter(action="resource.use_blocked")


def test_a_test_frozen_to_the_version_accepts_only_what_it_lists(world):
    data, people = world, world["people"]
    second_version(data)
    test = assign_water(data)
    assert test.requirement["method"]["revision"] == 2
    with pytest.raises(WorkRefused, match="category “Balance” is not one that method synthetic-kf"):
        record(data, test, REPLICATES[0], equipment_ids=[data["balance"].pk])
    event = blocked().get()
    assert event.after["activity"] == "synthetic-kf"
    subjects = {r["subject"] for r in event.after["refusals"]}
    assert subjects == {"SYN-BAL-09", "Method synthetic-kf"}  # and the titrator is missing
    assert not Observation.objects.filter(test=test).exists()

    observation = record(data, test, REPLICATES[0])
    (equipment,) = observation.eligibility["equipment"]
    (reagent,) = observation.eligibility["reagents"]
    assert equipment["suitable_as"] == "titrator"
    assert reagent["suitable_as"] == [
        {"kind": "reagent", "name": "Synthetic titrant", "lot": "SYN-KF-TITRANT-01"}
    ]
    # A correction is checked against the same version.
    with pytest.raises(WorkRefused, match="SYN-BAL-09"):
        analytical.correct_observation(
            actor=people["analyst"],
            observation=observation,
            inputs=REPLICATES[1],
            raw_reference="RAW-SYN-CB rev 2",
            equipment_ids=[data["equipment"].pk, data["balance"].pk],
            reagent_ids=[data["standard"].pk],
            reason="Transcription error",
        )


def test_the_entry_page_offers_only_the_listed_instruments(world, client):
    data, people = world, world["people"]
    second_version(data)
    test = assign_water(data)
    client.force_login(people["analyst"])
    body = client.get(reverse("analytical:observation_new", args=[test.pk])).content.decode()
    assert "SYN-TITRATOR-01" in body and "SYN-KF-TITRANT-01" in body
    assert "SYN-BAL-09" not in body
    # The method page shows both lines beside the register.
    client.force_login(people["author"])
    body = client.get(reverse("catalog:method", args=[data["method"].pk])).content.decode()
    assert "Suitable instruments, reagents and standards" in body
    assert "SYN-TITRATOR-01" in body and "SYN-KF-TITRANT-01" in body


def test_a_line_asking_for_an_instrument_qualified_for_the_method(world):
    data, people = world, world["people"]
    second_version(data, method_qualified=True)
    test = assign_water(data)
    with pytest.raises(
        WorkRefused, match="qualification of this instrument for method synthetic-kf"
    ):
        record(data, test, REPLICATES[0])
    qualification = laboratory.record_qualification(
        actor=people["author"],
        equipment=data["equipment"],
        activity="synthetic-kf",
        evidence_ref="PQ-SYN-KF rev 1",
        valid_from=timezone.localdate() - timedelta(days=1),
        valid_until=timezone.localdate() + timedelta(days=365),
        reason="Performance qualification for the method",
    )
    qualification = laboratory.approve_qualification(
        actor=people["approver"],
        pin=PIN,
        qualification=qualification,
        expected_revision=qualification.revision,
        reason="Independent review of the qualification",
    )
    observation = record(data, test, REPLICATES[0])
    assert observation.eligibility["equipment"][0]["method_qualification"] == qualification.pk


def test_tests_frozen_to_an_earlier_version_keep_its_rule(world):
    data = world
    earlier = assign_water(data, reference="SYN-CB-S-EARLY")
    assert earlier.requirement["method"]["revision"] == 1
    second_version(data)
    observation = record(
        data, earlier, REPLICATES[0], equipment_ids=[data["equipment"].pk, data["balance"].pk]
    )
    assert [e["asset_id"] for e in observation.eligibility["equipment"]] == [
        "SYN-TITRATOR-01",
        "SYN-BAL-09",
    ]
    assert all("suitable_as" not in e for e in observation.eligibility["equipment"])


@pytest.mark.parametrize("listed", [False, True])
def test_readings_are_offered_only_from_instruments_the_version_lists(world, client, listed):
    import json
    import re

    from tests.test_instrument_readings import connect

    data, people = world, world["people"]
    connection = connect(people["author"], data["balance"])
    second_version(data, balance=listed)
    test = assign_water(data)
    client.force_login(people["analyst"])
    page = client.get(reverse("analytical:observation_new", args=[test.pk])).content.decode()
    if not listed:
        assert 'id="vr-reading-options"' not in page and "SYN-BAL-09" not in page
        return
    options = json.loads(
        re.search(r'id="vr-reading-options" type="application/json">(.*?)</script>', page).group(1)
    )
    assert [(f["name"], f["instruments"]) for f in options["fields"]] == [
        ("input_sample_mass", [connection.pk])
    ]


def test_batch_qc_and_its_correction_accept_only_what_the_batch_version_lists(world):
    from decimal import Decimal

    from analytical.models import QCResult
    from catalog.models import Method
    from tests.test_calculation_bench_journey import qualify

    data, people = world, world["people"]
    author, analyst = people["author"], people["analyst"]
    revision = catalog.new_method_revision(
        actor=author,
        method=Method.objects.get(code="synthetic-lc"),
        technique="Chromatography",
        document_ref="SOP-SYN-LC rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-LC rev 1",
        requires_batch=True,
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=365),
        reason="Run on the titrator only",
    )
    catalog.add_method_resource(
        actor=author, revision=revision, kind="instrument", name="titrator", reason="Validated"
    )
    approve(revision, people["approver"])
    qualify(people, "synthetic-lc")
    batch = analytical.create_batch(
        actor=analyst, number="SYN-MR-B001", method_code="synthetic-lc", reason="Synthetic run"
    )
    assert batch.method_spec.revision == 2
    entry = {
        "actor": analyst,
        "batch": batch,
        "check_code": "control",
        "value": Decimal("100.2"),
        "raw_reference": "RAW-SYN-MR-QC rev 1",
        "reason": "Synthetic batch QC",
    }
    with pytest.raises(WorkRefused, match="category “Balance” is not one"):
        analytical.record_qc(**entry, equipment_ids=[data["balance"].pk])
    assert not QCResult.objects.exists() and blocked().count() == 1
    result = analytical.record_qc(**entry, equipment_ids=[data["equipment"].pk])
    assert result.eligibility["equipment"][0]["suitable_as"] == "titrator"
    with pytest.raises(WorkRefused, match="category “Balance” is not one"):
        analytical.correct_qc(
            actor=analyst,
            qc_result=result,
            value=Decimal("100.1"),
            raw_reference="RAW-SYN-MR-QC rev 2",
            reason="Transcription error",
            equipment_ids=[data["balance"].pk],
        )
    assert QCResult.objects.count() == 1 and blocked().count() == 2


@pytest.fixture
def import_world(django_user_model):
    from tests.test_instrument_import_journey import FILE_IMPORT

    data = build_world(django_user_model, file_import=FILE_IMPORT)
    data["balance"] = balance(data["people"])
    return data


def test_an_import_accepts_only_what_the_version_lists(import_world):
    from analytical import imports
    from tests.test_instrument_import_journey import ENTERED, attach, export

    data = import_world
    second_version(data)
    test = assign_water(data)
    assert test.spec.method.revision == 2 and test.spec.method.file_import
    stored = attach(data, test, export(test.label, "1,25", "1,31"))

    def run(equipment):
        fresh = type(test).objects.get(pk=test.pk)
        return imports.import_observations(
            actor=data["people"]["analyst"],
            test=fresh,
            stored=stored,
            expected_revision=fresh.revision,
            raw_reference="Titrator memory, run 4",
            entered={2: ENTERED[0], 3: ENTERED[1]},
            equipment_ids=[item.pk for item in equipment],
            reagent_ids=[data["standard"].pk],
        )

    with pytest.raises(WorkRefused, match="category “Balance” is not one"):
        run([data["equipment"], data["balance"]])
    assert not Observation.objects.exists() and blocked().count() == 1
    first, second = run([data["equipment"]])
    assert first.eligibility["equipment"][0]["suitable_as"] == "titrator"


def test_a_required_line_makes_the_entry_field_required():
    from types import SimpleNamespace

    from analytical.forms import bench_fields

    method = SimpleNamespace(requires_equipment=False, requires_reagent=False)
    choices = {
        "equipment": [(1, "LC-1")],
        "reagents": [(2, "RS-1")],
        "required": {"equipment": True, "reagents": False},
    }
    fields = bench_fields(choices, method)
    assert fields["equipment_ids"].required and not fields["reagent_ids"].required
    assert fields["equipment_ids"].help_text == "This method requires at least one instrument."
    assert bench_fields({"equipment": [], "reagents": []}, method) == {}


def test_the_bench_holds_an_entry_frozen_to_a_version_it_cannot_find(world):
    from django.core.exceptions import ValidationError

    from config.integrations import LaboratoryBench

    with pytest.raises(ValidationError, match="not approved here"):
        LaboratoryBench().choices(method_code="synthetic-kf", method_revision=9)
    assert LaboratoryBench().choices(method_code="synthetic-kf", method_revision=1)["equipment"]
    # A method from another requirement source lists nothing here.
    assert "required" not in LaboratoryBench().choices(method_code="SYN-OTHER", method_revision=1)
