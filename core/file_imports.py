"""Instrument export files read through an approved column mapping.

Shared by the catalog, which validates the mapping before a method version is approved, and by
testing, which reads a stored export with the mapping frozen on the test and reads it again at
submission and review.

A mapping (``oq.file-import/1``, frozen as the method's ``file_import``) describes delimited
text: the separator, the decimal mark, the text encoding, the row that holds the column names,
the column that names the test on each row, an optional column and value that select the rows
of one analyte or peak, and the column that holds each mapped field. A field is a calculation
input code, or ``value`` for a method whose result is entered directly.

Nothing is guessed. Each selected row is one replicate, in file order. A selected row whose
mapped cell is empty or is not a plain number (an optional sign, digits with the decimal mark
of the mapping, an optional exponent; no thousands separator, unit or qualifier) refuses the
whole file, and so does any row with more cells than the column names (its values would be read
from the wrong columns). Rows are matched to the test by its label (``T-12``), ignoring case and
the spaces around it. Rows are numbered as the file's records, the first being row 1.
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .formulas import is_name

SCHEMA = "oq.file-import/1"
KEYS = {
    "schema",
    "source",
    "delimiter",
    "decimal",
    "encoding",
    "header_row",
    "id_column",
    "filter_column",
    "filter_value",
    "columns",
}
COLUMN_KEYS = {"field", "column"}
VALUE = "value"  # the field of a result entered directly (a method without a calculation)

DELIMITERS = {"comma": ",", "semicolon": ";", "tab": "\t"}
DELIMITER_CHOICES = [("comma", "Comma (,)"), ("semicolon", "Semicolon (;)"), ("tab", "Tab")]
DECIMALS = {"point": ".", "comma": ","}
DECIMAL_CHOICES = [("point", "Point (12.5)"), ("comma", "Comma (12,5)")]
# Python codec for each encoding offered. UTF-8 accepts a byte-order mark; UTF-16 needs one.
ENCODINGS = {"utf-8": "utf-8-sig", "utf-16": "utf-16", "windows-1252": "cp1252"}
ENCODING_CHOICES = [
    ("utf-8", "UTF-8"),
    ("utf-16", "UTF-16 (with byte-order mark)"),
    ("windows-1252", "Windows-1252 (Western European)"),
]
MAX_HEADER_ROW = 50
MAX_COLUMN = 100
MAX_SOURCE = 200
MAX_FIELDS = 13
MAX_ROWS = 100_000
MAX_COLUMNS = 500
MAX_CELL = 1000

_NUMBER = {
    "point": re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?"),
    "comma": re.compile(r"[+-]?(?:[0-9]+(?:,[0-9]*)?|,[0-9]+)(?:[eE][+-]?[0-9]{1,3})?"),
}


class FileImportError(ValueError):
    """The mapping is not valid, or the file cannot be read with it."""


def _text(data, key, label, limit, required=True):
    value = data.get(key)
    if not isinstance(value, str) or len(value) > limit or value != value.strip():
        raise FileImportError(f"{label} must be text of at most {limit} characters, trimmed.")
    if required and not value:
        raise FileImportError(f"{label} is required.")
    return value


def _key(text):
    return text.strip().casefold()


def _width(cells):
    """The number of cells up to the last one that holds anything."""
    width = len(cells)
    while width and not cells[width - 1].strip():
        width -= 1
    return width


@dataclass(frozen=True)
class Column:
    field: str
    column: str


@dataclass(frozen=True)
class Row:
    """One selected row: its number in the file (1 = first row), the cell of each mapped field
    exactly as read, and the exact number it holds."""

    number: int
    cells: dict
    values: dict


@dataclass(frozen=True)
class Extract:
    """What a file holds for one test: the selected rows and how they were found."""

    rows: tuple
    data_rows: int  # rows below the header that hold anything
    named: int  # of those, rows that name the test


@dataclass(frozen=True)
class FileImport:
    source: str
    delimiter: str
    decimal: str
    encoding: str
    header_row: int
    id_column: str
    filter_column: str
    filter_value: str
    columns: tuple

    @property
    def fields(self):
        return tuple(column.field for column in self.columns)

    def column_of(self, field):
        for column in self.columns:
            if column.field == field:
                return column.column
        return ""

    @property
    def delimiter_label(self):
        return dict(DELIMITER_CHOICES)[self.delimiter]

    @property
    def decimal_label(self):
        return dict(DECIMAL_CHOICES)[self.decimal]

    @property
    def encoding_label(self):
        return dict(ENCODING_CHOICES)[self.encoding]

    def content(self):
        return {
            "schema": SCHEMA,
            "source": self.source,
            "delimiter": self.delimiter,
            "decimal": self.decimal,
            "encoding": self.encoding,
            "header_row": self.header_row,
            "id_column": self.id_column,
            "filter_column": self.filter_column,
            "filter_value": self.filter_value,
            "columns": [{"field": c.field, "column": c.column} for c in self.columns],
        }

    @property
    def hash(self):
        data = json.dumps(self.content(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(data.encode()).hexdigest()

    def number(self, text):
        """The exact number a cell holds, or None when it is not a plain number."""
        text = text.strip()
        if len(text) > 60 or not _NUMBER[self.decimal].fullmatch(text):
            return None
        if self.decimal == "comma":
            text = text.replace(",", ".")
        try:
            number = Decimal(text)
        except InvalidOperation:
            return None
        if not number.is_finite() or abs(number.adjusted()) > 40:
            return None
        # Written out in full, as an analyst would enter it: 1.25E+2 is 125, 0.50 stays 0.50.
        return Decimal(format(number, "f"))

    def read(self, content, label):
        """Read ``content`` (bytes) and return the rows that belong to the test ``label``.

        Raises FileImportError naming the row and column of the first problem; nothing is
        returned for part of a file.
        """
        try:
            text = bytes(content).decode(ENCODINGS[self.encoding])
        except UnicodeError as exc:
            raise FileImportError(
                f"The file is not {self.encoding_label} text, as the mapping states."
            ) from exc
        reader = csv.reader(
            io.StringIO(text, newline=""), delimiter=DELIMITERS[self.delimiter], strict=True
        )
        wanted = _key(label)
        header, rows, data_rows, named, number, width = None, [], 0, 0, 0, 0
        try:
            for number, cells in enumerate(reader, start=1):
                if number > MAX_ROWS + self.header_row:
                    raise FileImportError(f"The file has more than {MAX_ROWS} rows.")
                if len(cells) > MAX_COLUMNS:
                    raise FileImportError(f"Row {number} has more than {MAX_COLUMNS} columns.")
                if number < self.header_row:
                    continue
                if number == self.header_row:
                    header, width = self._header(cells), _width(cells)
                    continue
                if not any(cell.strip() for cell in cells):
                    continue
                data_rows += 1
                if _width(cells) > width:
                    raise FileImportError(
                        f"Row {number} has more cells than the column names in row "
                        f"{self.header_row}, so its values would be read from the wrong columns "
                        "(a decimal mark or separator inside a value?). Nothing was recorded."
                    )
                if _key(self._cell(cells, header, self.id_column)) != wanted:
                    continue
                named += 1
                if self.filter_column and _key(
                    self._cell(cells, header, self.filter_column)
                ) != _key(self.filter_value):
                    continue
                rows.append(self._row(number, cells, header))
        except csv.Error as exc:
            raise FileImportError(
                f"Row {number + 1} cannot be read as {self.delimiter_label.lower()}-"
                f"separated text: {exc}."
            ) from exc
        if header is None:
            raise FileImportError(
                f"The file has no row {self.header_row}, where the mapping expects the column "
                "names."
            )
        return Extract(rows=tuple(rows), data_rows=data_rows, named=named)

    def _header(self, cells):
        positions = {}
        for index, cell in enumerate(cells):
            positions.setdefault(_key(cell), []).append(index)
        wanted = [self.id_column, *([self.filter_column] if self.filter_column else [])]
        wanted += [column.column for column in self.columns]
        found = {}
        for name in wanted:
            places = positions.get(_key(name), [])
            if not places:
                raise FileImportError(
                    f"Row {self.header_row} has no column named “{name}”. Check that the file "
                    "is the export the mapping describes."
                )
            if len(places) > 1:
                raise FileImportError(
                    f"Row {self.header_row} names the column “{name}” more than once."
                )
            found[_key(name)] = places[0]
        return found

    @staticmethod
    def _cell(cells, header, name):
        index = header[_key(name)]
        cell = cells[index] if index < len(cells) else ""
        if len(cell) > MAX_CELL:
            raise FileImportError(f"A cell in column “{name}” is too long.")
        return cell

    def _row(self, number, cells, header):
        found, values = {}, {}
        for column in self.columns:
            cell = self._cell(cells, header, column.column)
            if not cell.strip():
                raise FileImportError(
                    f"Row {number}, column “{column.column}” is empty. Nothing was recorded; "
                    "enter this result by hand or correct the export."
                )
            value = self.number(cell)
            if value is None:
                raise FileImportError(
                    f"Row {number}, column “{column.column}” holds “{cell.strip()[:60]}”, which "
                    f"is not a plain number with a decimal {self.decimal}. Nothing was recorded; "
                    "enter this result by hand or correct the export."
                )
            found[column.field] = cell.strip()
            values[column.field] = value
        return Row(number=number, cells=found, values=values)


def parse(data):
    """Validate a frozen mapping and return it, or raise FileImportError."""
    if not isinstance(data, dict):
        raise FileImportError("The file import is not a mapping.")
    if set(data) != KEYS:
        unknown = sorted(set(data) - KEYS)
        missing = sorted(KEYS - set(data))
        raise FileImportError(f"File import keys differ (unknown {unknown}, missing {missing}).")
    if data["schema"] != SCHEMA:
        raise FileImportError("Unsupported file import schema.")
    if data["delimiter"] not in DELIMITERS:
        raise FileImportError("Choose the column separator from the list.")
    if data["decimal"] not in DECIMALS:
        raise FileImportError("Choose the decimal mark from the list.")
    if data["delimiter"] == "comma" and data["decimal"] == "comma":
        raise FileImportError(
            "A file whose columns are separated by commas cannot use a comma as decimal mark."
        )
    if data["encoding"] not in ENCODINGS:
        raise FileImportError("Choose the text encoding from the list.")
    header_row = data["header_row"]
    if (
        not isinstance(header_row, int)
        or isinstance(header_row, bool)
        or not 1 <= header_row <= MAX_HEADER_ROW
    ):
        raise FileImportError(f"The row of column names is a number from 1 to {MAX_HEADER_ROW}.")
    source = _text(data, "source", "What produces the file", MAX_SOURCE)
    id_column = _text(data, "id_column", "The column that names the test", MAX_COLUMN)
    filter_column = _text(data, "filter_column", "The column that selects rows", MAX_COLUMN, False)
    filter_value = _text(data, "filter_value", "The value that selects rows", MAX_COLUMN, False)
    if bool(filter_column) != bool(filter_value):
        raise FileImportError("Name both the column that selects rows and its value, or neither.")
    items = data["columns"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_FIELDS:
        raise FileImportError(f"Map 1 to {MAX_FIELDS} fields to columns of the file.")
    columns = []
    for item in items:
        if not isinstance(item, dict) or set(item) != COLUMN_KEYS:
            raise FileImportError("A mapped column is not valid.")
        if not is_name(item["field"]):
            raise FileImportError("A mapped field code is not valid.")
        columns.append(
            Column(item["field"], _text(item, "column", "A mapped column name", MAX_COLUMN))
        )
    fields = [c.field for c in columns]
    if len(set(fields)) != len(fields):
        raise FileImportError("A field is mapped to more than one column.")
    names = [_key(name) for name in (id_column, filter_column) if name]
    names += [_key(c.column) for c in columns]
    if len(set(names)) != len(names):
        raise FileImportError(
            "Each column of the file is used once: the column that names the test, the column "
            "that selects rows and each mapped column are different columns."
        )
    return FileImport(
        source=source,
        delimiter=data["delimiter"],
        decimal=data["decimal"],
        encoding=data["encoding"],
        header_row=header_row,
        id_column=id_column,
        filter_column=filter_column,
        filter_value=filter_value,
        columns=tuple(columns),
    )


def problems(data, fields):
    """What stops a mapping being approved for a method whose fields are ``fields`` (the
    calculation's input codes in order, or ``[VALUE]`` for a result entered directly)."""
    try:
        mapping = parse(data)
    except FileImportError as exc:
        return [str(exc)]
    found = []
    if unknown := [f for f in mapping.fields if f not in fields]:
        if fields == [VALUE]:
            found.append(
                "The method has no calculation, so the file holds the result itself; map only "
                "the result column. Unknown fields: " + ", ".join(unknown)
            )
        else:
            found.append(
                "The mapping reads fields the calculation does not have: " + ", ".join(unknown)
            )
    if fields == [VALUE] and VALUE not in mapping.fields:
        found.append("Map the column that holds the result.")
    return found
