---
date: 2026-11-16
type: added
impact: high
title: Export a lot's complete record as one package
area: Lots
link: quality:lot_list
pr: 33
---
**Export record** on the lot page downloads one ZIP file with a printed copy, an electronic copy, the lot's raw-data files and issued certificates byte for byte, and a checksum list. It is available to the admin, quality and auditor roles, and the export is recorded in the lot's audit trail.

## Technical notes

- Export of a lot's complete record: **Export record** on the lot page (admin, quality and auditor, the roles that read the audit trail) downloads one ZIP file with a printed copy (`record.pdf`), an electronic copy (`record.json`, schema `oq.lot-record/1`, every stored field with its label, kind and choices), the lot's raw-data files and issued certificates byte for byte, `manifest.json` and a `SHA256SUMS` list. Everything is read in one repeatable-read, read-only transaction. It covers the lot's receipt details, supplier certificates and accepted supplier results, requirement assignments, samples and sampling records, tests and the tests of its stability pulls, observations, raw-data files, investigations, QC batches, certificates, stability studies, reserves, retention obligations and holds, the instruments, reagent lots and contract laboratory reports used, the configuration they name (including the specification, method and rule set versions frozen in its requirements), every signature with its manifestation, the audit trail and its reviews. The checksums of stored files and the hashes stored with signatures, certificates, requirement assignments and approved versions are recomputed and each outcome is stated. The export states its purpose and is recorded in the lot's audit trail (`lot.record_exported`) with the package's SHA-256; nothing else changes.
