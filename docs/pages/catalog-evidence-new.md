---
title: New method evidence record
urls: catalog:evidence_new
views: catalog.evidence_views.evidence_new
templates: catalog/form.html
models: catalog.MethodEvidence
reviewed: 2026-11-19
summary: Record, as a draft, the evidence that a method is suitable for its intended use: a validation, verification, transfer or other documented fitness. Analysts, reviewers and quality users can record.
---

## Common tasks

### Record a validation, verification or transfer

1. Choose the [[Method]] and the [[Kind of evidence]], then enter the [[Title]].
2. Describe what was studied: [[Procedure studied]] and [[Intended use]]. Add the [[Source of the procedure]] or [[Transfer approach]] when the kind needs it.
3. Give the [[Report]], [[Report completed on]], [[Conclusion]] and [[Statement of suitability]].
4. Enter the [[Reason]] and select [[Record draft]]. The record opens so you can add its characteristics.

### Start from a method

1. On the method record, select [[New evidence record]]. The method is already chosen.

## Good to know

- The record is a draft. Add the characteristics evaluated, then another quality user approves it.
- Whoever records or changes a draft cannot approve it.
- A compendial verification and a transfer must name a source; a transfer must say how it was performed.
- The report cannot be dated in the future.

## Purpose

Records the summary of a method's suitability report as a draft evidence record, with its reason in the audit trail.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others, including an account holding only admin or auditor, receive 403. The role is checked before anything else.

## Layout

- **Header**: title, introduction "Summarize the report that shows the method is suitable for its intended use. The record stays a draft, and supports no method version, until a quality person who did not record or change it approves it."
- **Form sections**: Evidence, What was studied, Report, Conclusion, Change control. Buttons **Cancel** (to the list) and **Record draft**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record draft** | Always | Analyst, reviewer, quality | Creates the draft; message "MEV-n recorded as a draft. Add the characteristics evaluated; another quality person approves it."; opens the record |
| **Cancel** | Always | Same | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Method | `MethodEvidence.method` | Choice of method (search) | Yes | The method whose suitability the record shows. Preselected by the address `?method=<id>` when that method exists. |
| Kind of evidence | `MethodEvidence.kind` | Method validation, Compendial method verification, Method transfer, Documented fitness for intended use | Yes | Kind of evidence |
| Title | `MethodEvidence.title` | Text, max 160 | Yes | Short name |
| Procedure studied | `MethodEvidence.procedure_ref` | Text, max 200 | Yes | Controlled procedure with its revision |
| Intended use | `MethodEvidence.intended_use` | Text, max 4000 | Yes | Analyte or property, materials, range, decisions supported |
| Source of the procedure | `MethodEvidence.source` | Text, max 200 | Yes for a compendial verification or transfer | The pharmacopoeial text and edition, or the transferring laboratory |
| Transfer approach | `MethodEvidence.transfer_approach` | Not a transfer, Comparative testing, Co-validation between laboratories, Revalidation or partial revalidation, Transfer waiver | Yes for a transfer | Only a transfer has one |
| Protocol | `MethodEvidence.protocol_ref` | Text, max 200 | No | Approved protocol with its revision |
| Report | `MethodEvidence.report_ref` | Text, max 200 | Yes | Report with its revision in the document system |
| Report link | `MethodEvidence.report_url` | http or https link, max 500 | No | Link to the report |
| Report completed on | `MethodEvidence.completed_on` | Date | Yes | Not in the future |
| Conclusion | `MethodEvidence.conclusion` | Suitable for the intended use, Not suitable | Yes | The report's conclusion |
| Statement of suitability | `MethodEvidence.statement` | Text, max 4000 | Yes | Whether and how the method is fit, with conditions of use |
| Deviations | `MethodEvidence.deviations` | Text, max 4000 | No | Deviations and criteria not met, and how each was assessed |
| Reason | audit reason | Text, max 2000 | Yes | Stored in the audit event |

## Rules and hidden logic

- **State**: the record starts as Draft, revision 1, recorded by you. It supports no method version until approved.
- **Validations**: "Name the pharmacopoeial text that was verified, with its edition." (compendial verification without a source); "Name the laboratory that transferred the method." (transfer without a source); "Choose how the transfer was performed."; "Only a transfer has a transfer approach."; "A report cannot be completed in the future."; "A reason is required."
- **Audit**: event `method_evidence.recorded` with the record snapshot and your reason.
- **Database guards**: text that must be stated cannot be blank, and the kind, source and approach rules are also enforced by the database.
- **Failed submission** returns the form with errors.

## Related pages

- [Method evidence](/catalog/method-evidence/)
- Method evidence record (opens after saving)
- Method record (the preselected method)
