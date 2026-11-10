---
title: Reject QC batch
urls: analytical:batch_reject
views: analytical.views.batch_reject
templates: analytical/sign.html, analytical/_summary.html
models: analytical.QCBatch, analytical.AnalyticalTest, analytical.Investigation, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-10
---

## Purpose

A reviewer signs the rejection of a batch whose QC failed. Its tests are invalidated and replaced by linked reruns.

## Who can use it

- Sign-in required. **Reviewers** only; others receive 403.
- Never a user who recorded QC for the batch or generated data for any of its tests (including superseded entries and submitters), even with the reviewer role.
- Requires an enrolled signature PIN.

## Layout

- Card "Reject QC batch · BATCH": "Your signature records rejected for BATCH at record revision N", summary (Batch, QC status, Tests invalidated, Effect), signer, PIN link, form, **Cancel**, **Sign and reject**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and reject** | Always | Reviewer | "BATCH rejected; linked reruns were created."; returns to the batch |
| **Cancel** | Always | Reviewer | Nothing signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Reason for rejection |
| Expected revision (hidden) | `QCBatch.revision` | Integer | Yes | Revision when the page opened |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the batch record with the warning "Only an open batch with failed QC can be rejected.".
- **Preconditions**: batch Open ("Only open batches can be rejected."); QC failed ("Only a batch with failed QC can be rejected."); not your own work ("You cannot reject a batch containing your own work."); each test Open or Awaiting review ("Only open or awaiting-review tests can be invalidated by batch rejection."); lots in quarantine.
- **Effect**: each test becomes Invalidated and gets a new Open linked test (kind "Rerun after QC failure", or the same kind when it belongs to an investigation). A test with any value outside the limits and no investigation opens one. The batch becomes Rejected, lot revisions rise by 1, `test.invalidated` events, `signed.rejected` and an immutable signature are stored.
- **Stale page, identity, session and PIN** messages: "Record changed. Reload and review before signing."; "Enter your own signing username and PIN."; "Session expired. Sign in again before signing."; "Enroll a signature PIN first."; "Signature PIN was not accepted."; five failures lock the PIN for 15 minutes. Failed attempts are audited even though the signing is rejected.
- The summary count "Tests invalidated" is the number of tests linked to the batch.

## Related pages

- QC batch record (return target).
- [Signature PIN](/signature-pin/)
