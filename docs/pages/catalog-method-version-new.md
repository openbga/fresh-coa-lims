---
title: New version of a method
urls: catalog:method_version_new
views: catalog.views.method_version_new
templates: catalog/form.html
models: catalog.MethodRevision, catalog.MethodQCCheck, catalog.MethodCalculationInput
reviewed: 2026-11-12
---

## Purpose

Creates the next draft version of a method.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, New version. Title: "New version of" and the code.
- **Intro**: "The new draft copies the QC checks (when it runs in a QC batch), the calculation and its inputs of the latest version. The resource options start as in that version."
- **Form sections**: Procedure, "Resources recorded with results", Suitability, Effective period, Change control.
- **Buttons**: **Cancel** (back to the method) and **Create draft version**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft version** | Always | Quality | Creates draft version N+1, shows "Draft <code> vN created." and returns to the method record |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Technique | `MethodRevision.technique` | Text, max 120 | Yes | Help: "e.g. HPLC-UV, FTIR, plate count." |
| Summary | `MethodRevision.summary` | Text | No | Free description; shown on the method record (when entered) and on the approval page. |
| Controlled procedure | `MethodRevision.document_ref` | Text, max 160 | Yes | Help: "Document ID and revision of the approved procedure." |
| Runs in a QC batch | `MethodRevision.requires_batch` | Checkbox | No | Help: "If set, add the batch QC checks to the draft before approval." |
| Records an instrument | `MethodRevision.requires_equipment` | Checkbox | No | Help: "If set, every result and batch QC entry must record at least one instrument." Fixed at creation; starts as in the latest version. |
| Records a reagent or standard | `MethodRevision.requires_reagent` | Checkbox | No | Help: "If set, every result and batch QC entry must record at least one reagent or standard lot." Fixed at creation; starts as in the latest version. |
| Suitability basis | `MethodRevision.suitability_kind` | Method validation, Compendial method verification, Method transfer, Documented fitness for intended use | Yes | Kind of evidence of suitability for intended use. |
| Suitability evidence | `MethodRevision.suitability_ref` | Text, max 200 | Yes | Help: "Stable ID or location of the approved validation or verification report." |
| Effective from (time zone) | `MethodRevision.effective_from` | Date and time | Yes | Start of the effective period, inclusive. |
| Effective until (time zone) | `MethodRevision.effective_until` | Date and time | Yes | Exclusive end. Help text: "Exclusive end. Approved versions of one record must not overlap." |
| Reason for change | `MethodRevision.change_reason` | Text, max 2000 | Yes | Why this change is made; stored on the new record and in its audit event. |


## Rules and hidden logic

- **Numbering**: highest existing version number plus one. The form is not prefilled from earlier versions, except the two resource options, which start as in the latest version.
- **QC checks**: if "Runs in a QC batch" is ticked and an earlier version exists, its QC checks (from the highest-numbered version) are copied into the draft. Otherwise none are copied.
- **Calculation**: the latest version's formula, result unit, decimals and inputs are copied into the draft whatever its status, so a copy of an incomplete draft stays incomplete until fixed. Change them with the calculation pages on the method record.
- **Interval**: "The effective end must be after the start." Overlap with approved versions is checked only at approval.
- **Audit**: `method_revision.created` with your reason.
- Date-time fields are labelled with the deployment time zone (setting `TIME_ZONE`, default UTC) and shown in it.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
