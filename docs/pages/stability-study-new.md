---
title: New study
urls: stability:study_new
views: stability.views.study_new
templates: ops/form.html
models: stability.Study, stability.Pull, quality.Lot, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Start a stability study on an approved protocol and schedule its pulls from time zero.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Start study** | Always | Analyst or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Identifier | `Study.identifier` | Text, max 60, unique | Yes | "This study identifier already exists." if taken |
| Approved protocol | `Study.protocol` | Approved versions only | Yes | Preselected when opened from a protocol |
| Lot | `Study.lot` | Any lot | Yes | The lot under study |
| Container and closure | `Study.container_closure` | Text, max 200 | Yes | Marketed or proposed system |
| Time zero | `Study.start_date` | Date | Yes | Due dates are Time zero plus each timepoint's days |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- "Studies start only on the current approved protocol revision." The lot's rule revision at the start is stored as the decision basis.
- One study per protocol, lot and container closure. Event `study.started` records how many pulls were scheduled.

## Related pages

- [Stability studies](/stability/studies/)
