---
title: Record sampling
urls: sampling:sampling_new
views: sampling.views.sampling_new
templates: catalog/form.html
models: sampling.SamplingRecord, quality.Sample, sampling.LotAssignment
reviewed: 2026-11-10
---

## Purpose

Records what was actually sampled from a lot against its assigned sampling plan, and creates the lot's sample.

## Who can use it

- Sign-in required. **analyst** role only; others (including quality) receive 403 Forbidden.
- Requires current requirements in state "Requirements assigned". Otherwise you are redirected to the lot with "Assign approved requirements before recording sampling."
- You are recorded as the sampler.
- The page itself does not check the lot state; the lot page only offers the button for quarantined lots, and for a lot no longer in Quarantine the form opens but submitting is refused with "Only quarantined lots accept new samples."

## Layout

- **Breadcrumbs**: Sampling, lot number, Record sampling. Title: "Record sampling ·" and the lot number.
- **Intro**: "Record what was actually sampled. You are recorded as the sampler."
- **Record card**: Sampling plan (plan and basis), Minimum amount, Instructions.
- **Form sections**: Sample, Sampling, Containers, Amount, "Deviation and reason". Buttons **Cancel** and **Record sampling**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record sampling** | Always | Analyst | Creates the sample and the sampling record; shows "Sample <reference> recorded." and returns to the lot |
| **Cancel** | Always | Analyst | Returns to the lot |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Sample reference | `Sample.reference` | Text, max 80, unique | Yes | Identifier of the new sample. |
| Purpose | `SamplingRecord.purpose` | Routine sampling, Resample for an investigation; optional, defaults to routine | No | Help: "A resample is new material collected for an investigation." |
| Original sample | `SamplingRecord.resample_of` | Choice of this lot's samples that have a sampling record | Resamples only | Help: "Resamples only: the sampled original this resample replaces." Label "Original sample". |
| Sampled at (time zone) | `SamplingRecord.sampled_at` | Date and time, default now | Yes | When it was sampled; also the sample's collected time. Cannot be in the future. |
| Location | `SamplingRecord.location` | Text, max 160 | Yes | Help: "Where the sample was taken." |
| Containers in lot | `SamplingRecord.containers_total` | Integer, at least 1 | Yes | Number of containers in the lot. |
| Containers sampled | `SamplingRecord.containers_sampled` | Integer, at least 1 | Yes | Number of containers sampled. |
| Container identifiers | `SamplingRecord.container_ids` | Text | Yes | Help: "Identifiers of the containers sampled, e.g. C1, C4, C8." |
| Total amount collected | `SamplingRecord.quantity` | Decimal, up to 14 digits, 4 decimals, above 0 | Yes | Amount collected. "Enter an amount greater than zero." otherwise. |
| Amount unit | `SamplingRecord.quantity_unit` | mg, g, kg, mL, L, units (items); defaults to the plan's unit | Yes | Must equal the plan's unit. |
| Deviation | `SamplingRecord.deviation` | Text | Conditional | Help: "Required when fewer containers or less material than the plan were sampled." |
| Reason | `SamplingRecord.reason` | Text, max 2000 | Yes | Why this is recorded; stored in the audit event. |

## Rules and hidden logic

- **Required containers** come from the approved plan and the number of containers in the lot: fixed number; 1 + square root of N rounded up; every container; or a percentage rounded up, never below 1 and never above the lot size.
- **Deviation**: when fewer containers than required or less than the plan's minimum amount are recorded, a deviation is required: "Record a deviation: plan requires <N> containers; <M> sampled; plan requires at least <amount> <unit>." (parts shown only for the shortfalls).
- **Other validations**: "More containers sampled than the lot contains." "Sampling time cannot be in the future." "Sampling plan <plan> vN is not effective at this sampling time. Assign current requirements to the lot first." (on Sampled at, when the time is outside the plan version's effective period) "The approved plan states amounts in <unit>." "This sample reference already exists." "The assigned sampling plan is not approved." "Only quarantined lots accept new samples."
- **Resample**: "Choose a sampled original sample of this lot to resample." when Resample has no original, or the original belongs to another lot or has no sampling record. "Only a resample names an original sample." when a routine sample names one. Whether a resample is authorised is not decided here.
- **Deviation assessment**: a record with a deviation creates a pending deviation assessment. Quality must accept it before the lot's sampling stops blocking QC disposition.
- **Hold**: if requirements are missing or on hold at submission, the hold reasons are shown as the error.
- **Effects, in one transaction**: a quality sample is created (lot revision +1, audit `sample.collected`) and a sampling record linking the lot, sample, assignment and plan version is stored (audit `sampling.recorded`).
- **Not enforced by this page**: compositing (permitted or not) is not checked.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Lot requirements and sampling (record page).
- Quality lot record: the new sample appears there for testing.
