---
date: 2026-11-16
type: added
impact: high
title: Backup manifests and restore checks kept as evidence
area: Deployment
pr: 31
---
Two commands let an operator record what a backup should contain and check a restored copy against it. The report can be kept as evidence of the restore, and the application image includes the PostgreSQL client tools.

## Technical notes

- Backup and restore checks. `python manage.py backup_manifest --output FILE [--dump ARCHIVE]` reads the database in one read-only snapshot and writes a manifest: each table's row count and SHA-256 fingerprint, the columns, constraints, indexes, triggers and functions, the applied migrations and the sequence positions, and checks of the stored evidence (signature hashes and their audit events, issued certificate and raw-data checksums, enabled triggers). With `--dump` it runs `pg_dump` from the same snapshot and records the archive's checksum. `python manage.py verify_restore --manifest FILE --report FILE [--archive ARCHIVE]` checks a restored copy against the manifest and writes a report to keep as evidence; it fails unless the copy equals the manifest and its evidence is intact, and refuses the source database as a copy. Both commands only read, never overwrite a file and write files readable by their owner only.
- The application image includes the PostgreSQL 17 client tools (`pg_dump`, `pg_restore`, `psql`), and the container smoke job backs up, restores and checks a seeded copy with the image.
