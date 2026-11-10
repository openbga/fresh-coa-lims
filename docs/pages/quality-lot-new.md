---
title: New material lot
urls: quality:lot_new
views: quality.views.lot_new
templates: quality/form.html
models: quality.Lot, core.RuleSet
reviewed: 2026-11-10
---

## Purpose

Receive a manufacturing material lot into quarantine under an approved rule set.

## Who can use it

- Sign-in required. **Analysts** only; other roles receive 403, even though the list page shows the **New material lot** button to every viewer.

## Layout

- Title "New material lot", one form card with the fields below, **Receive lot** and **Cancel**.
- Errors appear above the form (whole-form errors) and beside fields.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Receive lot** | Always | Analyst | Creates the lot in Quarantine, shows "Lot received in quarantine." and opens the lot record |
| **Cancel** | Always | Any | Returns to Material lots without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | Audit event reason | Text, max 2000 | Yes | Why the lot is being received; stored on the audit event |
| Number | `Lot.number` | Text, max 80 | Yes | Lot identifier; must be unique |
| Material | `Lot.material` | Text, max 160 | Yes | Material name |
| Rules | `Lot.rules` | Choice of rule revisions | Yes | Rule set that fixes the required tests for this lot |

## Rules and hidden logic

- **Not the release requirements**: choosing a rule set does not assign approved specification or sampling requirements and does not show the lot is ready for testing. Requirements are assigned afterwards on Lot requirements and sampling; the rule set's required-test list is only part of the foundation path, not the whole native release gate.
- **Rule choices**: only rule revisions with status approved are offered. The chosen revision must also be effective now, else "An approved, effective rule revision is required."
- **Uniqueness**: "This lot number already exists." when the number is taken (exact match).
- **Defaults**: state Quarantine, revision 1, received by the signed-in user at the server time.
- **Audit**: writes `lot.received` with number, material and rule set.
- **Errors** return the form with status 422 and keep the entered values.

## Related pages

- [Material lots](/)
- Lot record (opened after saving).
- [Rule sets](/rules/)
- Assign requirements to a lot (after receipt).
