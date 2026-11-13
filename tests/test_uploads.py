"""Uploads are bounded before they are read and while they are received."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from core.uploads import FORM_ALLOWANCE, UploadSizeMiddleware, request_limit


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


class Unreadable:
    """A request body that must stay unread."""

    def read(self, *args, **kwargs):
        raise AssertionError("The request body was read.")

    readline = read


def declared(size, content_type="multipart/form-data; boundary=synthetic"):
    """WSGI environment of a POST that declares ``size`` bytes of a body nobody may read."""
    return {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": reverse("analytical:raw_file_new", args=[1]),
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(size),
        "wsgi.input": Unreadable(),
    }


@pytest.fixture
def visitor(db):
    """A browser that only opened the sign-in page: it holds a CSRF cookie and no account."""
    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("login")).status_code == 200
    assert "csrftoken" in client.cookies
    return client


@override_settings(RAW_DATA_MAX_BYTES=1024)
def test_an_upload_that_declares_too_much_is_refused_before_its_body_is_read(visitor):
    response = visitor.request(**declared(request_limit() + 1))
    assert response.status_code == 413
    body = response.content.decode()
    assert "Upload too large" in body
    assert "A file can be up to 1.0 KiB." in body
    assert "Content-Security-Policy" in response.headers


@override_settings(RAW_DATA_MAX_BYTES=1024)
def test_an_upload_within_the_request_limit_is_read_by_the_csrf_check(visitor):
    # The control for the test above: the same request at the limit goes on to be read.
    with pytest.raises(AssertionError, match="The request body was read."):
        visitor.request(**declared(request_limit()))


@override_settings(RAW_DATA_MAX_BYTES=1024)
def test_the_request_limit_is_the_file_limit_plus_room_for_the_form():
    assert request_limit() == 1024 + FORM_ALLOWANCE


@pytest.mark.parametrize(
    ("size", "content_type"),
    [
        (10**12, "application/x-www-form-urlencoded"),
        (10**12, "application/json"),
        ("", "multipart/form-data; boundary=synthetic"),
        ("many", "multipart/form-data; boundary=synthetic"),
    ],
    ids=["form-encoded", "json", "no-length", "unusable-length"],
)
def test_requests_that_cannot_carry_files_are_left_to_django(size, content_type):
    request = RequestFactory().request(**declared(size, content_type))
    assert UploadSizeMiddleware(None).process_view(request, None, (), {}) is None


@pytest.mark.parametrize(
    ("size", "content_type", "status"),
    [
        (10**12, "application/x-www-form-urlencoded", 400),  # DATA_UPLOAD_MAX_MEMORY_SIZE
        (10**12, "application/json", 403),  # never parsed, so it carries no CSRF token
        ("", "multipart/form-data; boundary=synthetic", 403),  # no length: nothing to read
    ],
    ids=["form-encoded", "json", "no-length"],
)
def test_django_answers_those_requests_without_reading_them(visitor, size, content_type, status):
    assert visitor.request(**declared(size, content_type)).status_code == status
