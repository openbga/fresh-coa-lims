---
title: Approve supplier qualification
urls: suppliers:qualification_approve
views: suppliers.qualification_views.qualification_approve
templates: ops/sign.html
models: suppliers.SupplierQualification, core.ElectronicSignature
reviewed: 2026-11-17
summary: Sign the recorded qualification evidence so that a supplier's certificate results for the tests covered can be relied on, for lots received within the stated dates.
---

## Common tasks
### Approve the qualification
1. Check the facts shown.
2. Enter [[Signing username]], [[Reason for signing]] and [[Signature PIN]].
3. Select [[Sign and approve]].
### Go back without signing
1. Select [[Cancel]], or [[Back to record]] when the page says you cannot sign.
## Good to know
- You cannot approve evidence you recorded, whatever roles you hold.
- The date the lot was received decides coverage, not the signing date. Evidence with past or future dates can be signed.
- Approval changes nothing on any lot. Each supplier result is still proposed and accepted on the lot, where its rule set allows.
- A revoked qualification cannot be approved. Record a new one.

## Purpose

Approve recorded supplier qualification evidence with meaning **approved**. From then on a result the supplier's certificate states for a covered test can be proposed in place of a test, for a lot of the material received within the stated dates.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive the standard 403 page.
- The Quality user who recorded the evidence sees "You cannot approve supplier qualification evidence you recorded."; a record already approved shows "This qualification is already signed."; a revoked one "This qualification was revoked. A revoked qualification is final; record a new one.". Each shows the facts, no PIN control, and a **Back to record** link (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Quality role has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Suppliers, the supplier's code, SQ-n, Approve), then a signing dialog (a plain card without JavaScript): SQ-n and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality, not the recorder | Signs with meaning **approved**; returns to the qualification record with "Supplier qualification signed." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Supplier / Material / Tests covered / Valid / How the supplier was qualified / Evidence / Evidence link / Recorded by | `SupplierQualification.supplier`, `.material`, `.test_codes`, `.valid_from`, `.valid_until`, `.basis`, `.evidence_ref`, `.evidence_url`, `.recorded_by` | Display | — | Everything the signature binds, from the qualification record; Valid reads "start to end"; an empty value shows a dash |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `SupplierQualification.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: awaiting approval ("Only recorded qualifications can be approved."); you did not record the evidence ("You cannot approve supplier qualification evidence you recorded.").
- Meaning text: "You approve this evidence as showing that the supplier's certificate results for the tests covered can be relied on, for lots received within the stated dates."
- **What the signature starts**: lots of the material received from Valid from to Valid until, both days inclusive, are covered for the tests named. The date the lot was received decides, not the signing time: a lot received before today is covered when that date lies within the dates. Evidence with a Valid from in the future can be signed; it shows as "Approved, starts later". Evidence whose Valid until has already passed can be signed too: it shows as "Expired" and covers lots received within its dates.
- **What the signature does not do**: it changes nothing on any lot. Each supplier result is still proposed by an analyst and accepted by a reviewer on the lot, and only where the lot's rule set allows reliance for that test.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Approved with the signing time, raises the record revision by 1, writes the audit event `signed.approved` and an immutable signature bound to the new revision. The database accepts the approval time only together with this change of state and never lets it change afterwards.
- **Not enforced by this page**: signing a qualification is not authorship of the results later accepted under it. A signer or recorder who also holds the analyst or reviewer role may propose or accept a supplier result under the qualification; the independence rules of the acceptance apply there.
- **Not enforced by this page**: the evidence document is not read by the system; the signer checks it. How often a supplier is re-confirmed is not enforced; the qualification's end date is the only limit.
- **Assumption**: two different Quality users, one recording and one signing, is a design default of this product, not a statement of what any regulation requires.

## Related pages

- Supplier qualification record (Cancel returns here)
- [Signature PIN](/signature-pin/)
