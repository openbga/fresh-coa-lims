---
title: Remove QC check from a method version
urls: catalog:qc_check_remove
views: catalog.views.qc_check_remove
templates: catalog/form.html
models: catalog.MethodQCCheck, catalog.MethodRevision
reviewed: 2026-11-10
---

## Purpose

Removes one batch QC check from a draft method version, recording why.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- The check must belong to the version in the URL, otherwise 404.
- Only drafts: for an approved or withdrawn version you are redirected back to the method with "QC checks can only be removed from a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Remove <code>". Title: "Remove QC check <code> ·" and the version.
- **Intro**: "Removal from a draft is recorded in its history with your reason."
- **Record card**: QC check, Unit.
- **Form**: Reason. Buttons **Cancel** and **Remove QC check**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Remove QC check** | Always on this page | Quality | Deletes the check; shows "QC check <code> removed from draft <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| QC check | `MethodQCCheck.code`, `name` | Text | — | The check being removed. |
| Unit | `MethodQCCheck.unit` | Unit | — | Unit of its limits. |
| Reason | audit event reason | Text, max 2000 | Yes | Why the check is removed. |
| Expected revision | — | Hidden integer | Yes | Record revision when the page opened. |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before removing this QC check."
- **Draft only**: "QC checks can only be removed from a draft version." (page redirect) and "Only draft revisions can be changed." (server, if the version stopped being a draft meanwhile). Approved and withdrawn versions are immutable at the database level.
- **Effect**: record revision increases by 1; audit event `method_revision.qc_check_removed` keeps the removed check's content and your reason.
- Removing the last check from a batch method leaves it unapprovable until another is added.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
