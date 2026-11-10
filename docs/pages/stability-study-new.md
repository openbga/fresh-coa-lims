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

- Breadcrumbs (Studies, New study), title, the introduction ("Creates a pull for every timepoint of the approved protocol revision."), the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Start study** | Always | Analyst or Quality; others receive 403 | Saves, shows "Study started; pulls are scheduled from time zero." and opens the study record; refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Identifier | `Study.identifier` | Text, max 60, unique | Yes | "This study identifier already exists." if taken |
| Approved protocol | `Study.protocol` | Approved protocol versions only | Yes | Preselected when opened with a protocol in the link (as from a protocol record) |
| Lot | `Study.lot` | Any lot, listed by lot number | Yes | The lot under study; no lot state check here |
| Container and closure | `Study.container_closure` | Text, max 200 | Yes | Marketed or proposed system |
| Time zero | `Study.start_date` | Date | Yes | Due dates are Time zero plus each timepoint's days |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- "Studies start only on the current approved protocol revision." The lot's rule revision at the start is stored as the decision basis.
- One study per protocol, lot and container closure; a repeat is refused by the model's uniqueness check.
- Creates one Pull per protocol timepoint (all conditions), due on Time zero plus the timepoint's interval days; starts Active with revision 1 and records you as the starter (you cannot close it later).
- Event `study.started` records how many pulls were scheduled and the protocol.
- Not enforced by this page: that Time zero is not in the future or the lot's relation to the protocol product.

## Related pages

- [Stability studies](/stability/studies/)
- Protocol record (approved protocols link here)
- Study record (opened after saving)
