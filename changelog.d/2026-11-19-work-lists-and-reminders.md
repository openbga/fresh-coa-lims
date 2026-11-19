---
date: 2026-11-19
type: added
impact: high
title: Plan open tests on a work list and see reminders of what falls due
area: Planning
link: planning:work_list
pr: 61
---
A new **Planning** section lists every test that is open or awaiting review, earliest due first, with the analyst it is assigned to and the instrument it is planned on. A test is due by the date a reviewer or quality person sets, or by the **turnaround target** quality sets for lot, stability or reassessment testing; a test keeps the target in force when it was assigned. Reviewers and quality tick tests and use **Plan selected tests** to give them a due date, an analyst and an instrument at once; an analyst can **Assign to me** a test nobody has taken. **Workload** shows open work by due date, by analyst and by instrument, and flags an instrument whose calibration runs out before its planned work. **Reminders** lists the calibrations, stability pulls and reagent and standard lots that fall due in the coming days, and the dashboard counts the tests overdue. Planning authorizes nothing: recording a result still checks the analyst's qualification, the instrument and every lot.

## Technical notes

- New app `planning` with migrations `planning.0001_initial` (`Target`, `Plan`) and `planning.0002_planning_guards`: targets are append-only by trigger; a plan is never deleted, stays with its test, advances its revision on every change and is written only while its test is open or awaiting review.
- Pages `planning:work_list`, `planning:plan`, `planning:workload`, `planning:reminders`, `planning:targets` and `planning:targets_change`; the POST-only action `planning:take`. New remote lookups `analysts` and `instruments-in-service`. Audit actions `plan.changed`, `plan.taken` and `turnaround_target.set`.
- No target exists after the upgrade, so open tests have no due date until quality sets targets (which apply to tests assigned afterwards) or a planner sets dates.
- Reminders are computed when the page is opened; nothing is sent and no scheduled job is added.
