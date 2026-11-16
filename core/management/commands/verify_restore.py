"""Check a restored copy of the database against its backup manifest (see core.recovery)."""

import hashlib

from django.core.management.base import BaseCommand, CommandError

from core import recovery


class Command(BaseCommand):
    help = (
        "Check the restored database this command connects to against a backup manifest and "
        "write the report to keep as evidence. Fails unless the copy equals the manifest and "
        "its stored evidence is intact. Changes nothing in the database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--manifest", required=True, help="Manifest written by backup_manifest."
        )
        parser.add_argument("--report", required=True, help="New file for the report (JSON).")
        parser.add_argument(
            "--archive", help="The restored archive, to compare with the checksum in the manifest."
        )
        parser.add_argument("--operator", help="Who checks the restore, as recorded in the report.")

    def handle(self, *args, **options):
        report_path = options["report"]
        try:
            recovery.refuse_existing(report_path)
            manifest, manifest_sha256 = recovery.read_manifest(options["manifest"])
            with recovery.new_file(report_path) as stream:
                report = recovery.build_report(
                    manifest,
                    manifest_sha256,
                    operator=options["operator"],
                    archive=options["archive"],
                )
                data = recovery.evidence_bytes(report)
                stream.write(data)
            digest = hashlib.sha256(data).hexdigest()
        except (recovery.RecoveryError, OSError) as error:
            raise CommandError(str(error)) from error
        for line in recovery.summary_lines(report["checks"]):
            self.stdout.write(line)
        self.stdout.write(f"Report {report_path}: SHA-256 {digest}.")
        failed = [check for check in report["checks"] if check["status"] == recovery.FAILED]
        if failed:
            raise CommandError(
                f"The restore check failed: {len(failed)} of {len(report['checks'])} checks "
                "failed (listed above). Do not rely on this copy."
            )
        self.stdout.write(self.style.SUCCESS("The restored copy matches its manifest."))
