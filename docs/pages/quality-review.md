---
title: Sign result review
urls: quality:review
views: quality.views.sign
templates: signatures/sign.html, signatures/dialog.html
models: quality.Result, quality.Lot, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-10
---

## Purpose

Independently review one foundation (manual-limit) result and sign it with meaning **reviewed**. Native test results are reviewed on their own analytical page (Sign review), which has broader authorship, QC and OOS rules.

## Who can use it

- Sign-in required. **Reviewers** only; others receive 403.
- Never the result's own analyst, even with the reviewer role.
- Requires an enrolled signature PIN.

## Layout

- A signing dialog (a plain card without JavaScript): meaning, lot number, the result's record revision, the result (test, value, unit, limits), the signer, a link to enrol or change the PIN, the form, **Sign reviewed** and **Cancel**. Focus starts in the PIN field or on the error.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign reviewed** | Always | Reviewer, not the analyst | Result becomes Reviewed; "Signed review recorded."; returns to the lot record |
| **Cancel** / Escape | Always | Any | Returns to the lot record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Review comment and reason for signing |
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; cleared after errors |
| Expected revision (hidden) | `Result.revision` | Integer | Yes | The result revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: lot is Quarantine and result is Recorded ("This result is not awaiting review."); result conforms ("Out-of-specification result: investigation is required."); not your own result ("You cannot review your own result."); rule set still approved and effective.
- **Stale page**: "Record changed. Reload and review before signing." when the result changed since opening. The dialog shows the result revision you are reviewing; the signature binds the resulting revision (shown + 1).
- **Identity**: username and PIN are re-entered for every signature; "Enter your own signing username and PIN." on mismatch (audited as `signature.identity_denied`).
- **Session**: defaults are a 15-minute idle and 8-hour absolute limit; sessions without recorded login times count as expired. On expiry the next request signs you out with "Your session expired. Sign in again to continue." The inline "Session expired. Sign in again before signing." is an extra safeguard at the moment of signing.
- **PIN**: "Enroll a signature PIN first."; "Signature PIN was not accepted."; 5 consecutive failures lock the PIN for 15 minutes ("Signature PIN is temporarily locked."). Failures are recorded (`signature.denied`) even though the review is rejected.
- **Effect**: in one transaction the result becomes Reviewed and its revision +1, the lot revision +1, an audit event `signed.reviewed` and an immutable signature (signer, meaning, server time, bound revision, content hash) are stored.

## Related pages

- Lot record.
- Sign review (native analytical test review).
- [Signature PIN](/signature-pin/)
