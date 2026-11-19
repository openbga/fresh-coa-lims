---
title: Record follow-up
urls: catalog:proficiency_follow_up
views: catalog.proficiency_views.proficiency_follow_up
templates: catalog/form.html
models: catalog.ProficiencyParticipation, impact.Assessment
reviewed: 2026-11-19
summary: Record the corrective follow-up of a reviewed participation as it progresses: cause, actions, results already reported, impact assessment and effectiveness check. Quality only; whoever records it cannot close it.
---

## Common tasks

### Record the investigation

1. Describe what the investigation found in [[Cause]] and what was done in [[Corrective actions]].
2. Enter the [[Reason for change]] and select [[Save follow-up]].

### Address results already reported

1. Describe the effect on reported results in [[Results already reported]].
2. Optionally choose an [[Impact assessment]], then select [[Save follow-up]].

### Show that the actions worked

1. Enter the [[Effectiveness check]] and optionally the [[Quality-system reference]], then select [[Save follow-up]].

## Good to know

- You can save in steps: every field is optional, but closing needs the cause, actions, reported results and effectiveness check.
- A linked impact assessment must be concluded before the follow-up can be closed, and a withdrawn one is refused.
- Whoever records the follow-up cannot close it, nor can whoever recorded or performed the report or results.
- Saving without a change is refused.

## Purpose

Keeps the corrective follow-up that a review asked for, until another quality person closes it.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.
- A participation that is not in follow-up redirects to its record with "PT-n has no corrective follow-up open."

## Layout

- **Header**: "Record follow-up · PT-n" with the introduction "Record the investigation, the actions and how they were shown to work, as they progress. Whoever records the follow-up cannot close it."
- **Record panel**: Participation, Outcome, Review.
- **Form sections**: Investigation (Cause, Corrective actions), Results already reported (Results already reported, Impact assessment), Effectiveness (Effectiveness check, Quality-system reference), Change control (Reason for change). Buttons **Cancel** and **Save follow-up**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save follow-up** | Follow-up open | Quality | Saves; message "Follow-up of PT-n recorded."; opens the participation |
| **Cancel** | Always | Quality | Returns to the participation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Cause | `ProficiencyParticipation.cause` | Text, max 4000 | For closing | What the investigation of the outcome found |
| Corrective actions | `actions` | Text, max 4000 | For closing | What was done, by whom and when |
| Results already reported | `reported_results` | Text, max 4000 | For closing | Whether results reported with the method since its last satisfactory comparison could be affected, and what was done |
| Impact assessment | `impact_assessment` | Choice of an impact assessment that is not withdrawn (search) | No | The assessment of the results already reported |
| Quality-system reference | `quality_reference` | Text, max 200 | No | The nonconformance or CAPA record in the quality system |
| Effectiveness check | `effectiveness` | Text, max 4000 | For closing | How the actions were shown to work, for example a later round or a repeat analysis of the remaining item |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Validations**: "<label> was withdrawn." for a withdrawn impact assessment; "Nothing was changed."; "A reason is required."
- **Stale record**: "Record changed. Reload before saving."
- **Effect**: revision increases by 1; audit event `participation.follow_up_recorded` with before and after values and your reason. Its actor cannot close the follow-up.
- **Database guards**: in follow-up only these fields, the state and the closure can change.
- Not enforced by this page: what the cause, actions or effectiveness check must contain.

## Related pages

- Participation record
- Close follow-up
- Impact assessment
