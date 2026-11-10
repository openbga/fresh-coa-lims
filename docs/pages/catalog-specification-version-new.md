---
title: New version of a specification
urls: catalog:specification_version_new
views: catalog.views.specification_version_new
templates: catalog/form.html
models: catalog.SpecificationRevision, catalog.SpecificationTest
reviewed: 2026-11-10
---

## Purpose

Creates the next draft version of an existing specification, starting from the tests of its latest version.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.

## Layout

- **Breadcrumbs**: Specifications and methods, the specification code, New version. Title: "New version of" and the code.
- **Intro**: "The new draft copies the tests of the latest version. Its effective period must not overlap an approved version when it is approved."
- **Form sections**: Basis, Effective period, Change control.
- **Buttons**: **Cancel** (back to the specification) and **Create draft version**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft version** | Always | Quality | Creates draft version N+1, shows "Draft <code> vN created from the latest version." and opens the version page |
| **Cancel** | Always | Quality | Returns to the specification |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Basis | `SpecificationRevision.basis` | Text | Yes | Help: "Scientific, compendial or contractual basis for these limits." Not prefilled from the previous version. |
| Effective from (time zone) | `SpecificationRevision.effective_from` | Date and time | Yes | Start of the effective period, inclusive. |
| Effective until (time zone) | `SpecificationRevision.effective_until` | Date and time | Yes | Exclusive end. Help text: "Exclusive end. Approved versions of one record must not overlap." |
| Reason for change | `SpecificationRevision.change_reason` | Text, max 2000 | Yes | Why this change is made; stored on the new record and in its audit event. |


## Rules and hidden logic

- **Numbering**: the new version number is the highest existing number plus one.
- **Copied tests**: every test line of the highest-numbered version, whatever its status (including Withdrawn), is copied into the new draft with you as creator. You can then add or remove lines.
- **Interval**: "The effective end must be after the start." The overlap check happens only at approval ("Effective dates overlap an approved version."), not here.
- **Several drafts** may exist at once; the page does not prevent it.
- **Audit**: `specification_revision.created`, recording which version the tests were copied from, with your reason.
- Date-time fields are labelled with the deployment time zone (setting `TIME_ZONE`, default UTC) and shown in it.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Specification (record page).
- Specification version (record page), opened after creation.
