---
title: Record findings
urls: trending:evaluation_findings
views: trending.views.evaluation_findings
templates: catalog/form.html
models: trending.Evaluation, impact.Assessment, core.AuditEvent
reviewed: 2026-11-19
summary: Record or change what an open out-of-trend evaluation found and did: laboratory check, cause, lots and results affected, actions, quality-system reference and impact assessment. Quality only. Whoever records cannot conclude.
---

## Common tasks

### Record the findings

1. Fill in the [[Laboratory check]], the [[Cause]] and the [[Lots and results affected]].
2. Add the [[Actions]] and, if there is one, the [[Quality-system reference]].
3. Enter the [[Reason for change]] and select [[Save findings]].

### Name an impact assessment

1. Choose it in [[Impact assessment]]. It must be concluded before the evaluation is.

## Good to know

- You can save before everything is filled in and come back; each save is a change in the history.
- Whoever records findings cannot conclude the evaluation; another quality person does.
- Concluding needs the laboratory check, the cause and the lots and results affected. A confirmed outcome also needs the actions.
- Saving with nothing different from what is stored is refused with "Nothing was changed."

## Purpose

Records the findings and follow-up of an open evaluation.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- A concluded evaluation is not changed: the page returns to it with "OOT-n is concluded: it no longer changes."

## Layout

- **Header**: title "Record findings · OOT-n" and an introduction: "Record what the evaluation found and did as it progresses. Whoever records findings cannot conclude the evaluation."
- **Record** panel: Evaluation and Chart.
- **Form sections**: Findings (Laboratory check, Cause, Lots and results affected), Follow-up (Actions, Quality-system reference, Impact assessment), Change control (Reason for change). Buttons **Cancel** (to the evaluation) and **Save findings**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save findings** | The evaluation is open | Quality | Saves; message "Findings of OOT-n recorded."; returns to the evaluation |
| **Cancel** | Always | Quality | Returns to the evaluation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Laboratory check | `Evaluation.laboratory_check` | Text | No | Whether a laboratory error explains the results: the data, calculations, instruments, standards and records checked, and what they showed |
| Cause | `cause` | Text | No | The cause found, in the laboratory, the material or the process, or that none was found |
| Lots and results affected | `effect` | Text | No | Whether the lots behind these results, and results already reported, are affected, and what was done about them |
| Actions | `actions` | Text | No | What was done or is planned, by whom and when |
| Quality-system reference | `quality_reference` | Text, max 200 | No | The deviation, investigation or CAPA record in the quality system |
| Impact assessment | `impact_assessment` | Choice (search) of assessments that are not withdrawn | No | An impact assessment of the lots and results affected. It must be concluded before the evaluation is |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `Evaluation.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Checked on saving** (under lock): the evaluation is open; the revision is unchanged ("Record changed. Reload before saving."); a withdrawn assessment is refused ("<label> was withdrawn."); "Nothing was changed."; "A reason is required."
- **Effect**: the values are stored, the revision rises by 1 and audit event `evaluation.findings_recorded` records the before and after with your reason.
- **Independence**: this event makes you an author of the findings, so you cannot conclude the evaluation.

## Related pages

- Evaluation record
- Conclude evaluation
- Impact assessment (named here)
