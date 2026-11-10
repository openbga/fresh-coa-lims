---
title: Laboratory operations
urls: laboratory:overview
views: laboratory.views.overview
templates: ops/overview.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.ReagentLot, laboratory.Qualification
reviewed: 2026-11-10
---

## Purpose

Work queues for equipment fitness, reagent lots and qualifications, each linking to the filtered list that resolves it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.

## Layout

- Dateline, title and introduction, then one table of queues: **Queue**, **Records** (count) and **Attention** ("Needs attention" or "Clear").
- Queues: Calibration overdue; Calibration due within 30 days; Equipment out of service; Calibrations awaiting acceptance; Reagent lots awaiting release; Released lots expiring within 30 days; Released lots past expiry; Qualifications awaiting approval; Qualifications expiring within 30 days.

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
- A queue with a zero count is shown as Clear.

## Related pages

- [Equipment](/laboratory/equipment/)
- [Calibrations](/laboratory/calibrations/)
- [Reagents and standards](/laboratory/reagents/)
- [Qualifications](/laboratory/qualifications/)
