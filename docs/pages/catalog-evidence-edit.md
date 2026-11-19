---
title: Change draft evidence record
urls: catalog:evidence_edit
views: catalog.evidence_views.evidence_edit
templates: catalog/form.html
models: catalog.MethodEvidence
reviewed: 2026-11-19
summary: Correct the fields of a draft method evidence record, with a reason. Whoever changes a draft cannot approve it.
---

## Common tasks

### Change a draft

1. Edit the fields that need correcting.
2. Enter the [[Reason for change]] and select [[Save changes]]. The record opens.

### Leave without changes

1. Select [[Cancel]].

## Good to know

- You cannot approve a draft you changed, even with the quality role.
- Saving with nothing different is refused: "Nothing was changed."
- If someone changed the draft after you opened this page, saving is refused. Reload and try again.
- Only a draft can be changed. An approved record is frozen.

## Purpose

Changes the fields of a draft evidence record. The change is kept in the audit trail with its reason.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403. The role is checked before the record is looked up.
- A record that is not a draft redirects to the record with "Only a draft record can be changed."

## Layout

- **Header**: "Change draft MEV-n", introduction "Whoever changes a draft cannot approve it."
- **Record panel**: Method.
- **Form sections**: Evidence, What was studied, Report, Conclusion, Change control. Buttons **Cancel** and **Save changes**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save changes** | Draft | Analyst, reviewer, quality | Saves; message "Draft MEV-n changed."; opens the record |
| **Cancel** | Always | Same | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Kind of evidence | `MethodEvidence.kind` | The four suitability kinds | Yes | Kind of evidence |
| Title | `MethodEvidence.title` | Text, max 160 | Yes | Short name |
| Procedure studied | `MethodEvidence.procedure_ref` | Text, max 200 | Yes | Procedure and revision |
| Intended use | `MethodEvidence.intended_use` | Text, max 4000 | Yes | What the method is used for |
| Source of the procedure | `MethodEvidence.source` | Text, max 200 | For a compendial verification or transfer | Pharmacopoeial text and edition, or transferring laboratory |
| Transfer approach | `MethodEvidence.transfer_approach` | Choice | For a transfer | Cleared when the kind is not a transfer |
| Protocol | `MethodEvidence.protocol_ref` | Text, max 200 | No | Protocol and revision |
| Report | `MethodEvidence.report_ref` | Text, max 200 | Yes | Report and revision |
| Report link | `MethodEvidence.report_url` | http or https link | No | Link to the report |
| Report completed on | `MethodEvidence.completed_on` | Date | Yes | Not in the future |
| Conclusion | `MethodEvidence.conclusion` | Suitable for the intended use, Not suitable | Yes | The report's conclusion |
| Statement of suitability | `MethodEvidence.statement` | Text, max 4000 | Yes | Whether and how the method is fit |
| Deviations | `MethodEvidence.deviations` | Text, max 4000 | No | Deviations and criteria not met |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `MethodEvidence.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before saving." when the revision differs.
- **Validations**: the same as for a new record, plus "Nothing was changed." and "Only a draft record can be changed."
- **Effect**: the revision increases by 1; audit event `method_evidence.changed` with before and after snapshots and your reason. The method cannot be changed.
- **Independence**: your change counts as editing, so you cannot approve the draft.

## Related pages

- Method evidence record (Cancel and save return here)
- New method evidence record
