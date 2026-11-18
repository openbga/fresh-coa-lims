"""Readings as balances and meters send them (core.device_formats), without a database.

The answers are written from each manufacturer's published interface description: METTLER TOLEDO
MT-SICS (I4, S), the A&D standard format and the Orion Star A-series GETMEAS PC (CSV) line.
Nothing is guessed: anything but exactly one reading of the format is refused.
"""

from decimal import Decimal

import pytest

from core import device_formats
from core.device_formats import DeviceFormatError

SICS = device_formats.get("mt_sics")
AND = device_formats.get("and_standard")
ORION = device_formats.get("orion_star")

ORION_PH = (
    "A211 pH, X01036, 3.04, ABCDE, 01/03/15 16:05:41, SAMPLE, CH-1, pH, 7.000, pH, 0.0, mV, "
    "25.0, C, 98.1,%, M100, #1\r> "
)


def sics(weight, serial="0123456789"):
    return f'I4 A "{serial}"\r\n{weight}\r\n'


def test_mt_sics_stable_weight_with_the_serial_number():
    value = SICS.read(sics("S S     100.00 g"))
    assert (value.text, value.unit, value.serial_number) == ("100.00", "g", "0123456789")
    assert value.value == Decimal("100.00")
    assert SICS.read(sics("S S    -0.0012 g")).text == "-0.0012"
    # A DeltaRange balance outside its fine range shows the last decimal as a space.
    assert SICS.read(sics("S S    4875.2  g")).text == "4875.2"
    assert SICS.read(sics("S S   250.4012 mg")).unit == "mg"
    assert SICS.request() == "I4\r\nS\r\n"


@pytest.mark.parametrize(
    "answer, message",
    [
        (sics("S D     100.00 g"), "did not report as stable"),
        (sics("S I"), "could not send a stable weight"),
        (sics("S +"), "overload"),
        (sics("S -"), "underload"),
        ("I4 I\r\nS S     100.00 g\r\n", "busy"),
        (sics("ES"), "did not recognize"),
        (sics("ET"), "garbled"),
        (sics("EL"), "logical error"),
        ("S S     100.00 g\r\n", "1 line"),
        ('I4 A "1"\r\nI4 A "1"\r\nS S     100.00 g\r\n', "3 lines"),
        ('I4 A "1"\r\nS S     100.00 g', "cut off"),
        ('I4 A "1"\r\nS S     1,000.00 g\r\n', "not a plain number"),
        ('I4 A "1"\r\nS S     100.00\r\n', "not an MT-SICS stable weight"),
        ('I4 "1"\r\nS S     100.00 g\r\n', "not an MT-SICS serial number"),
        ('I4 A "1"\r\nS S  0.000000001 g\r\n', "more than 8 decimals"),
        ('I4 A "1"\r\nS S  1234567890123 g\r\n', "digits before the decimal point"),
        ("", "did not answer"),
        ('I4 A "1"\r\nS S     100.00 \xb5g\r\n', "not plain text"),
    ],
)
def test_mt_sics_refusals(answer, message):
    with pytest.raises(DeviceFormatError, match=message):
        SICS.read(answer)


def test_a_and_d_standard_format_weight_without_a_serial_number():
    value = AND.read("ST,+00123.45  g\r\n")
    assert (value.text, value.unit, value.serial_number) == ("123.45", "g", "")
    assert AND.read("ST,+0.012345  g\r\n").text == "0.012345"
    assert AND.read("ST,-0012.345 mg\r\n").text == "-12.345"
    assert AND.read("ST,+00000.00  g\r\n").text == "0.00"
    assert not AND.identifies


@pytest.mark.parametrize(
    "answer, message",
    [
        ("US,+00123.45  g\r\n", "did not report as stable"),
        ("OL,+9999999 E\r\n", "overload"),
        ("QT,+00000012 PC\r\n", "counting mode"),
        ("EC,E02\r\n", "error code EC,E02"),
        ("ST,+00123.45  g\r\nST,+00123.46  g\r\n", "2 lines"),
        ("ST,+00123.45  g", "cut off"),
        ("ST,+00123.4  g\r\n", "not weighing data"),
        ("ST,+00123.45    \r\n", "not weighing data"),
        ("WT    +123.45  g\r\n", "not weighing data"),
        ("ST,+0012..45  g\r\n", "not a plain number"),
    ],
)
def test_a_and_d_refusals(answer, message):
    with pytest.raises(DeviceFormatError, match=message):
        AND.read(answer)


def test_orion_star_measurement_with_the_serial_number_and_prompt():
    value = ORION.read(ORION_PH)
    assert (value.text, value.unit, value.serial_number) == ("7.000", "pH", "X01036")
    # The echo of the request and earlier prompts are not measurements.
    assert ORION.read("> GETMEAS\r\n" + ORION_PH).text == "7.000"
    conductivity = (
        "A212 Cond, X01038, 3.04, ABCDE, 01/03/15 16:05:41, SAMPLE, CH-1, COND, 936.41, uS/cm, "
        "1977.59, uS, 25.0, C, 2.1,%/C, 25.0, C, 0.4750, /cm, M100, #1\r> "
    )
    assert ORION.read(conductivity).unit == "uS/cm"
    assert not ORION.reports_stability


@pytest.mark.parametrize(
    "answer, message",
    [
        (ORION_PH.replace("\r> ", "\r"), "cut off before its prompt"),
        ("> ", "0 measurement lines"),
        (ORION_PH.replace("\r> ", "\r") + ORION_PH, "2 measurement lines"),
        ("A211 pH, X01036, 3.04, ABCDE\r> ", "not a measurement"),
        (ORION_PH.replace("7.000", "Over"), "not a plain number"),
        (ORION_PH.replace("X01036", ""), "serial number"),
        (ORION_PH.replace("CH-1", "CH1"), "not a measurement in the meter's PC"),
        (
            ORION_PH.replace("M100, #1", "M100, CH-2, COND, 936.41, uS/cm, M200, #1"),
            "more than one channel",
        ),
    ],
)
def test_orion_star_refusals(answer, message):
    with pytest.raises(DeviceFormatError, match=message):
        ORION.read(answer)


def test_formats_offer_their_requests_and_factory_settings():
    assert [step["send"] for step in SICS.browser()] == ["I4\r\n", "S\r\n"]
    assert ORION.browser() == [{"send": "GETMEAS\r", "until": ">", "wait": 10000}]
    assert (AND.baud_rate, AND.data_bits, AND.parity, AND.stop_bits) == (2400, 7, "even", 1)
    assert {code for code, _ in device_formats.FORMAT_CHOICES} == {
        "mt_sics",
        "and_standard",
        "orion_star",
    }
    with pytest.raises(DeviceFormatError, match="Unknown device format"):
        device_formats.get("sartorius")
    assert device_formats.visible("S S 1 g\r\n") == "S S 1 g␍␊"
    assert [device_formats.kind_for(u) for u in ("mg", " g ", "ug", "µg", "pH", "% w/w")] == [
        "balance",
        "balance",
        "balance",
        "meter",
        "meter",
        "meter",
    ]
