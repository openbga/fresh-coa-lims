---
title: Participation record
urls: catalog:proficiency_detail
views: catalog.proficiency_views.proficiency_detail
templates: ops/record.html
models: catalog.ProficiencyParticipation, catalog.ProficiencyResult, catalog.MethodRevision, impact.Assessment, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One participation in a proficiency testing round: plan, the laboratory's report, each result with the provider's score, the signed review, corrective follow-up, the method's other rounds, signatures and history.
---

## Common tasks

### Record what the laboratory did

1. Select [[Record result]] once for each measurand the provider scored.
2. Select [[Record report]] to give the method version used, the days, where the laboratory's records are kept and the provider's report.
3. Read [[Before review]] for what is still missing.

### Review the outcome

1. Select [[Review outcome]]. It shows only to a quality user who recorded and performed none of the results or the report, and only when nothing is missing.
2. Write your review and sign with your PIN on that page.

### Complete the corrective follow-up

1. When the review required it, select [[Record follow-up]] and describe the cause, actions and effectiveness check.
2. Another quality person selects [[Close follow-up]] once nothing is missing, and signs.

### Cancel a round that will not take place

1. Select [[Cancel participation]] under the More menu. It shows to quality while no result is recorded.

## Good to know

- Whoever recorded the report, added or removed a result, or performed a result cannot review the outcome. The page shows the reason in place of the review button.
- The outcome follows the provider's scores: a z, z′ or ζ score is satisfactory up to 2, questionable above 2 and below 3, unsatisfactory from 3. An En number is satisfactory up to 1.
- A result without a score carries the provider's evaluation as you enter it; the participation's outcome is the worst of its results.
- Review and closure freeze what was signed. A result cannot be edited: remove it and record it again, while the participation is open.

## Purpose

Shows one participation with everything recorded about it, and leads to every action on it.

## Who can use it

- Sign-in required. Viewing: analyst, reviewer, quality, admin or auditor; others receive 403.
- **Record result**, **Record report**, result **Remove**: analyst, reviewer or quality, while the participation is open.
- **Change plan**, **Cancel participation**, **Review outcome**: quality, while open; **Record follow-up**, **Close follow-up**: quality, while follow-up is open. **Assess impact**: quality, while follow-up is open.
- Who the server allows is narrower than who sees a button: review and closure also need independence (see rules).

## Layout

- **Header**: "<provider> · <round>", state, PT-n, "Revision N" and the action buttons; **Cancel participation** and **Assess impact** under the More menu.
- **Notice**: "Results overdue" (red) while an open participation has no report and its due day has passed; "Before review" (blue) while an open participation lacks something; "Corrective follow-up open" (amber) in follow-up; "Cancelled" for a cancelled participation.
- **Details**: Outcome (once reviewed), Method, Kind, Provider or organizer, Provider's accreditation, Scheme, Round, Test item, Results due (with "Overdue" while it applies), Method version used, Item received, Results reported, Laboratory records, Provider's report, Report dated, Report link, Planned by, then once reviewed Review and Corrective follow-up ("Required" or "Not required"); when follow-up was required Cause, Corrective actions, Results already reported, Impact assessment, Quality-system reference, Effectiveness check; then Planned, Reviewed, Closed and Cancelled times when they exist.
- **Results**: Measurand (unit beneath), Laboratory's result, Assigned value, Score, Outcome, Analyst, Note, and **Remove** while open for recorders. A note explains the score criteria. Empty: "No result recorded yet."
- **Other participations for <method code>**: Participation, Provider, Results due, Outcome, State, newest due day first, at most 10, with "Showing the latest N of M." when there are more. Empty: "No other participation for this method."
- **Signatures** and **History**: the review and closure signatures, and the audit events of the participation.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record result** | Open | Analyst, reviewer, quality | Opens the Record result form |
| **Record report** | Open | Analyst, reviewer, quality | Opens the Record report form |
| **Remove** (row) | Open | Analyst, reviewer, quality | Opens the Remove result form |
| **Change plan** | Open | Quality | Opens the Change plan form |
| **Cancel participation** (More menu) | Open, no result recorded | Quality | Opens the Cancel participation form |
| **Review outcome** | Open, quality, independent, nothing missing | Quality | Opens the signed review page |
| The reason "You recorded or performed results or the report of this participation; another quality person reviews it." | Open, quality, you recorded or performed data | Quality | Shown in place of the review button, even while something is still missing |
| **Record follow-up** | Follow-up open | Quality | Opens the Record follow-up form |
| **Assess impact** (More menu) | Follow-up open | Quality | Opens the New impact assessment page (not linked to this participation automatically) |
| **Close follow-up** | Follow-up open, quality, independent, nothing missing | Quality | Opens the signed closure page |
| The reason "You recorded its follow-up, or results or the report of this participation; another quality person closes it." | Follow-up open, quality, you recorded any of them | Quality | Shown in place of the close button |
| Method, Participation (other rounds) links | Always | Any viewer | Open the method or the other participation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Outcome | `ProficiencyParticipation.outcome` | Satisfactory, Questionable, Unsatisfactory, Not evaluated | — | Worst outcome of the results, frozen at review |
| Method, Kind, Provider or organizer, Provider's accreditation, Scheme, Round, Test item, Results due | `ProficiencyParticipation` fields of those names | Text, date | — | The plan |
| Method version used, Item received, Results reported, Laboratory records, Provider's report, Report dated, Report link | `method_version`, `received_on`, `reported_on`, `data_ref`, `report_ref`, `report_on`, `report_url` | Version, dates, text, link | — | The laboratory's report; the version links to the method |
| Planned by | `planned_by` | Person | — | Who planned it |
| Review, Corrective follow-up | `review_conclusion`, `follow_up_required` | Text, Required or Not required | — | Shown once reviewed |
| Cause, Corrective actions, Results already reported, Impact assessment, Quality-system reference, Effectiveness check | follow-up fields | Text, link to the assessment with its state | — | Shown when follow-up was required |
| Planned, Reviewed, Closed, Cancelled | `planned_at`, `reviewed_at`, `closed_at`, `cancelled_at` | Date and time | — | Shown when set |
| Revision | `revision` | Integer | — | Increases with each change, result added or removed, review, follow-up and closure |
| Measurand, unit, Laboratory's result, Assigned value, Score, Outcome, Analyst, Note | `ProficiencyResult` fields | Text, "z = 1.2" (also z′, ζ and En) or "No score", status, person | — | One row per result, in the order recorded |

## Rules and hidden logic

- **State shown**: Planned, Results overdue (open, due day passed, no report), Results reported (open, reported day recorded), Follow-up open, Closed, Cancelled.
- **Before review** lists, joined in one text: "Record the laboratory's results with the provider's scores."; "Record the day the results were reported."; "Record where the laboratory's original records are kept."; "Record the provider's report and its date."
- **Score criteria** (the conventional ones of ISO 13528, as the note on the page states): z, z′ and ζ satisfactory when the score is 2 or less in absolute value, questionable above 2 and below 3, unsatisfactory at 3 or more; En satisfactory at 1 or less, unsatisfactory above. A result without a score carries the provider's evaluation. The database refuses a result whose outcome disagrees with its score.
- **Independence for review**: whoever recorded the report, added or removed a result, or performed a result (read from the audit trail and the results) cannot review. Planning, cancelling, or changing the plan before a result or the reported day is recorded, is not authorship; a plan change made after that (`participation.plan_corrected`) is.
- **Independence for closure**: additionally whoever recorded the follow-up.
- **Before closing**, as the notice states: "Record the cause found."; "Record the corrective actions."; "Record whether results already reported could be affected."; "Record how the actions were shown to work."; and a linked impact assessment that is withdrawn ("<label> was withdrawn: link another impact assessment or none.") or still open ("<label> is still open: conclude it before closing the follow-up."). The Quality-system reference is optional.
- **Immutability**: a reviewed participation keeps its review; in follow-up only the follow-up fields and the closure change; a closed or cancelled one never changes; results change only while open and are never updated; a participation is never deleted (database guards).
- Not enforced by this page: which outcome calls for which action beyond requiring follow-up for an unsatisfactory result, and whether the criteria suit the scheme. Assumption: a provider that evaluates by other criteria is recorded as a result without a score, with its own evaluation.

## Related pages

- [Proficiency testing](/catalog/proficiency/)
- Record result, Record report, Remove result, Change plan, Cancel participation, Review outcome, Record follow-up, Close follow-up
- Method record
- Impact assessment (linked in the follow-up)
