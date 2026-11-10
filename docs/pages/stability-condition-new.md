---
title: Add storage condition
urls: stability:condition_new
views: stability.views.condition_new
templates: ops/form.html
models: stability.ProtocolCondition, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Add an approved storage condition to a draft protocol.

## Who can use it

- Sign-in required. Roles: Analyst or Quality to open the page (others receive 403). Saving also requires that you are the protocol author. An unknown protocol returns 404.

## Layout

- Breadcrumbs (Stability and retention, Protocols, the protocol, Add condition), title "Add condition · <code> v<n>", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add condition** | Always (the protocol record links here only to its draft author) | Analyst or Quality, and only the protocol author | Saves and returns to the protocol record without a banner message (the new row shows under Storage conditions); refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Label | `ProtocolCondition.label` | Text, max 80, unique per protocol | Yes | For example long-term, accelerated |
| Setpoint | `ProtocolCondition.setpoint` | Text, max 200 | Yes | Condition as approved |
| Temperature (°C) | `ProtocolCondition.temperature_c` | Decimal, up to 5 digits, 1 place | No | Optional numeric setpoint |
| Relative humidity (%) | `ProtocolCondition.humidity_pct` | Decimal, up to 4 digits, 1 place, ≥ 0 | No | Optional numeric setpoint |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Only a draft accepts conditions; the database also refuses new content on a non-draft protocol.
- Messages: "An approved protocol is frozen; create a new version."; "Only the protocol author edits a draft."
- Adding content refreshes the protocol digest and raises its revision, so an approval dialog opened earlier goes stale. Event `protocol.condition_added` (records the protocol revision before and after).
- A label already used on this protocol is refused when saving (model uniqueness check shown as an error summary).

## Related pages

- Protocol record (plain name: opened from [Stability protocols](/stability/protocols/))
