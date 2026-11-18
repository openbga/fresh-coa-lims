---
title: New impact assessment
urls: impact:new
views: impact.views.assessment_new
templates: catalog/form.html
models: impact.Assessment, impact.Item, core.AuditEvent
reviewed: 2026-11-17
summary: Start an impact assessment: name what failed and the period it may have affected. The system then lists the tests, lots, studies and certificates it can find. Quality only.
---

## Common tasks

### Assess a failed instrument or chamber

1. Open the equipment record, select [[More]] then [[Assess impact]]. The equipment is filled in.
2. Enter [[Problem]], [[What happened]], [[Date found]] and the period of concern.
3. Select [[Start assessment]]. The records found from the cause are listed for decisions.

### Assess a supplier, reagent or contract laboratory

1. Use [[Assess impact]] on the supplier, reagent lot or contract laboratory record, or choose [[What failed]] here.
2. Pick the record in its own field, set the period and select [[Start assessment]].

### Assess a problem the system cannot trace

1. Choose Other in [[What failed]], describe it and select [[Start assessment]].
2. Add the records yourself with Add record.

## Good to know

- The period of concern decides which records are found. For equipment, start it at the last accepted passing calibration before the failure.
- Starting records nothing about the listed records. Each needs a decision, and the assessment changes none of them.
- A cause that finds more than 500 records is refused. Narrow the period and assess the rest in another assessment.
- Whoever starts an assessment cannot conclude it.

## Purpose

Starts an impact assessment. It records the problem, the period of concern and the quality-system reference, then adds the records the cause finds. Quality decides on each afterwards.

## Who can use it

- Sign-in required. **quality** role only; others, and an account holding only Admin, receive 403.
- The links **Assess impact** on equipment, reagent lot, supplier and contract laboratory records show to quality users and open this form with that record chosen (`?equipment=`, `?reagent_lot=`, `?supplier=` or `?contract_laboratory=`; the first valid one counts).

## Layout

- Breadcrumbs (Impact assessments, New impact assessment), title, an introduction saying the system finds the tests, lots, stability studies and certificates it can, and that the assessment changes none of the records it names.
- The form, then **Cancel** (to the list) and **Start assessment**. With JavaScript it opens in the shared form dialog (large).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Start assessment** | Always | Quality | Creates IA-n, adds the records found, message "IA-n started with N record(s) found from the cause; record a decision for each." and opens the record |
| **Cancel** | Always | Quality | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| What failed | `Assessment.cause` | Equipment, Reagent or standard lot, Supplier, Contract laboratory, Other | Yes | Decides which record is named and how records are found |
| Equipment | `Assessment.equipment` | Search of equipment | For Equipment | The instrument or chamber |
| Reagent or standard lot | `Assessment.reagent_lot` | Search of reagent lots | For Reagent | The lot; solutions prepared from it are included |
| Supplier | `Assessment.supplier` | Search of suppliers | For Supplier | Lots received from it in the period are included |
| Contract laboratory | `Assessment.contract_laboratory` | Search of contract laboratories | For Contract laboratory | Results it reported in the period are included |
| Problem | `Assessment.title` | Text, max 160 | Yes | The problem in a few words |
| What happened | `Assessment.description` | Text, max 4000 | Yes | What failed, how and when it was found; also the audit reason |
| Date found | `Assessment.found_on` | Date, default today | Yes | Not in the future |
| Period of concern from | `Assessment.period_from` | Date | Yes | First day the problem may have affected work |
| Period of concern until | `Assessment.period_until` | Date, default today | Yes | Last day, inclusive; not after today |
| Quality-system reference | `Assessment.quality_reference` | Text, max 200 | No | The deviation, CAPA or change record; also shown in the reference of any hold placed |

## Rules and hidden logic

- **Only the chosen cause names a record**: "Choose the record that failed." when the field for the cause is empty; "Only the record of the cause chosen is named." when another is filled.
- **Date messages**: "Enter a date."; "The date found cannot be in the future."; "The period of concern cannot end in the future."; "The period of concern ends on or after the day it begins."; "The period of concern begins on or before the date found."; "Name the problem."; "Describe what happened and how it was found."
- **Records found from the cause** (read-only, in the laboratory's time zone, the period counted from the first day's start to the end of the last day):
  - Equipment: tests the equipment was recorded as used for in the period; the tests of any QC batch it was used for; the lots of samples it was used for outside native testing. For a stability chamber also the studies with pulls stored in it, unless the study closed before the period began.
  - Reagent or standard lot: the same uses, for the lot and every solution prepared from it at any depth.
  - Supplier: the lots whose receipt in force (not corrected) names the supplier and was received in the period.
  - Contract laboratory: tests whose results it reported with a report date in the period.
  - Other: none; quality adds records.
- **Follow-through**: every test leads to its lot (its own, or the lot of its reassessment) or, for a stability pull test, to its study. Lots found from a supplier lead to their stability studies. Every lot in the assessment, found or added, leads to each issued certificate of it.
- **Limit**: more than 500 records is refused with "The cause finds N records, more than the 500 one assessment covers. Narrow the period of concern and assess the rest in another assessment." Nothing is saved.
- **Effect**: the assessment (state Open, revision 1), its records (origin "Found from the cause", no decision) and the audit events `impact.started` (reason: the description) and, when records were found, `impact.records_found` are committed together.
- **Independence**: whoever starts an assessment cannot conclude it.
- The assessment changes none of the records it names.
- Not enforced by this page: that the period is right for the failure; the form only states the guidance.

## Related pages

- [Impact assessments](/impact/)
- Equipment, reagent lot, supplier and contract laboratory records (the Assess impact action)
- Impact assessment record (opens after starting)
