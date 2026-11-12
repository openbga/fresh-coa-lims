---
title: Sign review
urls: analytical:test_review
views: analytical.views.test_review
templates: analytical/sign.html, analytical/_summary.html
models: analytical.AnalyticalTest, quality.Lot, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-12
---

## Purpose

Independently review one submitted test and sign it with meaning **reviewed**. Out-of-specification results can also be reviewed; the investigation decides their validity.

## Who can use it

- Sign-in required. **Reviewers** only; others receive 403.
- Never a user who generated the test's data (observation recorders including superseded ones, the submitter, recorders of the batch's QC), even with the reviewer role.
- Requires an enrolled signature PIN.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Breadcrumbs and a card "Sign review · T-n": the sentence "Your signature records reviewed for T-n at record revision N", a summary (test, lot and sample, Specification with its acceptance, Record revision, Replicates as recorded separated by "; " with the unit, or for qualitative tests each outcome followed by what was observed in brackets, Mean when there is one, Reportable with unit and " · conforms" or " · OUT OF SPECIFICATION"), signer, a link to enrol or change the PIN, the form, **Cancel** and **Sign and review**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and review** | Always | Reviewer | Test becomes Reviewed; "Signed review recorded for T-n."; returns to the test |
| **Cancel** | Always | Reviewer | Nothing signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Review comment |
| Expected revision (hidden) | `AnalyticalTest.revision` | Integer | Yes | Revision when the page opened |

## Rules and hidden logic

- **Checked before the PIN form opens** (on opening and on submitting, with the same rules the signature uses): an impossible review never shows a PIN field, so no PIN is checked and no failed attempt is counted. Redirects to the test record with the first applicable warning: "Lot LOT-TEST-001 is no longer in quarantine."; "This test is not awaiting review."; "You cannot review your own test." (you recorded, corrected or submitted its data, or recorded its batch QC, even if you also hold the reviewer role); "Batch QC no longer passes; this test cannot be reviewed.". Signing rechecks everything under lock, including the revision.
- **Preconditions**: test Submitted ("This test is not awaiting review."); not your own ("You cannot review your own test."); rule set approved and effective ("An approved, effective rule revision is required."); lot in quarantine; batch still Open with QC passed ("Batch QC no longer passes; this test cannot be reviewed."); calculation unchanged: the reportable value, the reportable text frozen at submission (for example "<10" or "Absent") and conformance are recalculated from the current replicates and must match ("Calculated result changed; return the test for resubmission.").
- **Stale page**: "Record changed. Reload and review before signing."
- **Identity and session**: "Enter your own signing username and PIN." (audited `signature.identity_denied`); "Session expired. Sign in again before signing."
- **PIN**: "Enroll a signature PIN first."; "Signature PIN was not accepted."; five consecutive failures lock the PIN for 15 minutes ("Signature PIN is temporarily locked."). Failures are audited (`signature.denied`) even though the signing is rejected.
- **Effect**: in one transaction the test becomes Reviewed, test and lot revisions rise by 1, `signed.reviewed` is audited and an immutable signature (signer, meaning, server time, revision, content hash) is stored.
- Review does not release the lot; disposition is a separate signed decision.

## Related pages

- Test record (return target).
- [Signature PIN](/signature-pin/)
