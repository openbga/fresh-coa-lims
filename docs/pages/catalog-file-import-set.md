---
title: File import of a method version
urls: catalog:file_import_set
views: catalog.views.file_import_set
templates: catalog/form.html
models: catalog.MethodRevision, catalog.MethodCalculationInput, core.AuditEvent
reviewed: 2026-11-18
summary: Describe how the instrument's export file is read into results: the file format, the rows of a test and the column of each input. Only a draft method version can be changed.
---

## Common tasks
### Describe the export of the method's instrument
1. Name the [[Export]] and choose the [[Column separator]], [[Decimal mark]] and [[Text encoding]] of the file.
2. Enter the [[Row of the column names]] and the [[Column naming the test]].
3. Under Columns, enter the column of each input the file holds; leave the others blank.
4. Give the [[Reason for change]] and select [[Save file import]]. The method record opens.
### Read only one peak or wavelength
1. Enter the [[Column selecting rows]] and the [[Value selecting rows]], for example Peak Name and the analyte's name.
## Good to know
- Copy the column names exactly as the export writes them. Case and the spaces around a name are ignored.
- An input left blank is entered by the analyst for each row when importing, for example a sample mass.
- Approval checks that every column you name belongs to an input of the calculation, or to the result when there is none.
- Analysts enter the test number, for example T-12, as the sample name on the instrument; rows are matched by it.
- Saving makes you an editor of the draft, so you can no longer approve it.

## Purpose

Sets or replaces the file import of a draft method version: how the delimited text export of the method's instrument is read into results. Analysts can then import results for tests of this version instead of typing them. The import is approved and frozen with the version.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Only draft versions. Otherwise you are redirected to the method with "The file import can only be changed on a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · File import". Title: "File import ·" and the version.
- **Intro**: "Analysts can then import results from the instrument's export instead of typing them. Each row that names the test is one replicate. Approval checks that the columns match the calculation."
- **Form sections**: Export, Rows of the test, Columns, Change control. When the version already has a file import, the fields start with its values.
- **Columns**: one field per calculation input, labelled "Column for <input name> (<code>, <unit>)", in the order the inputs were added. A version without a calculation has the single field **Column holding the result**.
- **Buttons**: **Cancel** and **Save file import**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save file import** | Draft version | Quality | Stores the file import; shows "File import set on <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Export | `MethodRevision.file_import` (`source`) | Text, max 200 | Yes | What produces the file, for example the spectrometer's result table export. Analysts see it when they import. |
| Column separator | `file_import.delimiter` | Comma, Semicolon or Tab | Yes | What separates the columns of a row. |
| Decimal mark | `file_import.decimal` | Point (12.5) or Comma (12,5) | Yes | A comma is refused with comma-separated columns. |
| Text encoding | `file_import.encoding` | UTF-8, UTF-16 (with byte-order mark) or Windows-1252 | Yes | How the file's text is stored. A UTF-8 byte-order mark is accepted. |
| Row of the column names | `file_import.header_row` | Whole number, 1 to 50; starts at 1 | Yes | Rows above it are not read. |
| Column naming the test | `file_import.id_column` | Text, max 100 | Yes | The column that holds the test number on each row. |
| Column selecting rows | `file_import.filter_column` | Text, max 100 | No | For a file with several rows per sample, such as one per peak or wavelength. |
| Value selecting rows | `file_import.filter_value` | Text, max 100 | With the column above | Only rows with this value in that column are read. |
| Column for an input / Column holding the result | `file_import.columns` | Text, max 100 | At least one (the result column when there is no calculation) | The column holding that input on each row. Blank: the analyst enters the input for each row. |
| Reason for change | audit event reason | Text, max 2000 | Yes | Stored in the audit event. |

## Rules and hidden logic

- **Validations** (form error, status 422): "Name the column of at least one input."; "Give both the column and the value, or neither."; from the server: "A file whose columns are separated by commas cannot use a comma as decimal mark."; "Each column of the file is used once: the column that names the test, the column that selects rows and each mapped column are different columns."; "Only draft revisions can be changed." if the version stopped being a draft meanwhile.
- **Not checked here**: whether the columns belong to the calculation's inputs, so the calculation can still change. Approval refuses "File import: The mapping reads fields the calculation does not have: ..." and, for a version without a calculation, "File import: ... map only the result column." or "File import: Map the column that holds the result."
- **Effect**: the record revision increases by 1; audit event `method_revision.file_import_set` keeps the file import before and after, with your reason. A new version of the method starts with a copy of the latest version's file import.
- **Immutability**: approval freezes the file import with the version; the database refuses later changes. Tests assigned under this version carry it in their frozen requirement.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary plus refusals from the server as form-level errors.
- Not enforced by this page: whether the export holds the instrument's complete original data. Where it does not, the method's procedure says where that data is kept; analysts record its location when importing.

## Related pages

- Method (record page).
- Clear file import, Calculation, Add calculation input, Approve method version.
- Import results (the test pages that use this file import).
