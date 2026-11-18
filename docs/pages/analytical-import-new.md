---
title: Import results
urls: analytical:import_new
views: analytical.imports.import_new
templates: analytical/raw_file_form.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.RawDataFile, core.AuditEvent
reviewed: 2026-11-18
summary: Upload the instrument's export file for a test. It is read with the method's approved file import, attached to the test as raw data, and its values shown for checking before they are recorded.
---

## Common tasks
### Import results from an instrument export
1. On the test record, select [[Import results]].
2. Choose the export in [[Instrument export]] and select [[Attach and read]].
3. Check the values read from the file on the next page, then record them.
### Leave without attaching a file
1. Select [[Cancel]] to return to the test record.
## Good to know
- The button appears only when the test's method version has an approved file import and the test still takes replicates.
- The export is read before it is stored. One that cannot be imported as it is is refused and not stored; an attached export is never changed or deleted.
- Enter the test number, for example T-12, as the sample name on the instrument: rows are matched by it.
- Attaching the file makes you an author of the test's data: you cannot review the test or sign the lot's QC disposition.

## Purpose

First step of importing results from an instrument export. The file is read with the method's approved file import; when it can be imported it is stored with the test's raw data, exactly as received, and the next page shows what was read from it.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403, including admin without the analyst role.
- A test that does not take an import now redirects you back to the test record with a warning (see Rules).

## Layout

- Heading "Import results · T-n" and breadcrumbs.
- Summary card: Test, Lot and sample ("Lot and stability pull" or "Lot and reassessment"), Export (what produces the file), Format (separator, decimal mark, encoding, row of the column names), Rows read (the column naming the test and any column and value selecting rows), Size limit.
- Form: **Instrument export**. Buttons **Cancel** and **Attach and read**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Import results** (test record header) | The test takes an import (see Rules) | Analyst | Opens this page |
| **Attach and read** | Always | Analyst | Reads the file; when it can be imported, attaches it with the description "Instrument export for import", shows "Export attached. Check the values read from it." and opens the page that shows the values read |
| **Cancel** | Always | Analyst | Returns to the test record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Instrument export | `RawDataFile.content`, `filename`, `size`, `sha256` | File, up to the size limit shown | Yes | Kept exactly as received with the test's raw data, then read with the method's approved file import. |

## Rules and hidden logic

- **When the test takes an import** (otherwise a warning on the test record): the test is Open and its lot is in quarantine (or its stability pull or reassessment takes testing); no supplier's result stands in place of it; its method version has a file import ("Method ... revision ... does not read an instrument file; record each replicate by hand."); the result is not qualitative ("A qualitative result is recorded by hand, with what was observed."); no contract laboratory reported it; it is in a QC batch when its method runs in one ("Assign this test to a QC batch before recording results."); and a replicate is still to be recorded ("All replicates are recorded. Correct a value instead.").
- **Read before storing**: the file is read as the page that follows would read it. When nothing can be imported from it (the refusals listed for Import results from a file, such as a missing column, a cell that is not a plain number, more rows than replicates left or a value with more than 8 decimals), the reason shows under **Instrument export** followed by "Nothing was stored.", with status 422; the file is not attached and the test does not change.
- **Attaching**: the same rules as Attach raw data: the size limit, at most 20 files per test, no second copy of a file already attached ("This file content is already attached to this test."), and the deployment's storage limit. Each refusal returns this page with status 422 and stores nothing.
- **Effect**: the file is stored, the test revision and the lot's (or pull's or reassessment's) revision rise by 1 and `rawdata.attached` is audited. No result is recorded on this page.

## Related pages

- Test record (where the button is, and the return target).
- Import results from a file (the next page), Attach raw data.
