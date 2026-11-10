---
title: New sampling plan
urls: sampling:plan_new
views: sampling.views.plan_new
templates: catalog/form.html
models: sampling.SamplingPlan, sampling.SamplingPlanRevision, catalog.Material
reviewed: 2026-11-10
---

## Purpose

Creates a sampling plan for one material at one stage together with its draft version 1.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.

## Layout

- **Breadcrumbs**: Sampling, Sampling plans, New sampling plan.
- **Intro**: "One plan covers one material at one stage. Another quality approver signs each version before lots can be sampled against it."
- **Form sections**: Plan, Containers to sample, Amount, Procedure, Effective period, Change control.
- **Buttons**: **Cancel** (to Sampling plans) and **Create draft**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft** | Always | Quality | Creates the plan and draft version 1, shows "Sampling plan created with draft version 1." and opens the plan |
| **Cancel** | Always | Quality | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `SamplingPlan.code` | Slug, max 60, unique | Yes | Stable identifier. |
| Title | `SamplingPlan.title` | Text, max 200 | Yes | Plan title. |
| Material | `SamplingPlan.material` | Choice of all materials | Yes | Material covered. |
| Stage | `SamplingPlan.stage` | Incoming material, In-process, Finished product, Stability | Yes | Stage covered. |
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

- **Code**: "This plan code already exists."
- **Uniqueness**: "A sampling plan already exists for this material and stage. Create a new version of it instead."
- **Parameter shape**: "Enter a positive count or percentage." "A fixed plan needs a whole number of containers." "A percentage cannot exceed 100." "This basis takes no parameter." (for 1 + √N and Every container).
- **Amount**: "Enter an amount greater than zero."
- **Interval**: "The effective end must be after the start." (form) and "The effective end must be after the effective start." (server).
- **Draft start**: version 1 is a draft, record revision 1, author = you. Its content is fixed at creation; change it with a new version.
- **Audit**: `sampling_plan.created` and `sampling_plan_revision.created` with your reason. No signature yet.
- Date-time fields are labelled with the deployment time zone (setting `TIME_ZONE`, default UTC) and shown in it.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- [Sampling plans](/sampling/plans/)
- Sampling plan (record page), opened after creation.
- [Materials](/catalog/materials/)
