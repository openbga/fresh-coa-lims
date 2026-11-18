"""Readings that balances and meters send over a serial connection to the analyst's computer.

Shared by the laboratory, which records how each instrument is connected (its format, serial
settings and the serial number it reports), and by testing, which reads what the device sent for
a test and reads it again at submission and review.

The browser talks to the device (the Web Serial API): it sends each request of the format and
passes on the bytes the device answered, unchanged. The server reads those bytes here, never a
value worked out by the browser. Nothing is guessed: the answer must have exactly the shape the
format's specification gives, a weight the device did not report as stable is refused, and so is
an overload, an error answer, a value that is not a plain number, a unit missing, or anything
before, between or after the expected lines.

Formats, each from its manufacturer's published interface description:

- ``mt_sics``: METTLER TOLEDO Standard Interface Command Set (MT-SICS) level 0. ``I4`` answers
  the serial number (``I4 A "0123456789"``), ``S`` the stable net weight
  (``S S     100.00 g``; ``S I``, ``S +`` and ``S -`` when it cannot).
- ``and_standard``: A&D standard format. ``S`` answers the weight once stable
  (``ST,+00123.45  g``; header ``US`` unstable, ``OL`` overload, ``QT`` counting). The format
  carries no serial number.
- ``orion_star``: Thermo Scientific Orion Star A-series meters, ``GETMEAS`` in the PC (CSV)
  format: one comma-separated line whose fields are the meter model, its serial number, the
  software revision, user, date and time, sample, channel, mode and then the measurement's value
  and unit (``A211 pH, X01036, 3.04, ABCDE, 01/03/15 16:05:41, SAMPLE, CH-1, pH, 7.000, pH, ...``),
  followed by the meter's ``>`` prompt. The answer does not say whether the reading was stable.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_RESPONSE = 2048  # bytes; a balance answers about 40, a meter's CSV line about 200
MAX_DIGITS = 20  # as an observation's value (analytical.contracts.DECIMAL)
MAX_DECIMALS = 8
MAX_SERIAL = 40

BAUD_RATES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
# Units a balance weighs in: a page offers a balance beside a value in one of these, and a meter
# beside any other. The server still requires the device's unit to be the value's, exactly.
# Devices send plain ASCII, so a microgram is "ug"; a value in µg is typed.
MASS_UNITS = frozenset({"g", "mg", "kg", "ug", "ct"})
PARITIES = ("none", "even", "odd")
FLOW_CONTROLS = ("none", "hardware")  # what the Web Serial API offers; no XON/XOFF

_NUMBER = re.compile(r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
_PRINTABLE = re.compile(r"[\x20-\x7e\r\n]*")


class DeviceFormatError(ValueError):
    """What the device sent cannot be read as a reading of its format."""


@dataclass(frozen=True)
class Step:
    """One request to the device: the text sent, the text that ends its answer and how long the
    browser waits for it in milliseconds."""

    send: str
    until: str
    wait: int


@dataclass(frozen=True)
class DeviceValue:
    """A reading as the device reported it: the number's text, its unit and, where the format
    reports one, the device's serial number."""

    text: str
    unit: str
    serial_number: str = ""

    @property
    def value(self):
        return Decimal(self.text)


@dataclass(frozen=True)
class Format:
    code: str
    label: str
    kind: str  # "balance" or "meter"
    steps: tuple
    identifies: bool  # the device reports its serial number
    reports_stability: bool
    baud_rate: int
    data_bits: int
    parity: str
    stop_bits: int
    flow_control: str = "none"

    def request(self):
        return "".join(step.send for step in self.steps)

    def read(self, response):
        """The value in ``response`` (the text the device sent, as received). Raises
        DeviceFormatError when it is not exactly one reading of this format."""
        text = _received(response)
        return _READERS[self.code](text)

    def browser(self):
        """What the browser needs to take a reading: the requests and when each is answered."""
        return [{"send": s.send, "until": s.until, "wait": s.wait} for s in self.steps]


def _received(response):
    if not isinstance(response, str):
        raise DeviceFormatError("Nothing was received from the device.")
    if len(response.encode("latin-1", "replace")) > MAX_RESPONSE:
        raise DeviceFormatError(
            f"The device sent more than {MAX_RESPONSE} bytes. Set it to answer requests only, "
            "without continuous or automatic output."
        )
    if not response:
        raise DeviceFormatError(
            "The device did not answer. Check that it is switched on, connected and set to the "
            "serial settings of its data connection."
        )
    if not _PRINTABLE.fullmatch(response):
        raise DeviceFormatError(
            "The device sent characters that are not plain text. Check the serial settings "
            "(baud rate, data bits, parity and stop bits) against the device's own."
        )
    return response


def _lines(text, terminator):
    """The lines of ``text``, each ended by ``terminator``; refuses anything after the last."""
    if not text.endswith(terminator):
        raise DeviceFormatError(
            "The device's answer was cut off. Read again; if it happens again, check the serial "
            "settings and the device's line ending (CR LF)."
        )
    return text[: -len(terminator)].split(terminator)


def checked_number(text):
    """``text`` as a plain number that fits an observation, or DeviceFormatError."""
    if not _NUMBER.fullmatch(text):
        raise DeviceFormatError(f"“{text}” is not a plain number.")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - the pattern admits only numbers
        raise DeviceFormatError(f"“{text}” is not a plain number.") from exc
    sign, digits, exponent = number.as_tuple()
    decimals = max(-exponent, 0)
    whole = max(len(digits) + exponent, 0)
    if decimals > MAX_DECIMALS or whole > MAX_DIGITS - MAX_DECIMALS:
        raise DeviceFormatError(
            f"“{text}” has more than {MAX_DECIMALS} decimals or "
            f"{MAX_DIGITS - MAX_DECIMALS} digits before the decimal point."
        )
    return text


# --- MT-SICS ---------------------------------------------------------------------------------

_SICS_SERIAL = re.compile(r'I4 A "([^"\x00-\x1f]{1,40})"')
_SICS_WEIGHT = re.compile(r"S S +(\S+) +(\S{1,5})")
_SICS_REFUSALS = {
    "S I": "The balance could not send a stable weight: it was busy, or the weight did not "
    "settle before the balance's time limit. Let it settle and read again.",
    "S +": "The balance is in overload.",
    "S -": "The balance is in underload. Check the weighing pan and zero the balance.",
    "I4 I": "The balance is busy and did not send its serial number. Read again.",
    "ES": "The balance did not recognize the request (syntax error).",
    "ET": "The balance received the request garbled (transmission error). Check the serial "
    "settings.",
    "EL": "The balance could not carry out the request (logical error).",
}


def _sics_refusal(line):
    message = _SICS_REFUSALS.get(line.rstrip())
    if message:
        raise DeviceFormatError(message)
    if line.startswith("S D"):
        raise DeviceFormatError("The balance sent a weight it did not report as stable.")


def _read_sics(text):
    lines = _lines(text, "\r\n")
    for line in lines:
        _sics_refusal(line)
    if len(lines) != 2:
        raise DeviceFormatError(
            f"The balance sent {len(lines)} line{'s' if len(lines) != 1 else ''}; an MT-SICS "
            "balance answers its serial number and then the stable weight, one line each. Set "
            "it to answer requests only, without automatic output."
        )
    serial = _SICS_SERIAL.fullmatch(lines[0])
    if not serial:
        raise DeviceFormatError(
            f'The first line, “{lines[0]}”, is not an MT-SICS serial number answer (I4 A "...").'
        )
    weight = _SICS_WEIGHT.fullmatch(lines[1])
    if not weight:
        raise DeviceFormatError(
            f"The second line, “{lines[1]}”, is not an MT-SICS stable weight (S S value unit)."
        )
    number, unit = weight.groups()
    return DeviceValue(text=checked_number(number), unit=unit, serial_number=serial.group(1))


# --- A&D standard format ---------------------------------------------------------------------

# Header, comma, polarity, eight characters of zero-padded data, a three-character unit: 15.
_AND_LINE = re.compile(r"ST,([+-])([0-9.]{8})(.{3})")
_AND_REFUSALS = {
    "US,": "The balance sent a weight it did not report as stable.",
    "OL,": "The balance is in overload.",
    "QT,": "The balance is in counting mode; set it to weighing.",
}


def _read_and(text):
    if text.startswith("EC,"):
        raise DeviceFormatError(
            f"The balance answered with the error code {text.strip()}. Check the serial "
            "settings and read again."
        )
    lines = _lines(text, "\r\n")
    if len(lines) != 1:
        raise DeviceFormatError(
            f"The balance sent {len(lines)} lines; it answers one line of weighing data. Set it "
            "to answer requests only (key mode), without stream or automatic output."
        )
    line = lines[0]
    if line[:3] in _AND_REFUSALS:
        raise DeviceFormatError(_AND_REFUSALS[line[:3]])
    match = _AND_LINE.fullmatch(line)
    unit = match.group(3).lstrip(" ") if match else ""
    if not match or not unit or " " in unit:
        raise DeviceFormatError(
            f"“{line}” is not weighing data in the A&D standard format (ST,+00123.45  g)."
        )
    sign, digits = match.group(1), checked_number(match.group(2))
    # The format pads with zeros and signs a zero +; keep the number as the device wrote it,
    # without its padding zeros (00123.45 -> 123.45).
    text_value = _unpadded(digits)
    if sign == "-":
        text_value = "-" + text_value
    return DeviceValue(text=text_value, unit=unit)


def _unpadded(number):
    whole, dot, fraction = number.partition(".")
    whole = whole.lstrip("0") or "0"
    return f"{whole}{dot}{fraction}"


# --- Orion Star A-series GETMEAS ---------------------------------------------------------------

# Model, serial number, software, user, date and time, sample, channel, mode, value, unit.
_ORION_FIELDS = 10


def _read_orion(text):
    # The meter ends its answer with its prompt "> " and may echo the request; the measurement
    # is the one line that is neither.
    lines = [line.strip() for line in re.split(r"\r\n|\r|\n", text)]
    measurements = [
        line for line in lines if line.lstrip(">").strip().upper() not in {"", "GETMEAS"}
    ]
    if not text.rstrip().endswith(">"):
        raise DeviceFormatError(
            "The meter's answer was cut off before its prompt (>). Read again; if it happens "
            "again, check the serial settings."
        )
    if len(measurements) != 1:
        raise DeviceFormatError(
            f"The meter sent {len(measurements)} measurement lines; GETMEAS answers one. Set the "
            "meter's output to PC (CSV) and turn off timed or continuous output."
        )
    fields = [field.strip() for field in measurements[0].split(",")]
    if len(fields) < _ORION_FIELDS + 2:
        raise DeviceFormatError(
            f"“{measurements[0]}” is not a measurement in the meter's PC (CSV) format. Set the "
            "meter's output format to PC (CSV)."
        )
    channels = sum(1 for field in fields if re.fullmatch(r"CH-[0-9]+", field))
    if channels > 1:
        raise DeviceFormatError(
            "The meter sent the measurements of more than one channel. Set it to measure one "
            "channel."
        )
    serial, channel, number, unit = fields[1], fields[6], fields[8], fields[9]
    if not re.fullmatch(r"CH-[0-9]+", channel):
        raise DeviceFormatError(
            f"“{measurements[0]}” is not a measurement in the meter's PC (CSV) format."
        )
    if not serial or len(serial) > MAX_SERIAL:
        raise DeviceFormatError("The meter's answer does not name its serial number.")
    if not unit:
        raise DeviceFormatError("The meter's answer does not state the unit of its reading.")
    return DeviceValue(text=checked_number(number), unit=unit, serial_number=serial)


_READERS = {"mt_sics": _read_sics, "and_standard": _read_and, "orion_star": _read_orion}

FORMATS = {
    f.code: f
    for f in (
        Format(
            code="mt_sics",
            label="MT-SICS (METTLER TOLEDO balances)",
            kind="balance",
            steps=(Step("I4\r\n", "\n", 3000), Step("S\r\n", "\n", 20000)),
            identifies=True,
            reports_stability=True,
            baud_rate=9600,
            data_bits=8,
            parity="none",
            stop_bits=1,
        ),
        Format(
            code="and_standard",
            label="A&D standard format (A&D balances)",
            kind="balance",
            steps=(Step("S\r\n", "\n", 20000),),
            identifies=False,
            reports_stability=True,
            baud_rate=2400,
            data_bits=7,
            parity="even",
            stop_bits=1,
        ),
        Format(
            code="orion_star",
            label="Orion Star A-series meters (GETMEAS, PC (CSV) output)",
            kind="meter",
            steps=(Step("GETMEAS\r", ">", 10000),),
            identifies=True,
            reports_stability=False,
            baud_rate=9600,
            data_bits=8,
            parity="none",
            stop_bits=1,
        ),
    )
}
FORMAT_CHOICES = [(f.code, f.label) for f in FORMATS.values()]


def kind_for(unit):
    """Which kind of instrument can supply a value in ``unit``: "balance" or "meter"."""
    return "balance" if unit.strip() in MASS_UNITS else "meter"


def get(code):
    try:
        return FORMATS[code]
    except KeyError as exc:
        raise DeviceFormatError(f"Unknown device format “{code}”.") from exc


def visible(text):
    """``text`` with its line endings shown (␍ ␊), for display of what the device sent."""
    return text.replace("\r", "␍").replace("\n", "␊")
