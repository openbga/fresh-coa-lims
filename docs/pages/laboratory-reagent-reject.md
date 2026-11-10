---
title: Reject reagent lot
urls: laboratory:reagent_reject
views: laboratory.views.reagent_reject
templates: ops/form.html
models: laboratory.ReagentLot, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Permanently block a lot (and anything prepared from it). Protective, so no signature is needed.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Reject lot** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the lot is rejected |

## Rules and hidden logic

- Messages: "State why the lot is rejected."; "The lot is already rejected."
- Rejection is irreversible; the database refuses any other change. Event `reagent.rejected`. Earlier recorded uses are kept for impact assessment.

## Related pages

- Reagent lot record
