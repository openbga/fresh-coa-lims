---
title: Plan selected tests
urls: planning:plan
views: planning.views.plan
templates: planning/plan.html
models: planning.Plan, analytical.AnalyticalTest, laboratory.Equipment
reviewed: 2026-11-19
summary: Set the due date, the analyst or the planned instrument of the tests ticked on the work list, all at once. Reviewers and quality only.
---

## Common tasks

### Give several tests one due date

1. Tick the tests on the [[Work list]] and select [[Plan selected tests]].
2. Enter the [[Due date]] and select [[Save plan]].

### Assign tests to an analyst

1. Choose the [[Analyst]] and select [[Save plan]]. Fields left blank keep each test's own value.

### Go back to the turnaround target

1. Tick [[Use the turnaround target instead]] and select [[Save plan]]. Each test is due again by its target.

## Good to know

- What you enter applies to every selected test; a blank field keeps each test's own value.
- Planning never authorizes work: the analyst still needs a current qualification, and the instrument a current calibration, when results are recorded.
- If anyone changed one of these tests' plans after you opened the page, nothing is saved. Open the work list again.
- Only tests that are open or awaiting review can be planned.

## Purpose

Plans the tests selected on the work list: the day each is due, the analyst it is assigned to and the instrument it is planned on, in one change.

## Who can use it

- Sign-in required, with the role **reviewer** or **quality**. Other roles, including admin and auditor, receive 403. Analysts take unassigned tests with **Assign to me** on the work list instead.

## Layout

- Breadcrumbs: Planning / Plan selected tests. Title and introduction.
- **Selected tests**: Test (with its code), Due, Lot (with the sample, pull or reassessment under it), Analyst, Instrument, as planned now.
- The form in four groups: **Due date** (Due date, Use the turnaround target instead), **Analyst** (Analyst, Remove the analyst), **Instrument** (Instrument, Remove the instrument) and **Change** (Reason), then **Cancel** and **Save plan**.
- When nothing can be planned (no test selected, a test that no longer exists or no longer takes work, more than 100 tests): a notice with the reason and **Back to the work list**, and no form.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save plan** | The selection can be planned | Reviewer, quality | Applies the change to every selected test and returns to the work list with "Planned N tests." Tests whose plan would not change are left as they are |
| **Cancel** | Always | Reviewer, quality | Returns to the work list without changing anything |
| **Back to the work list** | Nothing can be planned | Reviewer, quality | Returns to the work list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Due date | `Plan.due_on` | Date (YYYY-MM-DD) | No | Every selected test is due on this day. Blank keeps each test's date |
| Use the turnaround target instead | `Plan.due_on` | Tick box | No | Clears the planner's date: each test is due by the target in force when it was assigned (or has no due date without one). Not together with a due date |
| Analyst | `Plan.analyst` | Account | No | An active analyst, found by name or username. Blank keeps each test's analyst |
| Remove the analyst | `Plan.analyst` | Tick box | No | Leaves the tests unassigned. Not together with an analyst |
| Instrument | `Plan.equipment` | Equipment | No | Equipment in service, found by asset, description or category. Blank keeps each test's instrument |
| Remove the instrument | `Plan.equipment` | Tick box | No | Leaves the tests without a planned instrument. Not together with an instrument |
| Reason | — | Text, up to 500 characters | No | Kept with each change in the audit trail |
| (hidden) selection | `Plan.revision` | — | Yes | The tests and the revision of each plan the page showed |

## Rules and hidden logic

- At least one change is required: "Choose what to change: a due date, an analyst or an instrument." A value and its removal together are refused: "Choose … not both."
- Every selected test must still be open or awaiting review, and its plan must be the one the page showed; otherwise nothing is saved ("The plan of T-… changed after this page was opened. Open the work list again to see the current plan."). The change is all or nothing.
- The analyst must be an active account with the analyst role; the instrument must be in service. Planning does not check the analyst's qualification for the method or the instrument's calibration; recording a result does.
- Each changed test's plan advances its revision and records the audit event `plan.changed` with the due date, analyst and instrument before and after, and the reason. If no selected test would change: "Nothing changed: every selected test is already planned so."
- At most 100 tests at once (one page of the work list at its largest).
- The database refuses a plan change for a test that is no longer open or awaiting review, and a plan is never deleted.

## Related pages

- [Work list](/planning/): where tests are selected.
- [Workload](/planning/workload/): what each analyst and instrument has planned.
- [Turnaround targets](/planning/targets/): the due date a test returns to without a planner's date.
