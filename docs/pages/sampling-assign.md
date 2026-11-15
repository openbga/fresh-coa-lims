---
title: Assign requirements to a lot
urls: sampling:assign
views: sampling.views.assign
templates: catalog/form.html
models: sampling.LotAssignment, quality.Lot, catalog.Material
reviewed: 2026-11-15
---

## Purpose

Freezes the approved specification, its methods and the sampling plan that apply to a lot now, or records an applicability hold with the reasons if anything is missing.

## Who can use it

- Sign-in required. **analyst** or **quality** role; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the analyst or quality role acts with that role only, with no exception to the independence rules.
- Only lots in Quarantine: otherwise you are redirected to the lot with "Only quarantined lots can receive requirements." (the server also refuses).
- Only before testing starts: once any analytical test exists for the lot you are redirected to the lot with "Testing has started on this lot, so its requirements cannot be assigned again. Quality can replace them with a signature." (the server also refuses). From then on only Replace lot requirements changes them.

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
| Reason | `LotAssignment.reason` | Text, max 2000 | Yes | Why requirements are assigned or changed; stored on the assignment and in its audit event. |

## Rules and hidden logic

- **What is resolved**: the approved specification version for the material, stage and scope that is effective at the time you submit; the approved effective version of each test's method; the approved effective sampling plan for the material and stage, or, once the lot has been sampled, the plan version its samples were taken under; and the version in force of the lot's own rule set. Nothing is merged or guessed.
- **Hold reasons** (any one produces a hold): "Rule set <code> v<N> is not approved and effective." / "No specification exists for <material> at stage <stage> and scope <scope>." / "Specification <code> has no approved version effective now." / "Method <code> has no approved version effective now." / "Rule set requires tests missing from the specification: <codes>" / "No sampling plan exists for <material> at stage <stage>." / "Sampling plan <code> has no approved version effective now."
- **Sampling plan once sampled**: when the lot's current sampling records were all taken under one plan version of the same material and stage, that version is kept, also when a later version is in force, so the samples stay valid. When the material or the stage changes, or the records name several plan versions, the plan in force is taken and the sampling gate lists the samples that do not fit ("Sample <ref> was sampled under <plan vN>; the current requirements use <plan vM>.").
- **Append-only**: each submission, ready or hold, adds a new assignment that supersedes the previous one. No signature is needed before testing starts.
- **Rule set**: the lot follows its own rule set. When the lot's version has stopped applying (expired, or retired by a later approval) and another approved version of the same rule set is in force, that version is used, and a submission that freezes requirements moves the lot to it; a hold leaves the lot on the version it had. With no version of the rule set in force the hold reason is "Rule set <code> v<N> is not approved and effective.", naming the lot's version. The lot never moves to a different rule set.
- **Fixed after testing starts**: tests are bound to the frozen requirements, so a new assignment is refused once any analytical test exists for the lot: "Testing has started on this lot, so its requirements cannot be assigned again. Quality can replace them with a signature." Nothing is recorded and the lot revision is unchanged. After testing has started, quality changes the requirements on Replace lot requirements, with a signature.
- **Revision**: the lot's record revision increases by 1, so a disposition signing page opened earlier fails as stale.
- **Audit**: `lot.requirements_assigned` or `lot.requirements_held` with the specification and plan revision, payload hash and your reason, and the rule set version before and after when the lot moved to another version.
- **Reason**: a blank reason is refused by the form ("This field is required.").
- A refused submission returns status 422 with the error.

## Related pages

- Lot requirements and sampling (record page).
- Replace lot requirements (once testing has started).
- [Sampling plans](/sampling/plans/)
- [Specifications](/catalog/)
