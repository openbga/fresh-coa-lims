---
title: Correct supplier certificate
urls: quality:certificate_correct
views: quality.certificate_views.certificate_correct
templates: catalog/form.html
models: quality.SupplierCertificate, quality.SupplierCertificateResult, quality.Lot, quality.LotReceipt
reviewed: 2026-11-14
---

## Purpose

Corrects a supplier certificate record of a quarantined lot by adding a linked, newer record. The record it replaces is kept and stays visible in the History on the supplier certificate record. Every result is compared again with the lot's current requirements.

## Who can use it

- Sign-in required. **analyst** role only; others receive 403 Forbidden. Any analyst may correct, not only the one who recorded the certificate. The supplier certificate record shows **Correct supplier certificate** only to analysts, on a Quarantine lot that still has receipt details from a supplier and approved requirements, while the record is not withdrawn.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the analyst role acts with that role only, with no exception to the independence rules.
- The lot must still be able to hold a certificate. Otherwise no form is shown and you are redirected to the supplier certificate record with the reason: "Only quarantined lots accept supplier certificate records." (lot no longer in Quarantine); "Record the lot's receipt details before its supplier certificate."; "Only a lot received from a supplier has a supplier certificate." (the receipt details were corrected to Made on site); or "Assign approved requirements to the lot first: supplier results are recorded against them.", followed by why they are missing or held. These checks run on opening and on submission.
- Only the current, not withdrawn record can be corrected. Opening the page for another record redirects to the supplier certificate record with "The certificate record changed. Reload and review it before changing it." (a correction replaced it) or "A withdrawn certificate record cannot be changed."

## Layout

- **Breadcrumbs**: Material lots, lot number, "Supplier certificate" with the certificate number (link to the record), Correct supplier certificate.
- **Intro**: "A correction adds a record and keeps the one it replaces. Every result is compared again with the lot's current requirements. State what was wrong in the reason."
- **Record card**: Lot, Material, Status, then from the current receipt details Supplier (code · name), Supplier lot number ("Not known" when blank) and Manufacturer lot number ("Not stated" when blank).
- **Form** prefilled from the current record: Certificate; one section per approved requirement of the lot as it stands now, headed by the test name and its acceptance criterion; Change control. The reason starts blank.
- **Buttons**: **Cancel** (to the supplier certificate record) and **Correct supplier certificate**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Correct supplier certificate** | Always | Analyst | Adds the correction, shows "Supplier certificate corrected; the original is kept." and opens the supplier certificate record, now showing the new record |
| **Cancel** | Always | Analyst | Returns to the supplier certificate record without saving |

## Fields

In the table, "Test" stands for the name of each requirement, for example "Assay result (%)".

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Certificate number | `SupplierCertificate.number` | Text, max 80 | Yes | Help: "As printed on the certificate." |
| Issued by | `SupplierCertificate.issued_by` | Text, max 160 | Yes | Help: "The company the certificate names as its issuer." |
| Date of the certificate | `SupplierCertificate.issued_on` | Date | Yes | Cannot be in the future. |
| Lot number on the certificate | `SupplierCertificate.stated_lot` | Text, max 80 | Yes | Help: "As printed. It is shown beside the lot numbers of the receipt details." |
| Where the certificate is kept | `SupplierCertificate.document_ref` | Text, max 200 | Yes | Help: "Document number or location in your controlled records." |
| Notes | `SupplierCertificate.notes` | Text, max 2000 | No | Help: "Anything else the certificate states, for example a test that is not in the specification or a result in another unit." |
| Test result (unit) | `SupplierCertificateResult.value`, `value_text` | Decimal, at most 8 decimals and 12 digits before the point | No | Numeric and count requirements. Prefilled exactly as recorded, trailing zeros included. Help as on Record supplier certificate. |
| Test stated as less than this value | `SupplierCertificateResult.qualifier` | Checkbox | No | Ticked when the result was recorded as less than the value. Help: "For a result printed as <10. It is kept as stated and never becomes zero or the number." |
| Test result | `SupplierCertificateResult.outcome` | Menu: "Not stated on the certificate", then the requirement's two outcomes | No | Qualitative requirements. |
| Test wording on the certificate | `SupplierCertificateResult.stated_text` | Text, max 200 | With a result | Help: "The result in the certificate's own words, e.g. Complies." |
| Test method on the certificate | `SupplierCertificateResult.method` | Text, max 200 | No | Help: "The test method the certificate states. Leave blank if it states none." |
| Test limits on the certificate | `SupplierCertificateResult.limits` | Text, max 200 | No | Help: "The supplier's own limits, as printed. Leave blank if it states none." |
| Reason for correction | `SupplierCertificate.reason` | Text, max 2000 | Yes | What was wrong; stored on the new record and in the audit event. |
| Basis (hidden) | — | Hash | Yes | Identifies the requirements the page showed when it opened. See Stale requirements. |

## Rules and hidden logic

- **What is prefilled**: the certificate details of the current record. A result is carried over only where the lot still has a requirement for that test and the requirement takes the same kind of result: a number for a numeric or count requirement, or an outcome the requirement still offers. Any other result starts blank. The method and limits stated are carried over for every test the lot still requires.
- **The correction replaces the whole record**: the new record holds exactly the results on the form when you submit. A test you clear is not in the new record, and a test you fill in is added.
- **Compared again**: every result on the form is compared with the lot's current requirements and stored with them, including results you did not change. Correcting is how a result marked "Requirement no longer current" gets compared with the current requirement.
- **No change**: "The correction changes nothing." when the certificate details and every result, method, limits, comparison and requirement equal the current record. Differences only in surrounding spaces do not count. A different precision is a change ("99.6" instead of "99.60"), and so are unchanged values compared with a requirement that changed.
- **Stale record**: if another correction replaced the record, or it was withdrawn, after you opened the page, the submission is refused with status 422 and your entries stay on screen: "The certificate record changed. Reload and review it before changing it." or "A withdrawn certificate record cannot be changed." The server checks this under the lot lock, so two corrections of the same record cannot both apply.
- **Stale requirements**: the hidden Basis is a hash of the requirements the page showed. If they changed after you opened the page: "The lot's requirements changed after this page was opened. Reload and review the results against the current requirements." Nothing is saved and your entries stay on screen.
- **Same checks as recording**: "Enter at least one result stated on the certificate."; "Enter the result, or clear this test if the certificate does not state it."; "Enter the wording of the result on the certificate."; "A count must be a whole number of zero or more."; "A less-than result needs a value greater than zero."; "Ensure that there are no more than 8 decimal places."; "The date of the certificate cannot be in the future." (today's date in the deployment time zone). Units are not converted.
- **Quarantine only**: the lot is locked while saving; "Only quarantined lots accept supplier certificate records." if it was released after the page opened. The certificates of a released lot cannot be corrected.
- **Effect**: a new record linked to the one it replaces is added with you as recorder and becomes the current record of the certificate. The lot's record revision increases by 1. Audit event `supplier_certificate.corrected` stores the record before and after with your reason. A disposition signing page opened earlier then fails as stale.
- **What is kept**: the replaced record and its results are never changed. The supplier certificate record lists the correction in History and shows each changed detail as old value → new value. The lot record lists only the current record.
- **Independence**: correcting makes you an author of the lot's supplier certificate data, as does having recorded a record that was later replaced. None of these users can sign this lot's disposition, even with the quality role.
- **Append-only**: a certificate record and its results cannot be edited or deleted. The database also refuses a correction for a lot that is not in quarantine, a correction linked to another lot's record, a correction of a withdrawn record and a second correction of the same record.
- **What this record does not do**: supplier results do not answer a requirement, do not count towards QC disposition and do not block it, and are not printed on the certificate of analysis. A corrected result that does not meet the specification does not place a hold; place one from Holds if the lot must not be dispositioned.
- **One current record per number**: changing the certificate number to one that another current certificate of this lot holds is refused beside Certificate number: "This lot already holds a certificate with this number. Correct that record, or withdraw it if it does not belong to this lot." Upper and lower case and surrounding spaces do not make a number different; a withdrawn certificate does not count. The record keeps its own number without objection.
- **Not enforced by this page**: the supplier and the certificate's issuer are not checked for qualification or approval, and the record does not qualify the supplier.
- Unknown certificate: 404.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept."). Refusals from the server appear beside the field they concern, or in the summary when they concern the whole form.

## Related pages

- Supplier certificate record.
- Record supplier certificate; Withdraw supplier certificate.
- Lot record; Lot requirements and sampling.
- [Holds](/stability/holds/)
- [Material lots](/)
