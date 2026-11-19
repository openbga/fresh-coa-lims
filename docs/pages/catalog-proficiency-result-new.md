---
title: Record result
urls: catalog:proficiency_result_new
views: catalog.proficiency_views.proficiency_result_new
templates: catalog/form.html
models: catalog.ProficiencyResult, catalog.ProficiencyParticipation
reviewed: 2026-11-19
summary: Record one measurand of a participation: the laboratory's result as reported, the assigned value, the provider's score and the analyst. The outcome follows from the score.
---

## Common tasks

### Record a scored result

1. Enter the [[Measurand]], [[Laboratory's result]] and choose the [[Analyst]].
2. Choose the kind in [[Score]] and enter the [[Score value]] the provider gave.
3. Enter the [[Reason]] and select [[Record result]]. The message names the outcome.

### Record a result the provider did not score

1. Choose [[No score: the provider's evaluation]] in [[Score]].
2. Choose the [[Provider's evaluation]], leave [[Score value]] empty and select [[Record result]].

## Good to know

- You never choose the outcome of a scored result: it follows from the kind and value of the score.
- A result without a score carries the provider's evaluation as you enter it.
- Whoever records a result, and the analyst who performed it, cannot review the outcome.
- A result cannot be edited. Remove it and record it again while the participation is open.

## Purpose

Adds one result to an open participation, with the score the provider's report gives it.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403.
- A participation that is not open redirects to its record with a message such as "PT-n is closed: it no longer changes." A participation under corrective follow-up gives "PT-n is reviewed: its plan, report and results no longer change; its corrective follow-up is open."

## Layout

- **Header**: "Record result · PT-n" with the introduction "One measurand: the laboratory's result as reported to the provider, and the score the provider's report gives it. Whoever records a result, and the analyst who performed it, cannot review the outcome."
- **Record panel**: Participation, Method.
- **Form sections**: Result (Measurand, Unit, Laboratory's result, Assigned value, Analyst), Provider's score (Score, Score value, Provider's evaluation, Note), Change control (Reason). Buttons **Cancel** and **Record result**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record result** | Open | Analyst, reviewer, quality | Adds the result; message "<measurand> added to PT-n: <outcome>."; opens the participation |
| **Cancel** | Always | Same | Returns to the participation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Measurand | `ProficiencyResult.measurand` | Text, max 120 | Yes | The analyte or property, as the provider names it |
| Unit | `unit` | Text, max 40 | No | Unit of the values |
| Laboratory's result | `reported_value` | Text, max 60 | Yes | Exactly as reported to the provider, for example 98.6, <0.5 or Detected |
| Assigned value | `assigned_value` | Text, max 60 | No | As the provider's report states it |
| Analyst | `performed_by` | Choice of an active analyst (search) | Yes | Who performed the analysis |
| Score | `score_kind` | z score, z′ score, ζ score (zeta), En number, No score: the provider's evaluation | Yes | The kind of score the provider's report gives |
| Score value | `score` | Decimal, up to 12 digits, 4 decimals | When a score kind is chosen | As the report states it |
| Provider's evaluation | `outcome` | —, Satisfactory, Questionable, Unsatisfactory, Not evaluated | Only without a score | The provider's evaluation as stated |
| Note | `note` | Text, max 4000 | No | The provider's comment, if any |
| Reason | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | participation `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Outcome from the score**: z, z′ and ζ are satisfactory when the absolute value is 2 or less, questionable above 2 and below 3, unsatisfactory at 3 or more; En is satisfactory at 1 or less and unsatisfactory above. These are the conventional criteria of ISO 13528; the database refuses a result whose outcome disagrees.
- **Validations**: "Enter the score the provider gave." (a kind without a value); "A result without a score has no score value."; "Choose the provider's evaluation." (no score and no evaluation); "The outcome follows from the score: leave this empty." (evaluation given with a score); "Choose an active analyst."; "A participation has at most 30 results."; "A reason is required."
- **Stale record**: "Record changed. Reload before saving."
- **Effect**: the participation's revision increases by 1; audit event `participation.result_added` on the participation with the result and your reason. Both the recorder and the analyst are then authors of the data and cannot review.
- Assumption: the page does not check the score against the values entered; it records the score as the provider's report states it.

## Related pages

- Participation record
- Remove result
- Record report
