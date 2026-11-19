---
title: New training record
urls: laboratory:training_new
views: laboratory.views.training_new
templates: ops/form.html
models: laboratory.TrainingRecord, core.AuditEvent
reviewed: 2026-11-19
summary: Record training someone else received in a method or activity. It qualifies nobody; the trainee acknowledges it with their signature, and a qualification can then rely on it.
---

## Common tasks
### Record someone's training
1. Choose the person in [[Trainee]] and enter the method or activity code in [[Activity]].
2. Enter [[Procedure or course]], [[Kind of training]], [[Outcome]], [[Trainer or assessor]] and [[Completed on]].
3. Give a [[Reason]] and select [[Record training]]. The record opens, awaiting the trainee's acknowledgement.
### Leave without recording
1. Select [[Cancel]] to return to the Training list. Nothing is saved.
## Good to know
- You cannot record your own training. The trainee's account must be active and hold the analyst, reviewer or quality role, so that they can acknowledge it.
- Only the trainee can acknowledge it. Until then no qualification can rely on it.
- Only an assessment of competence finds someone Competent or Not yet competent. Other kinds are Completed.
- Enter the activity as the qualification will name it. A qualification can rely only on training in the same activity; upper and lower case are ignored.

## Purpose

Record a person's training or assessment in a method or activity as evidence for their qualifications. Recording does not qualify anyone.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules apply.

## Layout

- Breadcrumbs (Laboratory, Training, Record training), title "New training record", the introduction "Record training someone else received. Recording it qualifies nobody: the trainee acknowledges it with their signature, and a qualification can then rely on it.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record training** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves and opens the new training record with "Training recorded; the trainee acknowledges it with their signature."; refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns to the Training list without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Trainee | `TrainingRecord.trainee` | Choice of active accounts by username | Yes | The person trained; never yourself; must hold the analyst, reviewer or quality role |
| Activity | `TrainingRecord.activity` | Text, max 120 | Yes | Method or activity code, as the qualification it supports will name it |
| Procedure or course | `TrainingRecord.document_ref` | Text, max 200 | Yes | The controlled procedure, method or course trained on, with its revision |
| Kind of training | `TrainingRecord.kind` | Choice | Yes | Read and understood, Instruction or demonstration, Supervised practice, Assessment of competence |
| Outcome | `TrainingRecord.outcome` | Choice | Yes | Completed for training; Competent or Not yet competent for an assessment |
| Trainer or assessor | `TrainingRecord.trainer` | Text, max 160 | Yes | Who gave or assessed the training, or the provider of an outside course |
| Completed on | `TrainingRecord.completed_on` | Date | Yes | The day the training or assessment was completed; not in the future |
| Evidence reference | `TrainingRecord.evidence_ref` | Text, max 200 | No | Where the signed training record, test or certificate is kept |
| Evidence link | `TrainingRecord.evidence_url` | http(s) URL | No | Untrusted external link |
| Note | `TrainingRecord.note` | Text | No | Free note |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the training record |

## Rules and hidden logic

- "You cannot record your own training." when the trainee is you; "The trainee's account is inactive." for an inactive account; "The trainee needs the analyst, reviewer or quality role to acknowledge training." for an account without one of those roles.
- "Training cannot be completed in the future." appears on Completed on for a later date.
- Outcome must fit the kind: "An assessment finds the trainee competent or not yet competent." and "Only an assessment of competence finds a trainee competent." The database enforces the same pairing.
- The record starts as Awaiting acknowledgement. Only the trainee acknowledges it; it is immutable apart from that.
- Event `training.recorded`.

## Related pages

- [Training](/laboratory/training/)
- Training record (opens after saving)
