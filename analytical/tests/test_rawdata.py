import hashlib
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from analytical import gates, rawdata, services
from analytical.models import RawDataFile
from core.models import AuditEvent
from quality.models import Lot

from .conftest import PIN, fresh, login, record, submit

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("plain_static")]

PAYLOAD = b"\x00\x01instrument export\r\n<script>alert(1)</script>\xff"


def upload(content=PAYLOAD, name="run1.csv", content_type="text/html"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def attach(people, test, content=PAYLOAD, name="run1.csv", who="analyst", description="Export"):
    return rawdata.attach_raw_file(
        actor=people[who], test=test, upload=upload(content, name), description=description
    )


def stored_count():
    return RawDataFile.objects.count()


def test_attach_stores_unchanged_bytes_and_audits(people, assigned):
    lot, _, tests = assigned
    test = tests["assay"]
    test_rev, lot_rev = fresh(test).revision, fresh(lot).revision
    stored = attach(people, test)
    assert bytes(stored.content) == PAYLOAD
    assert (stored.size, stored.sha256) == (len(PAYLOAD), hashlib.sha256(PAYLOAD).hexdigest())
    assert stored.content_type == "text/html"  # informational only
    assert stored.uploaded_by == people["analyst"]
    assert fresh(test).revision == test_rev + 1 and fresh(lot).revision == lot_rev + 1
    event = AuditEvent.objects.get(action="rawdata.attached")
    assert (event.actor, event.object_type, event.object_id) == (
        people["analyst"],
        "analytical.analyticaltest",
        str(test.pk),
    )
    assert event.after == {
        "file": stored.pk,
        "filename": "run1.csv",
        "size": len(PAYLOAD),
        "sha256": stored.sha256,
        "description": "Export",
    }


@pytest.mark.parametrize("who", ["reviewer", "quality", "auditor", "multi_no_analyst"])
def test_only_analysts_attach(people, assigned, who):
    if who == "multi_no_analyst":
        people[who] = people["quality2"]
    with pytest.raises(PermissionDenied):
        attach(people, assigned[2]["assay"], who=who)
    assert stored_count() == 0 and not AuditEvent.objects.filter(action="rawdata.attached")


def test_closed_test_and_released_lot_refuse(people, assigned):
    lot, _, tests = assigned
    record(people, tests["identity"], "1.004")
    submit(people, tests["identity"])
    before = fresh(tests["identity"]).revision
    with pytest.raises(ValidationError, match="not accepting raw data"):
        attach(people, tests["identity"])
    assert fresh(tests["identity"]).revision == before
    Lot.objects.filter(pk=lot.pk).update(state="rejected")
    with pytest.raises(ValidationError, match="no longer in quarantine"):
        attach(people, tests["assay"])
    assert stored_count() == 0


def test_empty_oversize_twenty_first_and_duplicate_refused(people, assigned, settings):
    test = assigned[2]["assay"]
    with pytest.raises(ValidationError, match="empty"):
        attach(people, test, content=b"")
    settings.RAW_DATA_MAX_BYTES = 100
    with pytest.raises(ValidationError, match="larger than the limit"):
        attach(people, test, content=b"x" * 101)
    assert stored_count() == 0
    attach(people, test, content=b"x" * 100)  # exactly at the limit
    settings.RAW_DATA_MAX_BYTES = 10 * 1024 * 1024
    with pytest.raises(ValidationError, match="already attached"):
        attach(people, test, content=b"x" * 100, name="other.csv")
    for n in range(19):
        attach(people, test, content=f"file {n}".encode())
    assert stored_count() == 20
    revision = fresh(test).revision
    with pytest.raises(ValidationError, match="at most 20"):
        attach(people, test, content=b"one too many")
    assert stored_count() == 20 and fresh(test).revision == revision
    # The same content may be attached to a different test.
    attach(people, assigned[2]["identity"], content=b"x" * 100)


def test_description_is_required(people, assigned):
    with pytest.raises(ValidationError, match="Describe"):
        attach(people, assigned[2]["assay"], description="   ")
    assert stored_count() == 0


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\x.dll", "x.dll"),
        ("C:\\data\\run 1.csv", "run 1.csv"),
        ("a/b\\c/d.txt", "d.txt"),
        ("run\x00\x07\x1b[31m.csv", "run[31m.csv"),
        ("ev\u202eil.csv", "evil.csv"),
        ("  padded.csv  ", "padded.csv"),
    ],
)
def test_hostile_file_names_are_reduced_to_a_base_name(raw, clean):
    assert rawdata.clean_filename(raw) == clean


@pytest.mark.parametrize("raw", ["", "..", ".", "/", "dir/", "\\\\", "\x00\x01", "a/..\\.."])
def test_unusable_file_names_are_refused(people, assigned, raw):
    with pytest.raises(ValidationError):
        rawdata.clean_filename(raw)
    # Django's own upload classes refuse some of these names, so use a bare stand-in.
    fake = SimpleNamespace(
        name=raw, size=3, content_type="", seek=lambda n: None, read=lambda n: b"abc"
    )
    with pytest.raises(ValidationError):
        rawdata.attach_raw_file(
            actor=people["analyst"], test=assigned[2]["assay"], upload=fake, description="d"
        )
    assert stored_count() == 0


def test_very_long_file_name_is_refused(people, assigned):
    with pytest.raises(ValidationError, match="longer than 200"):
        attach(people, assigned[2]["assay"], name="a" * 201 + ".csv")
    assert stored_count() == 0
    assert attach(people, assigned[2]["assay"], name="b" * 200).filename == "b" * 200


def test_rows_are_append_only_in_the_database(people, assigned):
    stored = attach(people, assigned[2]["assay"])
    for sql in (
        "UPDATE analytical_rawdatafile SET description = 'changed' WHERE id = %s",
        "UPDATE analytical_rawdatafile SET content = '\\x00' WHERE id = %s",
        "DELETE FROM analytical_rawdatafile WHERE id = %s",
    ):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql, [stored.pk])
    with pytest.raises(DatabaseError), transaction.atomic():
        stored.description = "changed"
        stored.save()
    with pytest.raises(DatabaseError), transaction.atomic():
        RawDataFile.objects.filter(pk=stored.pk).delete()
    assert fresh(stored).description == "Export"


def test_database_refuses_empty_content_size(people, assigned):
    stored = attach(people, assigned[2]["assay"])
    with pytest.raises(DatabaseError), transaction.atomic():
        RawDataFile.objects.create(
            test=stored.test,
            filename="e",
            size=0,
            sha256="0" * 64,
            content=b"",
            description="d",
            uploaded_by=people["analyst"],
        )


def test_uploader_is_a_data_author_and_cannot_review(people, assigned):
    lot, _, tests = assigned
    test = tests["identity"]
    record(people, test, "1.004")
    attach(people, test, who="multi")
    assert people["multi"].pk in gates.data_author_ids(fresh(test))
    assert people["multi"].pk in gates.lot_author_ids(fresh(lot))
    submit(people, test)
    test = fresh(test)
    assert services.review_refusal(people["multi"], test) == "You cannot review your own test."
    with pytest.raises(ValidationError, match="own test"):
        services.review_test(
            actor=people["multi"],
            pin=PIN,
            test=test,
            expected_revision=test.revision,
            reason="Checked",
        )
    assert services.review_refusal(people["reviewer"], test) is None


# Views ---------------------------------------------------------------------------------------


def post(client, test, **extra):
    data = {"file": upload(), "description": "Instrument export", **extra}
    return client.post(reverse("analytical:raw_file_new", args=[test.pk]), data)


def test_upload_page_and_download_round_trip(client, people, assigned):
    test = assigned[2]["assay"]
    url = reverse("analytical:raw_file_new", args=[test.pk])
    login(client, people["analyst"])
    page = client.get(url)
    assert page.status_code == 200
    assert 'enctype="multipart/form-data"' in page.content.decode()
    response = post(client, test)
    assert response.status_code == 302 and response.url == reverse(
        "analytical:test_detail", args=[test.pk]
    )
    stored = RawDataFile.objects.get()
    detail = client.get(response.url).content.decode()
    assert "run1.csv" in detail and stored.sha256[:16] in detail and "Instrument export" in detail
    assert reverse("analytical:raw_file_download", args=[stored.pk]) in detail
    assert "Attach raw data" in detail
    for who in ("analyst", "reviewer", "quality", "auditor"):
        login(client, people[who])
        download = client.get(reverse("analytical:raw_file_download", args=[stored.pk]))
        assert download.status_code == 200
        assert download.content == PAYLOAD
        assert download["Content-Type"] == "application/octet-stream"
        assert download["X-Content-Type-Options"] == "nosniff"
        assert download["Content-Disposition"] == 'attachment; filename="run1.csv"'
        assert "no-store" in download["Cache-Control"]


def test_download_filename_header_is_safe(client, people, assigned):
    stored = attach(people, assigned[2]["assay"], name='we"ird\u00e9 name;.csv')
    login(client, people["auditor"])
    header = client.get(reverse("analytical:raw_file_download", args=[stored.pk]))[
        "Content-Disposition"
    ]
    assert header == 'attachment; filename="we_ird__name_.csv"'


def test_page_roles(client, people, assigned, django_user_model):
    test = assigned[2]["assay"]
    stored = attach(people, test)
    new = reverse("analytical:raw_file_new", args=[test.pk])
    download = reverse("analytical:raw_file_download", args=[stored.pk])
    nobody = django_user_model.objects.create_user("norole", password="x-synthetic-2026")
    for who in ("reviewer", "quality", "auditor"):
        login(client, people[who])
        assert client.get(new).status_code == 403
        assert post(client, test).status_code == 403
        assert (
            "Attach raw data</a>"
            not in client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
        )
    login(client, nobody)
    assert client.get(download).status_code == 403
    assert client.get(reverse("analytical:raw_file_download", args=[999999])).status_code == 403
    assert client.get(new).status_code == 403
    client.logout()
    assert client.get(download).status_code == 302
    assert stored_count() == 1


def test_upload_page_refuses_closed_test_and_shows_errors(client, people, assigned, settings):
    lot, _, tests = assigned
    login(client, people["analyst"])
    settings.RAW_DATA_MAX_BYTES = 10
    response = client.post(
        reverse("analytical:raw_file_new", args=[tests["assay"].pk]),
        {"file": upload(b"x" * 11), "description": "Too big"},
    )
    assert response.status_code == 422 and "larger than the limit" in response.content.decode()
    response = client.post(
        reverse("analytical:raw_file_new", args=[tests["assay"].pk]),
        {"file": upload(b""), "description": "Nothing"},
    )
    assert response.status_code == 422
    response = client.post(
        reverse("analytical:raw_file_new", args=[tests["assay"].pk]), {"description": "No file"}
    )
    assert response.status_code == 422
    assert stored_count() == 0
    Lot.objects.filter(pk=lot.pk).update(state="rejected")
    response = post(client, tests["assay"])
    assert response.status_code == 302 and stored_count() == 0
    assert (
        client.get(reverse("analytical:raw_file_new", args=[tests["assay"].pk])).status_code == 302
    )


def test_tampered_stored_row_refuses_download(client, people, assigned):
    stored = attach(people, assigned[2]["assay"])
    login(client, people["auditor"])
    url = reverse("analytical:raw_file_download", args=[stored.pk])
    assert client.get(url).content == PAYLOAD
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE analytical_rawdatafile DISABLE TRIGGER analytical_append_only")
        try:
            cursor.execute(
                "UPDATE analytical_rawdatafile SET content = %s WHERE id = %s",
                [b"tampered", stored.pk],
            )
        finally:
            cursor.execute(
                "ALTER TABLE analytical_rawdatafile ENABLE TRIGGER analytical_append_only"
            )
    response = client.get(url)
    assert response.status_code == 302
    assert b"tampered" not in response.content
    with pytest.raises(ValidationError, match="integrity"):
        rawdata.verified_content(fresh(stored))
