---
title: Out-of-trend evaluation record
urls: trending:evaluation_detail
views: trending.views.evaluation_detail
templates: ops/record.html
models: trending.Evaluation, trending.EvaluationAlert, trending.Chart, impact.Assessment, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One out-of-trend evaluation: the alerts it covers, the findings, the impact assessment, the conclusion and outcome, signature and history. Quality records findings, adds alerts and concludes it.
---

## Common tasks

### Record what was found

1. Select [[Record findings]]. It shows to quality while the evaluation is open.
2. Fill in the laboratory check, the cause, the lots and results affected and the actions; save as often as needed.

### Conclude the evaluation

1. Read [[Evaluation open]] for what is still missing.
2. Select [[Conclude evaluation]]. It shows to a quality person who recorded none of the findings or the covered results' data, once nothing is missing.
3. Choose the outcome and sign with your PIN on that page.

### Cover more alerts

1. Select [[Add alerts]] to add further open alerts of the same chart while the evaluation is open.

### Assess the impact on lots

1. Select [[Assess impact]] under the More menu to start an impact assessment; then name it in the findings.

## Good to know

- Whoever recorded findings, or data of a result the evaluation covers, cannot conclude it. The page shows the reason in place of the conclude button.
- A named impact assessment must be concluded before the evaluation is.
- Concluding freezes the alerts, the findings and the conclusion. A concluded evaluation never changes.
- A confirmed outcome needs actions recorded. Not confirmed does not.

## Purpose

Shows one evaluation with everything recorded about it and leads to every action on it.

## Who can use it

- Sign-in required. Viewing: analyst, reviewer, quality, admin or auditor; others receive 403.
- **Record findings**, **Add alerts**, **Assess impact** and **Conclude evaluation** show to the quality role while the evaluation is open. Concluding also needs independence (see rules).

## Layout

- **Header**: "Out-of-trend evaluation · test name · MAT-CODE", the state (Open, Out of trend confirmed, Not confirmed), OOT-n, "Revision N" and the action buttons; **Assess impact** under the More menu.
- **Notice**, while open: "Evaluation open" (amber), listing what is missing before it can be concluded, or "The findings are recorded. A quality person who recorded none of them, and none of the results' data, concludes the evaluation."
- **Details**: once concluded Outcome and Conclusion; then Chart, Laboratory check, Cause, Lots and results affected, Actions, Quality-system reference, Impact assessment (link with its state), Opened by, Opened, and Concluded when set.
- **Alerts covered**: Test, Lot, Result, Review signed, Limits, Rules broken. Empty: "No alert."
- **Signatures** and **History**: the conclusion signature and the audit events of the evaluation.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record findings** | Open | Quality | Opens the Record findings form |
| **Add alerts** | Open | Quality | Opens the Add alerts form |
| **Assess impact** (More menu) | Open | Quality | Opens the New impact assessment page (not linked to this evaluation automatically) |
| **Conclude evaluation** | Open, you recorded no findings or data of the covered results, nothing missing | Quality | Opens the signed conclusion page; it is the primary button |
| The reason "You recorded findings of this evaluation, or data of a result it covers; another quality person concludes it." | Open, quality, you are an author | Quality | Shown in place of the conclude button |
| Chart, Test, Lot, Limits, Impact assessment links | Always | Any viewer | Open the chart, the test, the lot, the limits version or the assessment |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Outcome | `Evaluation.outcome` | Out of trend confirmed, Not confirmed | — | Shown once concluded |
| Conclusion | `conclusion` | Text | — | What the evaluation concludes |
| Laboratory check | `laboratory_check` | Text | — | Whether a laboratory error explains the results |
| Cause | `cause` | Text | — | The cause found, or that none was found |
| Lots and results affected | `effect` | Text | — | Whether lots and results already reported are affected, and what was done |
| Actions | `actions` | Text | — | What was done or is planned, by whom and when |
| Quality-system reference | `quality_reference` | Text | — | The deviation, investigation or CAPA record |
| Impact assessment | `impact_assessment` | Link, label and state | — | The assessment named, if any |
| Opened by, Opened, Concluded | `opened_by`, `opened_at`, `concluded_at` | Person, date and time | — | Who opened it and when; when it was concluded |
| Revision | `revision` | Integer | — | Rises with each findings change, added alerts and the conclusion |
| Alerts covered | `EvaluationAlert` | One row per alert | — | The result, the limits version that judged it and the rules it broke, as they stood when it was added |

## Rules and hidden logic

- **Before concluding** (the notice): "Record the laboratory check."; "Record the cause found, or that none was found."; "Record whether the lots and results already reported are affected."; and a named impact assessment that is withdrawn ("<label> was withdrawn: name another impact assessment or none.") or open ("<label> is still open: conclude it before this evaluation."). With the outcome Out of trend confirmed, actions are also needed ("Record the actions taken on a confirmed out-of-trend result."); that is checked when you conclude. The Quality-system reference is optional.
- **Independence**: whoever recorded findings (audit trail) or recorded data of any covered result cannot conclude. Opening the evaluation or adding alerts is not authorship.
- **Immutability**: once concluded nothing changes; the database refuses changing it, changing or removing its alerts, and deleting an evaluation.
- Not enforced by this page: what follows an alert, and whether a lot is held; the disposition page only shows a notice.

## Related pages

- [Evaluations](/trends/evaluations/)
- Chart record
- Record findings, Add alerts, Conclude evaluation
- Impact assessment (named in the findings)
