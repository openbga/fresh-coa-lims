---
title: Add QC check to a method version
urls: catalog:qc_check_new
views: catalog.views.qc_check_new
templates: catalog/form.html
models: catalog.MethodQCCheck, catalog.MethodRevision
reviewed: 2026-11-10
---

## Purpose

Adds a batch QC check (for example a blank or control) with acceptance limits to a draft method version that runs in a QC batch.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Only draft versions that run in a QC batch. Otherwise you are redirected to the method with "QC checks can only be added to a draft batch method version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Add QC check". Title: "Add QC check ·" and the version.
- **Intro**: "Each analytical batch run with this method must record these checks within limits."
- **Form sections**: QC check, "Acceptance limits (inclusive)", Change control.
- **Buttons**: **Cancel** and **Add QC check**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add QC check** | Draft batch version | Quality | Adds the check; shows "QC check <code> added to <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `MethodQCCheck.code` | Slug, max 40 | Yes | Help: "e.g. blank or control." Unique within the version. |
| Name | `MethodQCCheck.name` | Text, max 160 | Yes | Check name. |
| Unit | `MethodQCCheck.unit` | Controlled unit list; the first entry "% (percent)" is preselected | Yes | Unit of the limits. |
| Lower limit | `MethodQCCheck.lower_limit` | Decimal, 20 digits, 8 decimals | One limit at least | Inclusive lower limit. |
| Upper limit | `MethodQCCheck.upper_limit` | Decimal, same format | One limit at least | Inclusive upper limit. |
| Reason for change | audit event reason | Text, max 2000 | Yes | Stored in the audit event. |

## Rules and hidden logic

- **Validations**: "This QC check code is already on the version." "Enter at least one limit." "The upper limit must not be below the lower limit." "QC checks apply only to methods that run in a QC batch." "Only draft revisions can be changed."
- **Effect**: the version's record revision increases by 1; audit event `method_revision.qc_check_added` with your reason. Adding a check makes you an editor, so you can no longer approve this version.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
