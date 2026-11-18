---
title: Impact assessment record
urls: impact:detail
views: impact.views.assessment_detail
templates: ops/record.html
models: impact.Assessment, impact.Item, stability.Hold, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One impact assessment: the problem, the records it names (tests, lots, studies, certificates) with the decision on each, holds placed, and the conclusion. Quality decides and concludes; others read.
---

## Common tasks

### Decide on each record

1. Select [[Record decision]] in the row. Use [[Change decision]] to revise it while the assessment is open.
2. Choose Affected or Not affected, give the reason, and for Affected say what is done about it.

### Protect an affected lot

1. In the Lots table, select [[Place hold]] in the lot's row and give the reason.
2. Release the hold later on its own page.

### Conclude the assessment

1. When every record has a decision and nothing new is found, select [[Conclude]]. Another quality person who took no part in it does this.
2. Sign with your PIN on that page.

### Add records the system did not find

1. Select [[Add record]], choose the kind and name the record.
2. If the page says new records are found, select [[Find affected records]] first.

## Good to know

- The assessment changes none of the records it names. Tests, lots, studies and certificates are acted on through their own pages and signatures.
- A certificate is withdrawn on the certificate's own page, with a signature and the evidence that recipients were notified. Marking it Affected here does not withdraw it.
- Conclude shows only when every record has a decision and no new record is found from the cause.
- You cannot conclude an assessment you started, decided or held part of, or whose assessed work you did.
- Concluded and Withdrawn are final. Earlier decisions stay in the audit trail.

## Purpose

The record of an impact assessment: what failed, the period of concern, every record the problem may have affected, quality's decision on each, any protective holds and the signed conclusion.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; others receive 403.
- **Find affected records**, **Add record**, **Record decision**, **Change decision**, **Place hold**, **Conclude** and **Withdraw** show to quality users while the assessment is Open. The server checks the role again on each page.
- A quality user who started the assessment, added or decided one of its records, placed one of its holds, used the failed resource in the period or produced or investigated the work it assesses sees "You took part in this assessment or in the work it assesses: another quality person concludes it." in place of **Conclude**.
- Admin alone is read-only here.

## Layout

- **Header**: breadcrumbs (Impact assessments, IA-n), the title "IA-n · <problem>", the status (Open, Concluded or Withdrawn) and the action buttons.
- **Notice** (when one applies): "New records found" with the number of records the cause now finds that are not yet in the assessment; "Decisions needed" with the number without a decision; "Concluded" with the counts affected and not affected and the reason; "Withdrawn" with the reason.
- **Facts**: Cause, What happened, Date found, Period of concern, Quality-system reference ("None" when empty), Records (total and without a decision), Started by, Started, Decided, Reason for the decision. The revision shows in the line under the title.
- **Records**, one table per kind that has records, in the order Tests, Lots, Stability studies, Certificates. Columns: Record (link), Now (the record's current status, "out of specification" for a failing test), Why it is in the assessment (the basis and whether Found from the cause or Added by quality), Decision (Affected with its follow-up, Not affected with its reason, or "No decision"), Follow-up reference, and Decide. The Lots table also has Hold (identifier, link and state) and Protect. A note under Lots explains the hold; a note under Certificates says a certificate is withdrawn on its own page.
- When there are no records: "No record is in the assessment. Add the records it may have affected."
- **Signatures** and **History**: the conclusion or withdrawal signature and the audit events of the assessment and its records.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Find affected records** | Open, and the cause finds records not yet in it | Quality | Opens Find affected records |
| **Add record** | Open | Quality | Opens Add record |
| **Conclude** (primary) | Open, no record without a decision, nothing new found, you are not an author | Quality | Opens Conclude impact assessment |
| **Withdraw** (under More, red) | Open and no hold placed through it is active | Quality | Opens Withdraw impact assessment |
| **Record decision** / **Change decision** | Open; a row without or with a decision | Quality | Opens the decision form for that record |
| **Place hold** | Open, a lot row with no hold and a lot that is not cancelled | Quality | Opens Place hold |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Cause | `Assessment.cause` and the named record | Text | — | What failed |
| What happened | `Assessment.description` | Text | — | As written when started |
| Date found, Period of concern | `found_on`, `period_from`, `period_until` | Dates | — | The period decides which records are found |
| Quality-system reference | `Assessment.quality_reference` | Text | — | The deviation, CAPA or change record |
| Started by, Started | `started_by`, `started_at` | Person, date and time | — | Who started it and when |
| Decided, Reason for the decision | `decided_at`, `decision_reason` | Date and time, text | — | When and why it was concluded or withdrawn |
| Revision | `Assessment.revision` | Integer | — | Raised by every change to the assessment or a record; signing pages bind to it |
| Record | `Item.test`, `lot`, `study`, `report` | Link | — | Test (T-n, code, lot), lot (number, material), study (identifier, lot) or certificate (number, lot) |
| Why it is in the assessment | `Item.basis`, `Item.origin` | Text | — | The reason a found record is named, or what quality wrote when adding it |
| Decision | `Item.decision`, `rationale`, `follow_up` | Choice and text | — | Affected or Not affected, with its reason and follow-up |
| Follow-up reference | `Item.follow_up_reference` | Text | — | The investigation, hold, certificate or quality record |
| Hold | `Item.hold` | Link | — | The quality hold placed through this record |

## Rules and hidden logic

- **States**: Open, then Concluded or Withdrawn. Both are final; a closed assessment takes no more records, decisions or holds.
- **Not changed by the assessment**: the tests, lots, studies and certificates named keep their own state, revision and signatures. Anything done about them, such as a retest, a reassessment, a hold release or a certificate withdrawal or amendment, is done on their own pages.
- **Records can only be added**: a record is never removed from an assessment, and each record appears once.
- **Conclude is hidden** while any record has no decision or the cause finds records not in the assessment; the notice says how many.
- **Withdraw is hidden** while a hold placed through the assessment is active.
- **Reading**: the page reads the cause again each time it opens, so a record made since the start shows in "New records found".
- Events written by the assessment: `impact.started`, `impact.records_found`, `impact.record_added`, `impact.record_decided`, `impact.hold_placed`, `signed.impact_assessed`, `signed.withdrawn`.
- **Database guards**: assessments and records cannot be deleted; a concluded or withdrawn assessment cannot be changed; what an assessment or record is about, and why, cannot be edited; the revision never moves back; a record is added undecided, only while the assessment is open; a hold linked to a record stays linked.

## Related pages

- [Impact assessments](/impact/)
- Find affected records; Add record; Record decision; Place hold; Conclude impact assessment; Withdraw impact assessment
- Test, lot, stability study and certificate records (each row links to its own page)
- Hold record (releasing a hold)
