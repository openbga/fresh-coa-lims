---
title: Record pull
urls: stability:pull_record
views: stability.views.pull_record
templates: ops/form.html
models: stability.Pull, stability.ProtocolTimepoint, laboratory.ResourceUse, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record that a scheduled pull was collected.

## Who can use it

- Sign-in required. Role: Analyst only; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record pull** | Always | Role: Analyst only; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Pulled on | `Pull.pulled_on` | Date | Yes | Not in the future; defaults to today |
| Quantity / unit | `Pull.quantity`, `.quantity_unit` | Decimal ≥ 0 (4 places) and text | Yes | Quantity pulled |
| Where the pull is held | `Pull.storage_location` | Text, max 120 | Yes | Location |
| Storage chamber | `Pull.chamber` | Equipment | No | If chosen it must be fit today; a use is recorded |
| Deviation reason | `Pull.deviation_reason` | Text | If outside the window | Why the pull is early or late |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Messages: "A pull cannot be dated in the future."; "The pull is outside its window (… to …); record the deviation reason."; "This pull is not awaiting collection."; "The study is no longer active."; an unfit chamber is refused with its reasons.
- Sets the pull to Pulled, records the puller, raises the revision; event `pull.recorded`.

## Related pages

- Pull record
