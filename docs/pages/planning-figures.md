---
title: Figures
urls: planning:figures
views: planning.views.figures
templates: planning/figures.html
models: analytical.AnalyticalTest, analytical.Observation, analytical.Investigation, core.ElectronicSignature, core.AuditEvent, planning.Plan, planning.Target
reviewed: 2026-11-19
summary: Turnaround and right-first-time figures for the tests reviewed in a period, overall and by kind of work, material, method, analyst or month. Every count opens the reviewed tests behind it.
---

## Common tasks

### See how the laboratory kept its due dates

1. Set [[From]] and [[To]] to the period, then select [[Show figures]].
2. Read [[Median turnaround]], [[9 in 10 reviewed within]] and [[Reviewed on time]].
3. Select [[Reviewed late]] to list the tests that missed their due date.

### Compare analysts, methods or materials

1. Choose [[Figures by]], for example [[Analyst]] or [[Method]], and select [[Show figures]].
2. Read the table below the summary. Select a count to see the tests behind it.

### Find the rework

1. Select [[Returned for correction]], [[A reading corrected]] or [[A repeat, or repeated]].
2. The list that opens says, for each test, what kept it from being right first time.

### Look at one kind of work only

1. Select [[More filters]], choose a [[Work]], then select [[Show figures]].

## Good to know

- A test counts in the period of the day its review was signed, not the day it was assigned.
- Turnaround is in calendar days, from the day a test was assigned to the day its review was signed.
- A test is on time when it was reviewed on or before its due date: the planner's date, else the turnaround target in force when it was assigned.
- A retest, resample, rerun or repeat is not right first time, and neither is the test it repeats. Nor is a test with a corrected reading, even one corrected before it was submitted.
- The figures name each analyst, so analysts cannot open them. They describe work done; they are not targets set by the software.

## Purpose

Shows how long reviewed tests took and how many were right first time, so that a laboratory can follow its turnaround and rework over a period and see where they come from.

## Who can use it

- Sign-in required. The roles **reviewer**, **quality**, **auditor** and **admin** can open it. An **analyst** without one of those roles receives 403, and the Figures and Reviewed tests tabs are not shown. The page changes nothing.

## Layout

- **Section tabs** (Work list, Workload, Reminders, Figures, Reviewed tests, Turnaround targets), title, today's date and the introduction naming the period.
- **In the period**: the toolbar (From, To, Figures by; More filters: Work; Show figures; Clear all when anything other than the default is chosen) and its note. Then the facts Reviewed tests, Median turnaround, 9 in 10 reviewed within, Reviewed on time and Right first time, and a table of counts: Figure, Tests, Share.
- **By ...** (By kind of work, By material, By method, By analyst or By month reviewed): one row for each value, most reviewed first (months in order). Columns: the value, Reviewed, Median days, 9 in 10 within days, On time (with its share of the tests that had a due date), Late, Right first time (with its share of the reviewed tests), Returned, Corrected, Repeat.
- Empty: "No test was reviewed in this period". Invalid filters: "The figures cannot be shown", with the error beside the field.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Show figures | Always | Any reader of the page | Reloads the page for the period, breakdown and work chosen |
| Clear all | Anything other than the default is chosen | Any reader | The last 30 days by kind of work |
| A figure in the In the period table | Tests were reviewed in the period | Any reader | Opens Reviewed tests for the same period and work, filtered to those tests |
| A count in the By table | The count is above zero (a zero is plain text) | Any reader | Opens Reviewed tests for the row's value (for a month, the part of the period in that month) and the column's filter |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| From, To | — | Date | No | The days the reviews were signed, in the deployment time zone, both included. Without them: the last 30 days up to today. With From only: 30 days from it, at most to today. With To only: the 30 days up to it |
| Figures by | — | Choice | No | Kind of work (default), Material, Method, Analyst or Month reviewed |
| Work | — | Choice | No | All work, Lot testing, Stability testing or Reassessment testing |
| Reviewed tests / Reviewed | `ElectronicSignature.signed_at` (meaning reviewed) | Count | — | Tests whose review was signed in the period, whatever their state since (an out-of-specification result later invalidated still counts) |
| Median turnaround / Median days | `AnalyticalTest.created_at`, `ElectronicSignature.signed_at` | Days, one decimal | — | The middle turnaround; for an even count, halfway between the two middle ones |
| 9 in 10 reviewed within / 9 in 10 within days | as above | Days | — | The fewest days that at least nine in ten of the tests did not exceed |
| Reviewed on time / On time | `Plan.due_on`, `Target.days` | Count and percentage | — | Reviewed on or before the due date; the share is of the tests that had a due date |
| Reviewed late / Late | as above | Count and percentage | — | Reviewed after the due date |
| No due date | as above | Count | — | No planner's date and no turnaround target applied |
| Right first time | — | Count and percentage | — | Never returned, no reading corrected, and neither a repeat of an earlier test nor followed by one; the share is of the reviewed tests |
| Returned for correction / Returned | `AuditEvent` (test.returned) | Count | — | Returned by a reviewer at least once before the review |
| A reading corrected / Corrected | `Observation.supersedes` | Count | — | At least one reading replaced by a correction, also one made before the test was first submitted |
| A repeat, or repeated / Repeat | `AnalyticalTest.kind`, `AnalyticalTest.parent` | Count | — | A retest, resample, rerun after a QC failure or repeat of a test not completed, or a test one of those follows |
| Out of specification | `AnalyticalTest.conforms` | Count | — | The reviewed result did not conform |
| Invalidated after investigation | `Investigation.outcome` | Count | — | The investigation of the result concluded that it was invalid; the share is of the results out of specification |

## Rules and hidden logic

- The period is at most 366 days, with dates from 1900-01-01 to 9998-12-31. "The period ends before it starts." and "Choose a period of at most 366 days." show beside To, "Enter a date from 1900-01-01 to 9998-12-31." beside the date, and no figures are shown.
- A test's due date is the work list's: the planner's date, else the assigned day plus the turnaround target in force for its kind of work when it was assigned. Days are local days of the deployment time zone.
- A repeat under replaced requirements is new work under new requirements and counts neither as a repeat nor against the test it follows.
- Analyst is the person who submitted the reviewed result. Material is the material of the lot tested, of the stability study's lot or of the reassessed lot. Method is the method code frozen on the test.
- Every count is the number of rows Reviewed tests shows when you select it. Percentages are rounded half up to whole percent.
- Not enforced by this page: what turnaround or right-first-time level is acceptable. No source the project read requires these figures; which ones a laboratory follows and what it does about them is its own procedure.

## Related pages

- [Reviewed tests](/planning/figures/tests/): the tests behind every count, with a CSV export.
- [Turnaround targets](/planning/targets/): the targets that give tests their due date.
- [Work list](/planning/): open work and its due dates.
