---
title: New study
urls: stability:study_new
views: stability.views.study_new
templates: ops/form.html
models: stability.Study, stability.Pull, quality.Lot, core.AuditEvent
reviewed: 2026-11-17
summary: Start a stability study of one lot on an approved protocol. A pull is scheduled for every timepoint, due from time zero. Analysts and quality users only.
---

## Common tasks
### Start a study
1. Enter the [[Identifier]] and choose the [[Approved protocol]] and the [[Lot]].
2. Enter the [[Container and closure]] and the [[Time zero]], the date the study actually started.
3. Enter a [[Reason]] and select [[Start study]]. The study record opens with its pull schedule.
### Leave without starting a study
1. Select [[Cancel]]. Nothing is saved.
## Good to know
- Time zero cannot be in the future. This page records studies that have actually started.
- When the protocol names a specification, the lot needs requirements assigned for that specification's material.
- Rejected and cancelled lots are not offered. A released lot can be studied.
- You are recorded as the person who started the study, so you cannot close it later.
- Time zero and the due dates of the pulls cannot be changed once saved.

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
| Lot | `Study.lot` | Lots in quarantine or released, listed by lot number | Yes | The lot under study; released lots are allowed. Rejected and cancelled lots are not offered. When the protocol names a specification, the lot must be of that specification's material |
| Container and closure | `Study.container_closure` | Text, max 200 | Yes | Marketed or proposed system |
| Time zero | `Study.start_date` | Date, today or earlier | Yes | Date the study actually started; due dates are Time zero plus each timepoint's days |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- "Studies start only on the current approved protocol revision." The lot's rule revision at the start is stored as the decision basis.
- When the protocol names a specification, the lot's latest assigned requirements decide its material. Refused: "Lot <number> has no requirements assigned, so its material is not established. <protocol> tests against specification <code> of <material>; assign the lot's requirements first." or "Lot <number> is <material>; <protocol> tests against specification <code> of <material>." A protocol with no specification has no such check.
- One study per protocol, lot and container closure; a repeat is refused by the model's uniqueness check.
- Creates one Pull per protocol timepoint (all conditions), due on Time zero plus the timepoint's interval days; starts Active with revision 1 and records you as the starter (you cannot close it later).
- Event `study.started` records how many pulls were scheduled and the protocol.
- Every due date and its window must be a representable calendar date; otherwise the start is refused with "<condition> <timepoint>: the pull date or its window falls outside the supported calendar range from this time zero." and no study or pull is saved.
- Time zero cannot be in the future: "Time zero cannot be in the future: this workflow records studies that have actually started." (also shown beside the field). Today and historical dates are accepted. This is an application rule for recording an actual start, not a regulatory requirement.
- Not compared with the lot: Time zero may predate the lot's receipt (historical starts are legitimate) and a lot in quarantine or released is allowed. A planned-study workflow (scheduling a study before it starts) is not supported.
- A lot that was rejected or cancelled is refused if submitted anyway: "Lot <number> was rejected. A study starts on a lot in quarantine or released." or "Lot <number> was cancelled as received in error; it has no material."
- Once saved, Time zero and every pull's due date are immutable (the database refuses changes).
- Not enforced by this page: that Time zero is plausible for the lot, or the lot's relation to the protocol product (apart from the material check above).

## Related pages

- [Stability studies](/stability/studies/)
- Protocol record (approved protocols link here)
- Study record (opened after saving)
