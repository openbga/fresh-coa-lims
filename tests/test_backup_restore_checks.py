"""Backup manifests and restore checks (core.recovery, backup_manifest, verify_restore).

The round trip dumps a populated database with pg_dump from the manifest's own snapshot,
restores it into a new database with pg_restore and checks the copy in a separate process, as
an operator would. It needs PostgreSQL client tools of the server's major version or newer and
is skipped without them; the container smoke job in CI runs the same cycle with the image.
"""

import copy as copying
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction

from analytical import services as analytical
from analytical.models import RawDataFile
from analytical.rawdata import attach_raw_file
from core import recovery
from core.models import AuditEvent, ElectronicSignature, PINCredential
from reporting import services as reporting
from reporting.models import ReportVersion
from tests.test_integrated_journey import PIN, assign_and_sample, dispose
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
RAW = b"time,signal\n0,0.001\n1,0.512\n"
# Signing refuses an enclosing transaction, so tests that sign commit and are flushed after.
TX = pytest.mark.django_db(transaction=True)


def released_with_certificate(data):
    """A lot through raw data, review, disposition and an issued certificate."""
    people = data["people"]
    sample = assign_and_sample(data)
    tests, holds = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign frozen required tests"
    )
    assert holds == []
    test = tests[0]
    analytical.record_observation(
        actor=people["analyst"],
        test=test,
        value=Decimal("100.25"),
        raw_reference="RAW-SYN-001 rev 1",
        reason="Synthetic original observation",
    )
    attach_raw_file(
        actor=people["analyst"],
        test=test,
        upload=SimpleUploadedFile("run.csv", RAW, "text/csv"),
        description="Synthetic instrument export",
    )
    test.refresh_from_db()
    test = analytical.submit_test(
        actor=people["analyst"], test=test, expected_revision=test.revision, reason="Submit"
    )[0]
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent original-data review",
    )
    lot = dispose(data, people["approver"])
    _, evidence_hash, blockers = reporting.preview(lot)
    assert blockers == []
    return reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic Customer",
        evidence_hash=evidence_hash,
        reason="Synthetic certificate",
    )


def state_now():
    with recovery.read_snapshot() as cursor:
        return recovery.collect(cursor)


def statuses(checks):
    return {check["check"]: check["status"] for check in checks}


def problems(checks, name):
    return next(check for check in checks if check["check"] == name)["problems"]


@contextmanager
def triggers_disabled(*tables):
    """Switch off the history triggers of ``tables`` to stand for an altered copy."""
    quoted = [connection.ops.quote_name(table) for table in tables]
    with connection.cursor() as cursor:
        for table in quoted:
            cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            for table in quoted:
                cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")


# What the manifest records


@TX
def test_manifest_counts_and_fingerprints_rows_and_reads_the_schema(integrated):
    state = state_now()
    audit = state["tables"]["core_auditevent"]
    assert audit["rows"] == AuditEvent.objects.count() > 0
    assert re.fullmatch(r"[0-9a-f]{64}", audit["sha256"])
    assert "core.0001_initial" in state["migrations"]
    assert state["database"]["name"] == connection.settings_dict["NAME"]
    triggers = state["schema"]["triggers"]
    assert triggers["core_auditevent.history_immutable"]["enabled"] == "O"
    assert any(name.startswith("core_auditevent.") for name in state["schema"]["constraints"])
    assert "core_auditevent.reason" in state["schema"]["columns"]
    sequences = state["sequences"]
    assert any(position["table"] == "core_electronicsignature" for position in sequences.values())

    # The fingerprint follows the content, not the order rows are read in.
    assert state_now()["tables"] == state["tables"]
    people = integrated["people"]
    people["analyst"].first_name = "Changed"
    people["analyst"].save(update_fields=["first_name"])
    changed = state_now()["tables"]
    assert changed["accounts_user"]["rows"] == state["tables"]["accounts_user"]["rows"]
    assert changed["accounts_user"]["sha256"] != state["tables"]["accounts_user"]["sha256"]
    assert changed["core_auditevent"] == audit


@TX
def test_manifest_holds_no_record_content_or_credentials(integrated):
    released_with_certificate(integrated)
    state = state_now()
    document = json.dumps({**state, "checks": recovery.evidence_checks(state)})
    encoded_pin = PINCredential.objects.first().encoded
    password_hash = integrated["people"]["analyst"].password
    for secret in (encoded_pin, password_hash, "pbkdf2_sha256$", "Synthetic Customer", "100.25"):
        assert secret not in document


@TX
def test_read_snapshot_refuses_an_enclosing_transaction():
    with transaction.atomic(), pytest.raises(recovery.RecoveryError, match="outside"):
        with recovery.read_snapshot():
            pass


# Checks of stored evidence


@TX
def test_intact_evidence_passes(integrated):
    released_with_certificate(integrated)
    checks = recovery.evidence_checks(state_now())
    assert set(statuses(checks).values()) == {recovery.PASSED}
    summaries = {check["check"]: check["summary"] for check in checks}
    assert summaries["certificates"].startswith("1 ")
    assert summaries["raw data files"].startswith("1 ")
    assert int(summaries["signatures"].split()[0]) == ElectronicSignature.objects.count() > 3


@TX
def test_altered_signature_and_audit_event_are_found(integrated):
    released_with_certificate(integrated)
    signature = ElectronicSignature.objects.order_by("pk").first()
    other = ElectronicSignature.objects.order_by("pk").last()
    with triggers_disabled("core_electronicsignature", "core_auditevent"):
        ElectronicSignature.objects.filter(pk=signature.pk).update(
            content={**signature.content, "reason": "rewritten"}
        )
        AuditEvent.objects.filter(pk=other.audit_event_id).update(after={"rewritten": True})
        checks = recovery.evidence_checks(state_now())
    found = problems(checks, "signatures")
    assert any(f"Signature {signature.pk} " in p and "content hash" in p for p in found)
    assert any(f"Signature {other.pk} " in p and "signed content" in p for p in found)
    # Both tables' history triggers were switched off to make the change.
    disabled = problems(checks, "triggers enabled")
    assert "Trigger core_electronicsignature.history_immutable is disabled" in disabled
    assert statuses(checks)["triggers enabled"] == recovery.FAILED


@TX
def test_altered_certificate_and_raw_file_bytes_are_found(integrated):
    report = released_with_certificate(integrated)
    version = report.versions.get()
    with triggers_disabled("reporting_reportversion", "analytical_rawdatafile"):
        ReportVersion.objects.filter(pk=version.pk).update(pdf=bytes(version.pdf) + b"%")
        RawDataFile.objects.update(content=RAW.replace(b"0.512", b"0.612"))
    checks = recovery.evidence_checks(state_now())
    assert problems(checks, "certificates") == [
        f"Certificate {report.number} version 1: the stored PDF does not match its checksum and "
        "size"
    ]
    assert "do not match their checksum" in problems(checks, "raw data files")[0]


# Comparing a copy with its manifest


@TX
def test_copy_equal_to_its_manifest_passes_and_every_difference_fails(integrated):
    manifest = state_now()
    assert set(statuses(recovery.compare(manifest, manifest)).values()) == {recovery.PASSED}

    integrated["people"]["analyst"].first_name = "Changed"
    integrated["people"]["analyst"].save(update_fields=["first_name"])
    copy = state_now()
    del copy["tables"]["core_auditreview"]
    copy["tables"]["extra_table"] = {"rows": 0, "sha256": "0" * 64}
    copy["migrations"] = copy["migrations"][1:]
    copy["schema"]["triggers"]["core_auditevent.history_immutable"]["enabled"] = "D"
    copy["schema"]["functions"].popitem()
    checks = recovery.compare(manifest, copy)
    assert statuses(checks) == {
        "migrations": recovery.FAILED,
        "tables": recovery.FAILED,
        "columns": recovery.PASSED,
        "constraints": recovery.PASSED,
        "indexes": recovery.PASSED,
        "triggers": recovery.FAILED,
        "functions": recovery.FAILED,
    }
    assert problems(checks, "tables") == [
        "Table core_auditreview is missing",
        "Table extra_table is not in the manifest",
        "Table accounts_user has the same number of rows, but their content differs",
    ]
    assert problems(checks, "migrations") == [f"Migration {manifest['migrations'][0]} is missing"]

    copy = copying.deepcopy(manifest)
    copy["tables"]["core_auditevent"]["rows"] -= 1
    assert problems(recovery.compare(manifest, copy), "tables") == [
        f"Table core_auditevent has {manifest['tables']['core_auditevent']['rows'] - 1} rows; "
        f"the manifest has {manifest['tables']['core_auditevent']['rows']}"
    ]


def test_array_casts_rewritten_by_a_restore_compare_equal():
    migrated = (
        "CHECK ((((kind)::text = ANY ((ARRAY['original'::character varying, "
        "'it''s'::character varying])::text[])) OR (investigation_id IS NOT NULL)))"
    )
    restored = (
        "CHECK ((((kind)::text = ANY (ARRAY[('original'::character varying)::text, "
        "('it''s'::character varying)::text])) OR (investigation_id IS NOT NULL)))"
    )
    assert recovery.normalized(migrated) == restored
    assert recovery.normalized(restored) == restored
    assert recovery._differences({"c": migrated}, {"c": restored}, "Constraint", True) == []
    assert recovery._differences({"c": migrated}, {"c": restored}, "Constraint") == [
        "Constraint c differs from the manifest"
    ]
    widened = restored.replace("'it''s'", "'other'")
    assert recovery._differences({"c": migrated}, {"c": widened}, "Constraint", True)


def test_sequences_must_lie_beyond_stored_identifiers_unless_the_source_did_not():
    def position(next_value, largest):
        return {"table": "t", "column": "id", "next_value": next_value, "largest_value": largest}

    manifest = {"sequences": {"a": position(11, 10), "b": position(1, 1), "c": position(5, 4)}}
    copy = {"sequences": {"a": position(1, 10), "b": position(1, 1), "d": position(1, None)}}
    check = recovery.check_sequences(manifest, copy)
    assert check["status"] == recovery.FAILED
    assert check["problems"] == [
        "Sequence c is missing",
        "Sequence d is not in the manifest",
        "Sequence a would next give 1, but t.id already holds 10",
    ]
    ahead = {"sequences": {"a": position(15, 10), "b": position(1, 1), "c": position(5, 4)}}
    assert recovery.check_sequences(manifest, ahead)["status"] == recovery.PASSED


def test_the_source_itself_is_not_a_restored_copy():
    source = {
        "name": "open_qual",
        "oid": 16384,
        "system_identifier": "7306",
        "server_address": "10.0.0.1",
        "server_port": 5432,
    }
    assert recovery.check_not_source(source, dict(source))["status"] == recovery.FAILED
    for change in ({"name": "restore"}, {"oid": 99}, {"system_identifier": "8000"}):
        assert recovery.check_not_source(source, {**source, **change})["status"] == "passed"
    # Without the server's identifier (no privilege), the server address decides.
    hidden = {**source, "system_identifier": None}
    assert recovery.check_not_source(hidden, dict(hidden))["status"] == recovery.FAILED
    moved = {**hidden, "server_address": "10.0.0.2"}
    assert recovery.check_not_source(hidden, moved)["status"] == recovery.PASSED


def test_archive_checksum_is_compared_when_both_are_known(tmp_path):
    archive = tmp_path / "a.dump"
    archive.write_bytes(b"archive bytes")
    digest, size = recovery.file_digest(archive)
    manifest = {"archive": {"sha256": digest, "size": size}}
    assert recovery.check_archive(manifest, archive)["status"] == recovery.PASSED
    archive.write_bytes(b"archive bytes, altered")
    assert recovery.check_archive(manifest, archive)["status"] == recovery.FAILED
    assert recovery.check_archive(manifest, None)["status"] == recovery.NOT_CHECKED
    assert recovery.check_archive({"archive": None}, archive)["status"] == recovery.NOT_CHECKED


# The commands


def fake_pg_dump(directory, script):
    path = directory / "pg_dump"
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(0o755)
    return str(path)


@TX
def test_backup_manifest_writes_an_owner_only_file_and_changes_nothing(integrated, tmp_path):
    events = AuditEvent.objects.count()
    output = tmp_path / "manifest.json"
    call_command("backup_manifest", output=str(output), operator="Synthetic Operator")
    assert AuditEvent.objects.count() == events
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    manifest = json.loads(output.read_text())
    assert manifest["format"] == recovery.MANIFEST_FORMAT
    assert manifest["result"] == recovery.PASSED
    assert manifest["archive"] is None
    assert manifest["taken_by"]["operator"] == "Synthetic Operator"
    assert manifest["tables"]["core_auditevent"]["rows"] == events
    with pytest.raises(CommandError, match="already exists"):
        call_command("backup_manifest", output=str(output))
    with pytest.raises(CommandError, match="two files"):
        call_command("backup_manifest", output=str(tmp_path / "m"), dump=str(tmp_path / "m"))


@TX
def test_backup_manifest_reports_failed_evidence_after_writing(integrated, tmp_path):
    output = tmp_path / "manifest.json"
    with triggers_disabled("core_auditevent"):
        with pytest.raises(CommandError, match="failed a check of its stored evidence"):
            call_command("backup_manifest", output=str(output))
    manifest = json.loads(output.read_text())
    assert manifest["result"] == recovery.FAILED
    assert "Trigger core_auditevent.history_immutable is disabled" in problems(
        manifest["checks"], "triggers enabled"
    )


@TX
def test_backup_manifest_refuses_an_unusable_pg_dump_and_leaves_no_files(integrated, tmp_path):
    output, archive = tmp_path / "manifest.json", tmp_path / "backup.dump"

    def attempt(pg_dump, match):
        with pytest.raises(CommandError, match=match):
            call_command("backup_manifest", output=str(output), dump=str(archive), pg_dump=pg_dump)
        assert not output.exists() and not archive.exists()

    attempt(str(tmp_path / "missing"), "pg_dump was not found")
    attempt(fake_pg_dump(tmp_path, "echo 'pg_dump (PostgreSQL) 9.6.24'\n"), "cannot dump")
    failing = fake_pg_dump(
        tmp_path,
        'case "$1" in --version) echo "pg_dump (PostgreSQL) 99.0";; '
        '*) echo "connection refused" >&2; exit 1;; esac\n',
    )
    attempt(failing, "pg_dump failed with exit status 1; no archive or manifest was kept")


@TX
def test_backup_manifest_never_puts_the_password_on_the_command_line(integrated, tmp_path):
    log = tmp_path / "invocation"
    recording = fake_pg_dump(
        tmp_path,
        'case "$1" in --version) echo "pg_dump (PostgreSQL) 99.0";; '
        f'*) echo "$@" > {log}; env | grep "^PG" | cut -d= -f1 | sort >> {log}; '
        'for arg in "$@"; do case "$arg" in --file=*) printf x > "${arg#--file=}";; esac; done;; '
        "esac\n",
    )
    output, archive = tmp_path / "manifest.json", tmp_path / "backup.dump"
    call_command("backup_manifest", output=str(output), dump=str(archive), pg_dump=recording)
    invocation = log.read_text()
    password = connection.settings_dict["PASSWORD"]
    assert password and password not in invocation
    assert "PGPASSWORD" in invocation.split()
    assert re.search(r"--snapshot=\S+", invocation)
    assert "--format=custom --no-owner --no-acl" in invocation
    manifest = json.loads(output.read_text())
    assert manifest["archive"]["sha256"] == recovery.file_digest(archive)[0]
    assert manifest["pg_dump"] == "pg_dump (PostgreSQL) 99.0"
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600


@TX
def test_verify_restore_refuses_files_it_cannot_use(tmp_path):
    report = tmp_path / "report.json"
    with pytest.raises(CommandError, match="Cannot read the manifest"):
        call_command("verify_restore", manifest=str(tmp_path / "none"), report=str(report))
    other = tmp_path / "other.json"
    other.write_text('{"format": "something else"}')
    with pytest.raises(CommandError, match="is not a backup manifest"):
        call_command("verify_restore", manifest=str(other), report=str(report))
    report.write_text("kept")
    with pytest.raises(CommandError, match="already exists"):
        call_command("verify_restore", manifest=str(other), report=str(report))
    assert report.read_text() == "kept"


def client_tool(name, server_major):
    path = shutil.which(name)
    if path is None:
        return None
    output = subprocess.run([path, "--version"], capture_output=True, text=True).stdout
    match = re.search(r"\b(\d+)(?:\.\d+)*\b", output)
    return path if match and int(match.group(1)) >= server_major else None


def database_url(name):
    db = connection.settings_dict
    credentials = quote(db["USER"], safe="")
    if db["PASSWORD"]:
        credentials += ":" + quote(db["PASSWORD"], safe="")
    return f"postgresql://{credentials}@{db['HOST'] or 'localhost'}:{db['PORT'] or 5432}/{name}"


@TX
def test_backup_restore_and_verify_round_trip(integrated, tmp_path):
    server_major = connection.pg_version // 10000
    pg_dump = client_tool("pg_dump", server_major)
    pg_restore = client_tool("pg_restore", server_major)
    if not (pg_dump and pg_restore):
        pytest.skip(f"pg_dump and pg_restore {server_major} or newer are not installed")
    released_with_certificate(integrated)
    manifest_path, archive = tmp_path / "manifest.json", tmp_path / "backup.dump"
    call_command("backup_manifest", output=str(manifest_path), dump=str(archive), pg_dump=pg_dump)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["result"] == recovery.PASSED
    assert manifest["archive"]["size"] == archive.stat().st_size

    # The source answers to its manifest in everything but being the source.
    source_report = tmp_path / "source-report.json"
    with pytest.raises(CommandError, match="1 of 15 checks failed"):
        call_command("verify_restore", manifest=str(manifest_path), report=str(source_report))
    checks = json.loads(source_report.read_text())["checks"]
    assert [c["check"] for c in checks if c["status"] == recovery.FAILED] == ["restored copy"]

    target = f"{connection.settings_dict['NAME']}_restore"
    quoted = connection.ops.quote_name(target)
    with connection.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS {quoted}")
        cursor.execute(f"CREATE DATABASE {quoted} TEMPLATE template0")
    try:
        environment = {k: v for k, v in os.environ.items() if k != "TEST_DATABASE_NAME"}
        subprocess.run(
            [
                pg_restore,
                f"--dbname={database_url(target)}",
                "--no-owner",
                "--no-acl",
                "--single-transaction",
                "--exit-on-error",
                str(archive),
            ],
            check=True,
            capture_output=True,
            env=environment,
        )
        report_path = tmp_path / "report.json"
        completed = subprocess.run(
            [
                sys.executable,
                "manage.py",
                "verify_restore",
                f"--manifest={manifest_path}",
                f"--archive={archive}",
                f"--report={report_path}",
                "--operator=Synthetic Operator",
            ],
            cwd=ROOT,
            env={**environment, "DATABASE_URL": database_url(target), "DEBUG": "true"},
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "The restored copy matches its manifest." in completed.stdout
        report = json.loads(report_path.read_text())
        assert report["format"] == recovery.REPORT_FORMAT
        assert report["result"] == recovery.PASSED
        assert set(statuses(report["checks"]).values()) == {recovery.PASSED}
        assert report["database"]["name"] == target
        assert report["manifest"]["sha256"] == recovery.file_digest(manifest_path)[0]
        assert report["checked_by"]["operator"] == "Synthetic Operator"
        assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)")
