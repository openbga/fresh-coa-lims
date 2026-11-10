---
title: Correct QC result
urls: analytical:qc_correct
views: analytical.views.qc_correct
templates: analytical/form.html, analytical/_summary.html
models: analytical.QCResult, analytical.QCBatch
reviewed: 2026-11-10
---

## Purpose

Correct a recorded QC result by adding a linked correction; the original stays visible.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.

## Layout

- Heading "Correct CHECK · BATCH". Summary: QC check, Acceptance, "Value being corrected".
- Form: **Observed value**, **Original record** (prefilled), **Reason for correction**, **Cancel**, **Correct QC result**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Correct QC result** | Always | Analyst | "QC correction recorded; the original value is preserved."; returns to the batch |
| **Cancel** | Always | Analyst | Returns to the batch |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Observed value | `QCResult.value` | Decimal, 8 decimals | Yes | Corrected value |
| Original record | `QCResult.raw_reference` | Text, max 200 | Yes | Source of the corrected value |
| Reason for correction | `QCResult.reason` | Text, max 2000 | Yes | "The original value stays visible in the record." |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the batch record with the warning "This QC result can no longer be corrected." (batch closed, QC frozen, or the result already corrected).
- **Preconditions**: batch Open and no test in it submitted (same messages as recording); "This QC result has already been corrected."
- **Effect**: a new row supersedes the old; batch revision rises by 1; `qc.corrected` is audited with before and after values. The batch QC status is recalculated from the current values.
- The link is offered on the batch record to every analyst, including for results recorded by others.

## Related pages

- QC batch record (return target).
