"""Checks of issued certificates: was this file issued by the laboratory, and is it current?

A check compares the SHA-256 of what it is given with the checksums stored with every issued
version: the PDF's (``pdf_sha256``) and the certificate data's (``data_sha256``). Nothing else
finds a certificate, so whoever checks must hold the exact file, or its checksum, and the answer
tells them nothing they could not read in the file apart from its status: current, replaced by
a later version, or withdrawn. A file is never stored, opened or interpreted: its bytes are
hashed while they arrive (``HashingUploadHandler``) and dropped.

A check that finds a version is kept as an append-only ``CertificateCheck``, its answer read
from the certificate head under a lock (the database refuses any other answer), so a check made
while an amendment or a withdrawal is signed answers as of one side of it. A check that finds
nothing names no certificate and is not kept. Checks without an account are kept once a day for
each version and answer: whoever holds one file could otherwise add rows that can never be
removed to the certificate and to its lot's exported record, all day long.

Checks made without an account (``settings.CERTIFICATE_CHECK``) are bounded for the whole
deployment by ``settings.CERTIFICATE_CHECK_RATE`` a minute (``take_slot``), counted before the
request body is read. The deployment's address is all a recipient needs; the certificate prints
nothing new for it.
"""

import hashlib
import io
import math
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import UploadedFile
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import CertificateCheck, CheckWindow, Report, ReportVersion

WINDOW = timedelta(minutes=1)
# One SHA-256 in hexadecimal, alone or as the first word of a checksum tool's line.
DIGEST = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
NOT_OFFERED = "This laboratory does not offer certificate checks without an account."


def max_bytes():
    """Largest file a check receives: the deployment's upload limit (RAW_DATA_MAX_BYTES)."""
    from analytical.rawdata import max_bytes as upload_limit

    return upload_limit()


def parse_digest(text):
    """The SHA-256 in what was typed or pasted, in lower case, or None.

    Accepts the 64 hexadecimal characters in any case, with spaces or colons between groups, or
    a checksum tool's line that adds the file name ("<sha256>  certificate.pdf"). Anything that
    holds no SHA-256, or more than one, is refused."""
    compact = re.sub(r"[\s:]", "", text or "").lower()
    if re.fullmatch(r"[0-9a-f]{64}", compact):
        return compact
    found = DIGEST.findall((text or "").lower())
    return found[0] if len(found) == 1 else None


class CheckedFile(UploadedFile):
    """What a check keeps of a file it received: the size and the SHA-256, not the bytes."""

    def __init__(self, name, size, sha256):
        super().__init__(file=io.BytesIO(), name=name, size=size)
        self.sha256 = sha256


class HashingUploadHandler(FileUploadHandler):
    """Hash each file of the request as it arrives and keep none of its bytes.

    Installed by the check views in place of the deployment's handlers, before anything reads the
    request body. Past ``limit`` bytes in all the request's files it stops the upload and marks
    the request (``upload_too_large``), like ``core.uploads.BoundedUploadHandler``; the request
    was already refused unread when it declared more (``core.uploads.UploadSizeMiddleware``)."""

    def __init__(self, request=None, limit=None):
        super().__init__(request)
        self.limit = max_bytes() if limit is None else limit
        self.received = 0

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.digest = hashlib.sha256()
        self.size = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > self.limit:
            if self.request is not None:
                self.request.upload_too_large = True
            raise StopUpload(connection_reset=False)
        self.size += len(raw_data)
        self.digest.update(raw_data)
        return None  # no later handler receives the bytes

    def file_complete(self, file_size):
        return CheckedFile(self.file_name, self.size, self.digest.hexdigest())


def digest_of(upload):
    """SHA-256 of an uploaded file: computed while it arrived, or read now in chunks."""
    if isinstance(upload, CheckedFile):
        return upload.sha256
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Result:
    """What a check found. ``version`` is None when nothing matched; otherwise ``report`` is its
    certificate as read under the lock, ``matched`` says which file matched, ``answer`` is a
    ``CertificateCheck.Answer`` value and ``latest`` the certificate's last issued version."""

    version: ReportVersion | None = None
    report: Report | None = None
    matched: str = ""
    answer: str = ""
    latest: ReportVersion | None = None

    @property
    def found(self):
        return self.version is not None

    @property
    def current(self):
        return self.answer == CertificateCheck.Answer.CURRENT

    @property
    def superseded(self):
        return self.answer == CertificateCheck.Answer.SUPERSEDED

    @property
    def withdrawn(self):
        return self.answer == CertificateCheck.Answer.WITHDRAWN

    @property
    def matched_data(self):
        return self.matched == CertificateCheck.Matched.DATA


def answer_for(report, version):
    """Withdrawn for every version of a withdrawn certificate, superseded for a version a later
    one replaced, current otherwise (the rule the database guard of the checks repeats)."""
    if report.state == "withdrawn":
        return CertificateCheck.Answer.WITHDRAWN
    if version.number < report.version_count:
        return CertificateCheck.Answer.SUPERSEDED
    return CertificateCheck.Answer.CURRENT


def _versions():
    # The stored bytes are never needed to answer a check.
    return ReportVersion.objects.defer("pdf", "data", "snapshot")


def check(digest, *, actor=None):
    """Find the issued version whose PDF or certificate data has this SHA-256 and keep the check.

    ``actor`` is the signed-in person who checks, who must be able to read certificates, or None
    for a recipient without an account, which only a deployment offering the check accepts."""
    from .services import require_reader

    if actor is None:
        if not settings.CERTIFICATE_CHECK:
            raise PermissionDenied(NOT_OFFERED)
    else:
        require_reader(actor)
    if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
        return Result()
    version = (
        _versions().filter(Q(pdf_sha256=digest) | Q(data_sha256=digest)).order_by("pk").first()
    )
    if version is None:
        return Result()
    matched = (
        CertificateCheck.Matched.PDF
        if version.pdf_sha256 == digest
        else CertificateCheck.Matched.DATA
    )
    with transaction.atomic():
        # An amendment or a withdrawal locks the head while it is signed: the answer is read
        # after it, and the check is kept with that answer.
        report = (
            Report.objects.select_for_update(no_key=True, of=("self",))
            .select_related("lot")
            .get(pk=version.report_id)
        )
        version.report = report
        answer = answer_for(report, version)
        latest = (
            version
            if version.number == report.version_count
            else _versions().get(report=report, number=report.version_count)
        )
        now = timezone.now()
        if actor is not None or not _kept_today(version, answer, now):
            CertificateCheck.objects.create(
                version=version, checked_at=now, checked_by=actor, matched=matched, answer=answer
            )
    return Result(version=version, report=report, matched=matched, answer=answer, latest=latest)


def _kept_today(version, answer, now):
    """A check without an account of this version, with this answer, is already kept today (the
    laboratory's day). Read under the certificate's lock, so two such checks cannot both pass."""
    day = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return CertificateCheck.objects.filter(
        version=version, checked_by__isnull=True, answer=answer, checked_at__gte=day
    ).exists()


def take_slot(now=None):
    """Count one check without an account in the deployment's current minute.

    Returns 0 when the check may proceed, otherwise the whole seconds until the minute ends. Runs
    in its own transaction, before the request body is read, so a refused request costs a row
    lock and nothing else. The time is read once the row is locked, so a request that waited for
    the lock does not start the window again; a window more than a minute ahead of this clock
    (a server's clock set back) starts again too."""
    with transaction.atomic():
        # The row exists from the first check on; a demonstration reset empties the table.
        CheckWindow.objects.bulk_create(
            [CheckWindow(id=1, started_at=now or timezone.now(), count=0)], ignore_conflicts=True
        )
        window = CheckWindow.objects.select_for_update().get(id=1)
        now = now or timezone.now()
        if not window.started_at - WINDOW <= now < window.started_at + WINDOW:
            window.started_at, window.count = now, 0
        if window.count >= settings.CERTIFICATE_CHECK_RATE:
            left = (window.started_at + WINDOW - now).total_seconds()
            return min(int(WINDOW.total_seconds()), max(1, math.ceil(left)))
        window.count += 1
        window.save(update_fields=["started_at", "count"])
    return 0
