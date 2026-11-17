---
title: Reject reagent lot
urls: laboratory:reagent_reject
views: laboratory.views.reagent_reject
templates: ops/form.html
models: laboratory.ReagentLot, core.AuditEvent
reviewed: 2026-11-17
summary: Reject a reagent, standard or prepared solution lot so it can no longer be used. Rejection is permanent and also blocks solutions prepared from it.
---

## Common tasks
### Reject the lot
1. In [[Reason]], say why the lot is rejected.
2. Select [[Reject lot]]. The lot record opens showing Rejected.
### Leave without rejecting
1. Select [[Cancel]] to return to the lot record. Nothing changes.
## Good to know
- Rejection cannot be undone.
- A lot already released for use can be rejected too.
- Solutions prepared from it are refused when used, but keep their own state label.
- Uses already recorded with the lot are kept for impact assessment.
- No signature is needed: rejection only protects, so any analyst, reviewer or quality user can do it.

## Purpose

Permanently block a lot (and anything prepared from it). Protective, so no signature is needed.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

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
