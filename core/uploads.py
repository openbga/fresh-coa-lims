"""Bound file uploads: refuse an oversized request unread, and stop a file while it arrives."""

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.shortcuts import render

# Room in an upload request for everything that is not file content: the form's other fields
# and the multipart framing around them.
FORM_ALLOWANCE = 1024 * 1024


def size_text(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / (1024 * 1024):.1f} MiB"


def stored_bytes():
    """Bytes of every file the deployment stores: raw data of tests and evidence of rehearsals.
    ``RAW_DATA_TOTAL_MAX_BYTES`` is one ceiling for all of them."""
    from django.apps import apps
    from django.db.models import Sum

    return sum(
        apps.get_model(label).objects.aggregate(total=Sum("size"))["total"] or 0
        for label in ("analytical.RawDataFile", "validation.RehearsalFile")
    )


# Advisory lock that serializes the ceiling check of every upload (any constant unique to it).
CEILING_LOCK = 681_241


def refuse_over_ceiling(size):
    """Refuse a file that would take the stored files past ``RAW_DATA_TOTAL_MAX_BYTES``.

    Called inside the upload's transaction after its own row locks; the advisory lock makes
    two uploads check and insert one after the other, whichever table they write to."""
    from django.conf import settings
    from django.core.exceptions import ValidationError
    from django.db import connection

    ceiling = getattr(settings, "RAW_DATA_TOTAL_MAX_BYTES", 0)
    if not ceiling:
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CEILING_LOCK])
    if stored_bytes() + size > ceiling:
        raise ValidationError(
            "This deployment has reached its storage limit for files. The file was not stored."
        )


def request_limit():
    """Largest body, in bytes, of a request that carries files."""
    return settings.RAW_DATA_MAX_BYTES + FORM_ALLOWANCE


class UploadSizeMiddleware:
    """Refuse a file upload by the size it declares, before any of its body is read.

    The CSRF check is the first code that reads a submitted form, so this is listed ahead of
    ``CsrfViewMiddleware``. A multipart request that declares more than ``request_limit()``
    bytes is answered with status 413 and its body is left unread; the server then closes the
    connection instead of receiving the rest. Django never reads past the declared length, so
    a request cannot carry more than it declares.

    Only multipart requests can carry files. Django refuses other oversized bodies itself,
    also unread, through ``DATA_UPLOAD_MAX_MEMORY_SIZE``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.content_type != "multipart/form-data":
            return None
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return None  # Django reads nothing of a request without a usable length
        if declared <= request_limit():
            return None
        return render(
            request, "413.html", {"limit": size_text(settings.RAW_DATA_MAX_BYTES)}, status=413
        )


class BoundedUploadHandler(FileUploadHandler):
    """Stop receiving a request's files once they exceed the raw-data size limit.

    Django otherwise writes an upload of any size to a temporary file before a view can refuse
    it. This handler runs first. When the files of one request add up to more than
    ``settings.RAW_DATA_MAX_BYTES`` it stops the upload and sets ``request.upload_too_large``,
    so the view can say why no file arrived. Django then discards the rest of the request
    body, which ``UploadSizeMiddleware`` has already limited to ``FORM_ALLOWANCE`` bytes.
    """

    def __init__(self, request=None):
        super().__init__(request)
        self.received = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > settings.RAW_DATA_MAX_BYTES:
            if self.request is not None:
                self.request.upload_too_large = True
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        return None  # the next handler builds the uploaded file
