---
title: Laboratory operations
urls: laboratory:overview
views: laboratory.views.overview
templates: ops/overview.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.ReagentLot, laboratory.Qualification, laboratory.TrainingRecord, laboratory.ContractApproval
reviewed: 2026-11-19
summary: Work queues for laboratory fitness: equipment calibration and service, reagent lots, qualifications, training and contract laboratory approvals. Each queue opens the list that resolves it.
---

## Common tasks
### See what needs attention
1. Look for queues marked [[Needs attention]]. [[Clear]] means nothing is waiting.
2. Select a queue name, for example [[Calibration overdue]], to open the list already filtered to those records.
### Find work waiting for a signature
1. Select [[Calibrations awaiting acceptance]], [[Reagent lots awaiting release]], [[Qualifications awaiting approval]] or [[Training awaiting acknowledgement]].
2. Open a record from that list. You cannot sign evidence you recorded yourself, and only the trainee acknowledges training.
### Open a laboratory list
1. Select a tab: [[Equipment]], [[Calibrations]], [[Qualifications]], [[Training]], [[Reagents and standards]], [[Contract laboratories]] or [[Resource use]].
## Good to know
- The counts cover everyone's records, not only your own work.
- Equipment that is not calibrated, has failed or is not qualified has no queue here. Use the Not calibrated or qualified status on the Equipment list.
- The two contract laboratory queues count laboratories, not approvals, so each count matches the list it opens.
- A qualification approved to start later is not counted as expiring until it is in effect.

## Purpose

Work queues for equipment fitness, reagent lots, qualifications, training and contract laboratory approvals, each linking to the filtered list that resolves it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Equipment, Calibrations, Qualifications, Training, Reagents and standards, Contract laboratories, Resource use. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Laboratory operations can use every section link.
- Dateline, title and introduction ("Equipment fitness, reagent and standard provenance, analyst qualification and contract laboratory approvals: the gates for laboratory work."), then one table of queues: **Queue**, **Records** (count) and **Attention** ("Needs attention" or "Clear").
- Queues, in this order, with what each counts and the list it opens:

| Queue | Counts | Opens |
|---|---|---|
| Calibration overdue | In-service equipment whose latest counting calibration passed and is past its due date | Equipment, Calibration overdue |
| Calibration due within 30 days | In-service, passing, qualified-if-required equipment due today to 30 days ahead | Equipment, Calibration due soon |
| Equipment out of service | Equipment not in service | Equipment, Out of service |
| Calibrations awaiting acceptance | Calibrations in state Awaiting acceptance | Calibrations, Awaiting acceptance |
| Reagent lots awaiting release | Lots in state Awaiting release | Reagents, Awaiting release |
| Released lots expiring within 30 days | Released lots expiring today to 30 days ahead | Reagents, Expiring within 30 days |
| Released lots past expiry | Released lots past expiry | Reagents, Released but expired |
| Qualifications awaiting approval | Qualifications in state Awaiting approval | Qualifications, Awaiting approval |
| Training awaiting acknowledgement | Training records in state Awaiting acknowledgement | Training, Awaiting acknowledgement |
| Qualifications expiring within 30 days | Approved qualifications already in effect and ending today to 30 days ahead (future-dated approvals are not counted until they start) | Qualifications, Expiring within 30 days |
| Contract laboratories with an approval awaiting signature | Contract laboratories holding at least one approval in state Awaiting approval | Contract laboratories, Approval awaiting signature |
| Contract laboratories with an approval expiring within 30 days | Contract laboratories holding at least one signed, unrevoked approval already in effect and ending today to 30 days ahead | Contract laboratories, Approval expiring within 30 days |

Queue names wrap on narrow screens to keep counts and attention labels easier to see. Wide tables can be scrolled sideways.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Queue name link | Always | Any reader | Opens the matching list with its status filter applied |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Records | — | Count | — | Number of records currently in that queue |

## Rules and hidden logic

- Counts are computed live over all records, not a page of them. Due-soon windows are 30 days. Dates are inclusive calendar days in the deployment time zone.
- A queue with a zero count is shown as Clear and neutral; otherwise "Needs attention" with the queue's tone (red for overdue, out of service and expired; amber for expiring; blue for awaiting action).
- The two contract laboratory queues count laboratories, not approvals, so each count equals the rows of the list it opens. Open a laboratory to reach its approvals.
- Queues are not limited to your own work, and they do not include unfit equipment that is not calibrated, failed or unqualified; use the Equipment list's "Not calibrated or qualified" filter for those.

## Related pages

- [Equipment](/laboratory/equipment/)
- [Calibrations](/laboratory/calibrations/)
- [Reagents and standards](/laboratory/reagents/)
- [Qualifications](/laboratory/qualifications/)
- [Contract laboratories](/laboratory/contract-laboratories/)
- [Resource use](/laboratory/uses/)
