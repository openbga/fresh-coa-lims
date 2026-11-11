---
title: Laboratory operations
urls: laboratory:overview
views: laboratory.views.overview
templates: ops/overview.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.ReagentLot, laboratory.Qualification
reviewed: 2026-11-11
---

## Purpose

Work queues for equipment fitness, reagent lots and qualifications, each linking to the filtered list that resolves it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Equipment, Calibrations, Qualifications, Reagents and standards, Resource use. The current page is highlighted; every tab is visible to anyone who can read Laboratory operations.
- Dateline, title and introduction, then one table of queues: **Queue**, **Records** (count) and **Attention** ("Needs attention" or "Clear").
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
| Qualifications expiring within 30 days | Approved qualifications already in effect and ending today to 30 days ahead (future-dated approvals are not counted until they start) | Qualifications, Expiring within 30 days |

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
- Queues are not limited to your own work, and they do not include unfit equipment that is not calibrated, failed or unqualified; use the Equipment list's "Not calibrated or qualified" filter for those.

## Related pages

- [Equipment](/laboratory/equipment/)
- [Calibrations](/laboratory/calibrations/)
- [Reagents and standards](/laboratory/reagents/)
- [Qualifications](/laboratory/qualifications/)
- [Resource use](/laboratory/uses/)
