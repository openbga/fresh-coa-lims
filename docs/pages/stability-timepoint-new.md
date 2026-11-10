---
title: Add timepoint
urls: stability:timepoint_new
views: stability.views.timepoint_new
templates: ops/form.html
models: stability.ProtocolTimepoint, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Add a pull timepoint and its required tests to a draft protocol.

## Who can use it

- Sign-in required. Roles: Analyst or Quality, and only the protocol author.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add timepoint** | Always | Analyst or Quality, and only the protocol author | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Condition | `ProtocolTimepoint.condition` | This protocol's conditions | Yes | Where the pull is stored |
| Label | `ProtocolTimepoint.label` | Text, max 40 | Yes | For example 3 months |
| Interval (days) | `ProtocolTimepoint.interval_days` | Whole days from time zero | Yes | 0 is time zero; unique per condition |
| Window (± days) | `ProtocolTimepoint.window_days` | Whole days | Yes (default 0) | Allowed deviation either side of the due date |
| Tests | `ProtocolTimepoint.test_codes` | Comma-separated test codes | Yes | "List one or more distinct test codes." |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Same draft and author rules as adding a condition. Event `protocol.timepoint_added`.

## Related pages

- Protocol record
