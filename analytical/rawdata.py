"""Raw-data files attached to a test: service, form and views.

A file is untrusted data. It is never parsed, rendered or executed: the bytes are stored as
received with their SHA-256 checksum, and a download re-verifies that checksum and returns the
bytes as an opaque attachment.
"""

import hashlib
import unicodedata

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.audit import record_event
from core.forms import StyledForm
from core.services import require_role
from core.uploads import size_text

from .models import AnalyticalTest, RawDataFile
from .services import ANALYST, _bump, _lock_lots, _touch

READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
MAX_FILES = 20
FILENAME_LENGTH = RawDataFile._meta.get_field("filename").max_length
DESCRIPTION_LENGTH = RawDataFile._meta.get_field("description").max_length


def max_bytes():
    return getattr(settings, "RAW_DATA_MAX_BYTES", DEFAULT_MAX_BYTES)


def clean_filename(name):
    """Base name of a client file name: control characters dropped, both separators handled."""
    name = "".join(c for c in (name or "") if not unicodedata.category(c).startswith("C"))
    name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if name in ("", ".", ".."):
        raise ValidationError("The file name is empty after removing the folder and any controls.")
    if len(name) > FILENAME_LENGTH:
        raise ValidationError(f"The file name is longer than {FILENAME_LENGTH} characters.")
    return name


def attach_raw_file(*, actor, test, upload, description):
    """Store an uploaded file against an open test, unchanged, with its checksum."""
    require_role(actor, ANALYST)
    description = (description or "").strip()
    if not description:
        raise ValidationError("Describe what the file is.")
    if len(description) > DESCRIPTION_LENGTH:
        raise ValidationError(f"The description is longer than {DESCRIPTION_LENGTH} characters.")
    filename = clean_filename(getattr(upload, "name", ""))
    limit = max_bytes()
    if upload.size > limit:
        raise ValidationError(f"The file is larger than the limit of {size_text(limit)}.")
    upload.seek(0)
    content = upload.read(limit + 1)
    if len(content) > limit:
        raise ValidationError(f"The file is larger than the limit of {size_text(limit)}.")
    if not content:
        raise ValidationError("The file is empty.")
    digest = hashlib.sha256(content).hexdigest()
    with transaction.atomic():
        test = AnalyticalTest.objects.select_for_update().get(pk=test.pk)
        (lot,) = _lock_lots(test.lot_id)
        if test.state != AnalyticalTest.State.OPEN:
            raise ValidationError("This test is not accepting raw data.")
        existing = RawDataFile.objects.filter(test=test)
        if existing.count() >= MAX_FILES:
            raise ValidationError(f"A test holds at most {MAX_FILES} raw-data files.")
        if existing.filter(sha256=digest).exists():
            raise ValidationError("This file content is already attached to this test.")
        ceiling = getattr(settings, "RAW_DATA_TOTAL_MAX_BYTES", 0)
        if ceiling:
            used = RawDataFile.objects.aggregate(total=Sum("size"))["total"] or 0
            if used + len(content) > ceiling:
                raise ValidationError(
                    "This deployment has reached its storage limit for raw-data files. "
                    "The file was not stored."
                )
        stored = RawDataFile.objects.create(
            test=test,
            filename=filename,
            content_type=(getattr(upload, "content_type", "") or "")[:100],
            size=len(content),
            sha256=digest,
            content=content,
            description=description,
            uploaded_by=actor,
        )
        _touch(test)
        _bump(lot)
        record_event(
            actor=actor,
            action="rawdata.attached",
            obj=test,
            after={
                "file": stored.pk,
                "filename": filename,
                "size": stored.size,
                "sha256": digest,
                "description": description,
            },
            reason=description,
        )
        return stored


def verified_content(stored):
    """The stored bytes, or a refusal when they no longer match the recorded checksum."""
    data = bytes(stored.content)
    if hashlib.sha256(data).hexdigest() != stored.sha256 or len(data) != stored.size:
        raise ValidationError("The stored file failed its integrity check.")
    return data


class RawFileForm(StyledForm):
    file = forms.FileField(
        label="File",
        help_text=(
            "Kept exactly as received and never opened by the system. "
            "Large files and duplicates of a file already attached are refused."
        ),
    )
    description = forms.CharField(
        label="What the file is",
        max_length=DESCRIPTION_LENGTH,
        help_text="For example: instrument export for replicate 1, or notebook page 12.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # static/js/app.js refuses a larger file in the browser, so it is never sent.
        self.fields["file"].widget.attrs.update(
            {"data-vr-max-bytes": max_bytes(), "data-vr-max-label": size_text(max_bytes())}
        )


def _crumbs(test):
    return [
        ("Testing", reverse("analytical:test_list")),
        (test.lot.number, reverse("analytical:lot_testing", args=[test.lot_id])),
        (test.label, reverse("analytical:test_detail", args=[test.pk])),
        ("Attach raw data", None),
    ]


@login_required
@require_http_methods(["GET", "POST"])
def raw_file_new(request, pk):
    require_role(request.user, ANALYST)
    test = get_object_or_404(AnalyticalTest.objects.select_related("lot", "sample"), pk=pk)
    back = reverse("analytical:test_detail", args=[test.pk])
    if test.state != AnalyticalTest.State.OPEN or test.lot.state != "quarantine":
        messages.warning(request, "This test is not accepting raw data.")
        return redirect(back)
    # A request far above the size limit never reaches this view (core.uploads refuses it
    # unread). Reading request.FILES receives the upload; BoundedUploadHandler stops a file
    # that is over the limit while it arrives and marks the request.
    if (
        request.method == "POST"
        and request.FILES is not None
        and getattr(request, "upload_too_large", False)
    ):
        messages.error(
            request,
            f"The file is larger than the limit of {size_text(max_bytes())}. Nothing was stored.",
        )
        return redirect("analytical:raw_file_new", pk=test.pk)
    form = RawFileForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            attach_raw_file(
                actor=request.user,
                test=test,
                upload=form.cleaned_data["file"],
                description=form.cleaned_data["description"],
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, "Raw data attached.")
            return redirect(back)
    return render(
        request,
        "analytical/raw_file_form.html",
        {
            "page_title": f"Attach raw data · {test.label}",
            "form": form,
            "submit_label": "Attach file",
            "crumbs": _crumbs(test),
            "cancel_url": back,
            "summary": [
                ("Test", f"{test.label} ({test.test_code})"),
                ("Lot and sample", f"{test.lot.number} / {test.sample.reference}"),
                ("Record revision", test.revision),
                ("Size limit", size_text(max_bytes())),
            ],
        },
        status=422 if request.method == "POST" else 200,
    )


@login_required
@require_http_methods(["GET"])
def raw_file_download(request, pk):
    require_role(request.user, *READ_ROLES)  # before the lookup: refusal must not reveal existence
    stored = get_object_or_404(RawDataFile.objects.select_related("test"), pk=pk)
    try:
        data = verified_content(stored)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("analytical:test_detail", pk=stored.test_id)
    name = "".join(
        c if c.isascii() and (c.isalnum() or c in "._-") else "_" for c in stored.filename
    )
    response = HttpResponse(data, content_type="application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response
