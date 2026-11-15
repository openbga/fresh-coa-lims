---
title: Record supplier certificate
urls: quality:certificate_new
views: quality.certificate_views.certificate_new
templates: catalog/form.html
models: quality.SupplierCertificate, quality.SupplierCertificateResult, quality.Lot, quality.LotReceipt
reviewed: 2026-11-15
---

## Purpose

Records what a supplier's certificate of analysis states for a quarantined lot: the certificate's own details and each stated result, entered against one approved requirement of the lot and compared with it. These are the supplier's results. They are kept apart from the laboratory's own tests. A recorded result stands in for a test only through an acceptance signed on the lot.

## Who can use it

- Sign-in required. **analyst** role only; others receive 403 Forbidden. The lot record shows **Record supplier certificate** only to analysts, on a Quarantine lot received from a supplier that has approved requirements.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the analyst role acts with that role only, with no exception to the independence rules.
- The lot must be able to hold a certificate. Otherwise no form is shown and you are redirected to the lot record with the reason: "Only quarantined lots accept supplier certificate records." (lot no longer in Quarantine); "Record the lot's receipt details before its supplier certificate." (no receipt details); "Only a lot received from a supplier has a supplier certificate." (the current receipt details say Made on site); or "Assign approved requirements to the lot first: supplier results are recorded against them." (no approved requirements), followed by why they are missing or held, for example "No specification or sampling requirements are assigned."
- These checks run when the page opens, again on submission, and once more under the lot lock when saving.

## Layout

- **Breadcrumbs**: Material lots, lot number, Record supplier certificate.
- **Intro**: "Record what the supplier's certificate states, against the lot's approved requirements. These are the supplier's results: they are kept apart from the laboratory's own tests. One stands in for a test only through an acceptance signed on the lot."
- **Record card**: Lot, Material, Status, then from the current receipt details Supplier (code · name), Supplier lot number ("Not known" when blank) and Manufacturer lot number ("Not stated" when blank). Read the certificate beside them.
- **Form sections**: Certificate; one section per approved requirement of the lot, in specification order, headed by the test name and its acceptance criterion (for example "Assay: specification 98 to 102 %"); Change control.
- **Buttons**: **Cancel** (to the lot record) and **Record supplier certificate**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record supplier certificate** | Always | Analyst | Adds the certificate record with its results, shows "Supplier certificate recorded." and opens the supplier certificate record |
| **Cancel** | Always | Analyst | Returns to the lot record without saving |

## Fields

In the table, "Test" stands for the name of each requirement, for example "Assay result (%)".

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Certificate number | `SupplierCertificate.number` | Text, max 80 | Yes | Help: "As printed on the certificate." |
| Issued by | `SupplierCertificate.issued_by` | Text, max 160 | Yes | Help: "The company the certificate names as its issuer." |
| Date of the certificate | `SupplierCertificate.issued_on` | Date | Yes | Starts blank: the date is stated, not assumed. Cannot be in the future. |
| Lot number on the certificate | `SupplierCertificate.stated_lot` | Text, max 80 | Yes | Help: "As printed. It is shown beside the lot numbers of the receipt details." |
| Where the certificate is kept | `SupplierCertificate.document_ref` | Text, max 200 | Yes | Help: "Document number or location in your controlled records." |
| Notes | `SupplierCertificate.notes` | Text, max 2000 | No | Help: "Anything else the certificate states, for example a test that is not in the specification or a result in another unit." |
| Test result (unit) | `SupplierCertificateResult.value`, `value_text` | Decimal, at most 8 decimals and 12 digits before the point | No | Numeric and count requirements. Help: "As stated on the certificate, in" the requirement's unit, then "Do not convert a result stated in another unit: leave it blank and describe it in the notes." For a count the help starts "Whole number of zero or more, as stated on the certificate". |
| Test stated as less than this value | `SupplierCertificateResult.qualifier` | Checkbox | No | Numeric and count requirements. Help: "For a result printed as <10. It is kept as stated and never becomes zero or the number." |
| Test result | `SupplierCertificateResult.outcome` | Menu: "Not stated on the certificate", then the requirement's two outcomes (Conforms and Does not conform, or Absent and Present) | No | Qualitative requirements. |
| Test wording on the certificate | `SupplierCertificateResult.stated_text` | Text, max 200 | With a result | Qualitative requirements. Help: "The result in the certificate's own words, e.g. Complies." |
| Test method on the certificate | `SupplierCertificateResult.method` | Text, max 200 | No | Help: "The test method the certificate states. Leave blank if it states none." A result without a stated method cannot later be proposed in place of a test. |
| Test limits on the certificate | `SupplierCertificateResult.limits` | Text, max 200 | No | Help: "The supplier's own limits, as printed. Leave blank if it states none." They are recorded only; the comparison uses the lot's requirement. A result without stated limits cannot later be proposed in place of a test. |
| Reason | `SupplierCertificate.reason` | Text, max 2000 | Yes | Why the certificate is recorded; stored on the record and in the audit event. |
| Basis (hidden) | — | Hash | Yes | Identifies the requirements the page showed when it opened. See Stale requirements. |

## Rules and hidden logic

- **Tests offered**: the required tests of the lot's current requirement assignment, as they stand when the page opens. Tests the specification lists for information only are not offered. A lot that is not assigned, or whose assignment is on hold, has no approved requirements.
- **A test the certificate does not state**: leave all of its fields blank. It is not recorded. A certificate may state only some of the requirements.
- **At least one result**: "Enter at least one result stated on the certificate."
- **Incomplete test**: "Enter the result, or clear this test if the certificate does not state it." when a method, limits, wording or the less-than box is filled in without a result.
- **Qualitative results**: choose the outcome and enter the certificate's own words: "Enter the wording of the result on the certificate." Both are kept, for example outcome "Conforms" stated as "Complies".
- **Numbers**: enter the number as the certificate prints it, in plain digits: an optional minus sign, digits, and a decimal point followed by digits where needed. The value is kept exactly as entered, trailing zeros included ("99.60" stays "99.60"). Anything else is refused, never reformatted: an exponent ("1E+2"), a plus sign, a leading zero ("099.6"), a missing digit before or after the point (".5", "100."), a decimal comma, digit separators, digits of another script and a negative zero all give "Enter the number as printed, in plain digits with a decimal point where needed, for example 99.60 or 0.5." Also: "Ensure that there are no more than 8 decimal places."; "Ensure that there are no more than 12 digits before the decimal point."; for a count, "A count must be a whole number of zero or more."
- **Less than**: a ticked box records the result as "<10". "A less-than result needs a value greater than zero."
- **Units are not converted**: enter a result only in the requirement's unit. Leave a result stated in another unit blank and describe it in Notes.
- **Comparison**: on saving, each result is compared once with its requirement and stored as "Meets the specification" or "Does not meet the specification". A number is checked against the limits, each limit including or excluding its boundary as approved (5 does not meet "less than 5"). A qualitative result meets the specification when it is the expected outcome. A less-than result meets it only when the requirement has no lower limit and the stated value is not above the upper limit; otherwise it is recorded as not meeting it.
- **Frozen requirement**: each result is stored with the exact requirement it was compared with. The comparison is never recalculated.
- **Certificate details**: "The date of the certificate cannot be in the future." (today's date in the deployment time zone) is checked by the server on saving and shown beside the date. Spaces around text values are removed before saving.
- **Stale requirements**: the hidden Basis is a hash of the requirements the page showed. If the lot's requirements changed after you opened the page (for example they were assigned again), nothing is saved: "The lot's requirements changed after this page was opened. Review every result against the requirements now shown, then submit again." The form is shown again with the lot's current requirements, your entries kept, and the Basis of what it now shows, so after the review you submit again without retyping. This stops a result from being compared with a requirement you never saw. The server repeats the check under the lot lock when saving.
- **Repeated by the server**: every rule is checked again under the lot lock when saving. For cases the form already stops, the server's own messages are "Enter the certificate number.", "Enter who issued the certificate.", "Enter the date of the certificate.", "Enter the lot number printed on the certificate.", "Enter where the certificate is kept." and "A reason is required."
- **Quarantine only**: the lot is locked while saving. A lot released in the meantime keeps its certificates unchanged: "Only quarantined lots accept supplier certificate records."
- **Effect**: one certificate record is added with you as recorder, holding its results in specification order. The lot's record revision increases by 1. Audit event `supplier_certificate.recorded` stores the certificate details, each result as stated, its comparison and the hash of its requirement, with your reason. A disposition signing page opened earlier then fails as stale.
- **Several certificates, one record per number**: a lot may hold several certificates, each with its own number. A number that a current certificate of this lot already holds is refused beside Certificate number: "This lot already holds a certificate with this number. Correct that record, or withdraw it if it does not belong to this lot." Upper and lower case and surrounding spaces do not make a number different. A withdrawn certificate does not count, and another lot may hold the same number. This also stops a form submitted twice from recording the certificate twice.
- **Not enforced by this page**: the lot number on the certificate is not required to match the receipt details. The record only shows whether it matches.
- **Independence**: recording a supplier certificate makes you an author of the lot's supplier certificate data. You cannot sign this lot's disposition, even with the quality role, and you cannot accept a result proposed from this record, even with the reviewer role.
- **Append-only**: a certificate record and its results cannot be edited or deleted. The database also refuses a certificate record or result for a lot that is not in quarantine, a record saved without all of its results, and a result added to a record later. Later changes go through Correct supplier certificate or Withdraw supplier certificate.
- **What this record does not do by itself**: recording a result answers no requirement, so the laboratory's own tests stay required. A stated result answers a requirement only through an acceptance: an analyst proposes it from the supplier certificate record and a reviewer signs it, where the lot's rule set allows it and a signed qualification covers the supplier. A result that was never proposed does not count towards QC disposition, does not block it and is not printed on the certificate of analysis. A result that does not meet the specification does not place a hold; place one from Holds if the lot must not be dispositioned.
- **Not enforced by this page**: recording a certificate does not need a qualified supplier and does not qualify the supplier; the qualification is checked only when a result is proposed and accepted. The certificate's issuer is not checked against the supplier. The record does not change which tests the lot requires.
- **Assumption**: keeping supplier results apart from the laboratory's tests, with no reduced testing on the strength of a certificate record alone, is a design default of this product. It is not a statement of what any regulation requires or permits.
- Unknown lot: 404.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept."). Refusals from the server appear beside the field they concern, or in the summary when they concern the whole form.

## Related pages

- Lot record.
- Supplier certificate record; Correct supplier certificate; Withdraw supplier certificate.
- Propose supplier result in place of a test (from the supplier certificate record).
- Lot requirements and sampling (where requirements are assigned).
- [Holds](/stability/holds/)
- [Suppliers](/suppliers/)
- [Material lots](/)
