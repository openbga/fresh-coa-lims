---
title: Withdraw supplier certificate
urls: quality:certificate_withdraw
views: quality.certificate_views.certificate_withdraw
templates: catalog/form.html
models: quality.SupplierCertificateWithdrawal, quality.SupplierCertificate, quality.SupplierCertificateResult, quality.Lot
reviewed: 2026-11-15
---

## Purpose

Marks a supplier certificate record of a quarantined lot as withdrawn when it should not stand, for example one recorded on the wrong lot. The record and its results are kept and shown as withdrawn.

## Who can use it

- Sign-in required. **analyst** role only; others receive 403 Forbidden. Any analyst may withdraw, not only the one who recorded the certificate. The supplier certificate record shows **Withdraw supplier certificate** only to analysts, on a Quarantine lot, while the record is not withdrawn.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the analyst role acts with that role only, with no exception to the independence rules.
- Only a Quarantine lot: otherwise no form is shown and you are redirected to the supplier certificate record with "Only quarantined lots accept supplier certificate records." This check runs on opening and on submission.
- Only the current, not withdrawn record can be withdrawn. Opening the page for another record redirects to the supplier certificate record with "The certificate record changed. Reload and review it before changing it." (a correction replaced it) or "A withdrawn certificate record cannot be changed."

## Layout

- **Breadcrumbs**: Material lots, lot number, "Supplier certificate" with the certificate number (link to the record), Withdraw supplier certificate.
- **Intro**: "Withdraw a certificate record that should not stand, for example one recorded on the wrong lot. The record and its results are kept and marked as withdrawn; a withdrawn record cannot be corrected."
- **Record card**: Lot, Material, Status, Certificate number, Issued by.
- **Form section**: Change control, with the reason.
- **Buttons**: **Cancel** (to the supplier certificate record) and **Withdraw supplier certificate** (red).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw supplier certificate** | Always | Analyst | Adds the withdrawal, shows "Supplier certificate withdrawn; the record is kept." and returns to the supplier certificate record |
| **Cancel** | Always | Analyst | Returns to the supplier certificate record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for withdrawal | `SupplierCertificateWithdrawal.reason` | Text, max 2000 | Yes | Why the record should not stand; shown on the supplier certificate record and stored in the audit event. |

The page has no hidden field. The server checks the record itself when saving.

## Rules and hidden logic

- **Stale record**: if a correction replaced the record, or it was withdrawn, after you opened the page, the submission is refused with status 422: "The certificate record changed. Reload and review it before changing it." or "A withdrawn certificate record cannot be changed." The server checks this under the lot lock, so a correction and a withdrawal of the same record cannot both apply.
- **Quarantine only**: the lot is locked while saving; "Only quarantined lots accept supplier certificate records." if it was released after the page opened. The certificates of a released lot cannot be withdrawn.
- **Fewer conditions than recording**: withdrawal does not need receipt details from a supplier or approved requirements. A certificate can be withdrawn after the lot's receipt details were corrected to Made on site.
- **Reason**: required. For a case the form already stops, the server's own message is "A reason is required."
- **Effect**: a withdrawal record with your reason, your name and the time is added to the certificate record. The lot's record revision increases by 1. Audit event `supplier_certificate.withdrawn` stores the certificate record as it stood and that it is now withdrawn, with your reason. A disposition signing page opened earlier then fails as stale.
- **What is kept**: the certificate record and its results are never changed or removed. The supplier certificate record shows the status "Withdrawn", the reason, and "Supplier certificate withdrawn" in History. The lot record lists the certificate with the status "Withdrawn" and the number of its results, without a comparison label.
- **Final**: a withdrawn record cannot be corrected or withdrawn again, and no page reverses a withdrawal. A new certificate, also one with the same number, can be recorded for the lot while it is Quarantine.
- **Supplier results in place of tests**: a withdrawal is not refused when a result of the record is proposed or accepted in place of a test. Every such proposal and acceptance stops standing: it shows "No longer stands" on the lot record with "supplier certificate COA-TEST-001 was corrected or withdrawn after the result was taken from it" and blocks the lot's QC disposition until it is withdrawn on its own record. The requirement then needs a laboratory test, or a result proposed from another current certificate record.
- **A failing result and other certificates**: a withdrawn certificate no longer contradicts a result of the same test on another certificate of the lot. A proposal or acceptance that had stopped standing only because this record stated a result that does not meet the specification stands again, and such a result can be proposed.
- **Disposition notice**: a withdrawn certificate no longer raises the warning on the disposition signing page for a result that does not meet the specification.
- **Independence**: withdrawing makes you an author of the lot's supplier certificate data. You cannot sign this lot's disposition, even with the quality role. The recorders of the withdrawn record remain authors too.
- **Append-only**: a withdrawal cannot be edited or deleted. The database also refuses a withdrawal for a lot that is not in quarantine, a withdrawal of a record that a correction replaced, a second withdrawal of the same record and a withdrawal without a reason.
- **What a withdrawal does not do**: it deletes nothing, and it does not place or release a hold. It does not withdraw an acceptance taken from the record; that is a separate step on the acceptance record. When no result of the record was proposed or accepted in place of a test, and none contradicted a result of another certificate, a withdrawal changes neither the tests the lot requires nor what its disposition needs.
- Unknown certificate: 404.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entry and shows an error summary. Refusals from the server appear in the summary.

## Related pages

- Supplier certificate record.
- Record supplier certificate; Correct supplier certificate.
- Lot record; Sign lot disposition.
- Supplier result acceptance record; Withdraw supplier result.
- [Holds](/stability/holds/)
- [Material lots](/)
