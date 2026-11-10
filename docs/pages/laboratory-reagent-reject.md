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

- Breadcrumbs (Laboratory, Reagents and standards, the lot, Reject), title "Reject LOT", the introduction "Rejection is permanent and blocks the lot and any solution prepared from it.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Reject lot** | Always (the lot record offers it only while not rejected) | Analyst, Reviewer or Quality; others receive 403 | Saves and opens the lot record with "Lot rejected."; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the lot is rejected |

## Rules and hidden logic

- The lot must exist (404 otherwise). A lot may be rejected from Awaiting release or Released.
- Messages: "State why the lot is rejected."; "The lot is already rejected."
- Rejection is irreversible; the database refuses any other change. Solutions prepared from the lot fail the use gate ("Source lot … was rejected.") but are not themselves marked rejected. Event `reagent.rejected`. Earlier recorded uses are kept for impact assessment.

## Related pages

- Reagent lot record
