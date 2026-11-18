---
title: Import results from a file
urls: analytical:import_file
views: analytical.imports.import_file
templates: analytical/import_form.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.Observation, analytical.RawDataFile, core.AuditEvent
reviewed: 2026-11-18
summary: Check the values the method's approved file import reads from a stored export for this test, enter the inputs the file does not hold, and record every row as the next replicate.
---

## Common tasks
### Check and record the values read
1. Compare each value under [[Values read from the file]] with the instrument's record.
2. Select the equipment and lots used, and enter any input the file does not hold for each row.
3. Say where the instrument's original data is kept in [[Original record]], then select [[Record imported results]].
### Import from a file already attached
1. On the test record, under [[Raw data files]], select [[Import results]] on the file's row.
## Good to know
- The values come from the stored file, read again by the server when you record them; nothing you type changes them.
- Every row that names the test is read. A file with more rows than replicates left is refused, so no row is left out.
- A cell that is empty or not a plain number refuses the whole file. Record such results by hand.
- An imported replicate is corrected like any other, with a reason; the imported original stays visible.
- A file attached with Attach raw data stays attached even when nothing can be imported from it.

## Purpose

Shows what the method's approved file import reads from one stored export for this test and records those rows as the test's next replicates, with the file and row each came from.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403, including admin without the analyst role.
- The file must be a raw-data file of this test; otherwise 404.
- A test that does not take an import now redirects you back to the test record with a warning (the rules of Import results).

## Layout

- Heading "Import results · T-n" and breadcrumbs.
- Summary card: Test, Lot and sample (or stability pull or reassessment), File (name and the first 12 characters of its SHA-256), Export, Format, Rows read, Replicates ("n of N recorded").
- **Values read from the file** (count of rows): one row per replicate to record, with the replicate number, the row of the file and the cell of each column read, exactly as written in the file. The footer says how many rows the file has below the column names and how many name this test.
- Form: equipment and reagent or standard lot checkboxes (as for recording an observation), one field "Row N: <input>" for each row and each calculation input the file does not hold, **Original record**, **Note**. Buttons **Cancel** and **Record imported results**.
- **Nothing imported**: when nothing can be imported from this file, a notice says why, adds "The file stays attached to the test as raw data." and offers **Back to the test** instead of the form.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record imported results** | The file can be imported | Analyst | Records one replicate per row; "n replicates imported."; returns to the test record |
| **Cancel** / **Back to the test** | Always | Analyst | Returns to the test record |
| **Import results** (Raw data files on the test record) | The test takes an import and no replicate was imported from that file | Analyst | Opens this page for that file |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Equipment used | `Observation.eligibility` | Checkboxes | When the method requires an instrument | Checked by the bench as for an observation entered by hand; the same evidence is kept on every imported replicate. |
| Reagent and standard lots used | `Observation.eligibility` | Checkboxes | When the method requires one | As above. |
| Row N: input | `Observation.inputs` | Decimal, at most 8 decimals, in the input's unit | Yes | A calculation input the file does not hold, for that row. |
| Original record | `Observation.raw_reference` | Text, max 200; starts with the file name | Yes | Where the instrument's original data is kept, for example its data system's project and run. |
| Note | `Observation.reason` | Text, max 2000 | No | Kept with each imported replicate. |
| Expected revision | — | Hidden integer | Yes | Test revision when the page opened. |
| Cells read (display) | `Observation.source` | Text as in the file | — | Kept with the replicate together with the row number. |

## Rules and hidden logic

- **Rows read**: rows below the column names whose test column holds the test number (case and surrounding spaces ignored) and, when the file import names one, whose selecting column holds its value. Each is one replicate, in file order. Blank rows are skipped. Rows are counted as the file's records from the first, as in the messages.
- **Nothing imported** (the notice): "No row of the file names T-n in column ..."; "n rows of the file name T-n, but none has ... in column ..."; "The file holds n rows for T-n and the test takes m more replicates. Every row that names the test in ... (and has ... in ..., when the file import selects rows) is read, so none is left out. Record the replicates by hand, with the reason the other rows do not count."; a row with more cells than the column names ("Row n has more cells than the column names in row h, so its values would be read from the wrong columns ..."); a row with more than 500 columns; a missing column ("Row 2 has no column named ..."), a column named twice, a file that is not in the stated encoding, or a cell that is empty or not a plain number ("Row 5, column ... holds ..., which is not a plain number with a decimal point. Nothing was recorded; enter this result by hand or correct the export."); a value the requirement cannot take ("Row n: The value has more than 8 decimal places.", a count that is not whole, or for a calculation an input with more than 8 decimals or 20 digits); "Results from this file are already recorded on this test."; "The stored file failed its integrity check."
- **Numbers**: an optional sign, digits with the file import's decimal mark and an optional exponent (1.25E+2 is recorded as 125). Thousands separators, units, less-than signs and text are refused, never converted. A value with more than 8 decimals is refused instead of rounded. A recorded value is written out in full (0.0000001, never 1E-7).
- **On recording**: the server locks the test, rejects a test changed since the page opened ("Record changed. Reload and review before continuing."), repeats every check, reads the stored file again and records all rows or none. A calculated result is calculated from the cells read and the inputs entered, with the method's formula; a refused row is named ("Row 6: ...").
- **Effect**: per row an observation with the file, the row and the cells read, and an audit event `observation.imported` with the file's name and SHA-256, the row, the cells, the reading and the hash of the file import. The test revision and the lot's (or pull's or reassessment's) revision rise by 1. A bench refusal is audited as for an observation entered by hand and stores nothing.
- **Later checks**: the test record, submission and review read every imported replicate's file again; one that no longer agrees blocks submission and review.

## Related pages

- Test record (return target; Raw data files list).
- Import results (upload), Correct observation, Submit for review, Sign review.
