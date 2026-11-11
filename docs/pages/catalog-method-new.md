---
title: New method
urls: catalog:method_new
views: catalog.views.method_new
templates: catalog/form.html
models: catalog.Method, catalog.MethodRevision
reviewed: 2026-11-10
---

## Purpose

Creates a method and its draft version 1, linking the controlled procedure and suitability evidence.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Another quality user must approve the version.

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, New method.
- **Intro**: "Link the controlled procedure and the evidence that the method is suitable for its intended use. Another quality approver signs the version before tests can rely on it."
- **Form sections**: Method, Procedure, Suitability, Effective period, Change control.
- **Buttons**: **Cancel** (to the Methods list) and **Create draft**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft** | Always | Quality | Creates the method and draft version 1, shows "Method created with draft version 1." and opens the method record |
| **Cancel** | Always | Quality | Returns to Methods |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `Method.code` | Slug, max 60, unique | Yes | Stable identifier. |
| Title | `Method.title` | Text, max 200 | Yes | Method title. |
| Technique | `MethodRevision.technique` | Text, max 120 | Yes | Help: "e.g. HPLC-UV, FTIR, plate count." |
| Summary | `MethodRevision.summary` | Text | No | Free description; shown on the method record (when entered) and on the approval page. |
| Controlled procedure | `MethodRevision.document_ref` | Text, max 160 | Yes | Help: "Document ID and revision of the approved procedure." |
| Runs in a QC batch | `MethodRevision.requires_batch` | Checkbox | No | Help: "If set, add the batch QC checks to the draft before approval." |
| Suitability basis | `MethodRevision.suitability_kind` | Method validation, Compendial method verification, Method transfer, Documented fitness for intended use | Yes | Kind of evidence of suitability for intended use. |
| Suitability evidence | `MethodRevision.suitability_ref` | Text, max 200 | Yes | Help: "Stable ID or location of the approved validation or verification report." |
| Effective from (time zone) | `MethodRevision.effective_from` | Date and time | Yes | Start of the effective period, inclusive. |
| Effective until (time zone) | `MethodRevision.effective_until` | Date and time | Yes | Exclusive end. Help text: "Exclusive end. Approved versions of one record must not overlap." |
| Reason for change | `MethodRevision.change_reason` | Text, max 2000 | Yes | Why this change is made; stored on the new record and in its audit event. |


## Rules and hidden logic

- **Code**: "This method code already exists."
- **Interval**: "The effective end must be after the start." (form) and "The effective end must be after the effective start." (server).
- **QC checks**: creating a batch method does not add checks. Add at least one on the method record before approval ("A method that runs in a QC batch needs at least one QC check.").
- **Audit**: `method.created` and `method_revision.created` with your reason. No signature yet.
- **Draft content** is fixed at creation; change it by creating a new version.
- Date-time fields are labelled with the deployment time zone (setting `TIME_ZONE`, default UTC) and shown in it.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- [Methods](/catalog/methods/)
- Method (record page), opened after creation.
