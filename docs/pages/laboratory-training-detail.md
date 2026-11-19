---
title: Training record
urls: laboratory:training_detail
views: laboratory.views.training_detail
templates: ops/record.html
models: laboratory.TrainingRecord, laboratory.Qualification, core.ElectronicSignature
reviewed: 2026-11-19
summary: One training record: who was trained, in what activity, by whom and with what outcome, whether the trainee has acknowledged it, and the qualifications that rely on it.
---

## Common tasks
### Acknowledge your own training
1. Select [[Acknowledge]]. It shows only to the trainee, while the record awaits acknowledgement.
2. Sign with your PIN on that page.
### Record a qualification that relies on this training
1. Select [[Record qualification]]. It shows once the training is acknowledged and is not an assessment found Not yet competent, unless you are the trainee.
2. The qualification form opens with the person, the activity and this record filled in. Complete it there.
### See what relies on the training
1. Read [[Qualifications relying on it]] below the details.
## Good to know
- Only the trainee can acknowledge the record. Whoever recorded it cannot, because they cannot record their own training.
- Acknowledging confirms that you received the training and that the record of it is right.
- A Not yet competent outcome stays on record, but no qualification can rely on it.
- Nothing here can be edited. A correction is a new training record.

## Purpose

Show one person's training in a method or activity and whether the trainee has acknowledged it, so a qualification can rely on it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- **Acknowledge** is shown to the trainee, who must hold the Analyst, Reviewer or Quality role. **Record qualification** is shown to those roles, except the trainee. The server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons.

## Layout

- **Header**: breadcrumbs (Laboratory, Training, TRN-n), title (the activity), identifier TRN-n, state label (Awaiting acknowledgement or Acknowledged), the revision, action buttons.
- **Details**: the facts below.
- **Qualifications relying on it**: Qualification (QUAL-n link with its activity), Qualified for, Valid until (inclusive), State. Empty: "No qualification relies on this training record yet."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Acknowledge** | Awaiting acknowledgement and you are the trainee | Trainee holding Analyst, Reviewer or Quality | Opens the acknowledgement signing page |
| **Record qualification** | The record is acknowledged and not Not yet competent, and you are not the trainee | Analyst, Reviewer, Quality | Opens the New qualification form with the person, the activity and this record filled in |
| Evidence link | An evidence URL was recorded | Any reader | Opens the external link; treat its content as untrusted |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Trainee / Activity | `TrainingRecord.trainee`, `.activity` | Person, text | — | Who was trained and the method or activity code |
| Procedure or course | `TrainingRecord.document_ref` | Text | — | The controlled procedure, method or course, with its revision |
| Kind / Outcome | `TrainingRecord.kind`, `.outcome` | Labels | — | Kind of training; Completed, Competent or Not yet competent (flagged in amber) |
| Trainer or assessor | `TrainingRecord.trainer` | Text | — | Who trained or assessed, or the course provider |
| Completed on | `TrainingRecord.completed_on` | Date | — | The day it was completed |
| Evidence reference / Evidence link / Note | `TrainingRecord.evidence_ref`, `.evidence_url`, `.note` | Text; http(s) link; text | — | Where the evidence is kept; blank when not given |
| Recorded by / Acknowledged / Revision | `TrainingRecord.recorded_by`, `.acknowledged_at`, `.revision` | User, time, integer | — | Authorship, when the trainee acknowledged it, and the revision |

## Rules and hidden logic

- The identifier is TRN- plus the record number. An outcome of Not yet competent is flagged in amber in Outcome; the state still says whether the trainee has acknowledged the record.
- The qualification table lists every qualification that cited this record, newest recorded first.
- The record is immutable apart from its acknowledgement (database guard); it cannot be edited or deleted. An unknown ID returns 404.
- Signatures and history are those of this record only.

## Related pages

- [Training](/laboratory/training/)
- [Qualifications](/laboratory/qualifications/)
- Acknowledge training and the qualification records listed above
