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

- Sign-in required. Roles: Analyst or Quality, and only the protocol author.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add condition** | Always | Analyst or Quality, and only the protocol author | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Label | `ProtocolCondition.label` | Text, max 80, unique per protocol | Yes | For example long-term |
| Setpoint | `ProtocolCondition.setpoint` | Text, max 200 | Yes | Condition as approved |
| Temperature (°C) | `ProtocolCondition.temperature_c` | Decimal, 1 place | No | Optional numeric setpoint |
| Relative humidity (%) | `ProtocolCondition.humidity_pct` | Decimal, 1 place, ≥ 0 | No | Optional numeric setpoint |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Messages: "An approved protocol is frozen; create a new version."; "Only the protocol author edits a draft."
- Adding content refreshes the protocol digest and raises its revision, so an approval dialog opened earlier goes stale. Event `protocol.condition_added`.

## Related pages

- Protocol record
