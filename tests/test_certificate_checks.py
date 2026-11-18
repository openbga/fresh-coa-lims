"""Checks of issued certificates: genuine and current, replaced or withdrawn.

A check compares the SHA-256 of a file, or one entered, with the checksums of every issued
version's PDF and certificate data. Staff check on a signed-in page; a recipient checks without an
account only where the deployment offers it (CERTIFICATE_CHECK), bounded for the whole
deployment per minute (CERTIFICATE_CHECK_RATE) before the request body is read. A file is hashed
while it arrives and never stored. A check that finds a version is kept, append-only, with the
answer the certificate gives under its lock; a check that finds nothing names nothing and is not
kept. The answer discloses only what the certificate prints and its status.

Uses a lot released through the production services (synthetic data).
"""

import hashlib
import io
import json
import threading
import zipfile
from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, connections, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from reporting import checks, lot_record, services
from reporting.forms import CheckForm
from reporting.models import CertificateCheck, CheckWindow, Report
from tests.test_customer_certificates import TIGHT, issue, released
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_result_types_journey import build_world

pytestmark = pytest.mark.django_db(transaction=True)

RECIPIENT = "Synthetic checked recipient"


@pytest.fixture
def world(django_user_model):
    return build_world(django_user_model, with_assay=True)


@pytest.fixture
def report(world):
    return issue(world, released(world, TIGHT), recipient=RECIPIENT)


@pytest.fixture
def staff(client, world):
    assert client.login(username="rt_reviewer", password=PASSWORD)
    return client


@pytest.fixture
def offered(settings):
    settings.CERTIFICATE_CHECK = True
    return settings


def pdf_of(version):
    return SimpleUploadedFile("certificate.pdf", bytes(version.pdf), "application/pdf")


def amend(world, report):
    _, digest, _ = services.preview(report.lot)
    services.amend_report(
        actor=world["people"]["author"],
        pin=PIN,
        report=Report.objects.get(pk=report.pk),
        expected_version=1,
        evidence_hash=digest,
        reason="Synthetic corrected address",
    )


def withdraw(world, report):
    report = Report.objects.get(pk=report.pk)
    services.withdraw_report(
        actor=world["people"]["approver"],
        pin=PIN,
        report=report,
        expected_revision=report.revision,
        reason="Synthetic withdrawal after an impact assessment",
        reference="IA-9",
    )


def page(response):
    return " ".join(response.content.decode().split())


# What a check accepts ---------------------------------------------------------------------------


def test_a_sha256_is_read_as_typed_pasted_or_from_a_checksum_tool():
    digest = hashlib.sha256(b"synthetic").hexdigest()
    spaced = " ".join(digest[i : i + 8] for i in range(0, 64, 8))
    assert checks.parse_digest(digest.upper()) == digest
    assert checks.parse_digest(spaced) == digest
    assert checks.parse_digest(":".join(digest[i : i + 2] for i in range(0, 64, 2))) == digest
    assert checks.parse_digest(f"{digest}  SYN-CERT-1-v1.pdf\n") == digest
    for refused in ("", digest[:63], digest + "0", f"{digest} {digest[::-1]}", "z" * 64):
        assert checks.parse_digest(refused) is None, refused


def test_the_form_takes_the_file_or_its_sha256_and_not_both():
    digest = hashlib.sha256(b"synthetic").hexdigest()
    upload = SimpleUploadedFile("c.pdf", b"%PDF-synthetic")
    both = CheckForm({"sha256": digest}, {"file": upload})
    assert not both.is_valid()
    assert both.non_field_errors() == ["Give the file or its SHA-256, not both."]
    neither = CheckForm({"sha256": "  "}, {})
    assert neither.non_field_errors() == ["Choose the certificate file, or enter its SHA-256."]
    wrong = CheckForm({"sha256": "abc"}, {})
    assert wrong.errors["sha256"] == ["A SHA-256 is 64 characters, 0-9 and a-f."]
    by_file = CheckForm({}, {"file": SimpleUploadedFile("c.pdf", b"%PDF-synthetic")})
    assert by_file.is_valid()
    assert by_file.cleaned_data["digest"] == hashlib.sha256(b"%PDF-synthetic").hexdigest()


def test_a_file_is_hashed_as_it_arrives_and_none_of_it_is_kept():
    handler = checks.HashingUploadHandler(limit=10)
    handler.new_file("file", "c.pdf", "application/pdf", 8)
    assert handler.receive_data_chunk(b"%PDF", 0) is None  # no later handler receives the bytes
    assert handler.receive_data_chunk(b"-1.7", 4) is None
    received = handler.file_complete(8)
    assert received.sha256 == hashlib.sha256(b"%PDF-1.7").hexdigest()
    assert received.size == 8
    assert received.read() == b""
    with pytest.raises(checks.StopUpload):
        handler.receive_data_chunk(b"more", 8)  # past the limit


# Signed-in checks -------------------------------------------------------------------------------


def test_the_file_as_issued_is_genuine_and_current_and_the_check_is_kept(staff, world, report):
    version = report.versions.get()
    response = staff.post(reverse("reporting:check"), {"file": pdf_of(version)})
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store, private"
    text = page(response)
    assert "Genuine and current" in text
    assert f"This file is certificate {report.number}, version 1" in text
    assert RECIPIENT in text  # staff see the recipient
    assert reverse("reporting:version", args=[report.pk, 1]) in text
    check = version.checks.get()
    assert (check.checked_by, check.matched, check.answer) == (
        world["people"]["reviewer"],
        "pdf",
        "current",
    )


def test_the_certificate_data_file_is_found_too(staff, report):
    version = report.versions.get()
    data = SimpleUploadedFile("certificate-data.json", bytes(version.data), "application/json")
    text = page(staff.post(reverse("reporting:check"), {"file": data}))
    assert f"This file is the certificate data of certificate {report.number}" in text
    assert "Certificate data (JSON)" in text
    assert version.checks.get().matched == "data"
    # The checksum alone finds it as well.
    staff.post(reverse("reporting:check"), {"sha256": version.data_sha256.upper()})
    assert version.checks.count() == 2


def test_a_changed_file_is_not_found_and_nothing_is_kept(staff, report):
    version = report.versions.get()
    changed = SimpleUploadedFile("certificate.pdf", bytes(version.pdf) + b"\n")
    response = staff.post(reverse("reporting:check"), {"file": changed})
    assert response.status_code == 200
    text = page(response)
    assert "Not found" in text
    assert "No certificate issued by this laboratory matches this file." in text
    assert report.number not in text
    assert not CertificateCheck.objects.exists()


def test_a_replaced_version_names_the_version_that_replaces_it(staff, world, report):
    amend(world, report)
    first, second = report.versions.order_by("number")
    text = page(staff.post(reverse("reporting:check"), {"file": pdf_of(first)}))
    assert "Replaced" in text
    assert "Version 2, issued on" in text
    assert "Send the recipient the current version." in text
    assert "1 of 2" in text
    current = page(staff.post(reverse("reporting:check"), {"sha256": second.pdf_sha256}))
    assert "Genuine and current" in current
    assert [c.answer for c in CertificateCheck.objects.order_by("id")] == ["superseded", "current"]


def test_a_withdrawn_certificate_answers_withdrawn_for_every_version(staff, world, report):
    amend(world, report)
    withdraw(world, report)
    for version in report.versions.order_by("number"):
        text = page(staff.post(reverse("reporting:check"), {"sha256": version.pdf_sha256}))
        assert "Withdrawn" in text
        assert "The laboratory withdrew this certificate on" in text
    assert set(CertificateCheck.objects.values_list("answer", flat=True)) == {"withdrawn"}
    # The certificate page lists the checks; staff checking it is not a recipient holding it.
    url = reverse("reporting:detail", args=[report.pk])
    detail = page(staff.get(url))
    assert "Synthetic Reviewer" in detail
    assert 'id="checks-heading">Checks</h2><span class="vr-count">2</span>' in detail
    assert "Checked since withdrawal" not in detail


def test_a_recipient_checking_a_withdrawn_certificate_is_shown_on_it(
    client, staff, offered, world, report
):
    withdraw(world, report)
    Client().post(reverse("certificate_check"), {"sha256": report.versions.get().pdf_sha256})
    detail = page(staff.get(reverse("reporting:detail", args=[report.pk])))
    assert "Checked since withdrawal" in detail
    assert "A recipient still holds this certificate: version 1 was checked without an account" in (
        detail
    )
    assert "A recipient, without an account" in detail


def test_the_certificate_page_lists_checks_or_says_none_were_made(staff, report):
    url = reverse("reporting:detail", args=[report.pk])
    assert "Not checked yet" in page(staff.get(url))
    staff.post(reverse("reporting:check"), {"sha256": report.versions.get().pdf_sha256})
    text = page(staff.get(url))
    assert "Not checked yet" not in text
    assert "Checked since withdrawal" not in text
    assert "Certificate PDF" in text


def test_without_a_reading_role_the_check_is_refused_and_nothing_is_kept(
    client, django_user_model, report
):
    page_url = reverse("reporting:check")
    signed_out = client.post(page_url, {"sha256": report.versions.get().pdf_sha256})
    assert signed_out.status_code == 302
    assert signed_out["Location"].startswith(reverse("login"))
    nobody = django_user_model.objects.create_user(username="rt_noroles", password=PASSWORD)
    assert client.login(username="rt_noroles", password=PASSWORD)
    assert client.get(page_url).status_code == 403
    assert client.post(page_url, {"sha256": report.versions.get().pdf_sha256}).status_code == 403
    with pytest.raises(PermissionDenied):
        checks.check(report.versions.get().pdf_sha256, actor=nobody)
    assert not CertificateCheck.objects.exists()


def test_a_file_over_the_upload_limit_is_stopped_and_not_checked(staff, report, settings):
    settings.RAW_DATA_MAX_BYTES = 1000
    big = SimpleUploadedFile("certificate.pdf", b"%PDF-" + b"0" * 4000)
    response = staff.post(reverse("reporting:check"), {"file": big})
    assert response.status_code == 422
    assert "The file is larger than the limit of 1000 B." in page(response)
    assert not CertificateCheck.objects.exists()


def test_the_signed_in_page_names_the_address_recipients_use_when_it_is_offered(staff, settings):
    url = reverse("reporting:check")
    assert "without an account at" not in page(staff.get(url))
    settings.CERTIFICATE_CHECK = True
    text = page(staff.get(url))
    assert "Recipients can make the same check without an account at" in text
    assert ">http://testserver/check/</span>" in text


def test_the_certificate_list_opens_the_check(staff):
    text = page(staff.get(reverse("reporting:list")))
    assert f'href="{reverse("reporting:check")}"' in text
    assert "Check a certificate" in text


# Checks without an account ----------------------------------------------------------------------


def test_the_check_without_an_account_is_not_offered_by_default(client, report):
    assert client.get(reverse("certificate_check")).status_code == 404
    digest = report.versions.get().pdf_sha256
    assert client.post(reverse("certificate_check"), {"sha256": digest}).status_code == 404
    assert reverse("certificate_check") not in page(client.get(reverse("login")))
    with pytest.raises(PermissionDenied, match="does not offer"):
        checks.check(digest)
    assert not CertificateCheck.objects.exists()
    assert not CheckWindow.objects.exists()


def test_a_recipient_checks_without_an_account_and_learns_only_the_status(client, offered, report):
    version = report.versions.get()
    url = reverse("certificate_check")
    assert f'href="{url}"' in page(client.get(reverse("login")))
    form = client.get(url)
    assert form.status_code == 200
    assert form["X-Robots-Tag"] == "noindex"
    response = client.post(url, {"file": pdf_of(version)})
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    text = page(response)
    assert "Genuine and current" in text
    assert f"certificate {report.number}, version 1" in text
    assert report.lot.number in text
    # Nothing the certificate's page holds beyond what it prints: no recipient, no links in.
    assert RECIPIENT not in text
    assert "/reports/" not in text
    # No session is started and nothing about the recipient is kept.
    assert settings_cookie(response) is None
    assert not Session.objects.exists()
    check = version.checks.get()
    assert check.checked_by is None and check.without_account


def settings_cookie(response):
    from django.conf import settings

    return response.cookies.get(settings.SESSION_COOKIE_NAME)


def test_a_recipient_is_told_to_ask_for_the_current_version(client, offered, world, report):
    amend(world, report)
    first = report.versions.get(number=1)
    text = page(client.post(reverse("certificate_check"), {"sha256": first.pdf_sha256}))
    assert "Replaced" in text and "Ask the laboratory for the current version." in text
    withdraw(world, report)
    text = page(client.post(reverse("certificate_check"), {"sha256": first.pdf_sha256}))
    assert "Withdrawn" in text and "Do not rely on it; contact the laboratory." in text
    assert "Synthetic withdrawal" not in text and "IA-9" not in text  # no reason or reference


def test_the_check_without_an_account_needs_the_csrf_token(offered, report):
    browser = Client(enforce_csrf_checks=True)
    url = reverse("certificate_check")
    digest = report.versions.get().pdf_sha256
    assert browser.post(url, {"sha256": digest}).status_code == 403
    browser.get(url)
    token = browser.cookies["csrftoken"].value
    assert browser.post(url, {"sha256": digest, "csrfmiddlewaretoken": token}).status_code == 200
    assert CertificateCheck.objects.count() == 1


def test_checks_without_an_account_are_bounded_per_minute(client, staff, offered, report):
    offered.CERTIFICATE_CHECK_RATE = 2
    version = report.versions.get()
    url = reverse("certificate_check")
    anonymous = Client()
    for _ in range(2):
        assert anonymous.post(url, {"sha256": version.pdf_sha256}).status_code == 200
    refused = anonymous.post(url, {"file": pdf_of(version)})
    assert refused.status_code == 429
    assert 1 <= int(refused["Retry-After"]) <= 60
    assert "Many certificates were checked in the last minute." in page(refused)
    assert version.checks.count() == 1  # kept once a day; the refused request was not read
    # Signed-in checks are not counted against recipients.
    assert staff.post(reverse("reporting:check"), {"sha256": version.pdf_sha256}).status_code == 200
    # The next minute takes checks again.
    later = CheckWindow.objects.get().started_at + timedelta(seconds=60)
    assert checks.take_slot(later) == 0
    assert CheckWindow.objects.get().count == 1


def test_the_window_survives_its_row_being_emptied_and_a_clock_set_back(offered):
    now = timezone.now()
    assert checks.take_slot(now) == 0
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE reporting_checkwindow")  # as a demonstration reset does
    assert checks.take_slot(now) == 0
    assert checks.take_slot(now - timedelta(minutes=5)) == 0  # a window in the future restarts
    assert CheckWindow.objects.get().count == 1


# The record of checks ---------------------------------------------------------------------------


def test_checks_are_append_only_and_keep_the_answer_the_certificate_gives(staff, world, report):
    version = report.versions.get()
    staff.post(reverse("reporting:check"), {"sha256": version.pdf_sha256})
    check = version.checks.get()
    for statement in (
        "UPDATE reporting_certificatecheck SET answer = 'withdrawn' WHERE id = %s",
        "DELETE FROM reporting_certificatecheck WHERE id = %s",
    ):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(statement, [check.pk])
    for answer in ("superseded", "withdrawn"):
        with pytest.raises(DatabaseError, match="answer its certificate gives"):
            with transaction.atomic():
                CertificateCheck.objects.create(
                    version=version, checked_at=timezone.now(), matched="pdf", answer=answer
                )
    amend(world, report)
    with pytest.raises(DatabaseError, match="answer its certificate gives"):
        with transaction.atomic():
            CertificateCheck.objects.create(
                version=version, checked_at=timezone.now(), matched="pdf", answer="current"
            )
    assert version.checks.count() == 1


def test_the_lot_record_keeps_the_checks_of_its_certificates(staff, world, report):
    version = report.versions.get()
    staff.post(reverse("reporting:check"), {"sha256": version.pdf_sha256})
    package = lot_record.export_lot_record(
        actor=world["people"]["author"],
        lot_pk=report.lot_id,
        purpose="Synthetic inspection request",
    )
    archive = zipfile.ZipFile(io.BytesIO(package.file.read()))
    (record_name,) = [n for n in archive.namelist() if n.endswith("/record.json")]
    record = json.loads(archive.read(record_name))
    (rows,) = [s["records"] for s in record["sections"] if s["key"] == "report_checks"]
    assert [
        (r["fields"]["version"], r["fields"]["answer"], r["fields"]["matched"]) for r in rows
    ] == [(version.pk, "current", "pdf")]


def test_a_recipients_checks_are_kept_once_a_day_for_each_version_and_answer(
    staff, offered, world, report
):
    first = report.versions.get()
    recipient = Client()
    for _ in range(3):
        assert (
            recipient.post(reverse("certificate_check"), {"file": pdf_of(first)}).status_code == 200
        )
    staff.post(reverse("reporting:check"), {"sha256": first.pdf_sha256})
    staff.post(reverse("reporting:check"), {"sha256": first.pdf_sha256})
    assert list(first.checks.order_by("id").values_list("checked_by", flat=True)) == [
        None,
        world["people"]["reviewer"].pk,
        world["people"]["reviewer"].pk,
    ]
    # Another answer, or another day, is kept again.
    amend(world, report)
    recipient.post(reverse("certificate_check"), {"sha256": first.pdf_sha256})
    assert first.checks.filter(checked_by=None).count() == 2
    assert not checks._kept_today(first, "superseded", timezone.now() + timedelta(days=1))


def test_someone_signed_in_is_named_on_the_check_without_an_account(staff, offered, world, report):
    staff.post(reverse("certificate_check"), {"sha256": report.versions.get().pdf_sha256})
    assert report.versions.get().checks.get().checked_by == world["people"]["reviewer"]


def test_a_check_waits_for_an_amendment_being_signed_and_answers_after_it(
    world, report, monkeypatch
):
    """The answer is read under the certificate's lock: a check of version 1 made while version 2
    is being signed waits for the signature and answers that version 1 is replaced."""
    first = report.versions.get()
    rendering, release = threading.Event(), threading.Event()
    render = services.render_certificate

    def slow_render(*args, **kwargs):
        rendering.set()
        release.wait(20)
        return render(*args, **kwargs)

    monkeypatch.setattr(services, "render_certificate", slow_render)
    answers = []

    def amend_meanwhile():
        try:
            amend(world, report)
        finally:
            connections.close_all()

    def check_meanwhile():
        try:
            answers.append(checks.check(first.pdf_sha256, actor=world["people"]["reviewer"]))
        finally:
            connections.close_all()

    signer = threading.Thread(target=amend_meanwhile)
    signer.start()
    checker = threading.Thread(target=check_meanwhile)
    try:
        assert rendering.wait(30)
        checker.start()
        checker.join(0.5)
        assert checker.is_alive()  # waiting for the certificate's lock
    finally:
        release.set()
        signer.join(60)
        checker.join(60)
    (result,) = answers
    assert result.answer == "superseded"
    assert result.latest.number == 2
    assert first.checks.get().answer == "superseded"


def test_the_views_receive_files_as_their_sha256_only(
    staff, offered, report, settings, monkeypatch
):
    """No upload handler of the deployment receives the bytes, so no temporary file is written,
    whatever the size."""
    from django.core.files import uploadhandler

    settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 0  # any stored upload would go to a temporary file

    def stored(*args, **kwargs):
        raise AssertionError("an upload handler of the deployment received the file")

    monkeypatch.setattr(uploadhandler.TemporaryFileUploadHandler, "new_file", stored)
    monkeypatch.setattr(uploadhandler.MemoryFileUploadHandler, "new_file", stored)
    version = report.versions.get()
    for client, url in (
        (staff, reverse("reporting:check")),
        (Client(), reverse("certificate_check")),
    ):
        response = client.post(url, {"file": pdf_of(version)})
        assert "Genuine and current" in page(response), url


def test_the_signed_in_check_needs_the_csrf_token(world, report):
    browser = Client(enforce_csrf_checks=True)
    assert browser.login(username="rt_reviewer", password=PASSWORD)
    digest = report.versions.get().pdf_sha256
    assert browser.post(reverse("reporting:check"), {"sha256": digest}).status_code == 403
    assert not CertificateCheck.objects.exists()


def test_a_recipients_file_over_the_limit_is_stopped(client, offered, report):
    offered.RAW_DATA_MAX_BYTES = 1000
    big = SimpleUploadedFile("certificate.pdf", b"%PDF-" + b"0" * 4000)
    response = client.post(reverse("certificate_check"), {"file": big})
    assert response.status_code == 422
    assert "The file is larger than the limit of 1000 B." in page(response)
    assert not CertificateCheck.objects.exists()


def test_past_the_limit_the_request_body_is_not_read(client, offered):
    offered.CERTIFICATE_CHECK_RATE = 1
    malformed = b"--edge\r\nContent-Disposition: form-data; name=broken\r\n"
    kind = "multipart/form-data"  # no boundary: Django refuses the body once it reads it
    url = reverse("certificate_check")
    # Within the limit the body is read, and a malformed one is refused as such.
    assert client.post(url, malformed, content_type=kind).status_code == 400
    assert client.post(url, malformed, content_type=kind).status_code == 429


def test_another_sites_page_cannot_use_up_the_checks(client, offered, report):
    url = reverse("certificate_check")
    digest = report.versions.get().pdf_sha256
    for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://elsewhere.example"}):
        assert client.post(url, {"sha256": digest}, headers=headers).status_code == 403
    same = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    assert client.post(url, {"sha256": digest}, headers=same).status_code == 200
    assert CheckWindow.objects.get().count == 1  # the refused posts took no slot


def test_concurrent_checks_take_no_more_than_the_minutes_slots(offered):
    offered.CERTIFICATE_CHECK_RATE = 3
    waits, start = [], threading.Barrier(8)

    def take():
        try:
            start.wait(10)
            waits.append(checks.take_slot())
        finally:
            connections.close_all()

    threads = [threading.Thread(target=take) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert sorted(w == 0 for w in waits) == [False] * 5 + [True] * 3
    assert all(1 <= w <= 60 for w in waits if w)
    assert CheckWindow.objects.get().count == 3


def test_a_check_names_an_issued_version(report):
    with pytest.raises(DatabaseError, match="names an issued version"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reporting_certificatecheck (version_id, checked_at, matched, answer)"
                " VALUES (%s, now(), 'pdf', 'current')",
                [report.versions.get().pk + 1000],
            )
