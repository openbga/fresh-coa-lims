---
title: Add sample
urls: quality:sample_new
views: quality.views.sample_new
templates: quality/form.html
models: quality.Sample, quality.Lot
reviewed: 2026-11-10
---

## Purpose

Record a sample taken from a quarantined lot so results can be recorded against it.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403. The **Add sample** link on the lot record is shown only to analysts while the lot is Quarantine.

## Layout

- Title "Add sample · <lot number>", the form, **Add sample** and **Cancel**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add sample** | Always | Analyst | Creates the sample and returns to the lot record |
| **Cancel** | Always | Any | Returns to Material lots without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | Audit event reason | Text, max 2000 | Yes | Why the sample is recorded |
| Reference | `Sample.reference` | Text, max 80 | Yes | Sample identifier; unique across all lots |
| Collected at | `Sample.collected_at` | Date and time, deployment time zone | Yes | When the sample was taken; defaults to now |

## Rules and hidden logic

- **Identity only**: this form records the sample reference and time. It does not record sampling-plan provenance, quantity or deviations. For native disposition each sample also needs a sampling record against the assigned plan (Record sampling on Lot requirements and sampling), and any deviation needs an accepted independent assessment.
- **Lot state**: only a Quarantine lot accepts samples ("Only quarantined lots accept new samples."). The lot is locked while saving.
- **Uniqueness**: "This sample reference already exists."
- **Revision**: the lot revision increases by 1, so open signing pages for this lot must be reloaded.
- **Audit**: writes `sample.collected` with lot, reference and collection time.
- Unknown lot: 404. Errors return status 422 with entered values kept.

## Related pages

- Lot record.
- Lot requirements and sampling; Record sampling.
- Record result (development-only manual result).
