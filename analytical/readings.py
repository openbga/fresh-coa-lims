"""Readings from balances and meters connected to the analyst's computer: service, checks and the
page that takes a reading.

The analyst's browser talks to the device through the equipment's data connection (laboratory
``DeviceConnection``) and passes on what the device answered, unchanged. The server reads that
answer with the connection's format (``core.device_formats``), refuses anything that is not
exactly one stable reading in the unit of the value it is taken for, and keeps the reading on the
test at once, with the time on the server, whether or not a replicate records it. A replicate
that records the reading names it; its value is the device's number as written. Submission and
review read every recorded reading again.
"""

import base64
import binascii

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import device_formats
from core.audit import record_event
from core.services import require_role

from .contracts import bench
from .models import AnalyticalTest, InstrumentReading
from .services import (
    ANALYST,
    REPORTED,
    _bump,
    _lock_subjects,
    _touch,
    subject_refusal,
    supplier_refusal,
)

VALUE = "value"  # the target of a result entered directly
NOT_ACCEPTING = "This test is not accepting observations."


def targets(spec):
    """{target: (label, unit, form field)} of the values of this requirement that a balance or
    meter can supply: each calculation input, or the value of a numeric result entered directly.
    A count, a qualitative result and a result without a unit are typed."""
    calculation = spec.calculation
    if calculation is not None:
        return {i.code: (i.name, i.unit, f"input_{i.code}") for i in calculation.inputs}
    if spec.is_qualitative or spec.result_type == "count" or not spec.unit:
        return {}
    return {VALUE: ("Observed value", spec.unit, VALUE)}


def reading_refusal(test):
    """Why no reading can be taken for this test now, or None. The service repeats it under the
    test's lock."""
    if test.state != AnalyticalTest.State.OPEN or subject_refusal(test):
        return NOT_ACCEPTING
    if refusal := supplier_refusal(test):
        return refusal
    if test.contract_source() is not None:
        return REPORTED
    if not targets(test.spec):
        return "This result is typed: it has no value a balance or meter can supply."
    return None


def _response(encoded):
    """The bytes the browser passed on (base64), as text with one character per byte."""
    if len(encoded or "") > 4 * -(-device_formats.MAX_RESPONSE // 3):
        raise ValidationError(
            f"The device sent more than {device_formats.MAX_RESPONSE} bytes. Set it to answer "
            "requests only, without continuous or automatic output."
        )
    try:
        raw = base64.b64decode(encoded or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("The device's answer did not arrive intact. Read again.") from exc
    if len(raw) > device_formats.MAX_RESPONSE:
        raise ValidationError(
            f"The device sent more than {device_formats.MAX_RESPONSE} bytes. Set it to answer "
            "requests only, without continuous or automatic output."
        )
    return raw.decode("latin-1")


def read_device(connection, response, unit):
    """The DeviceValue in ``response`` read through ``connection`` (its evidence), checked
    against the connection's serial number and the expected ``unit``; ValidationError if not."""
    fmt = device_formats.get(connection["format"])
    try:
        device = fmt.read(response)
    except device_formats.DeviceFormatError as exc:
        raise ValidationError(str(exc)) from exc
    asset = connection["asset_id"]
    if fmt.identifies and device.serial_number != connection["serial_number"]:
        raise ValidationError(
            f"The device reported serial number {device.serial_number}; the data connection of "
            f"{asset} names {connection['serial_number']}. Read from the instrument you "
            "selected, or have quality correct its data connection."
        )
    if device.unit != unit:
        raise ValidationError(
            f"{asset} reported its reading in {device.unit}; this value is in {unit}. Set the "
            f"instrument to {unit}, or type the value."
        )
    return device


@transaction.atomic
def take_reading(*, actor, test, target, connection_id, response):
    """Keep one reading taken for ``test`` through the data connection ``connection_id``.

    ``response`` is what the device sent, base64-encoded by the browser. Nothing is stored when
    the answer is not exactly one reading of the connection's format in the unit of ``target``.
    """
    require_role(actor, ANALYST)
    desk = bench()
    desk.lock_actor(actor)
    locked = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
    subjects = _lock_subjects(locked)
    if refusal := reading_refusal(locked):
        raise ValidationError(refusal)
    wanted = targets(locked.spec).get(target)
    if wanted is None:
        raise ValidationError("This test takes no reading for that value.")
    label, unit, _ = wanted
    try:
        connection = desk.connection(int(connection_id))
    except TypeError, ValueError:
        connection = None
    if connection is None:
        raise ValidationError(
            "This data connection is no longer current. Reload the page to read through the "
            "instrument's current connection."
        )
    text = _response(response)
    device = read_device(connection, text, unit)
    reading = InstrumentReading(
        test=locked,
        target=target,
        label=label,
        connection=connection,
        request=device_formats.get(connection["format"]).request(),
        response=text,
        value=device.value,
        value_text=device.text,
        unit=device.unit,
        serial_number=device.serial_number,
        read_by=actor,
    )
    reading.full_clean()
    reading.save()
    _touch(locked)
    _bump(*subjects)
    record_event(
        actor=actor,
        action="instrument.read",
        obj=locked,
        after={
            "reading": reading.pk,
            "target": target,
            "value": reading.value_text,
            "unit": reading.unit,
            "equipment": connection["asset_id"],
            "connection": connection["id"],
            "serial_number": reading.serial_number,
            "response": reading.response,
        },
        reason=f"{label} read from {connection['asset_id']}",
    )
    return reading


REFUSED = "reading_refused"  # the code of a refusal the analyst answers by reading again


def refused(message):
    return ValidationError(message, code=REFUSED)


def claim(desk, *, actor, test, readings, entered, equipment_ids):
    """Lock and check the readings a replicate records; returns them, still unlinked.

    ``readings`` maps a target to the id of a reading; ``entered`` maps each target to the text
    recorded for it. Runs inside the entry's transaction after the bench has locked the selected
    equipment, so a data connection cannot change before the replicate commits.
    """
    if not readings:
        return []
    try:
        ids = {target: int(pk) for target, pk in readings.items() if pk not in (None, "")}
    except (TypeError, ValueError) as exc:
        raise ValidationError("An instrument reading named is not valid.") from exc
    if not ids:
        return []
    found = {
        r.pk: r for r in InstrumentReading.objects.select_for_update().filter(pk__in=ids.values())
    }
    current = desk.current_connections(equipment_ids)
    errors, claimed = {}, []
    wanted = targets(test.spec)
    for target, pk in ids.items():
        reading = found.get(pk)
        field = wanted.get(target, (None, None, target))[2]
        if reading is None or reading.test_id != test.pk or reading.target != target:
            errors[field] = refused("This reading was not taken for this value of this test.")
            continue
        if reading.read_by_id != actor.pk:
            errors[field] = refused("A reading is recorded by the person who took it.")
            continue
        if reading.observation_id is not None:
            errors[field] = refused("This reading is already recorded in a replicate. Read again.")
            continue
        equipment = reading.connection.get("equipment")
        asset = reading.asset_id
        if equipment not in equipment_ids:
            # Recoverable on the form: the reading stays for the analyst to tick the instrument.
            errors[field] = ValidationError(
                f"This value was read from {asset}; select {asset} under Equipment used.",
                code="select_equipment",
            )
            continue
        if current.get(equipment) != reading.connection.get("id"):
            errors[field] = refused(
                f"The data connection of {asset} changed after this reading. Read again."
            )
            continue
        if entered.get(target) != reading.value_text:
            errors[field] = refused(
                f"The value differs from the reading {reading.value_text} {reading.unit} taken "
                f"from {asset}. Read again, or clear the reading and type the value."
            )
            continue
        claimed.append(reading)
    if errors:
        raise ValidationError(errors)
    return claimed


def link(readings, observation):
    """Record ``readings`` as read for ``observation`` (the database allows this once)."""
    for reading in readings:
        reading.observation = observation
        reading.save(update_fields=["observation"])


def evidence(readings):
    """What the audit event of a replicate keeps of the readings it records."""
    return [
        {
            "reading": r.pk,
            "target": r.target,
            "value": r.value_text,
            "unit": r.unit,
            "equipment": r.asset_id,
            "connection": r.connection.get("id"),
        }
        for r in readings
    ]


def reading_problems(test, observations):
    """Why recorded readings of ``observations`` no longer agree with what the device sent,
    read again with the format of the connection they were taken through (empty when they do)."""
    problems = []
    by_observation = {}
    for reading in InstrumentReading.objects.filter(
        observation__in=[o.pk for o in observations]
    ).order_by("pk"):
        by_observation.setdefault(reading.observation_id, []).append(reading)
    for observation in observations:
        recorded = {i.get("code"): i.get("value") for i in observation.inputs or []}
        for reading in by_observation.get(observation.pk, []):
            where = f"Replicate {observation.replicate}, {reading.label} from {reading.asset_id}"
            try:
                device = read_device(reading.connection, reading.response, reading.unit)
            except ValidationError as exc:
                problems.append(f"{where}: {' '.join(exc.messages)}")
                continue
            stored = (
                observation.value_text if reading.target == VALUE else recorded.get(reading.target)
            )
            if (
                device.text != reading.value_text
                or device.value != reading.value
                or device.serial_number != reading.serial_number
                or stored != reading.value_text
            ):
                problems.append(
                    f"{where}: the replicate records {stored}; the device sent "
                    f"{device.text} {device.unit}."
                )
    return problems


def recheck(test, observations, refusal):
    """Refuse when a recorded reading no longer agrees with what the device sent."""
    if problems := reading_problems(test, observations):
        raise ValidationError(f"{refusal} {' '.join(problems)}")


def form_options(test, form):
    """What the page's script needs to offer readings on ``form``: the connected instruments,
    the fields a reading can fill and the readings already taken into them. None when the test
    takes no reading or no instrument is connected."""
    from django.urls import reverse

    wanted = targets(test.spec)
    if not wanted or reading_refusal(test):
        return None
    # Only the instruments the analyst can select under Equipment used (which the bench narrows
    # to those the method version lists as suitable): a reading is recorded only with its
    # instrument selected there.
    selectable = form.fields.get("equipment_ids")
    offered = {str(value) for value, _ in selectable.choices} if selectable is not None else set()
    connections = {pk: c for pk, c in bench().connections().items() if str(pk) in offered}
    instruments = list(connections.values())
    fields = [
        {
            "name": field,
            "target": target,
            "label": label,
            "unit": unit,
            "instruments": [
                i["connection"]
                for i in instruments
                if i.get("kind") == device_formats.kind_for(unit)
            ],
        }
        for target, (label, unit, field) in wanted.items()
    ]
    fields = [f for f in fields if f["instruments"]]
    if not fields:
        return None
    taken = {}
    ids = {
        field: form[f"reading_{field}"].value()
        for _, _, field in wanted.values()
        if f"reading_{field}" in form.fields
    }
    found = {
        str(r.pk): r
        for r in InstrumentReading.objects.filter(
            pk__in=[pk for pk in ids.values() if str(pk or "").isdigit()],
            test=test,
            observation__isnull=True,
        )
    }
    for field, pk in ids.items():
        reading = found.get(str(pk or ""))
        if reading is not None:
            taken[field] = summary(reading)
    return {
        "url": reverse("analytical:instrument_read", args=[test.pk]),
        "instruments": [
            i for i in instruments if any(i["connection"] in f["instruments"] for f in fields)
        ],
        "fields": fields,
        "taken": taken,
    }


def drop_refused(form, spec):
    """After a refused entry, empty each value whose reading was refused, and its reading: the
    analyst reads it again or types it, never resubmits a reading the server would refuse."""
    if not form.is_bound or not form.errors:
        return
    data = form.data.copy()
    dropped = False
    errors = form.errors.as_data()
    for _, _, name in targets(spec).values():
        if data.get(f"reading_{name}") and any(e.code == REFUSED for e in errors.get(name, ())):
            data[f"reading_{name}"] = ""
            data[name] = ""
            dropped = True
    if dropped:
        form.data = data


def summary(reading):
    """A reading as the page shows it once taken."""
    return {
        "reading": reading.pk,
        "value": reading.value_text,
        "unit": reading.unit,
        "equipment": reading.connection.get("equipment"),
        "asset_id": reading.asset_id,
        "serial_number": reading.serial_number,
        "response": reading.response_text,
        "read_at": timezone.localtime(reading.read_at).strftime("%H:%M:%S"),
    }


@login_required
@require_POST
def instrument_read(request, pk):
    """Keep the reading the browser passes on; answer what was read or why it was refused."""
    test = get_object_or_404(AnalyticalTest, pk=pk)
    try:
        reading = take_reading(
            actor=request.user,
            test=test,
            target=request.POST.get("target", ""),
            connection_id=request.POST.get("connection"),
            response=request.POST.get("response", ""),
        )
    except PermissionDenied:
        return JsonResponse({"error": "Only an analyst takes readings for a test."}, status=403)
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=422)
    return JsonResponse(summary(reading), status=201)
