---
title: Reject QC batch
urls: analytical:batch_reject
views: analytical.views.batch_reject
templates: analytical/sign.html, analytical/_summary.html
models: analytical.QCBatch, analytical.AnalyticalTest, analytical.Investigation, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-17
summary: A reviewer signs the rejection of an open QC batch whose QC failed. Its tests are invalidated and replaced by linked reruns.
---

## Common tasks
### Reject the batch
1. Check the number of tests invalidated and the effect in the summary.
2. Enter your [[Signing username]], [[Signature PIN]] and a [[Reason]], then select [[Sign and reject]].
### Set or change your signature PIN
1. Select [[Enroll or change your signature PIN]] if you have no PIN yet.
## Good to know
- You cannot reject a batch whose QC you recorded or that holds a test with your data.
- An invalidated test with a reading outside its limits opens an investigation, unless it already belongs to one.
- Superseded tests, and tests of a rejected or cancelled lot, stay as they are and get no rerun.
- To fix a transcription error, correct the QC result instead of rejecting the batch.

## Purpose

A reviewer signs the rejection of a batch whose QC failed. Its tests are invalidated and replaced by linked reruns.

## Who can use it

- Sign-in required. **Reviewers** only; others receive 403.
- Never a user who recorded QC for the batch or generated data for any of its tests (including superseded entries and submitters), even with the reviewer role.
- Requires an enrolled signature PIN.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Card "Reject QC batch · BATCH": "Your signature records rejected for BATCH at record revision N", summary (Batch, QC status, Tests invalidated, Effect), signer, PIN link, form, **Cancel**, **Sign and reject**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and reject** | Always | Reviewer | "BATCH rejected; linked reruns were created.", or "BATCH rejected; no test was invalidated, so no rerun was created." when every test was left as it was; returns to the batch |
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
- **Preconditions**: batch Open ("Only open batches can be rejected."); QC failed ("Only a batch with failed QC can be rejected."); not your own work ("You cannot reject a batch containing your own work."); each test that is neither Superseded nor Not completed is Open or Awaiting review ("Only open or awaiting-review tests can be invalidated by batch rejection."); lots in quarantine (tests of rejected or cancelled lots and of stability pulls that take no more testing are left out, see below). The own-work check reads the batch's QC recorders and the authors of every test in the batch, superseded ones included.
- **Tests of a rejected or cancelled lot**: a lot that was rejected, or cancelled as received in error, no longer stops the batch from being rejected. Its tests stay as they were when the lot was decided: they are not invalidated, get no rerun, and the lot's revision is not raised. A lot that was released still stops the rejection ("lots in quarantine" above).
- **Superseded tests**: a test of the batch superseded when its lot's requirements were replaced stays as it is: it is not invalidated and gets no rerun. So does an open test of a stability pull that takes no more testing (the pull was recorded as missed, or its study closed); its pull's revision is not raised.
- **Not completed tests**: a test of the batch that quality signed as not completed stays as it is: it is not invalidated and gets no rerun. Its authors still count for the own-work check.
- **Effect**: each other test becomes Invalidated and gets a new Open linked test (kind "Rerun after QC failure", or the same kind when it belongs to an investigation). The rerun of a stability test stays with its pull: it names the pull, no lot and no sample. A batch may hold tests of lots and of pulls; each is locked and its revision raised by 1, the lot's or the pull's. A test with any current reading that fails on its own (a value outside the limits, a value that fails once rounded half-up to the reporting precision, a less-than reading such as "<5000" that cannot be shown to meet them, or, when every replicate is recorded, a set whose result submission would calculate fails, in which case all readings count) and no investigation opens one (its trigger is shortened to 200 characters with "…"); `test.invalidated` lists those readings as recorded. The batch becomes Rejected, lot revisions rise by 1, `test.invalidated` events, `signed.rejected` and an immutable signature are stored.
- **Stale page, identity, session and PIN** messages: "Record changed. Reload and review before signing."; "Enter your own signing username and PIN."; "Session expired. Sign in again before signing."; "Enroll a signature PIN first."; "Signature PIN was not accepted."; five failures lock the PIN for 15 minutes. Failed attempts are audited even though the signing is rejected.
- The summary count "Tests invalidated" is the number of tests linked to the batch that are neither Superseded nor Not completed and do not belong to a missed pull, a closed study, or a rejected or cancelled lot.

## Related pages

- QC batch record (return target).
- [Signature PIN](/signature-pin/)
