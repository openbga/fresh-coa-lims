---
title: Record QC result
urls: analytical:qc_record
views: analytical.views.qc_record
templates: analytical/form.html, analytical/_summary.html
models: analytical.QCBatch, analytical.QCResult
reviewed: 2026-11-12
---

## Purpose

Record the result of one QC check of a batch.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- An unknown check code gives 404.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Record CHECK · BATCH". Summary: Batch, QC check, Acceptance, Unit.
- Form: **Observed value**, **Equipment used**, **Reagent and standard lots used**, **Original record**, **Cancel**, **Record QC result**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record QC result** | Always | Analyst | Saves; "CHECK recorded."; returns to the batch |
| **Cancel** | Always | Analyst | Returns to the batch |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Observed value | `QCResult.value` | Decimal, 8 decimals, unit from the check | Yes | "Exact value as read; at most 8 decimal places. Never enter a nondetect as zero." |
| Equipment used | `QCResult.eligibility` (equipment) | Checkboxes from the bench | When the method requires equipment | Hidden when the bench offers none and the method does not require one |
| Reagent and standard lots used | `QCResult.eligibility` (reagents) | Checkboxes from the bench | When the method requires a lot | As for equipment |
| Original record | `QCResult.raw_reference` | Text, max 200 | Yes | Notebook page, instrument file or worksheet |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the batch record with the warning "QC entries for this batch are closed." (batch not Open, or a test in it already submitted).
- **Preconditions**: batch Open ("This batch is closed to QC entries."); no test in the batch submitted ("QC cannot change after test results in this batch are submitted."); check not already recorded ("This QC check is recorded. Correct it instead.").
- **Blank record**: "Record where the original QC observation is kept."
- **Bench checks**: without a configured bench the page redirects to the batch record with "No bench check is configured; results are held." The bench checks your current qualification for the batch method and every instrument and lot selected; a refusal shows "Refused: <subject>: <reason>" on the refused checkbox list or above the form, nothing is saved and the bench audits the attempt. A method that requires equipment or a reagent or standard lot refuses an entry with none selected. The evidence is frozen on the QC result (`QCResult.eligibility`) and in its audit event.
- **Effect**: batch revision rises by 1; `qc.recorded` is audited with whether the value conforms and the bench evidence. A failing value is saved and sets batch QC to failed.
- The batch recorder counts as data author for independence: they cannot review or reject tests or the batch.

## Related pages

- QC batch record (return target).
