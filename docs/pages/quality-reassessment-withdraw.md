---
title: Withdraw reassessment
urls: quality:reassessment_withdraw
views: quality.reassessment_views.reassessment_withdraw
templates: ops/sign.html
models: quality.Reassessment, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: Sign the withdrawal of a reassessment that was started in error. Quality only. The record, its tests and results are kept and the lot's dates do not change. A failed result cannot be withdrawn.
---

## Common tasks

### Withdraw the reassessment

1. Check the lot, the sample and each test line shown.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and withdraw]]. You return to the record, now Withdrawn.

### Find out why you cannot withdraw

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- Withdrawing leaves the lot's dates in force as they were. A new reassessment can start afterwards.
- The reassessment, its tests and their results are kept. Its tests take no more work.
- A reassessment with a failed result is not withdrawn. Conclude that the material is not suitable instead.
- Starting or testing the reassessment does not stop you withdrawing it. Independence is required to conclude it.

## Purpose

Sign a reassessment with meaning **withdrawn**, for one started in error. Nothing is deleted.

## Who can use it

- Sign-in required. **quality** role only; others, and an account holding only Admin, receive 403.
- Refused with the reason and no PIN control (403): "This reassessment is no longer open."; "Testing is in progress: …" with each item (a test awaiting review, an open test holding results or raw data that were not submitted, or an open investigation); or "A result of this reassessment does not meet its acceptance criterion. Conclude that the material is not suitable instead."
- The **Withdraw** button on the record is hidden while the withdrawal would be refused.
- Assumption: this page does not bar the person who started the reassessment or produced its test data; the independence rule applies to concluding.

## Layout

- Breadcrumbs (Material lots, the lot number, the reassessment, Withdraw), then a signing dialog (a plain card without JavaScript): the record and revision, the meaning, key facts (Lot, Reassessment and sample, Retest date in force, Expiry date, one line for each test code with its result and "Conforms", "Does not conform" or "Not decided", and what is not complete), the signer, the PIN link, the form, **Cancel** and **Sign and withdraw**. Opening the page never signs.
- **Denied**: the facts, a red "Not permitted" notice with the reason and **Back to record** (403).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and withdraw** | Not denied | Quality | Signs with meaning **withdrawn**; returns to the record with "RA-n withdrawn; the record is kept." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot, Reassessment, Retest date in force, Expiry date, test lines | — | Display | — | What the signature binds |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `Reassessment.decision_reason`, audit event reason | Text, max 2000 | Yes | Why it was started in error. Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Reassessment.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You withdraw a reassessment started in error. Its tests take no more work and the lot's dates in force do not change. The record, its tests and their results are kept."
- **Checked again when signing**, under the reassessment's lock: still open, nothing in progress, no failed result (a reviewed result that does not meet its criterion, or one confirmed by an investigation).
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Withdrawn with the time and the reason, raises the revision by 1, writes the audit event `signed.withdrawn` and an immutable signature bound to the new revision. No new retest date is set; the lot's record, dates and disposition are not changed, and the lot can be reassessed again.
- After withdrawal its tests are left as they are when a QC batch is rejected, and take no more work.

## Related pages

- Reassessment record (Cancel returns here)
- Conclude reassessment
- Lot record
- [Signature PIN](/signature-pin/)
