---
title: Calculation of a method version
urls: catalog:calculation_set
views: catalog.views.calculation_set
templates: catalog/form.html
models: catalog.MethodRevision, catalog.MethodCalculationInput
reviewed: 2026-11-12
---

## Purpose

Sets or replaces the formula, the result unit and the decimals of the calculation on a draft method version. Analysts then enter the inputs and the system calculates the result.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Only draft versions. Otherwise you are redirected to the method with "The calculation can only be changed on a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Calculation". Title: "Calculation ·" and the version.
- **Intro**: "Analysts enter the inputs and the system calculates the result with this formula. Add one input for each name the formula uses; approval checks that they match."
- **Form sections**: Calculation, Change control. When the version already has a formula, the fields start with its values.
- **Buttons**: **Cancel** and **Save calculation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save calculation** | Draft version | Quality | Stores the formula, unit and decimals; shows "Calculation set on <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Formula | `MethodRevision.calculation_formula` | Text, max 500 | Yes | Arithmetic over the input codes with + - * / and brackets; no functions or exponents. Names are a lower-case letter followed by lower-case letters, digits or underscores. |
| Unit of the calculated result | `MethodRevision.calculation_unit` | Controlled result unit list | Yes | A specification test that uses this method must be numeric with the same unit. |
| Decimals of the calculated result | `MethodRevision.calculation_decimals` | Whole number, 0 to 8 | Yes | The result is rounded half up to this many decimals when it is recorded. |
| Reason for change | audit event reason | Text, max 2000 | Yes | Stored in the audit event. |

## Rules and hidden logic

- **Validations**: the formula must parse ("Enter a formula." and the parser's message otherwise), the unit must be on the list and the decimals 0 to 8. "Only draft revisions can be changed." if the version stopped being a draft meanwhile.
- **Not checked here**: whether the names in the formula match the inputs, so inputs and formula can be entered in any order. Approval checks this and refuses a mismatch, no inputs, more than 12 inputs, or a missing unit or decimals.
- **Effect**: the record revision increases by 1; audit event `method_revision.calculation_set` keeps the calculation before and after, with your reason. Making the change makes you an editor, so you can no longer approve this version.
- **Immutability**: approval freezes the formula, unit, decimals and inputs; the database refuses later changes.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
- Add calculation input, Clear calculation.
