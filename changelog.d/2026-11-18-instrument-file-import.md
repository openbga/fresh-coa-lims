---
date: 2026-11-18
type: added
impact: high
title: Import results from an instrument's export file
area: Testing
link: catalog:methods
---
Quality can give a draft method version a **File import** that states how its instrument's export is read: the file's format, the column naming the test and the column of each input. It is approved with the version. On a test of that version, **Import results** attaches the export to the test's raw data and shows the values read from it for checking, with a field for anything the file does not hold. **Record imported results** then records every row as a replicate, with the file and the row it came from. A cell that is not a plain number refuses the whole file. Submission and review read the stored file again.

## Technical notes

- Migrations `catalog.0007_file_import` (the method version's `file_import`, changed on a draft like the calculation; the revision guard leaves it out of its comparison) and `analytical.0011_imported_observations` (`Observation.source_file` and `source`; a check constraint ties them together and an insert trigger requires a file of the same test).
- The file import is frozen in the method's approved content and in new test requirements as `oq.test-requirement/4` (the `/3` keys with an eight-key method whose `file_import` follows `oq.file-import/1`). Methods without one keep their earlier payloads and hashes.
- Delimited text only: comma, semicolon or tab; point or comma decimal; UTF-8, UTF-16 or Windows-1252; at most 100,000 rows of 500 columns, within `RAW_DATA_MAX_BYTES`. An export that cannot be imported is refused before it is stored.
- New pages `catalog:file_import_set`, `catalog:file_import_clear`, `analytical:import_new` and `analytical:import_file`; audit actions `method_revision.file_import_set`, `method_revision.file_import_cleared` and `observation.imported`.
