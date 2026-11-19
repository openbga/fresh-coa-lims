---
title: Correct QC result
urls: analytical:qc_correct
views: analytical.views.qc_correct
templates: analytical/form.html, analytical/_summary.html
models: analytical.QCResult, analytical.QCBatch
reviewed: 2026-11-19
summary: Correct a recorded QC result by adding a linked correction with a reason. The original value stays visible on the batch record.
---

## Common tasks
### Correct a QC result
1. Enter the corrected value in [[Observed value]] and tick the equipment and lots used.
2. Check [[Original record]], which starts with the earlier location.
3. Enter the [[Reason for correction]] and select [[Correct QC result]].
### Correct a value again
1. On the batch record, select [[Correct]] on the check's row. It corrects the newest value.
## Good to know
- The batch QC status is worked out again from the current values, so a correction can change QC failed to QC passed.
- Any analyst may correct a QC result, also one recorded by someone else. Both count as authors of the batch's QC.
- Corrections close once a test in the batch is submitted.
- Suitable resources the method version lists narrow the equipment and lot choices; a required one makes the field required.

## Purpose

Correct a recorded QC result by adding a linked correction; the original stays visible.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Correct CHECK · BATCH". Summary: QC check, Acceptance, "Value being corrected".
- Form: **Observed value**, **Equipment used**, **Reagent and standard lots used**, **Original record** (prefilled), **Reason for correction**, **Cancel**, **Correct QC result**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Correct QC result** | Always | Analyst | "QC correction recorded; the original value is preserved."; returns to the batch |
| **Cancel** | Always | Analyst | Returns to the batch |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Observed value | `QCResult.value` | Decimal, 8 decimals | Yes | Corrected value |
| Equipment used | `QCResult.eligibility` (equipment) | Checkboxes from the bench | When the method requires equipment | Hidden when the bench offers none and the method does not require one |
| Reagent and standard lots used | `QCResult.eligibility` (reagents) | Checkboxes from the bench | When the method requires a lot | As for equipment |
| Original record | `QCResult.raw_reference` | Text, max 200 | Yes | Source of the corrected value |
| Reason for correction | `QCResult.reason` | Text, max 2000 | Yes | "The original value stays visible in the record." |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the batch record with the warning "This QC result can no longer be corrected." (batch closed, QC frozen, or the result already corrected). QC is frozen once a test in the batch has been submitted; a test superseded before it was ever submitted does not count, one superseded after submission does.
- **Bench checks**: without a configured bench the page redirects to the batch record with "No bench check is configured; results are held." The bench checks your current qualification for the batch method and every instrument and lot selected; a refusal shows "Refused: <subject>: <reason>" on the refused checkbox list or above the form, nothing is saved and the bench audits the attempt. A method that requires equipment or a reagent or standard lot refuses an entry with none selected. The evidence is frozen on the correction (`QCResult.eligibility`) and in its audit event. The bench checks the correcting analyst.
- **Suitable resources**: the lines come from the approved content of the method version the batch is frozen to. Where it lists instrument categories, every instrument selected must be of a listed category; a lot of a kind it lists (reagent, reference standard or prepared solution), or prepared from a lot of such a kind, must be a listed one or prepared from one, while lots of other kinds stay open; every required line must be answered, and such a line makes the matching field required on the form; an instrument whose line asks for it needs an approved, current qualification whose activity is the method code. These refusals appear with the calibration, service, release and expiry refusals, nothing is saved, and the refusal is audited (`resource.use_blocked`).
- **Preconditions**: batch Open and no test in it submitted (same messages as recording); "This QC result has already been corrected."
- **Effect**: a new row supersedes the old; batch revision rises by 1; `qc.corrected` is audited with before and after values and the bench evidence. The batch QC status is recalculated from the current values.
- The link is offered on the batch record to every analyst, including for results recorded by others.

## Related pages

- QC batch record (return target).
