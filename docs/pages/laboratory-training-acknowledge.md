---
title: Acknowledge training
urls: laboratory:training_acknowledge
views: laboratory.views.training_acknowledge
templates: ops/sign.html
models: laboratory.TrainingRecord, core.ElectronicSignature
reviewed: 2026-11-19
summary: Sign to confirm that you received the training recorded about you and that the record is right. Only the trainee can sign. Acknowledged training can then be relied on by a qualification.
---

## Common tasks
### Acknowledge the training
1. Check [[Activity]], [[Procedure or course]], [[Kind]], [[Outcome]], [[Trainer or assessor]] and [[Completed on]] against what you received.
2. Enter [[Signing username]], [[Reason for signing]] and [[Signature PIN]].
3. Select [[Sign and acknowledge]]. The training record opens, acknowledged.
### Leave without signing
1. Select [[Cancel]]. If the page says you cannot sign, select [[Back to record]]. Nothing is signed.
## Good to know
- Only the trainee can acknowledge. Anyone else, whatever their role, is refused.
- If something is wrong, do not sign. Training records cannot be edited, so ask for a new record.
- Acknowledging does not qualify you. It lets a qualification rely on this training.
- Re-enter your PIN for every signature. Five wrong PINs in a row lock it for 15 minutes, even though the action is refused.

## Purpose

Sign the trainee's acknowledgement of a training record, with meaning **acknowledged**.

## Who can use it

- Sign-in required. Role: Analyst, Reviewer or Quality; others receive the standard 403 page.
- A user other than the trainee sees "Only the trainee can acknowledge this training record."; a record already acknowledged shows "This training record is already acknowledged." Both show the facts, no PIN control, and a **Back to record** link (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page.

## Layout

- Breadcrumbs (Laboratory, Training, TRN-n, Acknowledge), then a signing dialog (a plain card without JavaScript): TRN-n and revision, the meaning, key facts, signer, the link **Enroll or change your signature PIN**, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and acknowledge** | Not denied | The trainee | Signs with meaning **acknowledged**; returns to the training record with "Training acknowledged." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Activity / Procedure or course / Kind / Outcome / Trainer or assessor / Completed on / Recorded by | `TrainingRecord.activity`, `.document_ref`, `.kind`, `.outcome`, `.trainer`, `.completed_on`, `.recorded_by` | Display | — | From the training record |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `TrainingRecord.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: you are the trainee ("Only the trainee can acknowledge this training record."); the record awaits acknowledgement ("This training record is already acknowledged.").
- Meaning text: "You confirm that you received this training and that the record of it is right."
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Acknowledged and the acknowledgement time, raises the record revision by 1, writes the audit event `signed.acknowledged` and an immutable signature bound to the new revision.

## Related pages

- Training record (Cancel returns here)
