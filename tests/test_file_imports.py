"""The instrument export reader (core.file_imports): mapping validation and exact reading."""

import copy
from decimal import Decimal

import pytest

from core import file_imports
from core.file_imports import FileImportError, parse, problems

MAPPING = {
    "schema": "oq.file-import/1",
    "source": "Synthetic UV spectrometer result export",
    "delimiter": "comma",
    "decimal": "point",
    "encoding": "utf-8",
    "header_row": 2,
    "id_column": "Sample ID",
    "filter_column": "Wavelength",
    "filter_value": "254 nm",
    "columns": [
        {"field": "sample_abs", "column": "Sample Abs"},
        {"field": "standard_abs", "column": "Std Abs"},
    ],
}
EXPORT = (
    b"Synthetic UV export,Run 7\r\n"
    b"Sample ID,Wavelength,Sample Abs,Std Abs\r\n"
    b"T-12,254 nm,0.500625,0.5\r\n"
    b"T-12,280 nm,0.3,0.31\r\n"
    b",,,\r\n"
    b" t-12 , 254 NM ,4.9875E-1, 0.50 \r\n"
    b"T-120,254 nm,0.1,0.5\r\n"
)


def mapping(**changes):
    data = copy.deepcopy(MAPPING)
    data.update(changes)
    return data


def test_reads_the_rows_of_the_test_exactly_in_file_order():
    extract = parse(MAPPING).read(EXPORT, "T-12")
    assert (extract.data_rows, extract.named) == (4, 3)
    assert [row.number for row in extract.rows] == [3, 6]
    first, second = extract.rows
    assert first.cells == {"sample_abs": "0.500625", "standard_abs": "0.5"}
    assert first.values == {"sample_abs": Decimal("0.500625"), "standard_abs": Decimal("0.5")}
    # Case and surrounding spaces are ignored when matching; the cell keeps its text, the
    # number is written out in full and keeps its scale.
    assert second.cells == {"sample_abs": "4.9875E-1", "standard_abs": "0.50"}
    assert str(second.values["sample_abs"]) == "0.49875"
    assert str(second.values["standard_abs"]) == "0.50"


def test_semicolon_comma_decimal_and_windows_1252():
    data = mapping(
        delimiter="semicolon",
        decimal="comma",
        encoding="windows-1252",
        header_row=1,
        id_column="Probe",
        filter_column="",
        filter_value="",
        columns=[{"field": "value", "column": "Wasser %"}],
    )
    content = "Probe;Wasser %;Bemerkung\nT-3;0,125;Prüfung\nT-3;1,5E-1;\n".encode("cp1252")
    rows = parse(data).read(content, "T-3").rows
    assert [str(row.values["value"]) for row in rows] == ["0.125", "0.15"]
    assert rows[0].cells == {"value": "0,125"}


def test_utf8_with_byte_order_mark_and_utf16():
    content = "\ufeffSample ID,Wavelength,Sample Abs,Std Abs\nT-1,254 nm,1,2\n"
    assert parse(mapping(header_row=1)).read(content.encode(), "T-1").rows[0].number == 2
    utf16 = parse(mapping(header_row=1, encoding="utf-16"))
    rows = utf16.read(content[1:].encode("utf-16"), "T-1").rows
    assert rows[0].values == {"sample_abs": Decimal(1), "standard_abs": Decimal(2)}
    with pytest.raises(FileImportError, match="not UTF-16"):
        utf16.read(b"\xff\xfeA", "T-1")


@pytest.mark.parametrize(
    ("cell", "message"),
    [
        ("", "is empty"),
        ("<0.05", "not a plain number"),
        ("1,234.5", "not a plain number"),
        ("12.5 AU", "not a plain number"),
        ("n.a.", "not a plain number"),
        ("NaN", "not a plain number"),
        ("Infinity", "not a plain number"),
        ("1e999", "not a plain number"),
        ("−1.5", "not a plain number"),  # a minus sign that is not ASCII
        ("１.５", "not a plain number"),  # full-width digits
    ],
)
def test_a_cell_that_is_not_a_plain_number_refuses_the_whole_file(cell, message):
    content = (
        f'x\nSample ID,Wavelength,Sample Abs,Std Abs\nT-1,254 nm,0.5,0.5\nT-1,254 nm,"{cell}",0.5\n'
    )
    with pytest.raises(FileImportError, match=message) as caught:
        parse(MAPPING).read(content.encode(), "T-1")
    assert "Row 4, column “Sample Abs”" in str(caught.value)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"only one row\n", "has no row 2"),
        (b"x\nSample ID,Sample Abs,Std Abs\n", "no column named “Wavelength”"),
        (b"x\nSample ID,Wavelength,Sample Abs,Std Abs,sample abs\n", "more than once"),
        (b'x\nSample ID,Wavelength,Sample Abs,Std Abs\n"T-1,254\n', "cannot be read"),
        (b"\xff\xfe\x00broken", "not UTF-8 text"),
    ],
)
def test_files_that_do_not_fit_the_mapping_are_refused(content, message):
    with pytest.raises(FileImportError, match=message):
        parse(MAPPING).read(content, "T-1")


def test_rows_of_other_tests_and_other_peaks_are_not_read():
    extract = parse(MAPPING).read(EXPORT, "T-120")
    assert [row.number for row in extract.rows] == [7]
    none = parse(MAPPING).read(EXPORT, "T-1")
    assert (none.rows, none.named) == ((), 0)


def test_a_row_with_more_cells_than_the_column_names_refuses_the_file():
    # An unquoted decimal comma in a comma-separated file shifts the values to the right.
    content = b"x\nSample ID,Wavelength,Sample Abs,Std Abs\nT-1,254 nm,0,515,0.497\n"
    with pytest.raises(FileImportError, match="Row 3 has more cells than the column names"):
        parse(MAPPING).read(content, "T-1")
    # A row of another test is checked too: the file is malformed, whatever it names.
    other = b"x\nSample ID,Wavelength,Sample Abs,Std Abs\nT-1,254 nm,0.5,0.5\nT-2,a,b,c,d\n"
    with pytest.raises(FileImportError, match="Row 4 has more cells"):
        parse(MAPPING).read(other, "T-1")
    # Trailing empty cells are not values.
    padded = b"x\nSample ID,Wavelength,Sample Abs,Std Abs,\nT-1,254 nm,0.5,0.5,,\n"
    assert parse(MAPPING).read(padded, "T-1").rows[0].values["standard_abs"] == Decimal("0.5")


def test_rows_with_too_many_columns_are_refused_before_anything_else():
    header = ",".join(["Sample ID", "Wavelength", "Sample Abs", "Std Abs"] + ["x"] * 497)
    with pytest.raises(FileImportError, match="Row 2 has more than 500 columns"):
        parse(MAPPING).read(f"x\n{header}\n".encode(), "T-1")


def test_rows_are_numbered_as_records_also_in_read_errors():
    content = (
        b'x\nSample ID,Wavelength,Sample Abs,Std Abs\n"T-1\nbroken",254 nm,1,1\nT-1,"a"b,1,1\n'
    )
    with pytest.raises(FileImportError, match="^Row 4 cannot be read"):
        parse(MAPPING).read(content, "T-1")


def test_short_rows_read_missing_cells_as_empty():
    content = b"x\nSample ID,Wavelength,Sample Abs,Std Abs\nT-1,254 nm,0.5\n"
    with pytest.raises(FileImportError, match="Std Abs” is empty"):
        parse(MAPPING).read(content, "T-1")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema": "oq.file-import/2"}, "Unsupported"),
        ({"delimiter": "pipe"}, "separator"),
        ({"decimal": "comma"}, "cannot use a comma"),
        ({"encoding": "latin-9"}, "encoding"),
        ({"header_row": 0}, "1 to 50"),
        ({"header_row": True}, "1 to 50"),
        ({"source": ""}, "is required"),
        ({"source": " padded"}, "trimmed"),
        ({"id_column": ""}, "is required"),
        ({"filter_value": ""}, "both"),
        ({"columns": []}, "Map 1 to 13"),
        ({"columns": [{"field": "Bad Code", "column": "A"}]}, "field code"),
        ({"columns": [{"field": "a", "column": "A"}, {"field": "a", "column": "B"}]}, "more than"),
        ({"columns": [{"field": "a", "column": "Sample ID"}]}, "used once"),
        ({"columns": [{"field": "a", "column": "A", "extra": 1}]}, "not valid"),
        ({"extra": 1}, "keys differ"),
    ],
)
def test_invalid_mappings_are_refused(changes, message):
    with pytest.raises(FileImportError, match=message):
        parse(mapping(**changes))


def test_problems_against_the_method_fields():
    assert problems(MAPPING, ["sample_abs", "standard_abs", "standard_conc"]) == []
    assert "does not have: standard_abs" in problems(MAPPING, ["sample_abs"])[0]
    value = mapping(columns=[{"field": "value", "column": "Result"}])
    assert problems(value, [file_imports.VALUE]) == []
    assert "map only the result column" in problems(MAPPING, [file_imports.VALUE])[0]
    assert problems({"schema": "x"}, ["a"])[0].startswith("File import keys differ")


def test_hash_and_content_round_trip():
    parsed = parse(MAPPING)
    assert parsed.content() == MAPPING
    assert parse(parsed.content()).hash == parsed.hash
    assert parse(mapping(filter_value="280 nm")).hash != parsed.hash
