"""Uploads are bounded while they are received, before any view sees them."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings


def post(*files, **fields):
    data = {f"file{index}": upload for index, upload in enumerate(files)} | fields
    return RequestFactory().post("/upload/", data)


@override_settings(RAW_DATA_MAX_BYTES=1024)
def test_a_file_within_the_limit_is_received_unchanged():
    request = post(SimpleUploadedFile("export.csv", b"a" * 1024), description="Synthetic export")
    assert request.FILES["file0"].read() == b"a" * 1024
    assert request.POST["description"] == "Synthetic export"
    assert not getattr(request, "upload_too_large", False)


@override_settings(RAW_DATA_MAX_BYTES=1024)
def test_a_file_over_the_limit_is_dropped_and_the_request_is_marked():
    request = post(SimpleUploadedFile("export.csv", b"a" * 1025))
    assert "file0" not in request.FILES
    assert request.upload_too_large is True


@override_settings(RAW_DATA_MAX_BYTES=1024, FILE_UPLOAD_MAX_MEMORY_SIZE=16)
def test_the_limit_also_bounds_files_written_to_temporary_storage():
    request = post(SimpleUploadedFile("export.csv", b"a" * 4096))
    assert "file0" not in request.FILES
    assert request.upload_too_large is True


@override_settings(RAW_DATA_MAX_BYTES=1024)
def test_the_limit_applies_to_all_files_of_one_request_together():
    request = post(
        SimpleUploadedFile("one.csv", b"a" * 800), SimpleUploadedFile("two.csv", b"b" * 800)
    )
    assert "file1" not in request.FILES
    assert request.upload_too_large is True
