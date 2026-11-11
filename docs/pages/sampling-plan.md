---
title: Sampling plan record
urls: sampling:plan
views: sampling.views.plan_detail
templates: sampling/plan_detail.html
models: sampling.SamplingPlan, sampling.SamplingPlanRevision, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Shows a sampling plan with every version, its content, signatures and history. Quality users manage drafts here.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New version**, **Withdraw draft**: **quality** role only (**Withdraw draft** on drafts).
- **Review and approve**: quality, draft, and only when you did not author or edit that version; otherwise "Another quality approver must sign this draft." is shown.

## Layout

- **Breadcrumbs**: Sampling, Sampling plans, plan code. Under the heading: title, material code and stage.
- **One card per version**, newest first: heading "Version N" with status; draft buttons for quality; facts Material and stage, Containers to sample, Minimum total amount, Instructions, Rationale, Effective, Record revision, Author; then signatures or "Not signed."
- **Empty state**: "No versions" ("Create the first version of this plan.").
- **History**: audit events for the plan and all its versions, oldest first.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New version** | Quality role | Quality | Opens the New version form |
| **Withdraw draft** | Draft, quality | Quality | Opens the Withdraw page |
| **Review and approve** | Draft, quality, independent of author and editors | Quality | Opens the Approve page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Containers to sample | `SamplingPlanRevision.basis`, `parameter`, `composite_allowed` | Basis name, with the number (and "%" for percentage) and "compositing allowed" when set | — | Sampling rule. |
| Minimum total amount | `SamplingPlanRevision.minimum_quantity`, `quantity_unit` | Decimal with unit | — | Least amount to collect. |
| Instructions | `SamplingPlanRevision.instructions` | Text | — | Procedure. |
| Rationale | `SamplingPlanRevision.rationale` | Text | — | Why the plan is representative. |
| Effective | `SamplingPlanRevision.effective_from`, `effective_until` | Date and time range | — | End exclusive. |
| Record revision | `SamplingPlanRevision.revision` | Integer | — | Increases at approval and withdrawal. |
| Author | `SamplingPlanRevision.author` | User | — | Who created the version. |

## Rules and hidden logic

- **Immutability**: approved and withdrawn versions cannot be changed at the database level; draft content is fixed at creation.
- **Effective intervals** are half-open and approved versions of one plan may not overlap.
- **Independence**: the author, or anyone who changed the draft, cannot approve it.
- **Order**: versions newest first; history oldest first.
- Audit actions are shown as stored, for example `sampling_plan_revision.created`.

## Related pages

- [Sampling plans](/sampling/plans/)
- New version, Approve sampling plan, Withdraw draft.
- Lot requirements and sampling pages link to the plan frozen for a lot.
