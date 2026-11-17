---
title: Supplier certificate record
urls: quality:certificate_detail
views: quality.certificate_views.certificate_detail
templates: quality/certificate_detail.html
models: quality.SupplierCertificate, quality.SupplierCertificateResult, quality.SupplierCertificateWithdrawal, quality.SupplierResultAcceptance, quality.Lot, quality.LotReceipt, suppliers.Supplier
reviewed: 2026-11-15
---

## Purpose

Shows one supplier certificate of a lot: the current record of what the certificate states, each stated result beside the requirement it was compared with, and the history of the record. These are the supplier's results, not the laboratory's own tests. For each result the page also shows whether it stands in for a test, and lets an analyst propose that it does.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **Withdraw supplier certificate**: analysts only, while the lot is Quarantine and the record is not withdrawn. **Correct supplier certificate**: the same, and the lot's current receipt details must say "Received from a supplier" and the lot must have approved requirements. Other roles do not see them and receive 403 Forbidden if they open those pages directly.
- **Propose in place of a test**: analysts only, while the lot is Quarantine and the record is not withdrawn, and only beside a result that can be proposed. Analysts see why a result cannot be proposed; other roles see neither the link nor the reasons, and receive 403 Forbidden if they open that page directly.
- The page is read-only for every other role, including the admin role alone.

## Layout

- **Breadcrumbs**: Material lots, lot number, "Supplier certificate" with the certificate number. Title: the same, for example "Supplier certificate COA-TEST-001".
- **Header line**: the status "Supplier's results", or "Withdrawn"; "Lot" with a link to the lot record; the material.
- **Header buttons**: **Correct supplier certificate** and **Withdraw supplier certificate**, when shown.
- **Intro**: "Results stated by the supplier, compared with this lot's approved requirements. They are not the laboratory's own tests. A stated result answers a requirement and counts towards QC disposition only when it is accepted in place of a test, under a signed qualification of the supplier."
- **Withdrawn notice** (withdrawn records only): "This certificate record was withdrawn and no longer stands. It is kept as recorded.", then "Reason:" with the reason for withdrawal.
- **Certificate** card: Certificate number, Issued by, Date of the certificate, Lot number on the certificate (with "As on the receipt" or "Differs from the receipt"), Receipt, Where the certificate is kept, Notes and Recorded.
- **Results stated by the supplier** card, with the number of results: any notes (see Rules), then a table with Test, Result stated, Method stated, Limits stated, Specification and Comparison. Results are in specification order. Under a result, a line starting "In place of a test:" shows the proposal or acceptance that stands for the lot's requirement of that test, or whether the result can be proposed (see Rules); a result with nothing to show has no such line.
- **History** card: every record of this certificate, oldest first, then the withdrawal when there is one.
- **Foot line**: the certificate number, then "Viewed" with the time and your name.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Correct supplier certificate** | Analyst role, lot is Quarantine, the record is not withdrawn, the current receipt details say "Received from a supplier" and the lot has approved requirements | Analyst | Opens Correct supplier certificate, prefilled with this record |
| **Withdraw supplier certificate** | Analyst role, lot is Quarantine and the record is not withdrawn | Analyst | Opens Withdraw supplier certificate |
| **Propose in place of a test** (per result) | Analyst role, lot is Quarantine, the record is not withdrawn, no proposal or acceptance stands for the lot's requirement of that test, and nothing refuses the proposal | Analyst | Opens Propose supplier result in place of a test for that result |
| Acceptance link (SRA-n, per result) | A proposal or acceptance for the lot's requirement of that test is not withdrawn, whichever record it was taken from | Any viewer | Opens the supplier result acceptance record |
| Lot number link (header line and breadcrumb) | Always | Any viewer | Opens the lot record |
| Supplier code link | The lot's current receipt details name a supplier | Any viewer | Opens the supplier record |
| **Holds** | A result does not meet the specification and the record is not withdrawn | Viewers of that page | Opens the Holds list |
| **Material lots** (breadcrumb) | Always | Any viewer | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Certificate number | `SupplierCertificate.number` | Text | — | As printed on the certificate; also in the page title. |
| Issued by | `SupplierCertificate.issued_by` | Text | — | The company the certificate names as its issuer. |
| Date of the certificate | `SupplierCertificate.issued_on` | Date | — | Date printed on the certificate. |
| Lot number on the certificate | `SupplierCertificate.stated_lot` | Text and label | — | "As on the receipt" when it equals the supplier lot number or the manufacturer lot number of the lot's current receipt details, ignoring case and surrounding spaces. "Differs from the receipt" when it equals neither. No label when the receipt details state neither number. |
| Receipt | `LotReceipt.supplier`, `supplier_lot`, `manufacturer_lot` | Link and text | — | Shown when the current receipt details name a supplier: its code (link) and name, "supplier lot" with the number or "not known", and "manufacturer lot" with the number when recorded. |
| Where the certificate is kept | `SupplierCertificate.document_ref` | Text | — | Document number or location in your controlled records. |
| Notes | `SupplierCertificate.notes` | Text | — | "None" when blank. |
| Recorded | `SupplierCertificate.recorded_at`, `recorded_by` | Date and time, user | — | When and by whom the current record was saved. Full name, or the username when no name is set. |
| Test | `SupplierCertificateResult.requirement`, `test_code` | Text | — | Test name from the stored requirement, with the test code below it. |
| Result stated | `SupplierCertificateResult.value_text`, `stated_text` | Text with unit | — | Exactly as recorded, with the requirement's unit (for example "99.60 %" or "<10 CFU/g"). A qualitative result shows the outcome and "Stated as:" with the certificate's own words. |
| Method stated | `SupplierCertificateResult.method` | Text | — | "Not stated" when blank. |
| Limits stated | `SupplierCertificateResult.limits` | Text | — | The supplier's own limits; "Not stated" when blank. Not used in the comparison. |
| Specification | `SupplierCertificateResult.requirement` | Text | — | Acceptance criterion of the requirement the result was compared with (for example "98 to 102 %" or "at most 200 CFU/g"). Below it, the source of that requirement: the specification version and the lot's requirement assignment. |
| Comparison | `SupplierCertificateResult.conforms`, `requirement_hash` | Label | — | "Meets the specification" or "Does not meet the specification", as stored when the result was recorded. "Requirement no longer current" is added when the lot's current requirement for the test is not the stored one. |
| In place of a test (line under a result) | `SupplierResultAcceptance.state`, `evidence` | Link and label, or text | — | One of three: the acceptance (SRA-n) with "Awaiting acceptance", "Accepted" or "No longer stands", and "Taken from another record:" with a certificate number when it was not taken from this result; the link "Propose in place of a test"; or "Not available:" with the reason. No line when none applies. See Rules. |
| History entry | `SupplierCertificate.recorded_at`, `recorded_by`, `reason`, `corrects`; `SupplierCertificateWithdrawal.withdrawn_at`, `withdrawn_by`, `reason` | Date and time, user, text | — | One entry per record and one for the withdrawal. |

## Rules and hidden logic

- **Current record**: the page shows the record that no correction has replaced. Opening the address of a replaced record redirects to the current record of the same certificate. The buttons therefore always act on the current record.
- **Comparison stands as recorded**: each result was compared with the lot's requirement when it was recorded, and that requirement is stored with it. The comparison is never recalculated.
- **Requirements changed later**: a result whose stored requirement is not the lot's current one is marked "Requirement no longer current", with the note "A result was compared with a requirement that is no longer current for this lot. Its comparison stands as recorded." For an analyst who can correct the record the note continues "; correct the certificate record to compare it with the current requirements". Assigning requirements again replaces them, even when the limits are the same. The mark also shows while the lot's requirements are on hold.
- **In place of a test, three states**: (1) a proposal or acceptance that is not withdrawn stands for the lot's requirement, whichever record of whichever certificate it was taken from. Every viewer sees its number as a link under every statement of that test, with "Awaiting acceptance" or "Accepted", or "No longer stands" followed by "Withdraw it before proposing a result again." when it has problems. Under a statement it was not taken from, the line adds "Taken from another record: COA-TEST-002." with the number of the certificate record it was taken from. (2) Otherwise an analyst, on a Quarantine lot and a record that is not withdrawn, sees "Propose in place of a test" when the result can be proposed. (3) When it cannot, the analyst sees "Not available:" followed by the reason, for example "Not available: sup-syn-001 is not qualified for api-syn-001." or "Not available: Rule set rules-syn v1 requires the laboratory to perform identity itself; a supplier's result cannot stand in for it." The reasons are those listed on Propose supplier result in place of a test; the rule set is checked before the lot's records. Every other viewer, and an analyst on a released lot or a withdrawn record, sees no line unless a proposal or acceptance stands.
- **No longer stands**: the page checks the lot's records each time it is shown, as the lot record and the acceptance record do. The reasons are on those pages, for example the receipt details were corrected.
- **After a correction or a withdrawal of this record**: a proposal or acceptance taken from the record that was replaced or withdrawn stops standing. It blocks the lot's QC disposition until it is withdrawn on its own record. The withdrawn record, and after a correction the new current record, show its number with "No longer stands"; the new current record adds "Taken from another record:" with the number of the replaced record. Nothing is offered for that requirement until the acceptance is withdrawn; then propose the result again from the current record.
- **A result here that contradicts another certificate**: while this record is current, a result on it that does not meet the specification stops a result of the same test on another certificate of the lot from being proposed or accepted in place of a test. A proposal or acceptance already made for that test stops standing ("supplier certificate COA-TEST-002 states a result for assay that does not meet the specification") until this record is corrected or withdrawn, or the acceptance is withdrawn.
- **Result outside the specification**: it places no hold. The card shows "A supplier result that does not meet the specification does not hold the lot by itself. Place a hold from Holds if the lot must not be dispositioned until it is resolved." The note is not shown on a withdrawn record. The disposition signing page shows a warning for such a result on a current record; the warning does not block signing.
- **Lot number label**: compared with the lot's current receipt details each time the page is shown, so a receipt correction can change it. It is information only; a differing number is not refused.
- **Withdrawn record**: the record and its results stay visible with the status "Withdrawn" and the reason. It has no buttons: a withdrawn record cannot be corrected or withdrawn again.
- **History**: entries read "Supplier certificate recorded", "Supplier certificate corrected" or "Supplier certificate withdrawn", each with the time, the reason and "Recorded by" or "Withdrawn by" with the user. A correction lists each changed detail as old value → new value; an empty value reads "blank".
- **What a correction compares**: Certificate number, Issued by, Date of the certificate, Lot number on the certificate, Where the certificate is kept and Notes; and for each test its result, method, limits, specification, requirement and comparison. A test added or dropped by the correction reads "blank" on one side.
- **Buttons and the server**: Withdraw shows to analysts whenever the lot is Quarantine and the record is not withdrawn. Correcting also needs receipt details from a supplier and approved requirements, so Correct is hidden when the lot lost them (its receipt details were corrected to Made on site, or its requirements are no longer assigned or are held). Opening the Correct page directly then returns you here with the reason.
- **Released lot**: the record stays readable and has no buttons. Opening the Correct or Withdraw page directly returns you here with "Only quarantined lots accept supplier certificate records."
- **Independence**: everyone who recorded, corrected or withdrew a supplier certificate of the lot, including the recorder of a record that a correction replaced, is an author of the lot's data. None of them can sign the lot's disposition, even with the quality role. Whoever recorded or corrected this record also cannot accept a result proposed from it, even with the reviewer role.
- **Append-only**: certificate records, their results and withdrawals cannot be edited or deleted (database trigger). A correction adds a linked record and a withdrawal adds a withdrawal record. Audit events `supplier_certificate.recorded`, `supplier_certificate.corrected` and `supplier_certificate.withdrawn` are in the Audit trail.
- **What this record does not do by itself**: a stated result answers a requirement only through an acceptance that an analyst proposes and a reviewer signs; without one the laboratory's own test stays required. A result that was never proposed does not count towards QC disposition, does not block it and is not printed on the certificate of analysis. A proposal awaiting acceptance blocks QC disposition. An accepted result is printed on the certificate of analysis apart from the laboratory's results, as the supplier's. Units are not converted. A result that does not meet the specification does not place a hold and cannot be proposed.
- **Not enforced by this page**: recording a certificate does not need a qualified supplier, and the record does not qualify the supplier; the supplier's qualification is checked only when a result is proposed and accepted. The certificate's issuer is not checked against the supplier. The certificate document itself is not stored here; the record names where it is kept.
- **Assumption**: keeping supplier results apart from the laboratory's tests, relying on one only through a signed acceptance, requiring a stated method and stated limits for that, and flagging a differing lot number instead of refusing it are design defaults of this product. They are not statements of what any regulation requires or permits.
- Unknown certificate: 404.

## Related pages

- Lot record.
- Record supplier certificate, Correct supplier certificate, Withdraw supplier certificate.
- Propose supplier result in place of a test; Supplier result acceptance record.
- Supplier record; Sign lot disposition.
- [Holds](/stability/holds/)
- [Audit trail](/audit/)
- [Material lots](/lots/)
