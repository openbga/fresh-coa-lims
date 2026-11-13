---
title: Add calculation input to a method version
urls: catalog:calculation_input_new
views: catalog.views.calculation_input_new
templates: catalog/form.html
models: catalog.MethodCalculationInput, catalog.MethodRevision
reviewed: 2026-11-12
---

## Purpose

Adds a named input (for example a peak area or a sample mass) that analysts enter when the method calculates its result.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Only draft versions. Otherwise you are redirected to the method with "Calculation inputs can only be changed on a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Add calculation input". Title: "Add calculation input ·" and the version.
- **Intro**: "A calculation has 1 to 12 inputs. The analyst enters one value for each, in the order added."
- **Form sections**: Input, Change control.
- **Buttons**: **Cancel** and **Add input**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add input** | Draft version | Quality | Adds the input; shows "Calculation input <code> added to <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `MethodCalculationInput.code` | Text, max 40 | Yes | The name the formula uses: a lower-case letter, then lower-case letters, digits or underscores. Unique within the version. |
| Name | `MethodCalculationInput.name` | Text, max 160 | Yes | What the analyst enters, shown beside the value field. |
| Unit | `MethodCalculationInput.unit` | Controlled unit list (result and quantity units plus µL, µg, mmol/L, mol/L, peak area, AU and factor); the first entry is preselected | Yes | Unit of the value the analyst enters. |
| Reason for change | audit event reason | Text, max 2000 | Yes | Stored in the audit event. |

## Rules and hidden logic

- **Validations**: "Use a lower-case letter followed by lower-case letters, digits or underscores (40 at most)." "This input code is already on the version." "A calculation has at most 12 inputs." The database also refuses a thirteenth input.
- **Effect**: the record revision increases by 1; audit event `method_revision.calculation_input_added` with your reason. Adding an input makes you an editor, so you can no longer approve this version.
- **Approval**: the names the formula uses must be exactly the input codes; an input the formula does not use blocks approval.
- **Immutability**: approval freezes the inputs; the database refuses later changes.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
- Calculation, Remove calculation input.
