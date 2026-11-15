---
title: Revoke contract laboratory approval
urls: laboratory:contract_approval_revoke
views: laboratory.contract_views.contract_approval_revoke
templates: ops/sign.html
models: laboratory.ContractApproval, laboratory.ContractUse, core.ElectronicSignature
reviewed: 2026-11-14
---

## Purpose

Withdraw a signed contract laboratory approval with meaning **revoked**. No further report is accepted under it; results already recorded stay as they are and remain listed on the approval.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive the standard 403 page.
- Any Quality user may revoke, including the one who recorded the evidence or the one who approved it.
- A record not yet signed shows "This approval is not signed yet; there is nothing to revoke."; one already revoked shows "This approval was revoked. A revoked approval is final; record a new one.". Both show the facts, no PIN control, and a **Back to record** link (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Quality role has exactly that role's authority.

## Layout

- Breadcrumbs, then a signing dialog (a plain card without JavaScript): CLA-n and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and revoke** | Not denied | Role: Quality | Signs with meaning **revoked**; returns to the approval record with "Contract laboratory approval revoked." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Laboratory / Method / Valid / Evidence / Evidence link / Scope / Recorded by | `ContractApproval.laboratory`, `.method_code`, `.valid_from`, `.valid_until`, `.evidence_ref`, `.evidence_url`, `.scope_note`, `.recorded_by` | Display | — | Everything the signature binds, from the approval record; Valid reads "start to end"; an empty value shows a dash |
| Accepted reports that relied on it | `ContractUse` (count) | Display | — | How many reports were accepted under this approval. They are listed on the approval record |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `ContractApproval.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Precondition**: currently approved ("Only approved approvals can be revoked."). An approved record can be revoked after its last valid day or before its first.
- Meaning text: "You withdraw this approval; no further report is accepted under it. Results already recorded stay as they are and remain listed on the approval."
- **From the signature on**: no new report is accepted under this approval, whatever the date of the report. That includes a correction naming another laboratory, report number or report date. An attempt is refused with "The approval for method “METHOD” that covered 2026-01-05 was revoked; a revoked approval is relied on no further." unless another approved approval of the laboratory covers that date. A report being recorded while the revocation is signed waits for it and is then refused.
- **Results already recorded stay**: they are not changed, invalidated or held. A correction that keeps the laboratory and the report is still accepted and keeps the approval already relied on, so a transcription error can be fixed. The approval record shows the notice "Assess the results" with their number and lists them; each test record and its Sign review page show an "Approval revoked" notice with the revocation time, and the QC disposition signing page of the lot shows a warning for each such result.
- **Final**: a revoked approval cannot be approved again or edited (database guard). Record a new approval for the laboratory and method instead.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Revoked with the signing time, raises the record revision by 1, writes the audit event `signed.revoked` and an immutable signature bound to the new revision. The database requires the revocation time and keeps the approval time unchanged.
- **Not enforced by this page**: the software records no assessment of the results that relied on the approval and holds no lot by itself. The revocation does not block their review, the lot's disposition or its certificate. Place a hold from Holds if a lot must not be dispositioned.
- **Assumption**: letting any Quality user revoke, the recorder included, treats revocation as a protective act. It is a design default of this product.

## Related pages

- Contract laboratory approval record (Cancel returns here)
- [Holds](/stability/holds/)
- [Signature PIN](/signature-pin/)
