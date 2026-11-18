---
title: Clear file import of a method version
urls: catalog:file_import_clear
views: catalog.views.file_import_clear
templates: catalog/form.html
models: catalog.MethodRevision, core.AuditEvent
reviewed: 2026-11-18
summary: Remove the file import from a draft method version. Analysts then record its results by hand.
---

## Common tasks
### Clear the file import
1. Check the export shown under [[Record]].
2. Explain why in [[Reason]], then select [[Clear file import]]. The method record opens.
### Keep the file import
1. Select [[Cancel]].
## Good to know
- To change the columns or the format, use [[Change file import]] on the method record instead.
- The cleared file import stays in the history with your reason.
- Clearing makes you an editor of the draft, so you can no longer approve it.
- If someone changes the draft after you open this page, clearing is refused. Reload and try again.

## Purpose

Removes the file import from a draft method version, so analysts record the results of tests of that version by hand.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only.
- Only draft versions. Otherwise you are redirected to the method with "The file import can only be changed on a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Clear file import". Title: "Clear file import ·" and the version.
- **Intro**: "Analysts then record the results of this version by hand. Clearing is recorded in the history with your reason."
- **Record card**: Export ("None" when there is no file import).
- **Form**: Reason. Buttons **Cancel** and **Clear file import**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Clear file import** | Draft version | Quality | Removes the file import; shows "File import cleared from draft <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Export | `MethodRevision.file_import` (`source`) | Text | — | The file import being cleared. |
| Reason | audit event reason | Text, max 2000 | Yes | Why the file import is cleared. |
| Expected revision | — | Hidden integer | Yes | Record revision when the page opened. |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before clearing the file import."
- **Nothing to clear**: "This version has no file import." (server).
- **Draft only**: "Only draft revisions can be changed." if the version stopped being a draft meanwhile.
- **Effect**: record revision increases by 1; audit event `method_revision.file_import_cleared` keeps the removed file import and your reason.
- **Form behaviour**: an invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
- File import of a method version.
