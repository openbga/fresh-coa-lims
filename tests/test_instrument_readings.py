"""Readings from balances and meters connected to the analyst's computer, across apps.

Quality sets the data connection of an instrument -> the analyst's browser passes on what the
device answered -> the server reads it with the connection's format and keeps every reading on
the test -> a replicate records the readings it names, checked under the bench's equipment locks
-> submission and independent review read the recorded readings again. Uses the production
requirement adapter and bench bridge and service-created approvals only (synthetic data).
"""

import base64
import io
import json
import re
import zipfile
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from analytical import readings as instrument
from analytical import services as analytical
from analytical.models import InstrumentReading, Observation
from core.models import AuditEvent
from laboratory import services as laboratory
from laboratory.models import DeviceConnection
from reporting import lot_record
from tests.test_calculation_bench_journey import assign_water, build_world, calibrate, qualify
from tests.test_integrated_journey import PASSWORD, PIN

pytestmark = pytest.mark.django_db(transaction=True)

SERIAL = "B123456789"
MASSES = ("2500.4", "2498.7")


def sics(weight, serial=SERIAL):
    return f'I4 A "{serial}"\r\n{weight}\r\n'


def encoded(text):
    return base64.b64encode(text.encode("latin-1")).decode()


@pytest.fixture
def world(django_user_model):
    data = build_world(django_user_model)
    people = data["people"]
    balance = laboratory.register_equipment(
        actor=people["analyst"],
        asset_id="SYN-BAL-01",
        description="Synthetic analytical balance",
        category="balance",
        location="Synthetic weighing room",
        requires_qualification=False,
        reason="Synthetic equipment",
    )
    calibrate(people, balance)
    data["balance"] = balance
    data["connection"] = connect(people["author"], balance)
    data["test"] = assign_water(data)
    return data


def connect(actor, equipment, replacing=None, **overrides):
    values = {
        "device_format": "mt_sics",
        "baud_rate": 9600,
        "data_bits": 8,
        "parity": "none",
        "stop_bits": 1,
        "flow_control": "none",
        "serial_number": SERIAL,
        "verification_ref": "VER-SYN-BAL-01 interface check rev 1",
    } | overrides
    return laboratory.set_connection(
        actor=actor,
        equipment=equipment,
        reason="Synthetic balance connected to the bench computer",
        replacing=replacing,
        **values,
    )


def read(data, weight="S S   2500.4 mg", target="sample_mass", actor=None, connection_id=None):
    return instrument.take_reading(
        actor=actor or data["people"]["analyst"],
        test=data["test"],
        target=target,
        connection_id=connection_id or data["connection"].pk,
        response=encoded(sics(weight)),
    )


def record(data, mass="2500.4", readings=None, **overrides):
    arguments = {
        "actor": data["people"]["analyst"],
        "test": data["test"],
        "raw_reference": "Balance SYN-BAL-01 and titrator memory, run 4",
        "inputs": {"titrant_volume": "1.25", "titer": "4.98", "sample_mass": mass},
        "equipment_ids": [data["equipment"].pk, data["balance"].pk],
        "reagent_ids": [data["standard"].pk],
        "readings": readings or {},
        "reason": "Synthetic original observation",
    } | overrides
    return analytical.record_observation(**arguments)


def test_reading_is_kept_recorded_with_its_replicate_and_read_again_at_review(world):
    data, people = world, world["people"]
    first = read(data)
    assert (first.value_text, first.unit, first.serial_number) == ("2500.4", "mg", SERIAL)
    assert first.value == Decimal("2500.4")
    assert first.request == "I4\r\nS\r\n"
    assert first.response == sics("S S   2500.4 mg")
    assert first.connection["asset_id"] == "SYN-BAL-01"
    assert first.connection["serial_number"] == SERIAL
    assert first.observation is None
    event = AuditEvent.objects.get(action="instrument.read")
    assert event.actor == people["analyst"]
    assert event.after["reading"] == first.pk and event.after["value"] == "2500.4"

    # A second weighing is kept too; the replicate records the one it names.
    unused = read(data, "S S   2500.6 mg")
    observation = record(data, readings={"sample_mass": first.pk})
    first.refresh_from_db()
    assert first.observation == observation
    assert observation.inputs[2] == {
        "code": "sample_mass",
        "name": "Sample mass",
        "unit": "mg",
        "value": "2500.4",
    }
    recorded = AuditEvent.objects.get(action="observation.recorded")
    assert recorded.after["readings"] == [
        {
            "reading": first.pk,
            "target": "sample_mass",
            "value": "2500.4",
            "unit": "mg",
            "equipment": "SYN-BAL-01",
            "connection": data["connection"].pk,
        }
    ]
    # The second replicate is typed; nothing links it to a reading.
    typed = record(data, mass=MASSES[1])
    assert not typed.instrument_readings.exists()
    unused.refresh_from_db()
    assert unused.observation is None

    test = data["test"]
    test.refresh_from_db()
    analytical.submit_test(
        actor=people["analyst"],
        test=test,
        expected_revision=test.revision,
        reason="Results complete",
    )
    test.refresh_from_db()
    assert instrument.reading_problems(test, list(test.current_observations())) == []
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Readings checked against the balance",
    )
    test.refresh_from_db()
    assert test.state == "reviewed"


def test_a_direct_result_reads_its_value_from_a_meter(world, django_user_model):
    """A meter reports its own serial number in every reading; the unit must be the result's."""
    data = world
    meter = laboratory.register_equipment(
        actor=data["people"]["analyst"],
        asset_id="SYN-PH-01",
        description="Synthetic pH meter",
        category="pH meter",
        requires_qualification=False,
        reason="Synthetic meter",
    )
    connection_ = connect(
        data["people"]["author"], meter, device_format="orion_star", serial_number="X01036"
    )
    line = (
        "A211 pH, X01036, 3.04, ABCDE, 01/03/15 16:05:41, SAMPLE, CH-1, pH, 7.000, pH, 0.0, mV, "
        "25.0, C, 98.1,%, M100, #1\r> "
    )
    # This test's result is calculated: the meter's reading is no input of it.
    with pytest.raises(ValidationError, match="no reading for that value"):
        instrument.take_reading(
            actor=data["people"]["analyst"],
            test=data["test"],
            target="value",
            connection_id=connection_.pk,
            response=encoded(line),
        )
    evidence = connection_.evidence()
    assert instrument.read_device(evidence, line, "pH").text == "7.000"
    with pytest.raises(ValidationError, match="reported its reading in pH; this value is in mV"):
        instrument.read_device(evidence, line, "mV")
    with pytest.raises(ValidationError, match="serial number X01037"):
        instrument.read_device(evidence, line.replace("X01036", "X01037"), "pH")


@pytest.mark.parametrize(
    "weight, message",
    [
        ("S D   2500.4 mg", "did not report as stable"),
        ("S +", "overload"),
        ("S S   2.5004 g", "reported its reading in g; this value is in mg"),
    ],
)
def test_a_reading_that_cannot_be_used_stores_nothing(world, weight, message):
    with pytest.raises(ValidationError, match=message):
        read(world, weight)
    assert not InstrumentReading.objects.exists()
    assert not AuditEvent.objects.filter(action="instrument.read").exists()


def test_the_device_must_be_the_one_its_connection_names(world):
    data = world
    with pytest.raises(ValidationError, match="reported serial number B999"):
        instrument.take_reading(
            actor=data["people"]["analyst"],
            test=data["test"],
            target="sample_mass",
            connection_id=data["connection"].pk,
            response=encoded(sics("S S   2500.4 mg", serial="B999")),
        )
    with pytest.raises(ValidationError, match="did not arrive intact"):
        instrument.take_reading(
            actor=data["people"]["analyst"],
            test=data["test"],
            target="sample_mass",
            connection_id=data["connection"].pk,
            response="not base64!",
        )
    assert not InstrumentReading.objects.exists()


def test_only_an_analyst_reads_and_only_while_the_test_is_open(world):
    data, people = world, world["people"]
    for name in ("reviewer", "author"):
        with pytest.raises(PermissionDenied):
            read(data, actor=people[name])
    with pytest.raises(ValidationError, match="no reading for that value"):
        read(data, target="titrant_volume_x")
    laboratory.end_connection(
        actor=people["author"],
        equipment=data["balance"],
        reason="Balance moved to another bench",
        connection_id=data["connection"].pk,
    )
    with pytest.raises(ValidationError, match="no longer current"):
        read(data)
    assert not InstrumentReading.objects.exists()


def test_recording_checks_every_reading_it_names(world, django_user_model):
    data, people = world, world["people"]
    reading = read(data)

    def refused(message, **arguments):
        with pytest.raises(ValidationError, match=message):
            record(data, **arguments)
        reading.refresh_from_db()
        assert reading.observation is None
        assert not Observation.objects.exists()

    refused(
        "differs from the reading 2500.4 mg", mass="2500.40", readings={"sample_mass": reading.pk}
    )
    refused(
        "select SYN-BAL-01 under Equipment used",
        readings={"sample_mass": reading.pk},
        equipment_ids=[data["equipment"].pk],
    )
    refused("not taken for this value", readings={"titer": reading.pk})
    refused("not valid", readings={"sample_mass": "x"})

    colleague = django_user_model.objects.create_user("cb_analyst2", password=PASSWORD)
    colleague.groups.set(people["analyst"].groups.all())
    qualify({**people, "analyst": colleague}, data["method"].code)
    with pytest.raises(ValidationError, match="recorded by the person who took it"):
        analytical.record_observation(
            actor=colleague,
            test=data["test"],
            raw_reference="Balance SYN-BAL-01",
            inputs={"titrant_volume": "1.25", "titer": "4.98", "sample_mass": "2500.4"},
            equipment_ids=[data["equipment"].pk, data["balance"].pk],
            reagent_ids=[data["standard"].pk],
            readings={"sample_mass": reading.pk},
        )

    # A new connection after the reading: the reading is no longer relied on.
    connect(people["author"], data["balance"], replacing=data["connection"].pk)
    refused("changed after this reading", readings={"sample_mass": reading.pk})

    # A reading is recorded once.
    data["connection"] = DeviceConnection.objects.get(
        equipment=data["balance"], ended_at__isnull=True
    )
    fresh = read(data)
    record(data, readings={"sample_mass": fresh.pk})
    with pytest.raises(ValidationError, match="already recorded"):
        record(data, readings={"sample_mass": fresh.pk})


def test_a_correction_can_record_a_new_reading_and_keeps_the_original(world):
    data = world
    typed = record(data, mass="2500.9")
    reading = read(data)
    correction = analytical.correct_observation(
        actor=data["people"]["analyst"],
        observation=typed,
        raw_reference="Balance SYN-BAL-01 reading",
        reason="Sample mass mistyped; read from the balance",
        inputs={"titrant_volume": "1.25", "titer": "4.98", "sample_mass": "2500.4"},
        equipment_ids=[data["equipment"].pk, data["balance"].pk],
        reagent_ids=[data["standard"].pk],
        readings={"sample_mass": reading.pk},
    )
    reading.refresh_from_db()
    assert reading.observation == correction
    assert correction.supersedes == typed
    event = AuditEvent.objects.get(action="observation.corrected")
    assert event.after["readings"][0]["reading"] == reading.pk


def test_readings_and_connections_are_append_only(world, django_user_model):
    data, people = world, world["people"]
    reading = read(data)
    observation = record(data, readings={"sample_mass": reading.pk})
    for statement in (
        "UPDATE analytical_instrumentreading SET value_text = '1' WHERE id = %s",
        "UPDATE analytical_instrumentreading SET observation_id = NULL WHERE id = %s",
        "DELETE FROM analytical_instrumentreading WHERE id = %s",
    ):
        with pytest.raises(DatabaseError, match="immutable|cannot be deleted"):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(statement, [reading.pk])
    # A reading is recorded by a replicate of its own test, by the person who took it.
    colleague = django_user_model.objects.create_user("cb_analyst2", password=PASSWORD)
    colleague.groups.set(people["analyst"].groups.all())
    qualify({**people, "analyst": colleague}, data["method"].code)
    theirs = record(data, mass=MASSES[1], actor=colleague)
    unused = read(data)
    with pytest.raises(DatabaseError, match="by the person who took it"):
        with transaction.atomic():
            InstrumentReading.objects.filter(pk=unused.pk).update(observation=theirs)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            InstrumentReading.objects.filter(pk=unused.pk).update(observation=observation)
    for statement in (
        "UPDATE laboratory_deviceconnection SET serial_number = 'X' WHERE id = %s",
        "DELETE FROM laboratory_deviceconnection WHERE id = %s",
    ):
        with pytest.raises(DatabaseError, match="immutable|cannot be deleted"):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(statement, [data["connection"].pk])


def test_submission_and_review_refuse_a_reading_that_no_longer_agrees(world):
    data, people = world, world["people"]
    reading = read(data)
    record(data, readings={"sample_mass": reading.pk})
    record(data, mass=MASSES[1])
    test = data["test"]
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE analytical_instrumentreading DISABLE TRIGGER instrument_reading_guard"
        )
        cursor.execute(
            "UPDATE analytical_instrumentreading SET response = %s WHERE id = %s",
            [sics("S S   2501.4 mg"), reading.pk],
        )
        cursor.execute(
            "ALTER TABLE analytical_instrumentreading ENABLE TRIGGER instrument_reading_guard"
        )
    test.refresh_from_db()
    problems = instrument.reading_problems(test, list(test.current_observations()))
    assert problems == [
        "Replicate 1, Sample mass from SYN-BAL-01: the replicate records 2500.4; the device sent "
        "2501.4 mg."
    ]
    with pytest.raises(ValidationError, match="no longer agrees with what the device sent"):
        analytical.submit_test(
            actor=people["analyst"], test=test, expected_revision=test.revision, reason="Done"
        )
    client = Client()
    client.force_login(people["analyst"])
    page = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert "no longer agree with the replicates that record them" in page


def test_set_and_end_a_data_connection(world):
    data, people = world, world["people"]
    balance, first = data["balance"], data["connection"]
    with pytest.raises(PermissionDenied):
        connect(people["analyst"], balance, replacing=first.pk)
    with pytest.raises(ValidationError, match="changed while you were editing"):
        connect(people["approver"], balance, replacing=None)
    with pytest.raises(ValidationError, match="State why"):
        laboratory.set_connection(
            actor=people["author"],
            equipment=balance,
            reason=" ",
            replacing=first.pk,
            device_format="mt_sics",
            baud_rate=9600,
            data_bits=8,
            parity="none",
            stop_bits=1,
            serial_number=SERIAL,
            verification_ref="VER",
        )
    with pytest.raises(ValidationError, match="serial number the device reports"):
        connect(people["author"], balance, replacing=first.pk, serial_number="")
    with pytest.raises(ValidationError, match="does not report a serial number"):
        connect(people["author"], balance, replacing=first.pk, device_format="and_standard")

    second = connect(
        people["approver"],
        balance,
        replacing=first.pk,
        device_format="and_standard",
        baud_rate=2400,
        data_bits=7,
        parity="even",
        serial_number="",
    )
    first.refresh_from_db()
    assert first.ended_by == people["approver"] and first.ended_at is not None
    assert second.settings_text == "2400 baud, 7E1, no flow control"
    event = AuditEvent.objects.get(action="equipment.connection_set", after__connection=second.pk)
    assert event.before["connection"] == first.pk and event.after["connection"] == second.pk
    assert event.after["serial_number"] == "" and event.after["device_format"] == "and_standard"

    with pytest.raises(ValidationError, match="changed while you were editing"):
        laboratory.end_connection(
            actor=people["author"], equipment=balance, reason="Gone", connection_id=first.pk
        )
    laboratory.end_connection(
        actor=people["author"], equipment=balance, reason="Gone", connection_id=second.pk
    )
    assert not DeviceConnection.objects.filter(ended_at__isnull=True).exists()
    assert AuditEvent.objects.filter(action="equipment.connection_ended").count() == 1


def test_pages_offer_readings_show_them_and_export_them(world):
    data, people = world, world["people"]
    test = data["test"]
    analyst = Client()
    analyst.force_login(people["analyst"])
    url = reverse("analytical:observation_new", args=[test.pk])
    page = analyst.get(url).content.decode()
    options = json.loads(
        re.search(r'id="vr-reading-options" type="application/json">(.*?)</script>', page).group(1)
    )
    assert options["url"] == reverse("analytical:instrument_read", args=[test.pk])
    # A balance is offered beside the mass only; the volume and the titer are typed.
    assert [(f["name"], f["instruments"]) for f in options["fields"]] == [
        ("input_sample_mass", [data["connection"].pk])
    ]
    instrument_ = options["instruments"][0]
    assert instrument_["asset_id"] == "SYN-BAL-01"
    assert instrument_["open"] == {
        "baudRate": 9600,
        "dataBits": 8,
        "parity": "none",
        "stopBits": 1,
        "flowControl": "none",
    }
    assert "js/device-readings." in page
    assert 'name="reading_input_sample_mass"' in page

    # The reading page answers what was read, or why it was refused, as JSON.
    read_url = options["url"]
    answer = analyst.post(
        read_url,
        {
            "target": "sample_mass",
            "connection": data["connection"].pk,
            "response": encoded(sics("S S   2500.4 mg")),
        },
    )
    assert answer.status_code == 201
    taken = answer.json()
    assert taken["value"] == "2500.4" and taken["asset_id"] == "SYN-BAL-01"
    assert taken["response"] == 'I4 A "B123456789"␍␊S S   2500.4 mg␍␊'
    refused = analyst.post(
        read_url,
        {
            "target": "sample_mass",
            "connection": data["connection"].pk,
            "response": encoded("S +\r\n"),
        },
    )
    assert refused.status_code == 422 and "overload" in refused.json()["error"]
    reviewer = Client()
    reviewer.force_login(people["reviewer"])
    assert reviewer.post(read_url, {"target": "sample_mass"}).status_code == 403
    assert analyst.get(read_url).status_code == 405

    # Recorded through the page: the reading's id travels in the hidden field.
    response = analyst.post(
        url,
        {
            "input_titrant_volume": "1.25",
            "input_titer": "4.98",
            "input_sample_mass": "2500.4",
            "reading_input_sample_mass": str(taken["reading"]),
            "equipment_ids": [data["equipment"].pk, data["balance"].pk],
            "reagent_ids": [data["standard"].pk],
            "raw_reference": "Balance SYN-BAL-01 and titrator memory",
        },
    )
    assert response.status_code == 302
    observation = Observation.objects.get()
    assert observation.instrument_readings.get().pk == taken["reading"]

    # A refused entry keeps the reading in the form, and the page restores it.
    second = read(data, "S S   2498.7 mg")
    refused_page = analyst.post(
        url,
        {
            "input_titrant_volume": "1.31",
            "input_titer": "4.98",
            "input_sample_mass": "2498.7",
            "reading_input_sample_mass": str(second.pk),
            "equipment_ids": [data["equipment"].pk],
            "reagent_ids": [data["standard"].pk],
            "raw_reference": "Balance SYN-BAL-01",
        },
    )
    assert refused_page.status_code == 422
    body = refused_page.content.decode()
    assert "select SYN-BAL-01 under Equipment used" in body
    restored = json.loads(
        re.search(r'id="vr-reading-options" type="application/json">(.*?)</script>', body).group(1)
    )
    assert restored["taken"]["input_sample_mass"]["reading"] == second.pk

    detail = analyst.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert "Instrument readings" in detail
    assert "Read from instruments:" in detail
    assert "Typed: Titrant volume, Titrant water equivalent" in detail
    assert "Not recorded" in detail and "Replicate 1" in detail

    equipment_page = Client()
    equipment_page.force_login(people["author"])
    shown = equipment_page.get(
        reverse("laboratory:equipment_detail", args=[data["balance"].pk])
    ).content.decode()
    assert "Data connections" in shown and "VER-SYN-BAL-01 interface check rev 1" in shown
    assert reverse("laboratory:equipment_connection_new", args=[data["balance"].pk]) in shown

    package = lot_record.export_lot_record(
        actor=people["author"], lot_pk=data["lot"].pk, purpose="Synthetic inspection copy"
    )
    archive = zipfile.ZipFile(io.BytesIO(package.file.read()))
    (record_name,) = [n for n in archive.namelist() if n.endswith("/record.json")]
    record_json = json.loads(archive.read(record_name))
    (rows,) = [s["records"] for s in record_json["sections"] if s["key"] == "instrument_readings"]
    assert sorted(r["fields"]["value_text"] for r in rows) == ["2498.7", "2500.4"]


def test_connection_pages_are_for_quality(world):
    data, people = world, world["people"]
    balance = data["balance"]
    new_url = reverse("laboratory:equipment_connection_new", args=[balance.pk])
    end_url = reverse("laboratory:equipment_connection_end", args=[balance.pk])
    analyst = Client()
    analyst.force_login(people["analyst"])
    assert analyst.get(new_url).status_code == 403
    assert analyst.get(end_url).status_code == 403
    quality = Client()
    quality.force_login(people["approver"])
    page = quality.get(new_url)
    assert page.status_code == 200
    assert f'name="replacing" value="{data["connection"].pk}"' in page.content.decode()
    response = quality.post(
        new_url,
        {
            "replacing": data["connection"].pk,
            "device_format": "mt_sics",
            "baud_rate": "19200",
            "data_bits": "8",
            "parity": "none",
            "stop_bits": "1",
            "flow_control": "hardware",
            "serial_number": SERIAL,
            "verification_ref": "VER-SYN-BAL-01 rev 2",
            "reason": "Faster port on the new bench computer",
        },
    )
    assert response.status_code == 302
    current = DeviceConnection.objects.get(ended_at__isnull=True)
    assert current.baud_rate == 19200 and current.flow_control == "hardware"
    ended = quality.post(end_url, {"connection": current.pk, "reason": "Bench computer replaced"})
    assert ended.status_code == 302
    assert not DeviceConnection.objects.filter(ended_at__isnull=True).exists()
    assert quality.get(end_url).status_code == 302


def test_the_end_page_ends_only_the_connection_it_showed(world):
    data, people = world, world["people"]
    balance, shown = data["balance"], data["connection"]
    quality = Client()
    quality.force_login(people["approver"])
    end_url = reverse("laboratory:equipment_connection_end", args=[balance.pk])
    page = quality.get(end_url).content.decode()
    assert f'name="connection" value="{shown.pk}"' in page
    # Another quality person replaces the connection meanwhile.
    replacement = connect(people["author"], balance, replacing=shown.pk)
    response = quality.post(end_url, {"connection": shown.pk, "reason": "Moved to bench 2"})
    assert response.status_code == 422
    assert "changed while you were editing" in response.content.decode()
    replacement.refresh_from_db()
    assert replacement.ended_at is None
    assert not AuditEvent.objects.filter(action="equipment.connection_ended").exists()


def test_a_refused_reading_is_dropped_from_the_form_so_it_is_read_again_or_typed(world):
    data, people = world, world["people"]
    taken = read(data)
    connect(people["author"], data["balance"], replacing=data["connection"].pk)
    analyst = Client()
    analyst.force_login(people["analyst"])
    response = analyst.post(
        reverse("analytical:observation_new", args=[data["test"].pk]),
        {
            "input_titrant_volume": "1.25",
            "input_titer": "4.98",
            "input_sample_mass": "2500.4",
            "reading_input_sample_mass": str(taken.pk),
            "equipment_ids": [data["equipment"].pk, data["balance"].pk],
            "reagent_ids": [data["standard"].pk],
            "raw_reference": "Balance SYN-BAL-01",
        },
    )
    assert response.status_code == 422
    body = response.content.decode()
    assert "changed after this reading. Read again." in body
    assert 'name="reading_input_sample_mass" value="' not in body
    assert 'name="input_sample_mass" value="2500.4"' not in body
    assert 'name="input_titrant_volume" value="1.25"' in body
    assert not Observation.objects.exists()


def test_an_oversized_answer_is_refused_before_it_is_decoded(world):
    data = world
    with pytest.raises(ValidationError, match="more than 2048 bytes"):
        instrument.take_reading(
            actor=data["people"]["analyst"],
            test=data["test"],
            target="sample_mass",
            connection_id=data["connection"].pk,
            response="A" * 3000,
        )
