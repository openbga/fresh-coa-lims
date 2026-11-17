---
title: Clear calculation of a method version
urls: catalog:calculation_clear
views: catalog.views.calculation_clear
templates: catalog/form.html
models: catalog.MethodRevision, catalog.MethodCalculationInput
reviewed: 2026-11-17
summary: Remove the calculation from a draft method version: its formula, result unit, decimals and every input. Results are then entered directly.
---

## Common tasks
### Clear the calculation
1. Check the formula shown under [[Record]].
2. Explain why in [[Reason]], then select [[Clear calculation]]. The method record opens.
### Keep the calculation
1. Select [[Cancel]].
## Good to know
- Every input is removed too. To change only the formula, use [[Change formula]] on the method record instead.
- The cleared calculation, inputs included, stays in the history with your reason.
- Clearing makes you an editor of the draft, so you can no longer approve it.
- If someone changes the draft after you open this page, clearing is refused. Reload and try again.

## Purpose

Removes the calculation, with all its inputs, from a draft method version so results are entered directly again.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Only draft versions. Otherwise you are redirected to the method with "The calculation can only be changed on a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Clear calculation". Title: "Clear calculation ·" and the version.
- **Intro**: "Clearing removes the formula, the result unit, the decimals and every input. It is recorded in the history with your reason."
- **Record card**: Formula ("None" when not set).
- **Form**: Reason. Buttons **Cancel** and **Clear calculation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Clear calculation** | Draft version | Quality | Removes formula, unit, decimals and inputs; shows "Calculation cleared from draft <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Formula | `MethodRevision.calculation_formula` | Text | — | The formula being cleared. |
| Reason | audit event reason | Text, max 2000 | Yes | Why the calculation is cleared. |
| Expected revision | — | Hidden integer | Yes | Record revision when the page opened. |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before clearing the calculation."
- **Nothing to clear**: "This version has no calculation." (server).
- **Draft only**: "Only draft revisions can be changed." if the version stopped being a draft meanwhile.
- **Effect**: record revision increases by 1; audit event `method_revision.calculation_cleared` keeps the removed calculation, including its inputs, and your reason.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
- Calculation, Add calculation input.
