---
title: Approve contract laboratory approval
urls: laboratory:contract_approval_approve
views: laboratory.contract_views.contract_approval_approve
templates: ops/sign.html
models: laboratory.ContractApproval, core.ElectronicSignature
reviewed: 2026-11-17
summary: Sign approval evidence that a different quality user recorded, so reports from the laboratory for this method dated within its dates are accepted. Quality role only.
---

## Common tasks
### Approve the evidence
1. Check [[Laboratory]], [[Method]], [[Valid]], [[Evidence]] and [[Scope]], and open the link under [[Evidence link]] if there is one.
2. Enter [[Signing username]], [[Reason for signing]] and [[Signature PIN]].
3. Select [[Sign and approve]]. The approval record opens.
### Leave without signing
1. Select [[Cancel]]. If the page says you cannot sign, select [[Back to record]]. Nothing is signed.
## Good to know
- You cannot approve evidence you recorded, whatever other roles you hold.
- The dates decide, not the signing time. Evidence dated in the past or the future can be signed and covers reports dated within it.
- The system does not read the evidence document. You check it before signing.
- Re-enter your PIN for every signature. Five wrong PINs in a row lock it for 15 minutes, even though the action is refused.

## Purpose

Approve recorded contract laboratory evidence with meaning **approved**. From then on a report from the laboratory for this method is accepted when its date lies within the stated dates.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive the standard 403 page.
- The Quality user who recorded the evidence sees "You cannot approve contract laboratory evidence you recorded."; a record already approved shows "This approval is already signed."; a revoked one "This approval was revoked. A revoked approval is final; record a new one.". Each shows the facts, no PIN control, and a **Back to record** link (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Quality role has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs, then a signing dialog (a plain card without JavaScript): CLA-n and revision, the meaning, key facts, signer, the link **Enroll or change your signature PIN**, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality, not the recorder | Signs with meaning **approved**; returns to the approval record with "Contract laboratory approval signed." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Laboratory / Method / Valid / Evidence / Evidence link / Scope / Recorded by | `ContractApproval.laboratory`, `.method_code`, `.valid_from`, `.valid_until`, `.evidence_ref`, `.evidence_url`, `.scope_note`, `.recorded_by` | Display | — | Everything the signature binds, from the approval record; Valid reads "start to end"; an empty value shows a dash |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `ContractApproval.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: awaiting approval ("Only recorded approvals can be approved."); you did not record the evidence ("You cannot approve contract laboratory evidence you recorded.").
- Meaning text: "You approve this evidence as showing the laboratory may perform the method for reports dated within the stated dates."
- **What the signature starts**: reports dated from Valid from to Valid until, both days inclusive, are accepted for the method. The dates decide, not the signing time: a report dated before today is covered when its date lies within them. Evidence with a Valid from in the future can be signed; it shows as "Approved, starts later". Evidence whose Valid until has already passed can be signed too: it shows as "Expired" and covers reports dated within its dates.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Approved with the signing time, raises the record revision by 1, writes the audit event `signed.approved` and an immutable signature bound to the new revision. The database accepts the approval time only together with this change of state and never lets it change afterwards.
- **Not enforced by this page**: signing an approval is not authorship of the results later reported under it. A signer or recorder who also holds the analyst role may record a report under the approval; recording the report is what makes someone an author of that result.
- **Not enforced by this page**: the evidence document is not read by the system; the signer checks it. The Scope text is shown with each result that relies on the approval but is not checked when a report is accepted.
- **Assumption**: two different Quality users, one recording and one signing, is a design default of this product, not a statement of what any regulation requires.

## Related pages

- Contract laboratory approval record (Cancel returns here)
- [Signature PIN](/signature-pin/)
