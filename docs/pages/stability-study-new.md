---
title: New study
urls: stability:study_new
views: stability.views.study_new
templates: ops/form.html
models: stability.Study, stability.Pull, quality.Lot, core.AuditEvent
reviewed: 2026-11-11
---

## Purpose

Start a stability study on an approved protocol and schedule its pulls from time zero.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Studies, New study), title, the introduction ("Creates a pull for every timepoint of the approved protocol revision."), the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Start study** | Always | Analyst or Quality; others receive 403 | Saves, shows "Study started; pulls are scheduled from time zero." and opens the study record (a future Time zero is refused with the error above); refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Identifier | `Study.identifier` | Text, max 60, unique | Yes | "This study identifier already exists." if taken |
| Approved protocol | `Study.protocol` | Approved protocol versions only | Yes | Preselected when opened with a protocol in the link (as from a protocol record) |
| Lot | `Study.lot` | Any lot, listed by lot number | Yes | The lot under study; any lot state is allowed, including released lots |
| Container and closure | `Study.container_closure` | Text, max 200 | Yes | Marketed or proposed system |
| Time zero | `Study.start_date` | Date, today or earlier | Yes | Date the study actually started; due dates are Time zero plus each timepoint's days |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- "Studies start only on the current approved protocol revision." The lot's rule revision at the start is stored as the decision basis.
- One study per protocol, lot and container closure; a repeat is refused by the model's uniqueness check.
- Creates one Pull per protocol timepoint (all conditions), due on Time zero plus the timepoint's interval days; starts Active with revision 1 and records you as the starter (you cannot close it later).
- Event `study.started` records how many pulls were scheduled and the protocol.
- Every due date and its window must be a representable calendar date; otherwise the start is refused with "<condition> <timepoint>: the pull date or its window falls outside the supported calendar range from this time zero." and no study or pull is saved.
- Time zero cannot be in the future: "Time zero cannot be in the future: this workflow records studies that have actually started." (also shown beside the field). Today and historical dates are accepted. This is an application rule for recording an actual start, not a regulatory requirement.
- Not compared with the lot: Time zero may predate the lot's receipt (historical starts are legitimate) and any lot state, including released lots, is allowed. A planned-study workflow (scheduling a study before it starts) is not supported.
- Once saved, Time zero and every pull's due date are immutable (the database refuses changes).
- Not enforced by this page: that Time zero is plausible for the lot, or the lot's relation to the protocol product.

## Related pages

- [Stability studies](/stability/studies/)
- Protocol record (approved protocols link here)
- Study record (opened after saving)
