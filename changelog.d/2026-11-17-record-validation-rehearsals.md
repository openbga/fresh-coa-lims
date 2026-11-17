---
date: 2026-11-17
type: added
impact: high
title: Record rehearsals of recovery, downtime and upgrade
area: Validation
link: validation:rehearsal_list
pr: 43
---
Quality or an administrator records a rehearsal of recovery from backup, downtime and reconciliation, or an upgrade, and attaches its evidence files. A quality person who did not record it accepts it.

## Technical notes

- **Rehearsals** (`validation:rehearsal_list`, `rehearsal_new`, `rehearsal_detail`, `rehearsal_file_new`, `rehearsal_file`, `rehearsal_accept`, `rehearsal_withdraw`): quality or admin records a rehearsal of recovery from backup, downtime and reconciliation, or an upgrade, the recorder attaches its evidence files, and a quality person who did not record it accepts it. Guidance in `docs/operations.md` ("Validation records of the laboratory").
- The restore check's `raw data files` check also verifies rehearsal evidence files, and its summary counts both. `RAW_DATA_TOTAL_MAX_BYTES` is one ceiling for raw-data files and rehearsal evidence together, for both kinds of upload (`core.uploads.stored_bytes`); the refusal now reads "This deployment has reached its storage limit for files."
