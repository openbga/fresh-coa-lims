---
title: Remove calculation input from a method version
urls: catalog:calculation_input_remove
views: catalog.views.calculation_input_remove
templates: catalog/form.html
models: catalog.MethodCalculationInput, catalog.MethodRevision
reviewed: 2026-11-12
---

## Purpose

Removes one input from the calculation of a draft method version, recording why.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- The input must belong to the version in the URL, otherwise 404.
- Only drafts: for an approved or withdrawn version you are redirected back to the method with "Calculation inputs can only be removed from a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Remove <code>". Title: "Remove calculation input <code> ·" and the version.
- **Intro**: "Removal from a draft is recorded in its history with your reason."
- **Record card**: Input, Unit.
- **Form**: Reason. Buttons **Cancel** and **Remove input**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Remove input** | Always on this page | Quality | Deletes the input; shows "Calculation input <code> removed from draft <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Input | `MethodCalculationInput.code`, `name` | Text | — | The input being removed. |
| Unit | `MethodCalculationInput.unit` | Unit | — | Unit of the input. |
| Reason | audit event reason | Text, max 2000 | Yes | Why the input is removed. |
| Expected revision | — | Hidden integer | Yes | Record revision when the page opened. |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before removing this input."
- **Draft only**: "Only draft revisions can be changed." if the version stopped being a draft meanwhile.
- **Effect**: record revision increases by 1; audit event `method_revision.calculation_input_removed` keeps the removed input and your reason.
- Removing an input that the formula uses leaves the version unapprovable until the formula or the inputs are fixed.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
- Add calculation input, Calculation.
