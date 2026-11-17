---
title: Withdraw supplier result
urls: quality:acceptance_withdraw
views: quality.acceptance_views.acceptance_withdraw
templates: catalog/form.html, ops/sign.html
models: quality.SupplierResultAcceptance, quality.Lot, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

Withdraws a supplier result that was proposed or accepted in place of a test, while the lot is in quarantine. A proposal is withdrawn with a reason; an acceptance that was signed is withdrawn with a signature. The requirement is then answered by a test in the laboratory, or by a new proposal. The record is kept.

## Who can use it

- Sign-in required. A proposal (Awaiting acceptance): **analyst**, **reviewer** or **quality** role. An acceptance (Accepted): **reviewer** or **quality** role only; an analyst without one of them receives 403 Forbidden. Users with none of the three roles receive 403 Forbidden.
- The proposer may withdraw the proposal, and the reviewer who signed the acceptance may sign its withdrawal.
- **admin** or **auditor** alone do not see **Withdraw** on the acceptance record and receive 403 Forbidden if they open or submit this page.
- Only a record that is not withdrawn, on a Quarantine lot. Otherwise no form is shown and you are redirected to the acceptance record with "Supplier results are accepted only while the lot is in quarantine." or "This record is already withdrawn."

## Layout

- **Breadcrumbs**: Material lots, lot number, SRA-n (link to the record), Withdraw supplier result.
- **Proposal** (Awaiting acceptance), a form page. Intro: "A withdrawn proposal no longer stands for the requirement: the laboratory tests it, or the supplier's result is proposed again. The record is kept." Then the Record card (Lot, Record (SRA-n), Test ("Name (code)"), Supplier's result and State), the section Change control with the reason, and the buttons **Cancel** (to the acceptance record) and **Withdraw supplier result** (red).
- **Acceptance** (Accepted), a signing dialog (a plain card without JavaScript): SRA-n and revision, the meaning, the same five facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and **Sign and withdraw**. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw supplier result** | The record is Awaiting acceptance | Analyst, reviewer, quality | Marks the record Withdrawn, shows "Supplier result withdrawn; the record is kept." and returns to the acceptance record |
| **Sign and withdraw** | The record is Accepted | Reviewer, quality | Signs with meaning **withdrawn**; marks the record Withdrawn, with the same message and return |
| **Cancel** (Escape on the signing dialog) | Always | Any | Returns to the acceptance record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for withdrawal (proposal) | `SupplierResultAcceptance.withdrawal_reason` | Text, max 2000 | Yes | Why the record should not stand; shown on the acceptance record and stored in the audit event |
| Signing username (acceptance) | — | Text | Yes | Must equal your own username |
| Reason for signing (acceptance) | `SupplierResultAcceptance.withdrawal_reason`, `AuditEvent.reason` | Text, max 2000 | Yes | Why the acceptance should not stand; shown on the acceptance record and recorded with the signature |
| Signature PIN (acceptance) | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `SupplierResultAcceptance.revision` | Integer | Yes | Record revision when the page opened |
| Lot / Record / Test / Supplier's result / State | `Lot.number`, `SupplierResultAcceptance` (SRA-n), `evidence`, `state` | Text | — | The record being withdrawn; State is Awaiting acceptance or Accepted |

## Rules and hidden logic

- **When to withdraw**: the acceptance record shows "No longer stands" (the certificate record, the receipt details or the requirement changed, another certificate of the lot states a result for the test that does not meet the specification, laboratory work started, or a proposal can no longer be signed because its qualification was revoked or the rule set is no longer approved and effective); or the laboratory will test the requirement itself.
- **Proposal, reason only**: the page asks for a reason, not for a PIN. The withdrawal is attributed to you in the record and in the audit trail: audit event `supplier_result.withdrawn` stores the state before and after, the test and the lot, with your reason.
- **Acceptance, signature**: withdrawing reverses a signed decision, so a reviewer or a quality user signs it. Meaning text: "You withdraw the acceptance of this supplier's result. It no longer answers the requirement: the laboratory tests it, or the supplier's result is proposed again. The record and its signatures are kept." One transaction writes the audit event `signed.withdrawn` and an immutable signature with meaning **withdrawn**, bound to the new revision.
- **Identity, session and PIN** (acceptance): you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: a submission made after the record changed is refused with status 422 and nothing changes: "The record changed. Reload and review it before continuing." on the reason form, "Record changed. Reload and review before signing." on the signing dialog. A proposal that a reviewer accepted after you opened the page is not withdrawn by your reason: the signing dialog is shown instead, or 403 Forbidden for an analyst alone.
- **Quarantine only**: the lot is locked while saving; "Supplier results are accepted only while the lot is in quarantine." if it was released after the page opened (on the signing dialog under "Not permitted", without a PIN field, status 403). The records of a released lot cannot be withdrawn.
- **Reason**: required. For a case the form already stops, the server's own message is "A reason is required."
- **Effect**: the record becomes Withdrawn with your name, the time and your reason; its revision and the lot's record revision increase by 1. A disposition signing page opened earlier then fails as stale.
- **Afterwards**: nothing answers the requirement until the laboratory tests it or a new proposal is accepted. Tests of the requirement accept observations, a contract laboratory result, raw-data files and a QC batch again, and **Assign required tests** on the lot's testing page creates the test that was left out. A new proposal can be made from the supplier certificate record.
- **What is kept**: the record, its frozen evidence and its signatures (that of the acceptance included) stay as they are. The lot record and the supplier qualification record list it with the state "Withdrawn".
- **Final**: a withdrawn record cannot be accepted or withdrawn again, and no page reverses a withdrawal.
- **Independence**: withdrawing is not authorship of the lot's data. The analyst who proposed the result remains an author and cannot sign the lot's QC disposition, also after the withdrawal.
- **Never edited or deleted**: the database lets the record change only to Withdrawn, with the withdrawal details, and only while the lot is in quarantine.
- **Not enforced by this page**: who among the permitted roles withdraws. One person may withdraw a result that another proposed and a third accepted, and the reviewer who accepted a result may sign its withdrawal.
- **Form behaviour** (reason form): the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entry and shows an error summary.
- Unknown record: 404.

## Related pages

- Supplier result acceptance record (Cancel returns here).
- Supplier certificate record (to propose the result again); Propose supplier result in place of a test.
- Lot record; Lot testing.
- [Signature PIN](/signature-pin/)
- [Material lots](/lots/)
