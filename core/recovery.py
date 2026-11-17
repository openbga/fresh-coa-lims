"""Backup manifests and restore checks an operator keeps as evidence.

When a backup is taken, ``backup_manifest`` records what the database holds: each table's row
count and a SHA-256 fingerprint of its rows, the schema definitions, the applied migrations and
the sequence positions, all read in one read-only snapshot. With ``--dump`` it runs ``pg_dump``
from that same exported snapshot, so the archive and the manifest describe the same instant.

After the archive is restored into a new database, ``verify_restore`` reads the copy the same
way, compares it with the manifest and writes a report. A restore passes only when the copy
equals the manifest exactly and the evidence it holds is intact: signature hashes recompute and
link to their audit events, stored certificates and raw-data files match their checksums,
history triggers are enabled and sequences lie beyond every stored identifier.

Both commands only read. The manifest and the report hold counts, hashes and schema
definitions, never record content or credentials.
"""

import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from contextlib import ExitStack, contextmanager
from datetime import UTC
from pathlib import Path

from django.core import checks as system_checks
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

MANIFEST_FORMAT = "fresh-coa-lims.backup-manifest/1"
REPORT_FORMAT = "fresh-coa-lims.restore-check/1"

PASSED, FAILED, NOT_CHECKED = "passed", "failed", "not checked"
# A report lists at most this many problems per check and gives the total.
LISTED = 50

# Settings that fix the text form of every value, so a row reads alike on any server and in
# any session: the fingerprints of a table and of its restored copy are then comparable.
OUTPUT_SETTINGS = {
    "TimeZone": "UTC",
    "DateStyle": "ISO, YMD",
    "IntervalStyle": "postgres",
    "bytea_output": "hex",
    "extra_float_digits": "1",
}


class RecoveryError(Exception):
    """A refusal or a failed step; the message says what happened and what to do."""


# Reading


@contextmanager
def read_snapshot():
    """One read-only repeatable-read transaction: every read inside sees the same instant."""
    if connection.in_atomic_block:
        raise RecoveryError("Run outside a transaction: the check opens its own snapshot.")
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cursor.execute(
            "SELECT current_setting('transaction_isolation'), "
            "current_setting('transaction_read_only')"
        )
        if cursor.fetchone() != ("repeatable read", "on"):
            raise RecoveryError("Could not open a read-only repeatable-read snapshot.")
        fix_output(cursor)
        yield cursor


def fix_output(cursor):
    for name, value in OUTPUT_SETTINGS.items():
        cursor.execute("SELECT set_config(%s, %s, true)", [name, value])


def collect(cursor):
    """Everything a manifest records about the database, read with ``cursor``."""
    return {
        "database": database_identity(cursor),
        "migrations": applied_migrations(cursor),
        "tables": table_fingerprints(cursor),
        "sequences": sequence_positions(cursor),
        "schema": schema_definitions(cursor),
    }


def database_identity(cursor):
    cursor.execute(
        """
        SELECT current_database(), current_schema(), current_setting('server_version'),
               current_setting('server_version_num')::int, d.oid::bigint,
               host(inet_server_addr()), inet_server_port(), now(),
               has_function_privilege('pg_control_system()', 'EXECUTE')
        FROM pg_database d WHERE d.datname = current_database()
        """
    )
    name, schema, version, version_num, oid, address, port, now, can_read_control = (
        cursor.fetchone()
    )
    system_identifier = None
    if can_read_control:
        cursor.execute("SELECT system_identifier::text FROM pg_control_system()")
        system_identifier = cursor.fetchone()[0]
    return {
        "name": name,
        "schema": schema,
        "server_version": version,
        "server_version_num": version_num,
        "oid": oid,
        "server_address": address,
        "server_port": port,
        "system_identifier": system_identifier,
        "snapshot_at": now.astimezone(UTC).isoformat(),
    }


def applied_migrations(cursor):
    cursor.execute("SELECT app || '.' || name FROM django_migrations ORDER BY app, name")
    return [row[0] for row in cursor.fetchall()]


def table_names(cursor):
    cursor.execute(
        """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema() AND c.relkind = 'r' ORDER BY c.relname
        """
    )
    return [row[0] for row in cursor.fetchall()]


def table_fingerprints(cursor):
    """Row count and fingerprint of every table in the schema.

    The fingerprint is the SHA-256 of the sorted SHA-256 digests of the rows' text form. Sorting
    the digests (bytes, compared bytewise) makes it independent of physical order and of the
    collation, and the rows stream through a server-side cursor, so a table of any size is read
    without holding it in memory.
    """
    tables = {}
    for name in table_names(cursor):
        digest = hashlib.sha256()
        rows = 0
        with connection.chunked_cursor() as stream:
            # ROW(alias.*) is the whole row even when a column is named like the alias.
            stream.execute(
                f"SELECT sha256(convert_to(ROW(oq_row.*)::text, 'UTF8')) AS d "
                f"FROM {connection.ops.quote_name(name)} AS oq_row ORDER BY d"
            )
            while chunk := stream.fetchmany(2000):
                for (row,) in chunk:
                    digest.update(bytes(row))
                rows += len(chunk)
        tables[name] = {"rows": rows, "sha256": digest.hexdigest()}
    return tables


def sequence_positions(cursor):
    """Each sequence's position and, for one that numbers a column, that column's largest value.

    Sequences are not transactional: the position is the current one, which a busy database may
    have advanced beyond the snapshot. The restore check therefore requires each sequence to lie
    beyond the stored identifiers rather than equal the manifest.
    """
    cursor.execute(
        """
        SELECT s.relname, t.relname, a.attname
        FROM pg_class s
        JOIN pg_namespace n ON n.oid = s.relnamespace
        LEFT JOIN pg_depend d ON d.classid = 'pg_class'::regclass AND d.objid = s.oid
             AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
        LEFT JOIN pg_class t ON t.oid = d.refobjid
        LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S' AND n.nspname = current_schema()
        ORDER BY s.relname
        """
    )
    quote = connection.ops.quote_name
    positions = {}
    for sequence, table, column in cursor.fetchall():
        cursor.execute(f"SELECT last_value, is_called FROM {quote(sequence)}")
        last_value, is_called = cursor.fetchone()
        largest = None
        if table and column:
            cursor.execute(f"SELECT max({quote(column)}) FROM {quote(table)}")
            largest = cursor.fetchone()[0]
        positions[sequence] = {
            "table": table,
            "column": column,
            "next_value": last_value + 1 if is_called else last_value,
            "largest_value": largest,
        }
    return positions


def schema_definitions(cursor):
    """Columns, constraints, indexes, triggers and functions, each keyed by its name."""
    cursor.execute(
        """
        SELECT c.relname || '.' || a.attname,
               format_type(a.atttypid, a.atttypmod)
               || CASE WHEN a.attnotnull THEN ' not null' ELSE '' END
               || CASE WHEN a.attidentity::text <> ''
                       THEN ' identity ' || a.attidentity::text ELSE '' END
               || coalesce(' default ' || pg_get_expr(ad.adbin, ad.adrelid), '')
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
        WHERE n.nspname = current_schema() AND c.relkind = 'r' AND a.attnum > 0
              AND NOT a.attisdropped
        """
    )
    columns = dict(cursor.fetchall())
    cursor.execute(
        """
        SELECT cl.relname || '.' || con.conname, pg_get_constraintdef(con.oid)
        FROM pg_constraint con
        JOIN pg_class cl ON cl.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = con.connamespace
        WHERE n.nspname = current_schema()
        """
    )
    constraints = dict(cursor.fetchall())
    cursor.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema()")
    indexes = dict(cursor.fetchall())
    cursor.execute(
        """
        SELECT c.relname || '.' || t.tgname, t.tgenabled, pg_get_triggerdef(t.oid)
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal AND n.nspname = current_schema()
        """
    )
    triggers = {
        name: {"enabled": enabled, "definition": definition}
        for name, enabled, definition in cursor.fetchall()
    }
    cursor.execute(
        """
        SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',
               encode(sha256(convert_to(pg_get_functiondef(p.oid), 'UTF8')), 'hex')
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = current_schema() AND p.prokind IN ('f', 'p')
        """
    )
    functions = dict(cursor.fetchall())
    return {
        "columns": dict(sorted(columns.items())),
        "constraints": dict(sorted(constraints.items())),
        "indexes": dict(sorted(indexes.items())),
        "triggers": dict(sorted(triggers.items())),
        "functions": dict(sorted(functions.items())),
    }


# Checks of the evidence a database holds, run on the source and on the restored copy


def result(name, problems, summary, status=None):
    problems = list(problems)
    return {
        "check": name,
        "status": status or (FAILED if problems else PASSED),
        "summary": summary,
        "problem_count": len(problems),
        "problems": problems[:LISTED],
    }


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def check_signatures():
    """Each signature's stored content hashes to its content hash, and its audit event names
    the same signer and record and holds the signed content (for an account change, the
    account part of it) at the signed revision."""
    from core.models import ElectronicSignature

    problems = []
    count = 0
    signatures = ElectronicSignature.objects.select_related("audit_event").order_by("pk")
    for signature in signatures.iterator(chunk_size=500):
        count += 1
        label = f"Signature {signature.pk} ({signature.meaning}, {signature.object_type} "
        label += f"{signature.object_id})"
        content = signature.content
        if hashlib.sha256(_canonical(content)).hexdigest() != signature.content_hash:
            problems.append(f"{label}: the content does not hash to the stored content hash")
        signed = content
        if signature.meaning == "account_authorized" and isinstance(content, dict):
            signed = content.get("account")
        event = signature.audit_event
        if event.actor_id != signature.signer_id:
            problems.append(f"{label}: the audit event names another actor")
        if (event.object_type, event.object_id) != (signature.object_type, signature.object_id):
            problems.append(f"{label}: the audit event is about another record")
        if event.after != signed:
            problems.append(f"{label}: the audit event does not hold the signed content")
        if not isinstance(signed, dict) or signed.get("revision") != signature.revision:
            problems.append(f"{label}: the signed content is not at the signed revision")
    return result("signatures", problems, f"{count} signatures: content hashes and audit events")


def check_certificates():
    """Each issued certificate's stored PDF matches its checksum and size and its evidence
    snapshot its hash, and each report's head names its current version's checksums."""
    from reporting.evidence import canonical_hash
    from reporting.models import Report, ReportVersion

    problems = []
    count = 0
    versions = ReportVersion.objects.select_related("report").order_by("pk")
    for version in versions.iterator(chunk_size=20):
        count += 1
        label = f"Certificate {version.report.number} version {version.number}"
        pdf = bytes(version.pdf)
        if hashlib.sha256(pdf).hexdigest() != version.pdf_sha256 or len(pdf) != version.pdf_size:
            problems.append(f"{label}: the stored PDF does not match its checksum and size")
        if canonical_hash(version.snapshot) != version.snapshot_hash:
            problems.append(f"{label}: the evidence snapshot does not match its hash")
    for report in Report.objects.filter(version_count__gt=0).order_by("pk").iterator():
        current = (
            ReportVersion.objects.filter(report=report, number=report.version_count)
            .values("pdf_sha256", "snapshot_hash")
            .first()
        )
        if current is None:
            problems.append(f"Certificate {report.number}: its current version is missing")
        elif (report.current_pdf_sha256, report.current_snapshot_hash) != (
            current["pdf_sha256"],
            current["snapshot_hash"],
        ):
            problems.append(
                f"Certificate {report.number}: the head does not name its current version"
            )
    return result("certificates", problems, f"{count} issued certificate versions checksummed")


def check_raw_files():
    """Raw-data files of tests and evidence files of rehearsals: bytes against checksum."""
    from analytical.models import RawDataFile
    from validation.models import RehearsalFile

    problems = []
    count = evidence = 0
    for stored in RawDataFile.objects.order_by("pk").iterator(chunk_size=20):
        count += 1
        content = bytes(stored.content)
        if hashlib.sha256(content).hexdigest() != stored.sha256 or len(content) != stored.size:
            problems.append(
                f"Raw-data file {stored.pk} of test {stored.test_id}: the stored bytes do not "
                "match their checksum and size"
            )
    for stored in RehearsalFile.objects.order_by("pk").iterator(chunk_size=20):
        evidence += 1
        content = bytes(stored.content)
        if hashlib.sha256(content).hexdigest() != stored.sha256 or len(content) != stored.size:
            problems.append(
                f"Evidence file {stored.pk} of rehearsal {stored.rehearsal_id}: the stored "
                "bytes do not match their checksum and size"
            )
    return result(
        "raw data files",
        problems,
        f"{count} raw-data files and {evidence} rehearsal evidence files checksummed",
    )


def check_triggers(state):
    """Every trigger fires in normal sessions: enabled (``O``) or always (``A``). A disabled
    trigger (``D``) and one that fires only in replica sessions (``R``) protect nothing."""
    triggers = state["schema"]["triggers"]
    problems = []
    for name, trigger in triggers.items():
        if trigger["enabled"] == "D":
            problems.append(f"Trigger {name} is disabled")
        elif trigger["enabled"] not in ("O", "A"):
            problems.append(f"Trigger {name} fires only in replica sessions, not in normal use")
    return result(
        "triggers enabled",
        problems,
        f"{len(triggers) - len(problems)} of {len(triggers)} triggers enabled",
    )


def _behind(position):
    largest = position["largest_value"]
    return largest is not None and largest >= position["next_value"]


def check_sequences(manifest, state):
    """Each sequence of the copy lies beyond the identifiers its column holds, unless the
    source's did not either (a table that always names its one row, for instance).

    Sequences are not transactional: the manifest records the source's position when it was
    read, which a busy database may have advanced beyond the snapshot, so positions are not
    compared with the manifest for equality.
    """
    problems = []
    expected, actual = manifest["sequences"], state["sequences"]
    for name in sorted(expected.keys() - actual.keys()):
        problems.append(f"Sequence {name} is missing")
    for name in sorted(actual.keys() - expected.keys()):
        problems.append(f"Sequence {name} is not in the manifest")
    for name in sorted(expected.keys() & actual.keys()):
        position = actual[name]
        if _behind(position) and not _behind(expected[name]):
            problems.append(
                f"Sequence {name} would next give {position['next_value']}, but "
                f"{position['table']}.{position['column']} already holds "
                f"{position['largest_value']}"
            )
    return result(
        "sequences",
        problems,
        f"{len(actual)} sequences compared with the identifiers stored",
    )


def evidence_checks(state):
    """The checks that need no manifest; run on the source and on the restored copy."""
    return [
        check_signatures(),
        check_certificates(),
        check_raw_files(),
        check_triggers(state),
    ]


# Comparing a restored copy with its manifest


# PostgreSQL keeps an IN list over a text column, as Django writes it, as one array cast as a
# whole, ``(ARRAY['a'::character varying, 'b'::character varying])::text[]``. pg_dump prints
# it so, and the server reading it back stores each value cast in turn,
# ``ARRAY[('a'::character varying)::text, ('b'::character varying)::text]``. The two mean the
# same; definitions are compared in the second form.
_CAST_ARRAY = re.compile(
    r"\(ARRAY\[(?P<items>'(?:[^']|'')*'::[a-z]+(?: [a-z]+)*"
    r"(?:, '(?:[^']|'')*'::[a-z]+(?: [a-z]+)*)*)\]\)::(?P<type>[a-z]+(?: [a-z]+)*)\[\]"
)
_CAST_ITEM = re.compile(r"'(?:[^']|'')*'::[a-z]+(?: [a-z]+)*")


def normalized(definition):
    """``definition`` with arrays cast as a whole written as values cast one by one."""

    def each(match):
        items = _CAST_ITEM.findall(match["items"])
        return "ARRAY[" + ", ".join(f"({item})::{match['type']}" for item in items) + "]"

    return _CAST_ARRAY.sub(each, definition) if isinstance(definition, str) else definition


def _differences(expected, actual, kind, normalize=False):
    problems = []
    for name in sorted(expected.keys() - actual.keys()):
        problems.append(f"{kind} {name} is missing")
    for name in sorted(actual.keys() - expected.keys()):
        problems.append(f"{kind} {name} is not in the manifest")
    for name in sorted(expected.keys() & actual.keys()):
        want, have = expected[name], actual[name]
        if normalize:
            want, have = normalized(want), normalized(have)
        if want != have:
            problems.append(f"{kind} {name} differs from the manifest")
    return problems


def compare(manifest, state):
    """Checks of the restored copy ``state`` against ``manifest``: equal or failed."""
    checks = []
    expected, actual = manifest["migrations"], state["migrations"]
    checks.append(
        result(
            "migrations",
            [f"Migration {name} is missing" for name in expected if name not in actual]
            + [
                f"Migration {name} is not in the manifest"
                for name in actual
                if name not in expected
            ],
            f"{len(actual)} applied migrations compared with the manifest",
        )
    )
    problems = []
    for name in sorted(manifest["tables"].keys() - state["tables"].keys()):
        problems.append(f"Table {name} is missing")
    for name in sorted(state["tables"].keys() - manifest["tables"].keys()):
        problems.append(f"Table {name} is not in the manifest")
    for name in sorted(manifest["tables"].keys() & state["tables"].keys()):
        want, have = manifest["tables"][name], state["tables"][name]
        if want["rows"] != have["rows"]:
            problems.append(
                f"Table {name} has {have['rows']} rows; the manifest has {want['rows']}"
            )
        elif want["sha256"] != have["sha256"]:
            problems.append(f"Table {name} has the same number of rows, but their content differs")
    rows = sum(table["rows"] for table in state["tables"].values())
    checks.append(
        result(
            "tables",
            problems,
            f"{len(state['tables'])} tables and {rows} rows compared with the manifest",
        )
    )
    labels = {
        "columns": "Column",
        "constraints": "Constraint",
        "indexes": "Index",
        "triggers": "Trigger",
        "functions": "Function",
    }
    for part, kind in labels.items():
        want, have = manifest["schema"][part], state["schema"][part]
        checks.append(
            result(
                part,
                _differences(want, have, kind, normalize=part in ("constraints", "indexes")),
                f"{len(have)} {part} compared with the manifest",
            )
        )
    return checks


def check_not_source(manifest_database, database):
    """The copy checked must not be the database the manifest was taken from.

    The same database name and database identifier on the same server (its system identifier)
    are taken for the source. Without the system identifier on either side, the same name and
    identifier are. A physical copy or a point-in-time recovery keeps all three, so it is
    refused too: its moment has no manifest, and ``backup_manifest`` run on it checks its
    evidence instead.
    """
    known = manifest_database["system_identifier"] and database["system_identifier"]
    same = (
        manifest_database["name"] == database["name"]
        and manifest_database["oid"] == database["oid"]
        and (not known or manifest_database["system_identifier"] == database["system_identifier"])
    )
    problems = (
        [
            "This is the database the manifest was taken from, or a physical copy of it. "
            "Check a database restored from the manifest's archive instead."
        ]
        if same
        else []
    )
    return result(
        "restored copy",
        problems,
        f"Database {database['name']} checked against the manifest of {manifest_database['name']}",
    )


def check_application():
    """The code running the check matches the restored schema and passes its system checks."""
    problems = []
    executor = MigrationExecutor(connection)
    for migration, _backwards in executor.migration_plan(executor.loader.graph.leaf_nodes()):
        problems.append(f"Migration {migration.app_label}.{migration.name} is not applied")
    unknown = executor.loader.applied_migrations.keys() - executor.loader.disk_migrations.keys()
    for app_label, name in sorted(unknown):
        problems.append(f"Migration {app_label}.{name} is unknown to this release")
    for message in system_checks.run_checks():
        if message.is_serious():
            problems.append(f"System check {message.id}: {message.msg}")
    return result(
        "application", problems, "This release's migrations and system checks on the copy"
    )


def check_archive(manifest, archive):
    recorded = manifest.get("archive")
    if not recorded or archive is None:
        reason = (
            "give --archive to compare the archive with the manifest"
            if recorded
            else "the manifest records no archive; compare the archive with the checksum "
            "recorded when it was made"
        )
        return result("archive", [], f"Not compared: {reason}", NOT_CHECKED)
    digest, size = file_digest(archive)
    problems = []
    if (digest, size) != (recorded["sha256"], recorded["size"]):
        problems.append(
            f"The archive {archive} has SHA-256 {digest} and {size} bytes; the manifest "
            f"records {recorded['sha256']} and {recorded['size']} bytes"
        )
    return result("archive", problems, "The archive compared with the checksum in the manifest")


# Files


def file_digest(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def refuse_existing(*paths):
    for path in paths:
        if path is not None and os.path.lexists(path):
            raise RecoveryError(
                f"{path} already exists. Choose a new file; nothing is overwritten."
            )


@contextmanager
def new_file(path):
    """A new file readable by its owner only, opened for reading and writing; it is removed
    again if the block fails or the file cannot be written out, so a failed run leaves no
    partial file behind."""
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        raise RecoveryError(f"Cannot create {path}: {error.strerror}.") from error
    stream = os.fdopen(descriptor, "w+b")
    try:
        yield stream
        finish(stream)
        stream.close()
    except BaseException:
        stream.close()
        Path(path).unlink(missing_ok=True)
        raise


def finish(stream):
    """Write ``stream`` out to disk, so that a full disk fails the run while it can still
    remove its files."""
    try:
        stream.flush()
        os.fsync(stream.fileno())
    except OSError as error:
        raise RecoveryError(f"Cannot write {stream.name}: {error.strerror}.") from error


def evidence_bytes(document):
    return (json.dumps(document, indent=2) + "\n").encode()


def read_manifest(path):
    try:
        data = Path(path).read_bytes()
        manifest = json.loads(data)
    except (OSError, ValueError) as error:
        raise RecoveryError(f"Cannot read the manifest {path}: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("format") != MANIFEST_FORMAT:
        raise RecoveryError(f"{path} is not a backup manifest ({MANIFEST_FORMAT}).")
    return manifest, hashlib.sha256(data).hexdigest()


def run_context(operator):
    return {
        "operator": operator or "",
        "os_user": getpass.getuser(),
        "host": platform.node(),
        "application_revision": os.environ.get("SOURCE_REVISION")
        or os.environ.get("RENDER_GIT_COMMIT")
        or "",
    }


# pg_dump


def pg_dump_version(executable):
    try:
        output = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, check=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise RecoveryError(f"Cannot run {executable}: {error}") from error
    match = re.search(r"\b(\d+)(?:\.\d+)*\b", output)
    if not match:
        raise RecoveryError(f"Cannot read the version of {executable}: {output!r}")
    return output, int(match.group(1))


def find_pg_dump(executable, server_version_num):
    path = shutil.which(executable or "pg_dump")
    if path is None:
        raise RecoveryError(
            "pg_dump was not found. Install the PostgreSQL client tools of the server's major "
            "version or newer, or give --pg-dump."
        )
    version, major = pg_dump_version(path)
    if major < server_version_num // 10000:
        raise RecoveryError(
            f"{version} cannot dump a PostgreSQL {server_version_num // 10000} server. Use "
            "pg_dump of the server's major version or newer."
        )
    return path, version


# Connection settings that are secrets: pg_dump could receive them only on its command line,
# except the password, which goes in its environment.
SECRET_PARAMETERS = frozenset(
    {"password", "sslpassword", "oauth_client_secret", "scram_client_key", "scram_server_key"}
)


def libpq_arguments():
    """The connection string and environment for pg_dump to reach the database Django uses.

    The environment is passed on unchanged (``PGSSLMODE`` and the like apply to pg_dump as they
    do to Django) and the connection settings Django uses take precedence over it. The password
    goes in the environment, never on the command line, where other users could read it.
    """
    from psycopg import conninfo, pq

    params = connection.get_connection_params()
    secrets = sorted(key for key in SECRET_PARAMETERS - {"password"} if params.get(key))
    if secrets:
        raise RecoveryError(
            f"The database connection sets {', '.join(secrets)}, which pg_dump could only "
            "receive on its command line. Make the archive yourself and take the manifest "
            "without --dump while nothing writes to the database."
        )
    keywords = {default.keyword.decode() for default in pq.Conninfo.get_defaults()}
    settings = {
        key: str(value)
        for key, value in params.items()
        if key in keywords and key not in SECRET_PARAMETERS and value not in (None, "")
    }
    settings.setdefault("application_name", "qm-lims backup_manifest")
    environment = dict(os.environ)
    if params.get("password"):
        environment["PGPASSWORD"] = str(params["password"])
    return conninfo.make_conninfo(**settings), environment


def dump(cursor, executable, archive, stream):
    """Run pg_dump into ``archive``, the new file open as ``stream``, from the snapshot of the
    transaction open on ``cursor``, and return the archive's checksum read from ``stream``.

    pg_dump writes to the file through ``/dev/fd``, never through its name, so a name replaced
    meanwhile (by a link, in a directory others can write to) cannot send the archive anywhere
    else. As a file of its own, the archive is seekable and pg_dump writes it complete with its
    data offsets, as with a path (to an inherited standard output, pg_dump on Linux appends a
    second table of contents instead).
    """
    descriptor = stream.fileno()
    if not os.path.exists(f"/dev/fd/{descriptor}"):
        raise RecoveryError(
            "This system has no /dev/fd: run pg_dump yourself and take the "
            "manifest without --dump while nothing writes to the database."
        )
    cursor.execute("SELECT pg_export_snapshot()")
    snapshot_id = cursor.fetchone()[0]
    dbname, environment = libpq_arguments()
    completed = subprocess.run(
        [
            executable,
            "--format=custom",
            "--no-owner",
            "--no-acl",
            f"--snapshot={snapshot_id}",
            f"--file=/dev/fd/{descriptor}",
            f"--dbname={dbname}",
        ],
        env=environment,
        pass_fds=(descriptor,),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()[-2000:]
        raise RecoveryError(
            f"pg_dump failed with exit status {completed.returncode}; no archive or manifest "
            f"was kept. {detail}"
        )
    created, named = os.fstat(descriptor), os.lstat(archive)
    if (created.st_dev, created.st_ino) != (named.st_dev, named.st_ino):
        raise RecoveryError(
            f"{archive} was replaced while pg_dump wrote the archive, which was not kept. Write "
            "backups to a directory only the operator can write to."
        )
    stream.seek(0)
    digest = hashlib.sha256()
    size = 0
    while block := stream.read(1 << 20):
        digest.update(block)
        size += len(block)
    return {
        "file": os.path.basename(archive),
        "format": "custom",
        "sha256": digest.hexdigest(),
        "size": size,
    }


# The two documents


def build_manifest(*, operator=None, archive=None, archive_stream=None, pg_dump=None):
    """Read the database once and return the manifest, running pg_dump into ``archive_stream``
    from the same snapshot when one is given."""
    with read_snapshot() as cursor:
        dumped = None
        dumped_with = None
        if archive_stream is not None:
            identity = database_identity(cursor)
            executable, dumped_with = find_pg_dump(pg_dump, identity["server_version_num"])
            dumped = dump(cursor, executable, archive, archive_stream)
        state = collect(cursor)
        checks = evidence_checks(state)
    return {
        "format": MANIFEST_FORMAT,
        "taken_at": state["database"]["snapshot_at"],
        "taken_by": run_context(operator),
        "archive": dumped,
        "pg_dump": dumped_with,
        **state,
        "checks": checks,
        "result": overall(checks),
    }


def take_backup(*, output, archive=None, operator=None, pg_dump=None, stdout=None):
    """Write the manifest to ``output`` (or ``stdout`` for ``-``) and, when ``archive`` is
    given, the archive of the same snapshot. Both files are created before the database is
    read, and neither is kept unless both are complete. Returns the manifest and its SHA-256."""
    to_stdout = output == "-"
    if archive is not None and (
        archive == "-" or (not to_stdout and os.path.realpath(archive) == os.path.realpath(output))
    ):
        raise RecoveryError("The manifest and the archive need two files.")
    refuse_existing(None if to_stdout else output, archive)
    with ExitStack() as files:
        manifest_stream = None if to_stdout else files.enter_context(new_file(output))
        archive_stream = files.enter_context(new_file(archive)) if archive else None
        manifest = build_manifest(
            operator=operator, archive=archive, archive_stream=archive_stream, pg_dump=pg_dump
        )
        data = evidence_bytes(manifest)
        # Both files are written out before either is closed: a failure removes both.
        if archive_stream is not None:
            finish(archive_stream)
        if to_stdout:
            stdout.write(data.decode(), ending="")
        else:
            manifest_stream.write(data)
            finish(manifest_stream)
    return manifest, hashlib.sha256(data).hexdigest()


def build_report(manifest, manifest_sha256, *, operator=None, archive=None):
    with read_snapshot() as cursor:
        state = collect(cursor)
        checks = [check_not_source(manifest["database"], state["database"])]
        checks.append(check_archive(manifest, archive))
        checks += compare(manifest, state)
        checks.append(check_sequences(manifest, state))
        checks += evidence_checks(state)
        checks.append(check_application())
    return {
        "format": REPORT_FORMAT,
        "checked_at": timezone.now().astimezone(UTC).isoformat(),
        "checked_by": run_context(operator),
        "database": state["database"],
        "manifest": {
            "sha256": manifest_sha256,
            "taken_at": manifest["taken_at"],
            "database": manifest["database"],
            "application_revision": manifest["taken_by"].get("application_revision", ""),
        },
        "archive": str(archive) if archive else None,
        "checks": checks,
        "result": overall(checks),
    }


def overall(checks):
    return FAILED if any(check["status"] == FAILED for check in checks) else PASSED


def summary_lines(checks):
    marks = {PASSED: "ok", FAILED: "FAILED", NOT_CHECKED: "not checked"}
    lines = []
    for check in checks:
        lines.append(f"[{marks[check['status']]}] {check['check']}: {check['summary']}")
        for problem in check["problems"]:
            lines.append(f"    - {problem}")
        hidden = check["problem_count"] - len(check["problems"])
        if hidden > 0:
            lines.append(f"    ... and {hidden} more")
    return lines
