---
title: New version of a sampling plan
urls: sampling:plan_version_new
views: sampling.views.plan_version_new
templates: catalog/form.html
models: sampling.SamplingPlanRevision
reviewed: 2026-11-10
---

## Purpose

Creates the next draft version of a sampling plan.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.

## Layout

- **Breadcrumbs**: Sampling, Sampling plans, plan code, New version. Title: "New version of" and the code.
- **Form sections**: Containers to sample, Amount, Procedure, Effective period, Change control.
- **Buttons**: **Cancel** (back to the plan) and **Create draft version**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft version** | Always | Quality | Creates draft version N+1, shows "Draft <code> vN created." and returns to the plan |
| **Cancel** | Always | Quality | Returns to the plan |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Basis | `SamplingPlanRevision.basis` | Fixed number of containers; 1 + √N containers, rounded up; Every container; Percentage of containers, rounded up | Yes | How many containers to sample. |
| Parameter | `SamplingPlanRevision.parameter` | Decimal, up to 8 digits, 3 decimals | Fixed and percentage only | Help: "Containers for a fixed plan, or percent for a percentage plan; otherwise blank." |
| Compositing allowed | `SamplingPlanRevision.composite_allowed` | Checkbox | No | Whether samples may be composited. Shown on the plan; not checked by the sampling record. |
| Minimum total amount | `SamplingPlanRevision.minimum_quantity` | Decimal, up to 14 digits, 4 decimals, above 0 | Yes | Minimum total amount to collect. |
| Amount unit | `SamplingPlanRevision.quantity_unit` | mg, g, kg, mL, L, units (items) | Yes | Unit of the amounts. |
| Instructions | `SamplingPlanRevision.instructions` | Text | Yes | Sampling tools, location, precautions, labelling. |
| Rationale | `SamplingPlanRevision.rationale` | Text | Yes | Help: "Why the plan is representative. A sampling scheme is a configured choice reviewed by quality, not a legal requirement." |
| Effective from (time zone) | `SamplingPlanRevision.effective_from` | Date and time | Yes | Start of the effective period, inclusive. |
| Effective until (time zone) | `SamplingPlanRevision.effective_until` | Date and time | Yes | Exclusive end. Help text: "Exclusive end. Approved versions of one record must not overlap." |
| Reason for change | `SamplingPlanRevision.change_reason` | Text, max 2000 | Yes | Why this change is made; stored on the new record and in its audit event. |


## Rules and hidden logic

- **Numbering**: highest existing version number plus one. The form is not prefilled from earlier versions.
- **Parameter shape**: "Enter a positive count or percentage." "A fixed plan needs a whole number of containers." "A percentage cannot exceed 100." "This basis takes no parameter." (for 1 + √N and Every container).
- **Amount**: "Enter an amount greater than zero."
- **Interval**: "The effective end must be after the start." (form) and "The effective end must be after the effective start." (server).
- **Overlap** with approved versions is checked only at approval.
- **Audit**: `sampling_plan_revision.created` with your reason.
- Date-time fields are labelled with the deployment time zone (setting `TIME_ZONE`, default UTC) and shown in it.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Sampling plan (record page).
