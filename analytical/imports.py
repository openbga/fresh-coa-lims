"""Results imported from an instrument export file: service, check, forms and views.

The method version frozen on the test states how its instrument's export is read
(``core.file_imports``). The analyst attaches the export as a raw-data file of the test; the
server reads that stored file, never values sent by the browser, and shows what it found. On
confirmation each selected row becomes the next replicate, with the file and the row it came
from. Inputs of the calculation that the file does not hold are entered for each row. Submission
and review read the stored file again and refuse a replicate that no longer agrees with it.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from core import file_imports
from core.audit import record_event
from core.services import require_role
from core.uploads import size_text

from . import rawdata
from .contracts import Reading, entered_number
from .forms import BenchForm
from .models import AnalyticalTest, Observation, RawDataFile
from .services import (
    ANALYST,
    REPORTED,
    _authorize,
    _bump,
    _check_revision,
    _entry,
    _lock_subjects,
    _raise,
    _reading_record,
    _resource_ids,
    _touch,
    _with_bench,
    subject_refusal,
    supplier_refusal,
)

VALUE = file_imports.VALUE
NOT_ACCEPTING = "This test is not accepting observations."
ALREADY = "Results from this file are already recorded on this test."


def import_refusal(test):
    """Why results cannot be imported into this test now, or None. Shared by the pages; the
    service repeats every check under the test's lock."""
    if test.state != AnalyticalTest.State.OPEN or subject_refusal(test):
        return NOT_ACCEPTING
    if refusal := supplier_refusal(test):
        return refusal
    spec = test.spec
    if spec.method.file_import is None:
        return (
            f"Method {spec.method.code} revision {spec.method.revision} does not read an "
            "instrument file; record each replicate by hand."
        )
    if spec.is_qualitative:
        return "A qualitative result is recorded by hand, with what was observed."
    if test.contract_source() is not None:
        return REPORTED
    if spec.method.requires_batch and test.batch_id is None:
        return "Assign this test to a QC batch before recording results."
    if test.current_observations().count() >= spec.replicates:
        return "All replicates are recorded. Correct a value instead."
    return None


def read_file(test, stored):
    """What the stored file holds for the test, read with the method's frozen mapping.

    Raises ValidationError when the stored bytes fail their checksum or the file cannot be read
    with the mapping.
    """
    mapping = test.spec.method.file_import
    if mapping is None:
        raise ValidationError("The method of this test does not read an instrument file.")
    content = rawdata.verified_content(stored)
    try:
        return mapping.read(content, test.label)
    except file_imports.FileImportError as exc:
        raise ValidationError(str(exc)) from exc


def selection_refusal(test, extract, recorded):
    """Why the rows found cannot be imported as they are, or None: none names the test, or
    there are more than the replicates still to record."""
    mapping = test.spec.method.file_import
    if not extract.rows:
        if extract.named and mapping.filter_column:
            return (
                f"{extract.named} row{'s' if extract.named != 1 else ''} of the file name "
                f"{test.label}, but none has “{mapping.filter_value}” in column "
                f"“{mapping.filter_column}”."
            )
        return (
            f"No row of the file names {test.label} in column “{mapping.id_column}”. Enter the "
            "test's number as the sample name on the instrument, or record the results by hand."
        )
    remaining = test.spec.replicates - recorded
    if len(extract.rows) > remaining:
        selected = f"names the test in “{mapping.id_column}”"
        if mapping.filter_column:
            selected += f" and has “{mapping.filter_value}” in “{mapping.filter_column}”"
        return (
            f"The file holds {len(extract.rows)} rows for {test.label} and the test takes "
            f"{remaining} more replicate{'s' if remaining != 1 else ''}. Every row that "
            f"{selected} is read, so none is left out. Record the replicates by hand, with the "
            "reason the other rows do not count."
        )
    return None


def row_refusal(spec, rows):
    """Why a row read from the file cannot be recorded, before anything is entered, or None:
    a value with too many digits or decimals, or a result this requirement cannot take (a count
    that is not whole). A calculation's own refusals wait for the inputs the analyst enters."""
    try:
        for row in rows:
            if spec.calculation is None:
                _fields(spec, row, {})
                continue
            for field, value in row.values.items():
                item = next(i for i in spec.calculation.inputs if i.code == field)
                try:
                    entered_number(value, item.label)
                except ValidationError as exc:
                    raise ValidationError(f"Row {row.number}: {' '.join(exc.messages)}") from exc
    except ValidationError as exc:
        return " ".join(exc.messages)
    return None


def entered_fields(spec):
    """The calculation inputs the file does not hold: the analyst enters them for each row."""
    calculation = spec.calculation
    mapped = set(spec.method.file_import.fields)
    return [i for i in calculation.inputs if i.code not in mapped] if calculation else []


def _fields(spec, row, entered):
    """Observation fields for one row: the cells read and the inputs entered for it."""
    calculation = spec.calculation
    try:
        if calculation is None:
            number, text = entered_number(row.values[VALUE], "The value")
            fields = _entry(
                spec, value=number, qualifier="", outcome="", observed_text="", inputs=None
            )
            # Written out in full (0.0000001, never 1E-7), as the file's number was read.
            return {**fields, "value_text": text}
        values = dict(row.values)
        for item in entered_fields(spec):
            values[item.code] = entered.get(item.code)
        return _entry(spec, value=None, qualifier="", outcome="", observed_text="", inputs=values)
    except ValidationError as exc:
        raise ValidationError(f"Row {row.number}: {' '.join(exc.messages)}") from exc


def import_observations(
    *,
    actor,
    test,
    stored,
    expected_revision,
    raw_reference,
    entered=None,
    equipment_ids=(),
    reagent_ids=(),
    reason="",
):
    """Record the rows of a stored export as the next replicates of the test, all or none.

    ``entered`` maps each row number to the calculation inputs the file does not hold. The
    rows are read again from the stored file under the test's lock; a test changed since the
    analyst checked them (``expected_revision``) is refused.
    """
    require_role(actor, ANALYST)
    raw_reference = (raw_reference or "").strip()
    if not raw_reference:
        raise ValidationError("Record where the instrument's original data is kept.")
    equipment_ids = _resource_ids(equipment_ids, "equipment")
    reagent_ids = _resource_ids(reagent_ids, "reagent or standard lot")
    entered = entered or {}

    def work(desk, attempt):
        locked = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        subjects = _lock_subjects(locked)
        _check_revision(locked, expected_revision)
        _raise(import_refusal(locked))
        source = RawDataFile.objects.filter(pk=stored.pk, test=locked).first()
        if source is None:
            raise ValidationError("The file is not a raw-data file of this test.")
        if Observation.objects.filter(test=locked, source_file=source).exists():
            raise ValidationError(ALREADY)
        spec = locked.spec
        extract = read_file(locked, source)
        recorded = locked.current_observations().count()
        _raise(selection_refusal(locked, extract, recorded))
        rows = [(row, _fields(spec, row, entered.get(row.number, {}))) for row in extract.rows]
        eligibility = _authorize(
            desk,
            attempt,
            actor=actor,
            method=spec.method,
            test_code=locked.test_code,
            context=("analytical.analyticaltest", locked.pk),
            equipment_ids=equipment_ids,
            reagent_ids=reagent_ids,
            reason=reason
            or f"Replicates {recorded + 1} to {recorded + len(rows)} of {locked.label} "
            f"{locked.test_code} imported from {source.filename}",
        )
        file_record = {"id": source.pk, "filename": source.filename, "sha256": source.sha256}
        created = []
        for offset, (row, fields) in enumerate(rows, start=1):
            observation = Observation(
                test=locked,
                replicate=recorded + offset,
                unit=spec.unit,
                raw_reference=raw_reference,
                reason=reason,
                eligibility=eligibility,
                source_file=source,
                source={"row": row.number, "cells": row.cells},
                recorded_by=actor,
                **fields,
            )
            observation.full_clean()
            observation.save()
            created.append(observation)
            record_event(
                actor=actor,
                action="observation.imported",
                obj=locked,
                after={
                    "observation": observation.pk,
                    "replicate": observation.replicate,
                    **_reading_record(observation),
                    "unit": spec.unit,
                    "raw_reference": raw_reference,
                    "file": file_record,
                    "row": row.number,
                    "cells": row.cells,
                    "mapping": spec.method.file_import.hash,
                    "eligibility": eligibility,
                },
                reason=reason or f"Imported from {source.filename}, row {row.number}.",
            )
        _touch(locked)
        _bump(*subjects)
        return created

    return _with_bench(actor, work)


def import_problems(test, observations):
    """Why imported replicates no longer agree with the files they were read from (an empty
    list when they do, or when none was imported). Read-only; submission and review refuse a
    test with a problem."""
    imported = [o for o in observations if o.source_file_id is not None]
    if not imported:
        return []
    problems, extracts = [], {}
    for observation in imported:
        label = f"Replicate {observation.replicate}"
        if observation.source_file_id not in extracts:
            try:
                extracts[observation.source_file_id] = read_file(test, observation.source_file)
            except ValidationError as exc:
                extracts[observation.source_file_id] = " ".join(exc.messages)
        extract = extracts[observation.source_file_id]
        if isinstance(extract, str):
            problems.append(f"{label}: {observation.source_file.filename}: {extract}")
            continue
        number = observation.source.get("row")
        row = next((r for r in extract.rows if r.number == number), None)
        if row is None or row.cells != observation.source.get("cells"):
            problems.append(
                f"{label}: row {number} of {observation.source_file.filename} no longer reads "
                "as recorded."
            )
            continue
        if not _agrees(observation, row):
            problems.append(
                f"{label}: the recorded value differs from row {number} of "
                f"{observation.source_file.filename}."
            )
    return problems


def _agrees(observation, row):
    """Whether the replicate holds exactly the numbers read from its row."""
    if observation.is_calculated:
        recorded = {i.get("code"): i.get("value") for i in observation.inputs}
        return all(recorded.get(field) == format(v, "f") for field, v in row.values.items())
    value = row.values.get(VALUE)
    return value is not None and observation.reading == Reading(value=value)


def recheck_imports(test, observations, refusal):
    """Raise ``refusal`` when an imported replicate no longer agrees with its stored file."""
    if problems := import_problems(test, observations):
        raise ValidationError([refusal, *problems])


# Forms ----------------------------------------------------------------------------------------


class ImportFileForm(forms.Form):
    """The export to import: attached to the test as raw data, then read."""

    file = forms.FileField(
        label="Instrument export",
        help_text="Kept exactly as received with the test's raw data, then read with the "
        "method's approved file import. Large files and duplicates of a file already attached "
        "are refused.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs.update(
            {
                "data-vr-max-bytes": rawdata.max_bytes(),
                "data-vr-max-label": size_text(rawdata.max_bytes()),
            }
        )


class ImportForm(BenchForm):
    """Confirm the rows read from a stored export: the equipment and lots used, where the
    instrument's original data is kept, the calculation inputs the file does not hold (one per
    row and input) and an optional note. ``entered()`` returns ``{row: {code: text}}``."""

    raw_reference = forms.CharField(
        label="Original record",
        max_length=200,
        help_text="Where the instrument's original data is kept, for example its data "
        "system's project and run. The export is kept with the test either way.",
    )
    reason = forms.CharField(
        label="Note",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Optional. Kept with each imported replicate.",
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, spec, rows, choices, **kwargs):
        super().__init__(*args, choices=choices, method=spec.method, **kwargs)
        self.inputs = entered_fields(spec)
        extra = {}
        for row in rows:
            for item in self.inputs:
                extra[f"row{row.number}_{item.code}"] = forms.DecimalField(
                    label=f"Row {row.number}: {item.name}",
                    help_text=f"Exact value, in {escape(item.unit)}; not in the file.",
                    max_digits=20,
                    decimal_places=8,
                    widget=forms.TextInput(attrs={"unit": item.unit, "inputmode": "decimal"}),
                )
        if extra:
            fields = {}
            for name, field in self.fields.items():
                if name == "raw_reference":
                    fields.update(extra)
                fields[name] = field
            self.fields = fields
        self.rows = rows

    def entered(self):
        return {
            row.number: {
                item.code: self.cleaned_data[f"row{row.number}_{item.code}"] for item in self.inputs
            }
            for row in self.rows
        }


# Views ----------------------------------------------------------------------------------------


def _test(pk):
    return get_object_or_404(
        AnalyticalTest.objects.select_related(
            "lot",
            "sample",
            "batch",
            "pull__study__lot",
            "pull__timepoint__condition",
            "reassessment__lot",
        ),
        pk=pk,
    )


def _crumbs(test, current):
    return [
        ("Testing", reverse("analytical:test_list")),
        (test.subject_page[0], test.subject_url),
        (test.label, reverse("analytical:test_detail", args=[test.pk])),
        (current, None),
    ]


def mapping_facts(mapping):
    """How the method's approved file import reads the export, for the pages."""
    rows = f"column names in row {mapping.header_row}; one row per replicate"
    select = f"rows whose “{mapping.id_column}” is the test number"
    if mapping.filter_column:
        select += f" and whose “{mapping.filter_column}” is “{mapping.filter_value}”"
    return [
        ("Export", mapping.source),
        (
            "Format",
            f"{mapping.delimiter_label} separated, decimal {mapping.decimal}, "
            f"{mapping.encoding_label}; {rows}",
        ),
        ("Rows read", select),
    ]


@login_required
@require_http_methods(["GET", "POST"])
def import_new(request, pk):
    """Upload an export: read first, then attached to the test as raw data and shown on the
    next page. An export that cannot be imported as it is is refused and not stored."""
    require_role(request.user, ANALYST)
    test = _test(pk)
    back = reverse("analytical:test_detail", args=[test.pk])
    if refusal := import_refusal(test):
        messages.warning(request, refusal)
        return redirect(back)
    if (
        request.method == "POST"
        and request.FILES is not None
        and getattr(request, "upload_too_large", False)
    ):
        messages.error(
            request,
            f"The file is larger than the limit of {size_text(rawdata.max_bytes())}. "
            "Nothing was stored.",
        )
        return redirect("analytical:import_new", pk=test.pk)
    form = ImportFileForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        if refusal := upload_refusal(test, upload):
            form.add_error("file", f"{refusal} Nothing was stored.")
        else:
            try:
                stored = rawdata.attach_raw_file(
                    actor=request.user,
                    test=test,
                    upload=upload,
                    description="Instrument export for import",
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                messages.success(request, "Export attached. Check the values read from it.")
                return redirect("analytical:import_file", pk=test.pk, file_pk=stored.pk)
    mapping = test.spec.method.file_import
    return render(
        request,
        "analytical/raw_file_form.html",
        {
            "page_title": f"Import results · {test.label}",
            "form": form,
            "submit_label": "Attach and read",
            "crumbs": _crumbs(test, "Import results"),
            "cancel_url": back,
            "summary": [
                ("Test", f"{test.label} ({test.test_code})"),
                (test.subject_heading, test.subject_text),
                *mapping_facts(mapping),
                ("Size limit", size_text(rawdata.max_bytes())),
            ],
        },
        status=422 if request.method == "POST" else 200,
    )


@login_required
@require_http_methods(["GET", "POST"])
def import_file(request, pk, file_pk):
    """The rows a stored export holds for the test, checked by the analyst, then recorded."""
    require_role(request.user, ANALYST)
    test = _test(pk)
    stored = get_object_or_404(RawDataFile.objects.defer("content"), pk=file_pk, test=test)
    back = reverse("analytical:test_detail", args=[test.pk])
    if refusal := import_refusal(test):
        messages.warning(request, refusal)
        return redirect(back)
    spec = test.spec
    mapping = spec.method.file_import
    held, extract = "", None
    if Observation.objects.filter(test=test, source_file=stored).exists():
        held = ALREADY
    else:
        try:
            extract = read_file(test, stored)
        except ValidationError as exc:
            held = " ".join(exc.messages)
        else:
            recorded = test.current_observations().count()
            held = (
                selection_refusal(test, extract, recorded) or row_refusal(spec, extract.rows) or ""
            )
    choices, hold = (None, "") if held else rawdata_choices()
    held = held or hold
    rows = list(extract.rows) if extract and not held else []
    form = None
    if not held:
        form = ImportForm(
            request.POST or None,
            spec=spec,
            rows=rows,
            choices=choices,
            initial={"raw_reference": stored.filename[:200], "expected_revision": test.revision},
        )
        if request.method == "POST" and form.is_valid():
            from .views import perform

            data = form.cleaned_data
            if perform(
                form,
                lambda: import_observations(
                    actor=request.user,
                    test=test,
                    stored=stored,
                    expected_revision=data["expected_revision"],
                    raw_reference=data["raw_reference"],
                    entered=form.entered(),
                    equipment_ids=data.get("equipment_ids", ()),
                    reagent_ids=data.get("reagent_ids", ()),
                    reason=data["reason"],
                ),
            ):
                count = len(rows)
                messages.success(request, f"{count} replicate{'s' if count != 1 else ''} imported.")
                return redirect(back)
    recorded = test.current_observations().count()
    columns = [(field, mapping.column_of(field)) for field in mapping.fields]
    return render(
        request,
        "analytical/import_form.html",
        {
            "page_title": f"Import results · {test.label}",
            "form": form,
            "held": held,
            "crumbs": _crumbs(test, "Import results"),
            "cancel_url": back,
            "stored": stored,
            "rows": [
                {
                    "number": row.number,
                    "replicate": recorded + index,
                    "cells": [row.cells[field] for field, _ in columns],
                }
                for index, row in enumerate(rows, start=1)
            ],
            "columns": columns,
            "extract": extract,
            "revision": test.revision,
            "summary": [
                ("Test", f"{test.label} ({test.test_code})"),
                (test.subject_heading, test.subject_text),
                ("File", f"{stored.filename} · SHA-256 {stored.sha256[:12]}"),
                *mapping_facts(mapping),
                ("Replicates", f"{recorded} of {spec.replicates} recorded"),
            ],
        },
        status=422 if request.method == "POST" else 200,
    )


def upload_refusal(test, upload):
    """Why an uploaded export cannot be imported as it is, read before it is stored, or None.
    A file over the size limit is left to the attachment, which refuses it."""
    if upload.size > rawdata.max_bytes():
        return None
    upload.seek(0)
    content = upload.read()
    upload.seek(0)
    try:
        extract = test.spec.method.file_import.read(content, test.label)
    except file_imports.FileImportError as exc:
        return str(exc)
    recorded = test.current_observations().count()
    return selection_refusal(test, extract, recorded) or row_refusal(test.spec, extract.rows)


def rawdata_choices():
    """The bench's equipment and lot choices, or (None, hold message) without a bench."""
    from .views import bench_choices

    return bench_choices()
