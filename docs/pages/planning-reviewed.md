---
title: Reviewed tests
urls: planning:reviewed
views: planning.views.reviewed
templates: planning/reviewed.html
models: analytical.AnalyticalTest, analytical.Observation, analytical.Investigation, core.ElectronicSignature, core.AuditEvent, planning.Plan, planning.Target
reviewed: 2026-11-19
summary: The tests reviewed in a period, each with its turnaround, its due date kept or missed, and what kept it from being right first time. Filter, sort and export the list as CSV.
---

## Common tasks

### See which tests were late

1. Set [[From]] and [[To]], select [[More filters]], choose [[Due date]] [[Late]] and select [[Apply]].
2. Sort by [[Turnaround]] to see the longest first.

### Find the tests that needed rework

1. Choose [[First time]] [[Not right first time]] and select [[Apply]].
2. Read [[First time]] in each row: returned, readings corrected, a repeat of an earlier test or repeated by a later one.

### Export the list for a review

1. Filter the list as needed, then select [[Export filtered CSV]].

### Go back to the figures

1. Select [[Figures for this period]] in the introduction.

## Good to know

- Counts on Figures open this list with the same filters, so its rows are exactly the tests counted.
- A test is listed by the day its review was signed, even if its result was later invalidated.
- Late by is counted in calendar days from the due date to the day of the review.
- A reading corrected before the test was first submitted also makes it not right first time: every correction stays in the record.

## Purpose

Lists the tests reviewed in a period with what the figures count for each, so that a reviewer or quality person can see which tests were late or needed rework, and export them.

## Who can use it

- Sign-in required. The roles **reviewer**, **quality**, **auditor** and **admin** can open it and export it. An **analyst** without one of those roles receives 403, also for the export, and the tab is not shown. The page changes nothing.

## Layout

- **Section tabs** (Work list, Workload, Reminders, Figures, Reviewed tests, Turnaround targets), title and the introduction naming the period, with the link Figures for this period.
- **Toolbar**: Find, From, To, First time; More filters: Due date, Work, Material, Method, Analyst, Result; Apply; Export filtered CSV; Clear all when a filter is active; Columns; the note on dates.
- **Table** (newest review first): Test (with its kind when it is not an original, and the test name), Reviewed, Turnaround (days, and the day it was assigned), Due date (the date and On time, Late by N days or No due date; "From the target" when no planner set it), First time (Right first time, or Not right first time with each reason), Lot (with the sample, stability pull or reassessment), Material, Method, Analyst, Result (Conforms or Out of specification; "Invalidated after investigation" when an investigation concluded that).
- Empty: "No test was reviewed in this period"; with filters, no results and Clear filters.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Apply | Always | Any reader of the page | Reloads the list with the filters |
| Export filtered CSV | Always | Any reader | Downloads `reviewed-tests-<from>-<to>.csv` with every matching test; refused while a filter is invalid (the page shows the error) |
| Clear all | A filter or a period other than the default is active | Any reader | The last 30 days, unfiltered |
| Test | A row exists | Any reader | Opens the test record |
| Lot | A row exists | Any reader | Opens the lot's testing, the stability pull or the reassessment |
| Column headers Test, Reviewed, Turnaround | Always | Any reader | Sort by test, by review time or by turnaround |
| Figures for this period | Always | Any reader | Opens Figures for the same period |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find | `Lot.number`, `Sample.reference`, `Study.identifier`, `Lot.material`, `AnalyticalTest.test_code` | Text | No | Part of a lot number, sample reference, study identifier, material or test code |
| From, To | `ElectronicSignature.signed_at` | Date | No | The days the reviews were signed, both included; the last 30 days by default; at most 366 days; dates from 1900-01-01 to 9998-12-31 |
| First time | — | Choice | No | Right first time, Not right first time, Returned for correction, A reading corrected, A repeat, or repeated |
| Due date | — | Choice | No | On time, Late, No due date |
| Work | — | Choice | No | Lot testing, Stability testing or Reassessment testing |
| Material | `Lot.material` | Choice | No | The material of the lot tested (or of the study's or reassessed lot); the choices are the period's |
| Method | `AnalyticalTest.requirement` (method code) | Choice | No | The method code frozen on the test; the choices are the period's |
| Analyst | `AnalyticalTest.submitted_by` | Choice | No | Who submitted the reviewed result; the choices are the period's analysts and No analyst recorded |
| Result | `AnalyticalTest.conforms`, `Investigation.outcome` | Choice | No | Out of specification, or Invalidated after investigation |
| Turnaround | `AnalyticalTest.created_at`, `ElectronicSignature.signed_at` | Days | — | Calendar days from the day assigned to the day reviewed |
| Due date | `Plan.due_on`, `Target.days` | Date | — | The planner's date, else the target's |

The CSV holds every matching test, not only the page shown, and is sent row by row. Cells that start like a spreadsheet formula are prefixed with an apostrophe. Reviewed at is in the deployment time zone. CSV columns: Test, Test code, Kind, Work, Lot, Material, Method, Method revision, Analyst (username), Assigned on, Due on, Due from (planner, target or empty), Reviewed at, Reviewed on, Turnaround days, Due date kept, Returns, Corrected readings, Repeat of, Repeated by, Right first time, Conforms, Invalidated after investigation.

## Rules and hidden logic

- The list holds tests with a review signature in the period, whatever their state since. A test returned and reviewed later counts once, on the day of its review.
- Right first time: never returned, no reading corrected (also before the first submission), not a retest, resample, rerun or repeat of a test not completed, and not followed by one. A repeat under replaced requirements is not a repeat.
- A material, method or analyst named in the address that the period does not hold lists no test rather than an error.
- Dates are local days of the deployment time zone. Sorting keeps a stable order by test.
- Invalid dates show "The period ends before it starts.", "Choose a period of at most 366 days." or "Enter a date from 1900-01-01 to 9998-12-31." beside the field; the list and the export then show the error instead.

## Related pages

- [Figures](/planning/figures/): the counts this list opens.
- [Work list](/planning/): open work and its due dates.
- [Turnaround targets](/planning/targets/): the targets behind due dates.
