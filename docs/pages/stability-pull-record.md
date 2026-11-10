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

- Breadcrumbs (Studies, study, pull), title "Record pull" with the timepoint, the introduction ("Window <from> to <to>. A pull outside it needs a deviation reason."), the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record pull** | Always | Role: Analyst only; others receive 403 | Saves, shows "Pull recorded; link its testing evidence." and returns to the pull record; refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Pulled on | `Pull.pulled_on` | Date | Yes | Defaults to today; not in the future |
| Quantity / unit | `Pull.quantity`, `.quantity_unit` | Decimal ≥ 0 (up to 14 digits, 4 places) and text, max 20 | Yes | Quantity pulled |
| Where the pull is held | `Pull.storage_location` | Text, max 120 | Yes | Location |
| Storage chamber | `Pull.chamber` | Equipment (any) | No | If chosen it must be fit for use today; a laboratory equipment use (activity "stability-storage") is recorded |
| Deviation reason | `Pull.deviation_reason` | Text | Only if outside the window | Why the pull is early or late; blank entries do not count |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Messages: "A pull cannot be dated in the future."; "The pull is outside its window (… to …); record the deviation reason."; "This pull is not awaiting collection."; "The study is no longer active."; an unfit chamber is refused as "<asset ID>: <reasons>".
- Allowed only while the pull is Scheduled and the study is Active. The window is the due date minus and plus the timepoint's window days, inclusive.
- Sets the pull to Pulled, records you as the puller (you cannot later accept it), raises the revision by 1; event `pull.recorded`. Pulled data cannot be re-recorded; link testing evidence next.

## Related pages

- Pull record
- Link pull evidence (next step)
