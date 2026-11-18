"""Results imported from an instrument export, across apps.

Approved method with a calculation and a file import -> frozen oq.test-requirement/4 -> export
attached and read -> replicates recorded with the instrument and standard lot checked by the
production bench bridge -> submission and independent review read the stored file again.
Uses the production requirement adapter and service-created approvals only (synthetic data).
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from analytical import imports, rawdata
from analytical import services as analytical
from analytical.models import Observation
from core.models import AuditEvent
from tests.test_calculation_bench_journey import assign_water, build_world, qualify
from tests.test_integrated_journey import PIN

pytestmark = pytest.mark.django_db(transaction=True)

FILE_IMPORT = {
    "source": "Synthetic titrator determination export",
    "delimiter": "semicolon",
    "decimal": "comma",
    "encoding": "windows-1252",
    "header_row": 1,
    "id_column": "Sample ID",
    "columns": {"titrant_volume": "Volume (mL)", "titer": "", "sample_mass": ""},
}
ENTERED = [
    {"titer": Decimal("4.98"), "sample_mass": Decimal("2500.4")},
    {"titer": Decimal("4.98"), "sample_mass": Decimal("2498.7")},
]


def export(label, *volumes):
    lines = ["Sample ID;Method;Volume (mL);Remark"]
    lines += [f"{label};KF-SYN;{volume};Prüfung" for volume in volumes]
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


@pytest.fixture
def world(django_user_model):
    return build_world(django_user_model, file_import=FILE_IMPORT)


def attach(world, test, content):
    return rawdata.attach_raw_file(
        actor=world["people"]["analyst"],
        test=test,
        upload=SimpleUploadedFile("kf-run.txt", content),
        description="Titrator export",
    )


def import_rows(world, test, stored, entered=ENTERED):
    test = type(test).objects.get(pk=test.pk)
    rows = imports.read_file(test, stored).rows
    return imports.import_observations(
        actor=world["people"]["analyst"],
        test=test,
        stored=stored,
        expected_revision=test.revision,
        raw_reference="Titrator SYN-TITRATOR-01 memory, run 4",
        entered={row.number: values for row, values in zip(rows, entered, strict=True)},
        equipment_ids=[world["equipment"].pk],
        reagent_ids=[world["standard"].pk],
    )


def test_approved_file_import_reaches_the_test_and_its_rows_are_reviewed(world):
    test = assign_water(world)
    assert test.requirement["schema"] == "oq.test-requirement/4"
    mapping = test.spec.method.file_import
    assert mapping.fields == ("titrant_volume",) and mapping.decimal == "comma"
    stored = attach(world, test, export(test.label, "1,25", "1,31"))
    first, second = import_rows(world, test, stored)
    # 1.25 * 4.98 / 2500.4 * 100 = 0.2489... -> 0.25; 1.31 * 4.98 / 2498.7 * 100 -> 0.26
    assert (first.value_text, second.value_text) == ("0.25", "0.26")
    assert first.inputs[0] == {
        "code": "titrant_volume",
        "name": "Titrant volume",
        "unit": "mL",
        "value": "1.25",
    }
    assert first.source == {"row": 2, "cells": {"titrant_volume": "1,25"}}
    assert first.equipment_used and first.reagents_used
    test, investigation = analytical.submit_test(
        actor=world["people"]["analyst"],
        test=type(test).objects.get(pk=test.pk),
        expected_revision=type(test).objects.get(pk=test.pk).revision,
        reason="Results complete",
    )
    assert investigation is None and test.conforms
    reviewed = analytical.review_test(
        actor=world["people"]["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Checked the export rows against the titrator memory",
    )
    assert reviewed.state == "reviewed"
    assert AuditEvent.objects.filter(action="observation.imported").count() == 2


def test_the_production_bench_checks_imported_rows_like_entered_ones(world):
    test = assign_water(world)
    stored = attach(world, test, export(test.label, "1,25", "1,31"))
    with pytest.raises(ValidationError, match="requires at least one reagent"):
        imports.import_observations(
            actor=world["people"]["analyst"],
            test=test,
            stored=stored,
            expected_revision=type(test).objects.get(pk=test.pk).revision,
            raw_reference="Titrator memory",
            entered={2: ENTERED[0], 3: ENTERED[1]},
            equipment_ids=[world["equipment"].pk],
        )
    assert not Observation.objects.exists()


def test_a_reviewer_who_imported_cannot_review(world):
    test = assign_water(world)
    analyst = world["people"]["analyst"]
    reviewer = world["people"]["reviewer"]
    reviewer.groups.add(*analyst.groups.all())
    world["people"]["analyst"] = reviewer
    qualify({**world["people"], "analyst": reviewer}, world["method"].code)
    stored = attach(world, test, export(test.label, "1,25", "1,31"))
    import_rows(world, test, stored)
    test = type(test).objects.get(pk=test.pk)
    analytical.submit_test(
        actor=reviewer, test=test, expected_revision=test.revision, reason="Complete"
    )
    test = type(test).objects.get(pk=test.pk)
    with pytest.raises(ValidationError, match="own"):
        analytical.review_test(
            actor=reviewer, pin=PIN, test=test, expected_revision=test.revision, reason="Self"
        )
