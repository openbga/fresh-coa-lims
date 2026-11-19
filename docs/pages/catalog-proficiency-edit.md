---
title: Change plan
urls: catalog:proficiency_edit
views: catalog.proficiency_views.proficiency_edit
templates: catalog/form.html
models: catalog.ProficiencyParticipation
reviewed: 2026-11-19
summary: Change the plan of an open participation: its kind, provider, round, test item or due day, with a reason. Quality only. The method cannot change.
---

## Common tasks

### Change the plan

1. Edit the fields that changed, for example [[Results due]] when the provider moves the deadline.
2. Enter the [[Reason for change]] and select [[Save plan]]. The participation opens.

### Leave it as it is

1. Select [[Cancel]].

## Good to know

- Only an open participation can change. After review or cancellation it no longer changes.
- Saving without changing anything is refused: "Nothing was changed."
- Changing the plan does not make you an author of the results, so you can still review the outcome.
- If the participation changed after you opened this page, saving is refused. Reload and try again.

## Purpose

Corrects or updates the plan of an open participation while keeping each change in its history.

## Who can use it

- Sign-in required. **quality** role only; others receive 403. The role is checked before the participation is looked up.
- A participation that is not open redirects to its record with a message such as "PT-n is closed: it no longer changes." A participation under corrective follow-up gives "PT-n is reviewed: its plan, report and results no longer change; its corrective follow-up is open." (the state is shown in lower case).

## Layout

- **Header**: "Change plan · PT-n" with the introduction "Changing the plan does not stop you from reviewing the outcome."
- **Record panel**: Method.
- **Form sections**: Comparison (Kind, Provider or organizer, Provider's accreditation, Scheme, Round), Plan (Test item, Results due), Change control (Reason for change). Buttons **Cancel** and **Save plan**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save plan** | Open | Quality | Saves; message "Plan of PT-n changed."; opens the participation |
| **Cancel** | Always | Quality | Returns to the participation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Kind | `ProficiencyParticipation.kind` | Proficiency testing scheme, Interlaboratory comparison | Yes | Kind of comparison |
| Provider or organizer | `provider` | Text, max 160 | Yes | Who runs the comparison |
| Provider's accreditation | `provider_accreditation` | Text, max 200 | No | As the provider states it |
| Scheme | `scheme` | Text, max 160 | No | Scheme or programme |
| Round | `round_ref` | Text, max 80 | Yes | Round number or reference |
| Test item | `test_item` | Text, max 200 | Yes | Material or matrix and measurands |
| Results due | `results_due` | Date | Yes | Day results are due to the provider |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before saving." when the revision changed (checked under the lock).
- **Validations**: "Nothing was changed." when every value equals the stored one; "Choose the kind of comparison."; "State the day results are due."; "A reason is required."
- **Effect**: revision increases by 1; audit event `participation.plan_changed` with before and after values and your reason, or `participation.plan_corrected` when a result or the day results were reported is already recorded. The change leaves the report and results untouched.
- **Correction after results**: once a result or the reported day is recorded, the review will freeze the plan with them, so whoever changes the plan then becomes an author of the participation's data and cannot review the outcome or close its follow-up. Before that, changing the plan is not authorship. The page introduction says so.
- **Database guards**: the method, the planner and the planning time are fixed.

## Related pages

- Participation record
- [Proficiency testing](/catalog/proficiency/)
