---
title: Remove characteristic
urls: catalog:evidence_characteristic_remove
views: catalog.evidence_views.characteristic_remove
templates: catalog/form.html
models: catalog.MethodEvidenceCharacteristic, catalog.MethodEvidence
reviewed: 2026-11-19
summary: Remove a characteristic from a draft evidence record, with a reason. The removal stays in the record's history.
---

## Common tasks

### Remove a characteristic

1. Check the characteristic shown on the page.
2. Explain why in [[Reason]] and select [[Remove characteristic]]. The record opens.

### Keep it

1. Select [[Cancel]].

## Good to know

- Only a draft record loses characteristics.
- The removed characteristic is kept in the history with your reason.
- Removing counts as changing the draft, so you cannot approve that record.
- If the record changed after you opened this page, removal is refused. Reload and try again.

## Purpose

Removes a characteristic from a draft evidence record while keeping what was removed in the audit trail.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403.
- A record that is not a draft redirects to the record with "Only a draft record can be changed." A characteristic of another record gives 404.

## Layout

- **Header**: "Remove characteristic · MEV-n" with the introduction "Removal from a draft is recorded in its history with your reason."
- **Record panel**: Characteristic, Acceptance criterion, Result obtained, Criterion. **Form**: Reason; buttons **Cancel** and **Remove characteristic**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Remove characteristic** | Draft | Analyst, reviewer, quality | Deletes it; message "<characteristic> removed from draft MEV-n."; opens the record |
| **Cancel** | Always | Same | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | audit reason | Text, max 2000 | Yes | Why it is removed |
| Expected revision (hidden) | `MethodEvidence.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before saving." when the record changed after the page opened (checked under the record lock).
- **Effect**: the record's revision increases by 1; audit event `method_evidence.characteristic_removed` with the removed characteristic and your reason.

## Related pages

- Method evidence record
- Add characteristic
