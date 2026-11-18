"""The file import of a method version: set on a draft, checked and frozen at approval."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.urls import reverse

from analytical.contracts import parse_requirement
from catalog import services
from catalog.models import MethodRevision
from core.models import AuditEvent

from .factories import approve, material, method_revision, numeric_line, specification
from .test_calculations import calculated

pytestmark = pytest.mark.django_db(transaction=True)

EXPORT = {
    "source": "Synthetic HPLC data system result table",
    "delimiter": "comma",
    "decimal": "point",
    "encoding": "utf-8",
    "header_row": 1,
    "id_column": "Sample Name",
    "filter_column": "Peak Name",
    "filter_value": "Synthetic API",
}
COLUMNS = {"peak_area": "Area", "standard_area": "Std Area", "standard_mass": "", "sample_mass": ""}


def set_import(actor, revision, columns=COLUMNS, **changes):
    return services.set_file_import(
        actor=actor,
        revision=revision,
        reason="Export of the data system",
        columns=columns,
        **{**EXPORT, **changes},
    )


def test_set_on_a_draft_is_audited_and_frozen_with_the_approval(people):
    revision = calculated(people["author"])
    before = revision.revision
    locked = set_import(people["author"], revision)
    assert locked.revision == before + 1
    assert locked.file_import["columns"] == [
        {"field": "peak_area", "column": "Area"},
        {"field": "standard_area", "column": "Std Area"},
    ]
    event = AuditEvent.objects.get(action="method_revision.file_import_set")
    assert event.after == locked.file_import and event.reason == "Export of the data system"
    approved = approve(locked, people["approver"])
    assert approved.approved_content["file_import"] == locked.file_import
    # Approved content is immutable, the import included.
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodRevision.objects.filter(pk=approved.pk).update(file_import=None)
    with pytest.raises(ValidationError, match="Only draft"):
        set_import(people["author"], approved)


def test_only_quality_sets_or_clears(people):
    revision = calculated(people["author"])
    for who in ("analyst", "reviewer", "admin", "auditor"):
        with pytest.raises(PermissionDenied):
            set_import(people[who], revision)
    set_import(people["author"], revision)
    with pytest.raises(PermissionDenied):
        services.clear_file_import(actor=people["analyst"], revision=revision, reason="No")
    cleared = services.clear_file_import(actor=people["author"], revision=revision, reason="No")
    assert cleared.file_import is None
    assert AuditEvent.objects.filter(action="method_revision.file_import_cleared").exists()
    with pytest.raises(ValidationError, match="no file import"):
        services.clear_file_import(actor=people["author"], revision=revision, reason="No")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"decimal": "comma"}, "cannot use a comma"),
        ({"columns": {"peak_area": "", "standard_area": ""}}, "Map 1 to 13"),
        ({"columns": {"peak_area": "Sample Name"}}, "used once"),
        ({"filter_value": ""}, "both"),
        ({"header_row": 0}, "1 to 50"),
    ],
)
def test_invalid_mappings_are_refused_when_set(people, changes, message):
    revision = calculated(people["author"])
    with pytest.raises(ValidationError, match=message):
        set_import(people["author"], revision, **changes)
    assert MethodRevision.objects.get(pk=revision.pk).file_import is None


def test_approval_checks_the_columns_against_the_calculation(people):
    revision = calculated(people["author"])
    set_import(people["author"], revision, columns={**COLUMNS, "dilution": "Dilution"})
    with pytest.raises(ValidationError, match="File import: .*does not have: dilution"):
        approve(revision, people["approver"])
    plain = set_import(
        people["author"],
        method_revision(people["author"], code="plain-file"),
        columns={"value": "Water %"},
    )
    assert services.file_import_problems(plain) == []
    wrong = set_import(
        people["author"],
        method_revision(people["author"], code="wrong-file"),
        columns={"peak_area": "Area"},
    )
    assert "map only the result column" in services.file_import_problems(wrong)[0]


def test_a_new_version_copies_the_file_import(people):
    first = calculated(people["author"])
    set_import(people["author"], first)
    approve(first, people["approver"])
    nxt = method_revision(people["author"], code="hplc-calc", method=first.method)
    assert nxt.file_import == MethodRevision.objects.get(pk=first.pk).file_import


def test_the_import_is_frozen_into_the_test_requirement_as_v4(people):
    mat = material(people["author"])
    with_file = calculated(people["author"])
    set_import(people["author"], with_file)
    approve(with_file, people["approver"])
    plain = approve(method_revision(people["author"], code="plain-ident"), people["approver"])
    _, revision = specification(people["author"], mat)
    numeric_line(people["author"], revision, with_file.method, code="assay", unit="%")
    numeric_line(people["author"], revision, plain.method, code="water", unit="%")
    approve(revision, people["approver"])
    resolved = services.resolve_requirements(material=mat, stage="incoming")
    payloads = {t["code"]: services.test_requirement(t, "catalog:x@v1") for t in resolved["tests"]}
    assert payloads["assay"]["schema"] == "oq.test-requirement/4"
    assert payloads["water"]["schema"] == "oq.test-requirement/1"
    spec = parse_requirement(payloads["assay"])
    assert spec.method.file_import.fields == ("peak_area", "standard_area")
    assert spec.method.file_import.filter_value == "Synthetic API"
    assert parse_requirement(payloads["water"]).method.file_import is None


def test_a_requirement_whose_import_does_not_fit_the_calculation_holds(people):
    revision = set_import(people["author"], calculated(people["author"]))
    payload = services.test_requirement(
        {
            "code": "assay",
            "name": "Assay",
            "result_type": "numeric",
            "unit": "%",
            "lower_limit": "98",
            "upper_limit": "102",
            "lower_inclusive": True,
            "upper_inclusive": True,
            "reporting_decimals": 1,
            "expected_text": "",
            "replicates": 1,
            "replicate_limits": True,
            "max_retests": 0,
            "method": {
                "code": "hplc-calc",
                "version": 1,
                "requires_batch": False,
                "qc_checks": [],
                "calculation": revision.calculation(),
                "file_import": {**revision.file_import, "columns": [{"field": "x", "column": "X"}]},
            },
        },
        "catalog:x@v1",
    )
    with pytest.raises(ValidationError, match="file import is invalid"):
        parse_requirement(payload)


# Pages -----------------------------------------------------------------------------------------


def test_pages_set_show_and_clear_the_file_import(client, people):
    revision = calculated(people["author"], code="web-file")
    client.force_login(people["author"])
    detail_url = reverse("catalog:method", args=[revision.method_id])
    detail = client.get(detail_url).content.decode()
    assert "No file import" in detail
    setter = reverse("catalog:file_import_set", args=[revision.pk])
    assert setter in detail
    page = client.get(setter).content.decode()
    assert "Column for Sample peak area (peak_area, peak area)" in page
    body = {
        **EXPORT,
        "column_peak_area": "Area",
        "column_standard_area": "",
        "column_standard_mass": "",
        "column_sample_mass": "",
        "reason": "Export",
    }
    blank = {**body, "column_peak_area": ""}
    assert "at least one input" in client.post(setter, blank).content.decode()
    assert client.post(setter, {**body, "filter_value": ""}).status_code == 422
    assert client.post(setter, body).status_code == 302
    detail = client.get(detail_url).content.decode()
    assert "Synthetic HPLC data system result table" in detail
    assert "Entered by the analyst for each row" in detail and "Area" in detail
    # The form opens with the saved mapping.
    assert 'value="Sample Name"' in client.get(setter).content.decode()
    clear = reverse("catalog:file_import_clear", args=[revision.pk])
    revision.refresh_from_db()
    response = client.post(clear, {"expected_revision": revision.revision, "reason": "Typed"})
    assert response.status_code == 302
    assert MethodRevision.objects.get(pk=revision.pk).file_import is None
    approved = approve(revision, people["approver"])
    response = client.get(reverse("catalog:file_import_set", args=[approved.pk]))
    assert response.status_code == 302  # only a draft takes a file import
    client.force_login(people["analyst"])
    assert client.get(setter).status_code == 403
