---
title: Turnaround targets
urls: planning:targets
views: planning.views.targets
templates: planning/targets.html
models: planning.Target
reviewed: 2026-11-19
summary: How many calendar days a test of each kind of work is due after it is assigned, and every change of those targets. Quality changes them.
---

## Common tasks

### See the targets in force

1. Read [[Targets in force]]: lot testing, stability testing and reassessment testing.

### Change a target

1. Select [[Change targets]] (quality only), enter the days and your reason, and save.

## Good to know

- A test keeps the target in force when it was assigned. A new target applies to tests assigned after it is set.
- A planner's date on a test wins over the target.
- Without a target, a test has no due date until someone plans one.
- Every change is kept: the Changes list shows who set each target, when and why.

## Purpose

Shows the laboratory's turnaround targets, the number of calendar days after assignment by which a test is due, for each kind of work, and the history of their changes.

## Who can use it

- Sign-in required. The roles **analyst**, **reviewer**, **quality**, **admin** and **auditor** can open it; other accounts receive 403.
- **Change targets** is shown to **quality** only.

## Layout

- **Section tabs** (Work list, Workload, Reminders, Figures and Reviewed tests (these two not for analysts), Turnaround targets), title, the introduction and, for quality, **Change targets**.
- **Targets in force**: Work (Lot testing, Stability testing, Reassessment testing), Target ("N days" or "No target"), Since, Set by.
- **Changes**: every target set, newest first: Set, Work, Target, Set by, Reason. Empty: "No target set yet".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Change targets** | Always, for quality | Quality | Opens Change targets |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Work | `Target.work` | Lot testing, Stability testing, Reassessment testing | — | The kind of work: a test of a lot, of a stability pull or of a reassessment of a released lot |
| Target | `Target.days` | Calendar days, 1 to 365 | — | Days from the day a test is assigned to its due date; "No target" when none is set |
| Since / Set | `Target.set_at` | Date and time | — | When the target was set |
| Set by | `Target.set_by` | Person | — | Who set it |
| Reason | `Target.reason` | Text | — | Why it was set |

## Rules and hidden logic

- Targets are append-only: a change adds a new row and the database refuses any edit or deletion of an earlier one. The newest row of a kind is the target in force.
- A test takes the target in force at the moment it was assigned; changing a target never moves a test already assigned. The days are calendar days, without a working-day calendar.
- Assumption: which targets apply, and whether different materials need different ones, are the laboratory's decisions; the page holds one target per kind of work.

## Related pages

- [Work list](/planning/): the due dates the targets give.
- [Figures](/planning/figures/): how reviewed tests kept the due dates.
- Change targets: reached with **Change targets**.
