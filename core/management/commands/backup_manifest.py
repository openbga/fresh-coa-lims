"""Record what the database holds when a backup is taken (see core.recovery)."""

import hashlib

from django.core.management.base import BaseCommand, CommandError

from core import recovery


class Command(BaseCommand):
    help = (
        "Write a backup manifest: each table's rows and fingerprint, the schema, the migrations "
        "and the checks of stored evidence, read in one read-only snapshot. With --dump, also "
        "run pg_dump from that same snapshot. Changes nothing in the database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            required=True,
            help="New file for the manifest (JSON), or - for standard output (the summary then "
            "goes to standard error).",
        )
        parser.add_argument(
            "--dump",
            metavar="ARCHIVE",
            help="Also write a pg_dump custom-format archive of the same snapshot to this new "
            "file, and record its SHA-256 in the manifest.",
        )
        parser.add_argument(
            "--pg-dump",
            metavar="PATH",
            help="pg_dump to run with --dump (default: pg_dump on PATH). Its major version must "
            "be at least the server's.",
        )
        parser.add_argument("--operator", help="Who takes the backup, as recorded in the manifest.")

    def handle(self, *args, **options):
        output, archive = options["output"], options["dump"]
        try:
            if archive is not None and archive == output:
                raise recovery.RecoveryError("The manifest and the archive need two files.")
            to_stdout = output == "-"
            recovery.refuse_existing(None if to_stdout else output, archive)
            manifest = recovery.build_manifest(
                operator=options["operator"], archive=archive, pg_dump=options["pg_dump"]
            )
            if to_stdout:
                data = recovery.evidence_bytes(manifest)
                self.stdout.write(data.decode(), ending="")
                digest = hashlib.sha256(data).hexdigest()
            else:
                digest = recovery.write_evidence(output, manifest)
        except (recovery.RecoveryError, OSError) as error:
            raise CommandError(str(error)) from error
        out = self.stderr if to_stdout else self.stdout
        for line in recovery.summary_lines(manifest["checks"]):
            out.write(line)
        tables = manifest["tables"]
        rows = sum(table["rows"] for table in tables.values())
        out.write(
            f"Manifest of {manifest['database']['name']} at {manifest['taken_at']}: "
            f"{len(tables)} tables, {rows} rows."
        )
        if manifest["archive"]:
            out.write(
                f"Archive {archive}: SHA-256 {manifest['archive']['sha256']}, "
                f"{manifest['archive']['size']} bytes ({manifest['pg_dump']})."
            )
        out.write(f"Manifest {'(standard output)' if to_stdout else output}: SHA-256 {digest}.")
        if manifest["result"] == recovery.FAILED:
            raise CommandError(
                "The manifest is written, but the database failed a check of its stored "
                "evidence (listed above). Keep the backup and investigate before relying on it."
            )
