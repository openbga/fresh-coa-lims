---
title: Change targets
urls: planning:targets_change
views: planning.views.targets_change
templates: planning/targets_change.html
models: planning.Target
reviewed: 2026-11-19
summary: Set the turnaround target of lot, stability and reassessment testing in calendar days, with a reason. Quality only; tests already assigned keep their due dates.
---

## Common tasks

### Set or change a target

1. Enter the days for [[Lot testing]], [[Stability testing]] or [[Reassessment testing]].
2. Enter the [[Reason]] and select [[Change targets]].

### Remove a target

1. Clear the days of that kind of work, give the reason and select [[Change targets]].

## Good to know

- Tests already assigned keep their due dates; the new targets apply to tests assigned from now on.
- Only the kinds whose days change get a new record; leaving all as they are is refused.
- If someone changed the targets after you opened the page, nothing is saved. Open it again.

## Purpose

Changes the turnaround targets that give new tests their due dates.

## Who can use it

- Sign-in required, with the role **quality**. Other roles, including admin, receive 403.

## Layout

- Breadcrumbs: Planning / Turnaround targets / Change targets. Title and introduction.
- The form: Lot testing, Stability testing and Reassessment testing (each in days, filled with the target in force), Reason, then **Cancel** and **Change targets**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Change targets** | Always | Quality | Records each changed target and returns to Turnaround targets with "The turnaround targets are changed." |
| **Cancel** | Always | Quality | Returns to Turnaround targets without changes |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot testing / Stability testing / Reassessment testing | `Target.days` | Whole days, 1 to 365 | No | Days after assignment by which a test of that kind is due. Blank: no target |
| Reason | `Target.reason` | Text, up to 2000 characters | Yes | Why the targets change, for example the procedure that sets them |
| (hidden) expected | — | — | — | The targets the page showed, to refuse a change made meanwhile |

## Rules and hidden logic

- Each kind whose days differ from the target in force gets a new target row and the audit event `turnaround_target.set` with the days before and after and the reason. Unchanged kinds add nothing; if none changed: "Nothing changed: every target is already as entered."
- Changes are serialized; when the targets changed after the page was opened: "The turnaround targets changed after this page was opened. Open it again to see the targets in force."
- Days outside 1 to 365 are refused on the form and by the database.

## Related pages

- [Turnaround targets](/planning/targets/)
- [Work list](/planning/)
