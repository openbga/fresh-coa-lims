---
title: New resource use
urls: laboratory:use_new
views: laboratory.views.use_new
templates: ops/form.html
models: laboratory.ResourceUse, quality.Sample, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record the equipment and reagents used for a sample, gated by their fitness and your own qualification.

## Who can use it

- Sign-in required. Role: Analyst only; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Laboratory, Resource use, New use), title "New use", the introduction "Every resource and your own qualification for the activity must be eligible now. Refusals are audited.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record use** | Always | Role: Analyst only; others (including Quality and Reviewer) receive 403 | Saves and opens Resource use with "Recorded N eligible resource use(s)."; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Sample reference | `Sample.reference` | Text, max 80, trimmed | Yes | Sample the work is performed on, exactly as recorded; must exist ("No sample has this reference."). The use is stored against the sample's record number |
| Activity | `ResourceUse.activity` | Text, max 120 | Yes | Method or activity code; you need approved, current analyst qualification for it (matched case-insensitively) |
| Test code / Test profile revision | `ResourceUse.test_code`, `.profile_ref` | Text, max 80 / 120 | No | Context for the use; revision "If known." |
| Equipment / Reagents and standards | `ResourceUse.equipment`, `.reagent_lot` | Checkbox lists: all equipment; all lots except rejected ones | At least one in total | "Select at least one piece of equipment or reagent lot." |
| Reason or work context | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Eligible now means: you have an approved, current qualification for the activity and an active account; each equipment is in service, has a counting calibration that is a pass and not expired, and current approved qualification if it requires one; each lot is released, not rejected, not expired, not dated in the future, and every source lot is released, unrejected and unexpired. Other errors: "A reason is required."
- Every selected resource and you must be eligible now. If any is not, nothing is recorded as a use and the page shows "Work is blocked: …" naming each refusal (status 422). The refusal is audited as `resource.use_blocked` even though the action is rejected.
- On success one use row is written per resource with the evidence relied on, plus the audit event `resource.used`.

## Related pages

- [Resource use](/laboratory/uses/) (Cancel returns here)
- [Equipment](/laboratory/equipment/) and [Reagents and standards](/laboratory/reagents/) show each resource's eligibility
