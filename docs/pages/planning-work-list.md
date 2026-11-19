---
title: Work list
urls: planning:work_list
views: planning.views.work_list
templates: planning/work_list.html, analytical/_test_status.html
models: analytical.AnalyticalTest, planning.Plan, planning.Target, laboratory.Equipment
reviewed: 2026-11-19
summary: Every test still open or awaiting review, earliest due first, with its analyst and planned instrument. Find your own work, take an unassigned test, or select tests to plan.
---

## Common tasks

### See what is due first

1. The list opens with the earliest due date first; overdue tests come first.
2. Choose [[Overdue]] or [[Due today]] under [[Due]] and select [[Apply]] to see only those.

### Find your own work

1. Under [[Analyst]], choose [[Assigned to me]] and select [[Apply]].
2. Select a test number to open the test and record its results.

### Take a test nobody is assigned to

1. Under [[Analyst]], choose [[Not assigned]] and select [[Apply]].
2. Select [[Assign to me]] in the test's row (analysts only). The test is assigned to you.

### Plan several tests at once

1. Tick the tests on this page (reviewers and quality).
2. Select [[Plan selected tests]] and set a due date, an analyst or an instrument on the next page.

## Good to know

- Planning never authorizes work: recording a result still checks the analyst's qualification, the instrument and every lot used, whoever the test is assigned to.
- "From the target" means nobody set a date: the test is due by the turnaround target in force when it was assigned.
- A test assigned before any target was set has no due date until someone plans one.
- A test leaves the list once it is reviewed, invalidated, superseded or recorded as not completed.
- Selection covers the ticked tests of this page only.

## Purpose

The laboratory's open work in one list: every test that is open or awaiting review, from lot testing, stability pulls and reassessments, with the date it is due, the analyst it is assigned to and the instrument it is planned on.

## Who can use it

- Sign-in required. The roles **analyst**, **reviewer**, **quality**, **admin** and **auditor** can open it; other accounts receive 403.
- **Plan selected tests** and the row tick boxes are shown to **reviewers** and **quality**.
- **Assign to me** is shown to **analysts**, in the rows of open tests that nobody is assigned to.
- Admin and auditor read the list only.

## Layout

- **Section tabs**: Work list, Workload, Reminders, Turnaround targets.
- Title "Work list", the introduction and, for planners, **Plan selected tests** at the right of the title.
- The toolbar: **Find**, **Due**, **Analyst** and **Status**, then **More filters** (**Instrument**, **Work**), **Apply** and **Clear all** when a filter is active.
- For planners, a line under the toolbar: "Tick the tests to plan on this page, then select Plan selected tests." with the count selected.
- The table: (planners) a tick box; **Test** (number, a kind label for a retest or repeat, and the test name under it); **Due**; **Status**; **Lot** (with the sample, the stability pull or the reassessment under it); **Code**; **Analyst**; **Instrument**; **Assigned** (the day the test was assigned). Code and Assigned give way first on narrow screens. **Columns** chooses and orders the columns; your layout is saved to your account.
- Empty: "No open work". With filters that match nothing: "No tests match these filters".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Plan selected tests** | Always, for planners | Reviewer, quality | Opens Plan selected tests with the ticked tests of this page |
| **Assign to me** | An open test with no analyst | Analyst | Assigns the test to you and returns to the same list with the message "T-… is assigned to you." Refused when someone planned the test after the page was opened, or another analyst took it |
| Test number | Always | Any reader | Opens the test record |
| Lot link | Always | Any reader | Opens the lot's testing page, the stability pull or the reassessment |
| Instrument link | An instrument is planned | Any reader | Opens the equipment record |
| **Apply** / **Clear all** | Always / a filter is active | Any reader | Filters the list / removes every filter |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find | — | Text | No | Matches lot numbers, sample references, stability study identifiers, the lot of a study or reassessment, and test codes |
| Due | — | Choice | No | Any due date; Overdue (before today); Due today; Due in the next 7 days (tomorrow to 7 days ahead); Due after 7 days; No due date |
| Analyst | `Plan.analyst` | Choice | No | Anyone; Assigned to me; Not assigned; or one analyst (active analysts and anyone an open test is still assigned to) |
| Status | `AnalyticalTest.state` | Choice | No | Open or awaiting review (default); Open; Awaiting review |
| Instrument | `Plan.equipment` | Choice | No | Any instrument; No instrument planned; or one instrument some open test is planned on |
| Work | — | Choice | No | All work; Lot testing; Stability testing; Reassessment testing |
| Due (column) | `Plan.due_on`, `Target.days` | Date and status | — | The date a planner set or, without one, the day the test was assigned plus the target for its kind of work in force that day. "From the target" marks a date from the target. Status: "Overdue by N days" (red), "Due today" and "Due in N days" up to 7 days (amber), "Due in N days" later (neutral), "No due date" |
| Status (column) | `AnalyticalTest.state` | Status | — | Open, Not tested · supplier result (a supplier's result is proposed or accepted for it), Awaiting review, or Out of specification · awaiting review |
| Analyst (column) | `Plan.analyst` | Person | — | Who the test is assigned to; "Not assigned" otherwise |
| Instrument (column) | `Plan.equipment` | Asset | — | The instrument the test is planned on |
| Assigned (column) | `AnalyticalTest.created_at` | Date | — | The day the test was assigned to its sample, pull or reassessment: where a turnaround target starts |

## Rules and hidden logic

- Lists every test in state Open or Awaiting review (lot, stability and reassessment tests alike). Reviewed, invalidated, superseded and not completed tests are left out.
- Default order: due date, earliest first, tests without a due date last; then the day assigned. **Test** and **Assigned** also sort. The server filters, sorts and pages the whole list (25, 50 or 100 rows).
- A test's due date is the planner's date when one is set; otherwise the day it was assigned (deployment time zone) plus the days of the turnaround target for its kind of work in force at the moment it was assigned. A later change of a target does not move it. Calendar days, with no working-day calendar.
- **Assign to me** checks on the server that you hold the analyst role and are active, that the test is still open, that nobody is assigned to it, and that its plan has not changed since the page was opened. It records the audit event `plan.taken`.
- Not enforced by this page: an assignment does not stop another qualified analyst from recording the test's results, and planning does not check qualifications or calibrations; the result pages do.

## Related pages

- [Workload](/planning/workload/): open work by due date, analyst and instrument.
- [Reminders](/planning/reminders/): calibrations, stability pulls and reagent lots falling due.
- [Turnaround targets](/planning/targets/): the targets that give tests their due dates.
- [Testing](/testing/): every test, including closed ones.
- Plan selected tests: reached with the tests ticked here.
