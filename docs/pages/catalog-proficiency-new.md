---
title: New participation
urls: catalog:proficiency_new
views: catalog.proficiency_views.proficiency_new
templates: catalog/form.html
models: catalog.ProficiencyParticipation, catalog.Method
reviewed: 2026-11-19
summary: Plan the laboratory's participation in one round of a proficiency testing scheme or other interlaboratory comparison for a method, with the day results are due. Quality only.
---

## Common tasks

### Plan a participation

1. Choose the [[Method]] and the [[Kind]], then enter the [[Provider or organizer]] and the [[Round]].
2. Describe the [[Test item]] and enter the day in [[Results due]].
3. Enter the [[Reason]] and select [[Plan participation]]. The participation opens.

### Start from a method

1. On the method record, select [[New participation]]. The method is already chosen.

## Good to know

- The day results are due puts the round on the Reminders page until the day its results were reported is recorded or it is cancelled.
- The method cannot be changed later, so choose it with care. Cancel and plan again if it is wrong.
- Planning is not authorship: you can still review the outcome later if you record none of the report or results and do not change the plan once they are recorded.
- Not enforced by this page: which methods must take part, how often, and in which scheme.

## Purpose

Plans one participation for a method, recording who runs the comparison, which round and item, and when results are due.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403. The role is checked before anything else.

## Layout

- **Header**: title "New participation" and an introduction: the description of a participation followed by "The day results are due puts it on the reminders."
- **Form sections**: Comparison (Method, Kind, Provider or organizer, Provider's accreditation, Scheme), Plan (Round, Test item, Results due), Change control (Reason). Buttons **Cancel** (to the list) and **Plan participation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Plan participation** | Always | Quality | Creates the participation as open; message "PT-n planned."; opens the participation |
| **Cancel** | Always | Quality | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Method | `ProficiencyParticipation.method` | Choice of method (search) | Yes | The method whose results are compared. Preselected by the address `?method=<id>` when that method exists. |
| Kind | `kind` | Proficiency testing scheme, Interlaboratory comparison | Yes | Kind of comparison |
| Provider or organizer | `provider` | Text, max 160 | Yes | Who runs the scheme, or the laboratory or group that organizes the comparison |
| Provider's accreditation | `provider_accreditation` | Text, max 200 | No | As the provider states it, for example its accreditation to ISO/IEC 17043 and the certificate number |
| Scheme | `scheme` | Text, max 160 | No | The scheme or programme, when it has a name |
| Round | `round_ref` | Text, max 80 | Yes | The round number or the comparison's reference |
| Test item | `test_item` | Text, max 200 | Yes | The material or matrix of the item and the measurands |
| Results due | `results_due` | Date | Yes | The day the laboratory's results are due to the provider |
| Reason | audit reason | Text, max 2000 | Yes | Stored in the audit event |

## Rules and hidden logic

- **State**: the participation starts as Open, revision 1, planned by you.
- **Validations**: "Choose the kind of comparison."; "State the day results are due."; "A reason is required."; required fields left blank are refused by the form. A due day in the past is accepted: the participation then shows "Results overdue".
- **Audit**: event `participation.planned` with the participation snapshot and your reason.
- **Database guards**: provider, round and test item cannot be blank.
- Dates and text are entered as the provider's documents give them; the page does not check them against the provider.

## Related pages

- [Proficiency testing](/catalog/proficiency/)
- Participation record (opens after saving)
- Method record (the preselected method)
