"""Run the acceptance journeys in a database created for them and write their evidence.

    python manage.py acceptance_journeys --database NAME --output DIR --operator NAME

Run it with the release being accepted, in its own environment, against a new database that
has been migrated to that release and holds nothing else (docs/operations.md, "Acceptance
journeys"). It refuses a database other than the one named, so a run never lands in the
database the deployment normally uses (even a new one migrated for production before its first
account), and one that holds any account (every audit event names one), so it never writes
into a laboratory's records. Exits non-zero when any step failed; the
report is written either way.
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from validation.acceptance import AcceptanceRun, Evidence, write_report

NOT_EMPTY = (
    "Refusing to run: this database already holds accounts. The acceptance journeys create "
    "synthetic accounts, configuration and lots and keep them, so they run only in a new "
    "database created for them and migrated to this release. Nothing was changed."
)


class Command(BaseCommand):
    help = (
        "Run the acceptance journeys (passing, failing, corrected, rejected and amended "
        "records) in a new, empty database migrated to this release, and write their evidence "
        "to a new directory."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            required=True,
            dest="database_name",
            help="The name of the new database created for the run; it must be the database "
            "this process is connected to.",
        )
        parser.add_argument(
            "--output", required=True, help="A new directory for the evidence (must not exist)."
        )
        parser.add_argument(
            "--operator", required=True, help="Who runs the journeys, as the report names them."
        )

    def handle(self, *args, **options):
        output = Path(options["output"])
        operator = " ".join(options["operator"].split())
        if not operator:
            raise CommandError("Name the operator who runs the journeys.")
        if output.exists():
            raise CommandError(f"{output} already exists. Choose a new directory.")
        if not output.parent.is_dir():
            raise CommandError(f"{output.parent} does not exist.")
        connected = connection.settings_dict["NAME"]
        if options["database_name"] != connected:
            raise CommandError(
                f"Refusing to run: connected to the database {connected!r}, not "
                f"{options['database_name']!r}. Nothing was changed."
            )
        self._require_this_release()
        if get_user_model().objects.exists():
            raise CommandError(NOT_EMPTY)
        output.mkdir()
        self.stdout.write(f"Acceptance journeys in the database {connected!r}; evidence: {output}")
        run = AcceptanceRun(
            evidence=Evidence(output), operator=operator, log=lambda text: self.stdout.write(text)
        )
        try:
            run.run()
        finally:
            # Written even when the run is interrupted by an error it could not attribute.
            report = write_report(run, output)
        summary = report["summary"]
        line = (
            f"{summary['journeys_passed']} of {summary['journeys']} journeys passed; "
            f"{summary['steps_passed']} of {summary['steps']} steps passed. "
            f"Evidence in {output} (report.html, report.json, SHA256SUMS)."
        )
        if report["outcome"] != "passed":
            raise CommandError(f"Acceptance journeys failed: {line}")
        self.stdout.write(self.style.SUCCESS(f"Acceptance journeys passed: {line}"))

    def _require_this_release(self):
        """The journeys test this release's schema: the database must be migrated to it."""
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError(
                "Refusing to run: this release has migrations the database lacks. Run migrate "
                "with this release first."
            )
        if executor.loader.applied_migrations.keys() - executor.loader.disk_migrations.keys():
            raise CommandError(
                "Refusing to run: the database has migrations this release does not know."
            )
