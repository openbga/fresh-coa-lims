---
title: Add characteristic
urls: catalog:evidence_characteristic_new
views: catalog.evidence_views.characteristic_new
templates: catalog/form.html
models: catalog.MethodEvidenceCharacteristic, catalog.MethodEvidence
reviewed: 2026-11-19
summary: Add one performance characteristic to a draft evidence record, with its acceptance criterion, the result obtained and whether the criterion was met.
---

## Common tasks

### Add a characteristic

1. Choose the [[Characteristic]]. Describe it in [[Detail]] when it helps; it is required for Other.
2. Enter the [[Acceptance criterion]], the [[Result obtained]] and whether the [[Criterion]] was met.
3. Enter the [[Reason]] and select [[Add characteristic]]. The record opens.

### Leave without adding

1. Select [[Cancel]] to return to the record.

## Good to know

- Only a draft takes characteristics. They cannot be edited; to correct one, remove it and add it again.
- A record has at most 30 characteristics.
- Adding one counts as changing the draft, so you cannot approve that record.
- "Not met" with a "Suitable" conclusion blocks approval until Deviations explains it.

## Purpose

Adds an evaluated performance characteristic to a draft evidence record.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403.
- A record that is not a draft redirects to the record with "Only a draft record can be changed."

## Layout

- **Header**: "Add characteristic · MEV-n" with the introduction "One performance characteristic the study evaluated, with the acceptance criterion set in advance and the result the report gives."
- **Record panel**: Record, Method. **Form sections**: Characteristic, Criterion and result, Change control. Buttons **Cancel** and **Add characteristic**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add characteristic** | Draft | Analyst, reviewer, quality | Adds it; message "<characteristic> added to MEV-n."; opens the record |
| **Cancel** | Always | Same | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Characteristic | `MethodEvidenceCharacteristic.characteristic` | Specificity or selectivity, Range and response (linearity), Accuracy, Repeatability, Intermediate precision, Reproducibility, Detection limit, Quantitation limit, Robustness, Comparison between laboratories, Other | Yes | What was evaluated |
| Detail | `MethodEvidenceCharacteristic.detail` | Text, max 160 | For Other | What was evaluated, e.g. recovery levels |
| Acceptance criterion | `MethodEvidenceCharacteristic.criterion` | Text, max 4000 | Yes | Criterion set in advance |
| Result obtained | `MethodEvidenceCharacteristic.result` | Text, max 4000 | Yes | The report's result |
| Criterion | `MethodEvidenceCharacteristic.outcome` | Met, Not met | Yes | Whether the criterion was met |
| Reason | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `MethodEvidence.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Validations**: "Say what was evaluated." (Other without detail); "A record has at most 30 characteristics."; "A reason is required."; "Only a draft record can be changed."
- **Effect**: the record's revision increases by 1; audit event `method_evidence.characteristic_added` with the characteristic and your reason. Characteristics are immutable once saved.
- **Independence**: adding counts as changing the draft.
- **Stale record**: "Record changed. Reload before saving." when the record changed after the page opened (checked under the record lock).

## Related pages

- Method evidence record
- Remove characteristic
