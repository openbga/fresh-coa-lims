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

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record use** | Always | Role: Analyst only; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Sample reference | `Sample.reference` | Text, max 80 | Yes | Must exist ("No sample has this reference.") |
| Activity | `ResourceUse.activity` | Text, max 120 | Yes | You need approved current qualification for it |
| Test code / Test profile revision | `ResourceUse.test_code`, `.profile_ref` | Text | No | Context for the use |
| Equipment / Reagents and standards | `ResourceUse.equipment`, `.reagent_lot` | Checkbox lists | At least one | "Select at least one piece of equipment or reagent lot." |
| Reason or work context | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Every selected resource and you must be eligible now. If any is not, nothing is recorded as a use and the page shows "Work is blocked: …" naming each refusal (status 422). The refusal is audited as `resource.use_blocked` even though the action is rejected.
- On success one use row is written per resource with the evidence relied on, plus the audit event `resource.used`.

## Related pages

- [Resource use](/laboratory/uses/)
