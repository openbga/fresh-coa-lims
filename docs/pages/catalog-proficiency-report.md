---
title: Record report
urls: catalog:proficiency_report
views: catalog.proficiency_views.proficiency_report
templates: catalog/form.html
models: catalog.ProficiencyParticipation, catalog.MethodRevision
reviewed: 2026-11-19
summary: Record or change what the laboratory did in a round and what the provider's report says: method version, days, where the records are kept, the report and its date. Whoever records it cannot review the outcome.
---

## Common tasks

### Record the laboratory's report

1. Choose the [[Method version used]] and enter [[Item received]] and [[Results reported]].
2. Enter where the originals are kept in [[Laboratory records]].
3. Enter the [[Provider's report]], [[Report dated]] and optionally the [[Report link]].
4. Enter the [[Reason for change]] and select [[Save report]].

### Update it when the provider's report arrives

1. Open the page again, fill in the report fields and select [[Save report]].

## Good to know

- Everything is optional on this page, but a review needs the reported day, the laboratory's records, the provider's report and its date.
- Whoever saves a report change cannot review the outcome of this participation.
- Saving without a change is refused and does not make you an author.
- Dates cannot be in the future.

## Purpose

Records the laboratory's side of a round (which approved method version was used, when the item arrived and results were sent, where the original records are kept) and the provider's report.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403.
- A participation that is not open redirects to its record with a message such as "PT-n is closed: it no longer changes." A participation under corrective follow-up gives "PT-n is reviewed: its plan, report and results no longer change; its corrective follow-up is open."

## Layout

- **Header**: "Record report · PT-n" with the introduction "What the laboratory did and what the provider's report says. Whoever records the report cannot review the outcome."
- **Record panel**: Participation, Method.
- **Form sections**: Laboratory (Method version used, Item received, Results reported, Laboratory records), Provider's evaluation (Provider's report, Report dated, Report link), Change control (Reason for change). Buttons **Cancel** and **Save report**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save report** | Open | Analyst, reviewer, quality | Saves; message "Report of PT-n recorded."; opens the participation |
| **Cancel** | Always | Same | Returns to the participation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Method version used | `ProficiencyParticipation.method_version` | Choice of an approved version of the method, newest first; "Not stated" | No | The version the results were obtained with |
| Item received | `received_on` | Date | No | Day the item arrived; not in the future |
| Results reported | `reported_on` | Date | No | Day the laboratory sent its results to the provider; not in the future |
| Laboratory records | `data_ref` | Text, max 200 | No | Worksheet, notebook or data system reference of the original records |
| Provider's report | `report_ref` | Text, max 200 | No | The report that evaluates the round, with its number or version |
| Report dated | `report_on` | Date | No | Date of the provider's report; not in the future |
| Report link | `report_url` | http or https link, max 500 | No | Optional link to the report |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Validations**: "Choose an approved version of this method."; "The day the item was received cannot be in the future."; "The day results were reported cannot be in the future."; "The report's date cannot be in the future."; "Results cannot be reported before the item was received."; "State the day results were reported before the report's date."; "Nothing was changed."; "A reason is required."; a link that is not http or https is refused.
- **Stale record**: "Record changed. Reload before saving."
- **Effect**: revision increases by 1; audit event `participation.report_recorded` with before and after values and your reason. Its actor is an author of the participation's data and so cannot review it.
- **Dates**: none in the future; the reported day not before the day the item was received ("Results cannot be reported before the item was received."); a report date needs the reported day ("State the day results were reported before the report's date.") and cannot be before it ("The provider's report cannot be dated before results were reported.").
- A recorded reported day moves an open participation from Planned or Results overdue to Results reported, and removes its reminder.
- Not enforced by this page: that the report matches the provider's document, or that the version named is the one the analyst used.

## Related pages

- Participation record
- Record result
- [Proficiency testing](/catalog/proficiency/)
