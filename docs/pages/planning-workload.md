---
title: Workload
urls: planning:workload
views: planning.views.workload
templates: planning/workload.html, ops/_cell.html
models: analytical.AnalyticalTest, planning.Plan, laboratory.Equipment, laboratory.Calibration
reviewed: 2026-11-19
summary: Open work at a glance: tests overdue and due soon, each analyst's open tests and the tests planned on each instrument beside its calibration. Every count opens the work list.
---

## Common tasks

### See who has too much work

1. Read [[By analyst]]: each analyst's open tests, overdue, due today and due in the next 7 days.
2. Select a count to open the work list filtered to those tests.

### Check instruments against planned work

1. Read [[By instrument]]. [[Check]] names a problem, such as [[Calibration runs out before planned work]].
2. Select the instrument to open its record, or a count to see its tests.

### Find work nobody has planned

1. Select [[Open, no analyst assigned]] or [[No due date]] under [[Open work]].

## Good to know

- Every count is the number of tests the work list shows when you select it.
- By analyst and By instrument count open tests only; tests awaiting review are the reviewers' work and are counted under Awaiting review.
- The instrument check compares the calibration with the latest due date planned on it; recording a result still checks the calibration on the day.
- Counts cover the whole laboratory for every reader.

## Purpose

An overview of the laboratory's open work: how much is overdue or due soon, how it is spread across analysts, and what is planned on each instrument compared with its fitness and calibration.

## Who can use it

- Sign-in required. The roles **analyst**, **reviewer**, **quality**, **admin** and **auditor** can open it; other accounts receive 403. The page changes nothing.

## Layout

- **Section tabs** (Work list, Workload, Reminders, Figures and Reviewed tests (these two not for analysts), Turnaround targets), title, today's date and the introduction.
- **Open work**: Queue, Tests and Attention ("Needs attention" in the queue's tone, or "Clear"). Queues: Overdue; Due today; Due in the next 7 days; No due date; Open, no analyst assigned; Awaiting review.
- **By analyst**: one row per active analyst (and anyone an open test is still assigned to), then **Not assigned**. Columns: Analyst, Open tests, Overdue, Due today, Due in the next 7 days, No due date.
- **By instrument**: one row per instrument some open test is planned on. Columns: Instrument (asset and description), Fitness, Calibration valid until, Open tests, Overdue, Latest due date, Check. Empty: "No test is planned on an instrument".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Queue name | Always | Any reader | Opens the work list with that filter |
| A count | The count is above zero (a zero is plain text) | Any reader | Opens the work list filtered to the analyst or instrument, open tests and the due filter of the column |
| Instrument | A row exists | Any reader | Opens the equipment record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Overdue / Due today / Due in the next 7 days / No due date | `Plan.due_on`, `Target.days` | Count | — | Tests open or awaiting review by their due date, as the work list's Due filter |
| Open, no analyst assigned | `Plan.analyst` | Count | — | Open tests with no analyst |
| Awaiting review | `AnalyticalTest.state` | Count | — | Tests submitted and not yet reviewed |
| Open tests (By analyst, By instrument) | `AnalyticalTest.state` | Count | — | Open tests assigned to the analyst, or planned on the instrument |
| Fitness | `Equipment.state`, `Calibration` | Status | — | As on the Equipment list: Ready, Due soon, Calibration overdue, Calibration failed, Not calibrated, Not qualified, Out of service |
| Calibration valid until | `Calibration.due_date` | Date | — | Last day of the latest counting calibration |
| Latest due date | — | Date | — | The latest due date among the open tests planned on the instrument |
| Check | — | Status | — | The instrument's fitness problem when it is out of service, unfit or overdue; otherwise "Calibration runs out before planned work" when the calibration ends before the latest due date; otherwise "No conflict found" |

## Rules and hidden logic

- Each Open work count uses the same filter as the work list it opens. Due dates follow the work list's rule: the planner's date, else the turnaround target in force when the test was assigned.
- By analyst and By instrument count tests in state Open only.
- "No conflict found" means only that the planned dates fall within the calibration and the instrument is fit today. Not enforced by this page: whether an instrument suits a method, and its fitness on the day of use (the result pages check that).

## Related pages

- [Work list](/planning/): the tests behind every count.
- [Equipment](/laboratory/equipment/): fitness and calibration of each instrument.
- [Reminders](/planning/reminders/): calibrations, pulls and reagent lots falling due.
