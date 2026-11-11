---
title: Correct sampling record
urls: sampling:sampling_correct
views: sampling.views.sampling_correct
templates: catalog/form.html
models: sampling.SamplingRecord, quality.Sample
reviewed: 2026-11-10
---

## Purpose

Corrects a sampling record by adding a linked, newer record. The original stays visible in the history.

## Who can use it

- Sign-in required. **analyst** role only; others receive 403 Forbidden. Any analyst may correct, not only the original sampler.
- Only the latest record of a quarantined lot: otherwise you are redirected to the lot with "Sampling for a dispositioned lot cannot be corrected here." (lot no longer in Quarantine) or "This record was already corrected. Correct the latest record." The server repeats both checks on submission.

## Layout

- **Breadcrumbs**: Sampling, lot number, "Correct <sample reference>". Title: "Correct sampling ·" and the sample reference.
- **Intro**: "A correction adds a linked record. The original stays visible in the history."
- **Record card**: Sample, Sampled by, Original containers.
- **Form** prefilled with the record's values: sections Sampling, Containers, Amount, "Deviation and reason". Buttons **Cancel** and **Record correction**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record correction** | Always | Analyst | Adds the correction; shows "Correction recorded; the original record is preserved." and returns to the lot |
| **Cancel** | Always | Analyst | Returns to the lot |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Sampled at (time zone) | `SamplingRecord.sampled_at` | Date and time | Yes | Corrected time; cannot be in the future. |
| Location | `SamplingRecord.location` | Text, max 160 | Yes | Help: "Where the sample was taken." |
| Containers in lot | `SamplingRecord.containers_total` | Integer, at least 1 | Yes | Number of containers in the lot. |
| Containers sampled | `SamplingRecord.containers_sampled` | Integer, at least 1 | Yes | Number sampled. |
| Container identifiers | `SamplingRecord.container_ids` | Text | Yes | Help: "Identifiers of the containers sampled, e.g. C1, C4, C8." |
| Total amount collected | `SamplingRecord.quantity` | Decimal, 4 decimals, above 0 | Yes | Corrected amount. "Enter an amount greater than zero." otherwise. |
| Amount unit | `SamplingRecord.quantity_unit` | mg, g, kg, mL, L, units (items) | Yes | Must equal the plan's unit. |
| Deviation | `SamplingRecord.deviation` | Text | Conditional | Required when below the plan. |
| Reason for correction | `SamplingRecord.reason` | Text, max 2000 | Yes | Why the record is corrected; blank at start. |

## Rules and hidden logic

- **Only the latest record of an open lot**: the two redirect messages above, also raised by the server.
- **Plan effective at sampling time**: "Sampling plan <plan> vN is not effective at this sampling time. Assign current requirements to the lot first." (on Sampled at) when the sampled time is outside the plan version's effective period.
- **Same checks as recording**: required containers and deviation rule against the plan version originally used, plus "More containers sampled than the lot contains." "Sampling time cannot be in the future." "The approved plan states amounts in <unit>."
- **What is kept**: the sample, assignment, plan version, purpose, original sample (for a resample) and original sampler stay the same; you are stored as the recorder. The sample reference cannot change.
- **Deviation assessment**: a correction that has a deviation creates a new pending assessment for the correction; the original's assessment no longer counts (the lot page still shows its old status on the corrected row, with no **Assess deviation** button).
- **Effect**: a new record linked to the original is added, the original shows "Corrected", the lot's record revision increases by 1, and audit event `sampling.corrected` stores the before and after.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Lot requirements and sampling (record page).
