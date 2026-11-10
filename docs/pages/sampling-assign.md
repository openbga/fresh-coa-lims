---
title: Assign requirements to a lot
urls: sampling:assign
views: sampling.views.assign
templates: catalog/form.html
models: sampling.LotAssignment, quality.Lot, catalog.Material
reviewed: 2026-11-10
---

## Purpose

Freezes the approved specification, its methods and the sampling plan that apply to a lot now, or records an applicability hold with the reasons if anything is missing.

## Who can use it

- Sign-in required. **analyst** or **quality** role; others receive 403 Forbidden.
- Only lots in Quarantine: otherwise you are redirected to the lot with "Only quarantined lots can receive requirements." (the server also refuses).
- Only before testing starts: once any analytical test exists for the lot you are redirected to the lot with "Testing has started on this lot, so its requirements cannot be reassigned. Controlled supersession of requirements after testing is not supported." (the server also refuses).

## Layout

- **Breadcrumbs**: Sampling, lot number, Assign requirements. Title: "Assign requirements ·" and the lot number.
- **Intro**: "The approved specification, its methods and the sampling plan effective now are frozen for this lot. If anything is missing or not approved, the lot is placed on an applicability hold with the reasons; nothing is guessed or merged."
- **Record card**: Lot, Material as received, Rule set, Current requirements ("None", "Requirements assigned" or "Applicability hold").
- **Form sections**: Applicability, Change control. Buttons **Cancel** and **Assign requirements**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign requirements** | Always | Analyst, quality | Resolves requirements; redirects to the lot with "Approved requirements frozen for this lot." or the warning "Applicability hold recorded: " followed by the reasons |
| **Cancel** | Always | Analyst, quality | Returns to the lot |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Material | `LotAssignment.material` | Choice of all materials | Yes | Help: "The controlled material this lot is." Prefilled from the current assignment, or a material whose name or code equals the lot's material as received. |
| Stage | `LotAssignment.stage` | Incoming material, In-process, Finished product, Stability | Yes | Stage of the material; prefilled from the current assignment. |
| Scope | `LotAssignment.scope` | Slug, max 60, default "general" | Yes | Help: "general, or a named market/customer overlay." |
| Reason | `LotAssignment.reason` | Text, max 2000 | Yes | Why requirements are assigned or changed. |

## Rules and hidden logic

- **What is resolved**: the approved specification version for the material, stage and scope that is effective at the time you submit; the approved effective version of each test's method; the approved effective sampling plan for the material and stage; and the lot's rule set. Nothing is merged or guessed.
- **Hold reasons** (any one produces a hold): "Rule set <code> v<N> is not approved and effective." / "No specification exists for <material> at stage <stage> and scope <scope>." / "Specification <code> has no approved version effective now." / "Method <code> has no approved version effective now." / "Rule set requires tests missing from the specification: <codes>" / "No sampling plan exists for <material> at stage <stage>." / "Sampling plan <code> has no approved version effective now."
- **Append-only**: each submission, ready or hold, adds a new assignment that supersedes the previous one.
- **Fixed after testing starts**: tests are bound to the frozen requirements, so a new assignment is refused once any analytical test exists for the lot: "Testing has started on this lot, so its requirements cannot be reassigned. Controlled supersession of requirements after testing is not supported." Nothing is recorded and the lot revision is unchanged. Not supported by this page: controlled supersession of requirements after testing.
- **Revision**: the lot's record revision increases by 1, so a disposition signing page opened earlier fails as stale.
- **Audit**: `lot.requirements_assigned` or `lot.requirements_held` with the specification and plan revision, payload hash and your reason.
- **Reason**: "A reason is required."
- A refused submission returns status 422 with the error.

## Related pages

- Lot requirements and sampling (record page).
- [Sampling plans](/sampling/plans/)
- [Specifications](/catalog/)
