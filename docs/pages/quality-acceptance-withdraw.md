---
title: Withdraw supplier result
urls: quality:acceptance_withdraw
views: quality.acceptance_views.acceptance_withdraw
templates: catalog/form.html
models: quality.SupplierResultAcceptance, quality.Lot, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

Withdraws a supplier result that was proposed or accepted in place of a test, while the lot is in quarantine. The requirement is then answered by a test in the laboratory, or by a new proposal. The record is kept.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403 Forbidden. The proposer and the reviewer who signed the acceptance may withdraw it too.
- **admin** or **auditor** alone do not see **Withdraw** on the acceptance record and receive 403 Forbidden if they open or submit this page.
- Only a record that is not withdrawn, on a Quarantine lot. Otherwise no form is shown and you are redirected to the acceptance record with "Supplier results are accepted only while the lot is in quarantine." or "This record is already withdrawn."

## Layout

- **Breadcrumbs**: Material lots, lot number, SRA-n (link to the record), Withdraw supplier result.
- **Intro**: "A withdrawn proposal or acceptance no longer answers the requirement: the laboratory tests it, or the supplier's result is proposed again. The record is kept."
- **Record card**: Lot, Record (SRA-n), Test ("Name (code)"), Supplier's result and State.
- **Form section**: Change control, with the reason.
- **Buttons**: **Cancel** (to the acceptance record) and **Withdraw supplier result** (red).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw supplier result** | Always | Analyst, reviewer, quality | Marks the record Withdrawn, shows "Supplier result withdrawn; the record is kept." and returns to the acceptance record |
| **Cancel** | Always | Analyst, reviewer, quality | Returns to the acceptance record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for withdrawal | `SupplierResultAcceptance.withdrawal_reason` | Text, max 2000 | Yes | Why the record should not stand; shown on the acceptance record and stored in the audit event |
| Expected revision (hidden) | `SupplierResultAcceptance.revision` | Integer | Yes | Record revision when the page opened |
| Lot / Record / Test / Supplier's result / State (Record card) | `Lot.number`, `SupplierResultAcceptance` (SRA-n), `evidence`, `state` | Text | — | The record being withdrawn; State is Awaiting acceptance or Accepted |

## Rules and hidden logic

- **When to withdraw**: the acceptance record shows "No longer stands" (the certificate record, the receipt details or the requirement changed, or laboratory work started); a proposal can no longer be signed because its qualification was revoked; or the laboratory will test the requirement itself.
- **No signature**: the page asks for a reason, not for a PIN, also when the record was already accepted. The withdrawal is attributed to you in the record and in the audit trail.
- **Stale page**: if the record changed after you opened the page (for example a reviewer accepted it), the submission is refused with status 422: "The record changed. Reload and review it before continuing."
- **Quarantine only**: the lot is locked while saving; "Supplier results are accepted only while the lot is in quarantine." if it was released after the page opened. The records of a released lot cannot be withdrawn.
- **Reason**: required. For a case the form already stops, the server's own message is "A reason is required."
- **Effect**: the record becomes Withdrawn with your name, the time and your reason; its revision and the lot's record revision increase by 1. Audit event `supplier_result.withdrawn` stores the state before and after, the test and the lot, with your reason. A disposition signing page opened earlier then fails as stale.
- **Afterwards**: nothing answers the requirement until the laboratory tests it or a new proposal is accepted. Tests of the requirement accept observations, a contract laboratory result and a QC batch again, and **Assign required tests** on the lot's testing page creates the test that was left out. A new proposal can be made from the supplier certificate record.
- **What is kept**: the record, its frozen evidence and any signature stay as they are. The lot record and the supplier qualification record list it with the state "Withdrawn".
- **Final**: a withdrawn record cannot be accepted or withdrawn again, and no page reverses a withdrawal.
- **Independence**: withdrawing is not authorship of the lot's data. The analyst who proposed the result remains an author and cannot sign the lot's QC disposition, also after the withdrawal.
- **Never edited or deleted**: the database lets the record change only to Withdrawn, with the withdrawal details, and only while the lot is in quarantine.
- **Not enforced by this page**: who among analysts, reviewers and quality users withdraws; one person may withdraw a result that another proposed and a third accepted.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entry and shows an error summary.
- Unknown record: 404.

## Related pages

- Supplier result acceptance record (Cancel returns here).
- Supplier certificate record (to propose the result again); Propose supplier result in place of a test.
- Lot record; Lot testing.
- [Material lots](/)
