"""Results imported from an instrument export through the method's approved file import."""

import hashlib
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from analytical import fixtures, imports, rawdata, services
from analytical.contracts import WorkRefused
from analytical.models import Observation, RawDataFile
from core.models import AuditEvent

from .conftest import fresh, login, review

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("plain_static")]

STANDARDS = {"standard_conc": Decimal("1.000"), "sample_conc": Decimal("1")}


def uv_export(label, *rows, header=True):
    lines = ["Synthetic UV export,Run 7"] if header else []
    lines.append("Sample ID,Wavelength,Sample Abs,Std Abs")
    lines += [
        f"{name or label},{wave},{sample},{standard}" for name, wave, sample, standard in rows
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


def kf_export(label, *values):
    lines = ["Probe;Methode;Wasser %;Bemerkung"]
    lines += [f"{label};KF-Vol;{value};Prüfung" for value in values]
    return ("\n".join(lines) + "\n").encode("cp1252")


@pytest.fixture
def imported(people, make_lot):
    lot, sample = make_lot("SYN-IMP", tests=("uv_file", "kf_file"))
    created, holds = services.assign_tests(actor=people["analyst"], sample=sample, reason="Go")
    assert holds == []
    return lot, sample, {t.test_code: t for t in created}


def attach(people, test, content, name="run7.csv", who="analyst"):
    return rawdata.attach_raw_file(
        actor=people[who],
        test=test,
        upload=SimpleUploadedFile(name, content),
        description="Instrument export",
    )


def run_import(people, test, stored, who="analyst", entered=None, **kwargs):
    test = fresh(test)
    rows = imports.read_file(test, stored).rows
    kwargs.setdefault("equipment_ids", [2])
    return imports.import_observations(
        actor=people[who],
        test=test,
        stored=stored,
        expected_revision=kwargs.pop("expected_revision", test.revision),
        raw_reference=kwargs.pop("raw_reference", "UV-CDS project SYN, run 7"),
        entered=entered if entered is not None else {row.number: dict(STANDARDS) for row in rows},
        **kwargs,
    )


def uv_pair(people, test):
    content = uv_export(
        test.label,
        ("", "254 nm", "0.500625", "0.5"),
        ("", "280 nm", "0.3", "0.31"),
        ("T-99999", "254 nm", "0.1", "0.5"),
        ("", "254 nm", "4.9875E-1", "0.50"),
    )
    return attach(people, test, content)


def test_calculated_rows_become_replicates_with_their_file_row_and_entered_inputs(people, imported):
    lot, _, tests = imported
    test = tests["uv_file"]
    stored = uv_pair(people, test)
    before = fresh(test).revision, fresh(lot).revision
    created = run_import(people, test, stored)
    assert [o.replicate for o in created] == [1, 2]
    first, second = (fresh(o) for o in created)
    assert (first.value, first.value_text) == (Decimal("100.13"), "100.13")
    assert second.value_text == "99.75"
    assert first.source_file == stored and first.source == {
        "row": 3,
        "cells": {"sample_abs": "0.500625", "standard_abs": "0.5"},
    }
    assert second.source["row"] == 6
    assert second.source["cells"] == {"sample_abs": "4.9875E-1", "standard_abs": "0.50"}
    assert [i["value"] for i in second.inputs] == ["0.49875", "0.50", "1.000", "1"]
    assert first.raw_reference == "UV-CDS project SYN, run 7"
    assert first.calculation["method"] == "SYN-UV-FILE"
    assert first.recorded_by == people["analyst"]
    assert first.eligibility == second.eligibility and first.equipment_used
    test = fresh(test)
    assert test.revision == before[0] + 1 and fresh(lot).revision == before[1] + 1
    events = sorted(
        AuditEvent.objects.filter(action="observation.imported"),
        key=lambda event: event.after["replicate"],
    )
    assert len(events) == 2
    assert events[0].after["file"] == {
        "id": stored.pk,
        "filename": "run7.csv",
        "sha256": stored.sha256,
    }
    assert events[0].after["row"] == 3 and events[0].after["value"] == "100.13"
    assert events[0].after["mapping"] == test.spec.method.file_import.hash
    assert events[0].reason == "Imported from run7.csv, row 3."
    assert imports.import_problems(test, list(test.current_observations())) == []


def test_direct_values_with_comma_decimals_import_and_submit(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12", "0,145"), name="kf.txt")
    created = run_import(people, test, stored, entered={}, equipment_ids=[])
    assert [o.value_text for o in created] == ["0.12", "0.145"]
    assert [o.inputs for o in created] == [[], []]
    assert created[0].source["cells"] == {"value": "0,12"}
    submitted, investigation = services.submit_test(
        actor=people["analyst"],
        test=fresh(test),
        expected_revision=fresh(test).revision,
        reason="Complete",
    )
    assert investigation is None and submitted.reportable_text == "0.13"
    review(people, submitted)
    assert fresh(test).state == "reviewed"


@pytest.mark.parametrize("who", ["reviewer", "quality", "auditor"])
def test_only_analysts_import(people, imported, who):
    _, _, tests = imported
    stored = uv_pair(people, tests["uv_file"])
    with pytest.raises(PermissionDenied):
        run_import(people, tests["uv_file"], stored, who=who)
    assert not Observation.objects.exists()


def test_stale_revision_refuses_and_stores_nothing(people, imported):
    _, _, tests = imported
    test = tests["uv_file"]
    stored = uv_pair(people, test)
    with pytest.raises(ValidationError, match="Record changed"):
        run_import(people, test, stored, expected_revision=fresh(test).revision - 1)
    assert not Observation.objects.exists()
    assert not AuditEvent.objects.filter(action="observation.imported").exists()


def test_a_file_is_imported_once(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12"))
    run_import(people, test, stored, entered={}, equipment_ids=[])
    with pytest.raises(ValidationError, match="already recorded"):
        run_import(people, test, stored, entered={}, equipment_ids=[])
    assert Observation.objects.count() == 1


def test_more_rows_than_replicates_left_refuses_the_whole_file(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12", "0,13", "0,40"))
    with pytest.raises(ValidationError, match="holds 3 rows .* takes 2 more replicates"):
        run_import(people, test, stored, entered={}, equipment_ids=[])
    first = attach(people, test, kf_export(test.label, "0,12"), name="first.txt")
    run_import(people, test, first, entered={}, equipment_ids=[])
    second = attach(people, test, kf_export(test.label, "0,12", "0,14"), name="second.txt")
    with pytest.raises(ValidationError, match="takes 1 more replicate\\."):
        run_import(people, test, second, entered={}, equipment_ids=[])
    assert Observation.objects.count() == 1


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"x\nSample ID,Wavelength,Sample Abs,Std Abs\nSYN-9,254 nm,0.5,0.5\n", "No row of"),
        (None, "none has “254 nm”"),
        (b"x\nSample ID,Sample Abs\n", "no column named"),
    ],
)
def test_files_without_rows_for_the_test_refuse(people, imported, content, message):
    _, _, tests = imported
    test = tests["uv_file"]
    if content is None:
        content = uv_export(test.label, ("", "280 nm", "0.3", "0.31"))
    stored = attach(people, test, content)
    with pytest.raises(ValidationError, match=message):
        run_import(people, test, stored, entered={})
    assert not Observation.objects.exists()


def test_a_cell_that_is_not_a_number_refuses_every_row(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12", "<0,05"))
    with pytest.raises(ValidationError, match="Row 3, column “Wasser %” holds “<0,05”"):
        imports.read_file(fresh(test), stored)
    assert not Observation.objects.exists()


def test_missing_or_invalid_entered_inputs_refuse_with_the_row(people, imported):
    _, _, tests = imported
    test = tests["uv_file"]
    stored = uv_pair(people, test)
    with pytest.raises(ValidationError, match="Row 3: Enter Standard concentration"):
        run_import(people, test, stored, entered={3: {}, 6: dict(STANDARDS)})
    with pytest.raises(ValidationError, match="Row 6: .*cannot be calculated"):
        run_import(
            people,
            test,
            stored,
            entered={3: dict(STANDARDS), 6: {**STANDARDS, "sample_conc": Decimal(0)}},
        )
    assert not Observation.objects.exists()


def test_more_decimals_than_recorded_refuse_instead_of_rounding(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,123456789"))
    with pytest.raises(ValidationError, match="Row 2: The value has more than 8 decimal"):
        run_import(people, test, stored, entered={}, equipment_ids=[])


def test_small_direct_values_are_written_out_in_full(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,0000001", "1,2E-7"))
    created = run_import(people, test, stored, entered={}, equipment_ids=[])
    assert [o.value_text for o in created] == ["0.0000001", "0.00000012"]
    assert imports.import_problems(fresh(test), created) == []


def test_preview_refuses_rows_the_requirement_cannot_take(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,1", "0,123456789"))
    refusal = imports.row_refusal(fresh(test).spec, imports.read_file(fresh(test), stored).rows)
    assert refusal == "Row 3: The value has more than 8 decimal places."
    uv = tests["uv_file"]
    wide = attach(
        people, uv, uv_export(uv.label, ("", "254 nm", "0.123456789", "0.5")), name="wide.csv"
    )
    rows = imports.read_file(fresh(uv), wide).rows
    assert imports.row_refusal(fresh(uv).spec, rows).startswith("Row 3: Sample absorbance")
    assert (
        imports.row_refusal(fresh(uv).spec, imports.read_file(fresh(uv), uv_pair(people, uv)).rows)
        is None
    )


def test_bench_refusal_is_audited_and_stores_nothing(people, imported):
    _, _, tests = imported
    test = tests["uv_file"]
    stored = uv_pair(people, test)
    with pytest.raises(ValidationError, match="requires at least one instrument"):
        run_import(people, test, stored, equipment_ids=[])
    with pytest.raises(WorkRefused):
        run_import(people, test, stored, equipment_ids=[3])  # out of service
    assert not Observation.objects.exists()
    assert fixtures.BENCH_LOG[-1][0] == "record_refusal"


def test_a_file_of_another_test_is_refused(people, imported):
    _, _, tests = imported
    other = attach(people, tests["kf_file"], kf_export(tests["uv_file"].label, "0,12"))
    with pytest.raises(ValidationError, match="not a raw-data file of this test"):
        imports.import_observations(
            actor=people["analyst"],
            test=tests["uv_file"],
            stored=other,
            expected_revision=fresh(tests["uv_file"]).revision,
            raw_reference="X",
            equipment_ids=[2],
        )


def test_methods_without_a_file_import_and_closed_tests_refuse(people, imported, assigned):
    _, _, tests = assigned
    assert "does not read an instrument file" in imports.import_refusal(tests["assay"])
    _, _, mine = imported
    test = mine["kf_file"]
    run_import(
        people,
        test,
        attach(people, test, kf_export(test.label, "0,12", "0,13")),
        entered={},
        equipment_ids=[],
    )
    assert imports.import_refusal(fresh(test)) == (
        "All replicates are recorded. Correct a value instead."
    )


def test_the_database_keeps_imported_rows_with_a_file_of_their_own_test(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12"))
    (observation,) = run_import(people, test, stored, entered={}, equipment_ids=[])
    other = attach(people, tests["uv_file"], b"other")
    with pytest.raises(DatabaseError, match="own test"), transaction.atomic():
        Observation.objects.create(
            test=test,
            replicate=2,
            value=Decimal("0.1"),
            value_text="0.1",
            unit="% w/w",
            raw_reference="X",
            source_file=other,
            source={"row": 2, "cells": {}},
            recorded_by=people["analyst"],
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        Observation.objects.create(
            test=test,
            replicate=2,
            value=Decimal("0.1"),
            value_text="0.1",
            unit="% w/w",
            raw_reference="X",
            source_file=stored,
            recorded_by=people["analyst"],
        )  # an imported row names its row
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        Observation.objects.filter(pk=observation.pk).update(source={"row": 9, "cells": {}})


def tamper(stored, content):
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE analytical_rawdatafile DISABLE TRIGGER analytical_append_only")
        try:
            cursor.execute(
                "UPDATE analytical_rawdatafile SET content = %s, sha256 = %s, size = %s "
                "WHERE id = %s",
                [content, hashlib.sha256(content).hexdigest(), len(content), stored.pk],
            )
        finally:
            cursor.execute(
                "ALTER TABLE analytical_rawdatafile ENABLE TRIGGER analytical_append_only"
            )


def test_submission_and_review_read_the_stored_file_again(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12", "0,14"))
    run_import(people, test, stored, entered={}, equipment_ids=[])
    tamper(stored, kf_export(test.label, "0,12", "0,44"))
    current = list(fresh(test).current_observations())
    assert imports.import_problems(fresh(test), current) == [
        "Replicate 2: row 3 of run7.csv no longer reads as recorded."
    ]
    with pytest.raises(ValidationError, match="no longer agrees"):
        services.submit_test(
            actor=people["analyst"],
            test=fresh(test),
            expected_revision=fresh(test).revision,
            reason="Complete",
        )
    assert fresh(test).state == "open"
    tamper(stored, kf_export(test.label, "0,12", "0,14"))
    services.submit_test(
        actor=people["analyst"],
        test=fresh(test),
        expected_revision=fresh(test).revision,
        reason="Complete",
    )
    tamper(stored, b"broken")
    with pytest.raises(ValidationError, match="no longer agrees"):
        review(people, fresh(test))
    assert fresh(test).state == "submitted"


def test_a_corrected_import_is_entered_by_hand_and_keeps_the_original(people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12", "0,14"))
    first, _ = run_import(people, test, stored, entered={}, equipment_ids=[])
    correction = services.correct_observation(
        actor=people["analyst"],
        observation=first,
        raw_reference="KF printout p2",
        reason="Transcription on the instrument",
        value=Decimal("0.13"),
    )
    assert correction.source_file is None and correction.source == {}
    assert fresh(first).source_file == stored
    assert imports.import_problems(fresh(test), list(fresh(test).current_observations())) == []


# Pages ------------------------------------------------------------------------------------------


def test_upload_attaches_reads_and_records_through_the_pages(client, people, imported):
    _, _, tests = imported
    test = tests["uv_file"]
    login(client, people["analyst"])
    detail = client.get(reverse("analytical:test_detail", args=[test.pk]))
    assert b"Import results" in detail.content and b"File import" in detail.content
    content = uv_export(test.label, ("", "254 nm", "0.500625", "0.5"))
    response = client.post(
        reverse("analytical:import_new", args=[test.pk]),
        {"file": SimpleUploadedFile("run7.csv", content)},
    )
    stored = RawDataFile.objects.get(test=test)
    assert response.status_code == 302
    assert response["Location"] == reverse("analytical:import_file", args=[test.pk, stored.pk])
    assert stored.description == "Instrument export for import"
    page = client.get(response["Location"])
    assert page.status_code == 200
    text = page.content.decode()
    assert "Values read from the file" in text and "0.500625" in text and "Row 3: " in text
    test = fresh(test)
    data = {
        "equipment_ids": ["2"],
        "row3_standard_conc": "1.000",
        "row3_sample_conc": "1",
        "raw_reference": "UV-CDS run 7",
        "reason": "",
        "expected_revision": test.revision,
    }
    done = client.post(response["Location"], data)
    assert done.status_code == 302, done.content.decode()[:2000]
    observation = Observation.objects.get(test=test)
    assert observation.value_text == "100.13" and observation.source["row"] == 3
    detail = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert "Imported from:" in detail and "Sample Abs 0.500625" in detail
    assert "Results imported" in detail
    # The same file cannot be imported twice; the page says so instead of a form.
    again = client.get(response["Location"]).content.decode()
    assert "already recorded" in again and "Record imported results" not in again


def test_an_export_that_cannot_be_imported_is_refused_before_it_is_stored(client, people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    login(client, people["analyst"])
    url = reverse("analytical:import_new", args=[test.pk])
    revision = fresh(test).revision
    for content, message in [
        (kf_export(test.label, "n.a."), "not a plain number"),
        (kf_export("T-0", "0,12"), "No row of the file names"),
        (kf_export(test.label, "0,1", "0,2", "0,3"), "holds 3 rows"),
        (kf_export(test.label, "0,123456789"), "more than 8 decimal places"),
        (b"Sample;Wasser %\n", "no column named"),
    ]:
        response = client.post(url, {"file": SimpleUploadedFile("kf.txt", content)})
        text = response.content.decode()
        assert response.status_code == 422 and message in text, (message, text[-3000:])
        assert "Nothing was stored." in text
    assert not RawDataFile.objects.filter(test=test).exists()
    assert fresh(test).revision == revision
    assert not AuditEvent.objects.filter(action="rawdata.attached").exists()


def test_stale_preview_and_unreadable_file_are_explained(client, people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    login(client, people["analyst"])
    stored = attach(people, test, kf_export(test.label, "n.a."))
    url = reverse("analytical:import_file", args=[test.pk, stored.pk])
    held = client.get(url).content.decode()
    assert "Nothing imported" in held and "not a plain number" in held
    good = attach(people, test, kf_export(test.label, "0,12"), name="good.txt")
    url = reverse("analytical:import_file", args=[test.pk, good.pk])
    revision = fresh(test).revision
    attach(people, test, b"another file", name="other.bin")  # the test changes meanwhile
    stale = client.post(url, {"raw_reference": "KF", "reason": "", "expected_revision": revision})
    assert stale.status_code == 422 and "Record changed" in stale.content.decode()
    assert not Observation.objects.exists()


def test_import_pages_refuse_other_roles_and_other_tests(client, people, imported, assigned):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12"))
    for who in ("reviewer", "quality", "auditor"):
        login(client, people[who])
        assert client.get(reverse("analytical:import_new", args=[test.pk])).status_code == 403
        url = reverse("analytical:import_file", args=[test.pk, stored.pk])
        assert client.get(url).status_code == 403
    login(client, people["analyst"])
    wrong = reverse("analytical:import_file", args=[tests["uv_file"].pk, stored.pk])
    assert client.get(wrong).status_code == 404
    plain = assigned[2]["assay"]
    response = client.get(reverse("analytical:import_new", args=[plain.pk]))
    assert response.status_code == 302
    page = client.get(reverse("analytical:test_detail", args=[plain.pk])).content.decode()
    assert "Import results" not in page


def test_review_page_shows_the_imported_rows_and_the_check(client, people, imported):
    _, _, tests = imported
    test = tests["kf_file"]
    stored = attach(people, test, kf_export(test.label, "0,12", "0,14"))
    run_import(people, test, stored, entered={}, equipment_ids=[])
    services.submit_test(
        actor=people["analyst"],
        test=fresh(test),
        expected_revision=fresh(test).revision,
        reason="Complete",
    )
    login(client, people["reviewer"])
    page = client.get(reverse("analytical:test_review", args=[test.pk])).content.decode()
    assert "replicate 1 from run7.csv row 2; replicate 2 from run7.csv row 3" in page
    assert "read again from the stored file: agrees" in page
    tamper(stored, b"broken")
    detail = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert "no longer agree with them" in detail
