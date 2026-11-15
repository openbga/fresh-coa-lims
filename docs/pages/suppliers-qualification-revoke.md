---
title: Revoke supplier qualification
urls: suppliers:qualification_revoke
views: suppliers.qualification_views.qualification_revoke
templates: ops/sign.html
models: suppliers.SupplierQualification, quality.SupplierResultAcceptance, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

Revoke an approved supplier qualification with meaning **revoked**. No further supplier result is accepted under it. Acceptances already signed stay as they are.

## Who can use it

- Sign-in required. Role: Quality. Any Quality user may revoke, the one who recorded the evidence included.
- Other roles receive the standard 403 page.
- A record still awaiting approval shows "This qualification is not signed yet; there is nothing to revoke."; a revoked one "This qualification was revoked. A revoked qualification is final; record a new one.". Each shows the facts, no PIN control, and a **Back to record** link (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Quality role has exactly that role's authority.

## Layout

- Breadcrumbs (Suppliers, the supplier's code, SQ-n, Revoke), then a signing dialog (a plain card without JavaScript): SQ-n and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and revoke** | Not denied | Role: Quality | Signs with meaning **revoked**; returns to the qualification record with "Supplier qualification revoked." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Supplier / Material / Tests covered / Valid / How the supplier was qualified / Evidence / Evidence link / Recorded by | `SupplierQualification.supplier`, `.material`, `.test_codes`, `.valid_from`, `.valid_until`, `.basis`, `.evidence_ref`, `.evidence_url`, `.recorded_by` | Display | — | The qualification being revoked; Valid reads "start to end"; an empty value shows a dash |
| Supplier results that relied on it | `SupplierResultAcceptance.state` | Count | — | Proposals awaiting acceptance and accepted results made under this qualification; withdrawn records are not counted. The qualification record lists them |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Why the qualification is revoked; recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `SupplierQualification.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Precondition**: approved ("Only approved qualifications can be revoked."). An Expired qualification, and one that has not started yet, can be revoked.
- Meaning text: "You withdraw this qualification; no further supplier result is accepted under it. Acceptances already signed stay as they are and remain listed on the qualification."
- **No new reliance**: a new proposal that only this qualification covered is refused: "The qualification of sup-syn-001 for assay of api-syn-001 that covered 2026-11-02 was revoked; a revoked qualification is relied on no further." This applies also to lots received before the revocation. Another signed qualification that covers the result is relied on instead.
- **Proposals awaiting acceptance**: a proposal made under this qualification can no longer be signed. The reviewer is refused when signing: "SQ-1 no longer covers this result: it was revoked, or the lot's date of receipt is outside its dates. What this proposal relied on has changed since it was made. Withdraw it and propose the supplier's result again." The proposal keeps blocking the lot's QC disposition until it is withdrawn.
- **Acceptances already signed**: they stand as signed and keep answering their requirement. Each shows "Qualification revoked" on its record and "Qualification revoked since" on the lot record. The lot's QC disposition signing page shows a warning that does not block signing. The certificate of analysis still lists the result.
- **Not enforced by this page**: the software records no assessment of the results accepted before the revocation and holds no lot by itself. Assess them under your procedure. Withdraw an acceptance on its record, or place a hold from Holds, if a lot must not be dispositioned.
- **Assumption**: ending further reliance without undoing acceptances already signed is a design default of this product. It is not a statement of what any regulation requires or permits.
- **Final**: a revoked qualification cannot be approved again. Record a new qualification.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Revoked with the signing time, raises the record revision by 1, writes the audit event `signed.revoked` and an immutable signature bound to the new revision.

## Related pages

- Supplier qualification record (Cancel returns here; it lists the supplier results that relied on the qualification)
- Supplier result acceptance record (to withdraw a proposal or an acceptance)
- [Holds](/stability/holds/)
- [Signature PIN](/signature-pin/)
