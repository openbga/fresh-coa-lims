---
title: Lot record
urls: quality:lot_detail
views: quality.views.lot_detail
templates: quality/lot_detail.html
models: quality.Lot, quality.LotReceipt, quality.LotDates, quality.SupplierCertificate, quality.SupplierCertificateResult, quality.SupplierCertificateWithdrawal, quality.SupplierResultAcceptance, quality.Sample, quality.Result, suppliers.Supplier, suppliers.SupplierQualification, core.RuleSet, core.ElectronicSignature, sampling.LotAssignment, reporting.Report, stability.RetentionObligation
reviewed: 2026-11-17
summary: Everything about one material lot: its receipt, supplier certificates, samples and signatures, and the actions that take it out of quarantine.
---

## Common tasks

### Add a sample

1. Select [[Add sample]]. It shows only while the lot is in Quarantine.

### Check requirements and test results

1. Select [[Requirements and sampling]] to see the specification and sampling requirements that apply.
2. Select [[Testing and investigations]] for native results, reviews and investigations.

### Record or correct the receipt details

1. In the Receipt card, select [[Record receipt details]], or [[Correct receipt details]] when details exist.
2. A correction adds a new record. The earlier one stays in the receipt history.

### Release or reject the lot

1. Select [[Review disposition]] to release it, or [[Reject lot]] if it failed its requirements or cannot be used.
2. Sign with your PIN on that page. If you cannot decide this lot, the page says why before asking for a PIN.

### Issue a certificate of analysis

1. After release, select [[Issue certificate of analysis]] at the top of the page.

## Good to know

- You cannot release or reject a lot that holds your own receipt, supplier certificate, expiry and retest dates, sampling or test data, even with the quality role.
- A discrepancy found on receipt does not hold the lot. Place a hold from the [[Holds]] link in the Receipt card if it must not be dispositioned.
- A supplier result counts towards disposition only once a reviewer accepts it in place of a test. A proposal awaiting acceptance blocks disposition.
- Receipt details and supplier certificates are never edited. A correction or withdrawal adds a linked record and the earlier one stays.
- The results table here shows manual foundation results only. Native testing is on [[Testing and investigations]].

## Purpose

The hub for one material lot: its facts, receipt details, supplier certificates, supplier results proposed or accepted in place of tests, and samples, links to its requirements, sampling and native testing, the signed QC disposition that releases it, and its certificates of analysis.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Add sample** and **Record result**: analysts only.
- **Record receipt details** and **Correct receipt details**: analysts only, while the lot is Quarantine. Other roles do not see them and receive 403 if they open those pages directly.
- **Record supplier certificate**: analysts only, while the lot is Quarantine, was received from a supplier and has approved requirements. Other roles do not see it and receive 403 if they open that page directly. Every viewer can open a supplier certificate record from its number.
- **Supplier results in place of tests**: every viewer can open a record from its number. Nothing is proposed, accepted or withdrawn on this page: analysts propose from the supplier certificate record, and reviewers accept on the acceptance record.
- **Review result**: reviewers only, and never the analyst who recorded that result.
- **Record dates** and **Correct dates**: analyst or quality role, while the lot is Quarantine. Others do not see them and receive 403 if they open that page directly.
- **Review disposition**, **Reject lot**, **Cancel lot received in error** and **Issue certificate of analysis**: quality role only. Reject and cancel are shown to every quality user on a Quarantine lot; the server refuses anyone who authored the lot's records (and, for cancellation, whoever received the lot).
- **Export record**: **admin**, **quality** and **auditor**, the roles that read the audit trail. Analysts and reviewers do not see it and receive 403 if they open that page directly.
- Scientific action links require their corresponding role as well as the state condition. Admin-only viewers see records and navigation links, without laboratory mutation controls. The server independently checks roles, independence and state.

## Layout

- **Breadcrumbs**: Lots › the lot number.
- **Header**: the lot number as the title. First line: the lot status, "Expired" (after the expiry date) or "Retest due" (from the retest date on) for a Quarantine or Released lot with dates in force, a "Phase I laboratory investigation" or "Phase II full investigation" label for each open investigation, "Applicability hold" when the lot's requirements are on an applicability hold, the hold's kind ("Quality hold", "Investigation hold", "Regulatory hold", "Legal hold"; a link to the hold, its identifier in the tooltip) for each active stability hold on a Quarantine lot, and the material with its kind icon and code (from the current requirement assignment when there is one). Second line: "Received" with the receipt date and "Record revision" with the lot's revision. Actions at the right: **Export record** (admin, quality, auditor) in any state; on a Quarantine lot, quality users see **Review disposition** (the primary button), **Reject lot** and a **More** menu with **Cancel lot received in error**, and analysts see **Add sample** (the primary for an analyst without the quality role, a secondary button for a user who holds both). A quality user who authored the lot's data sees **Review disposition** as a secondary button only: signing would refuse them. On a Released lot, quality users see **Issue certificate of analysis**.
- **Where the lot is**: six steps, Lot, Samples, Results, Review, Disposition and Certificate, each with a short line derived from the record: the requirement assignment ("Requirements assigned", "Applicability hold", "Not assigned"), the number of samples, "N of M entered" and "N of M reviewed" (tests that are not superseded or invalidated), the decision ("Released", "Rejection signed", "Investigation open", "Not decided") and the certificate ("Certificate issued", "Not issued"). A cancelled lot shows "Received in error". The current step is marked; a held step (applicability hold, open investigation) is shown as on hold.
- **Hold notice** (one, the first that applies): an open investigation (its number as a link, its phase, the test and its sample, and "An open investigation holds its lot, or its stability pull, until quality signs a conclusion."), else an active stability hold ("HOLD-n (quality hold) is active: reason", the identifier as a link), else an applicability hold (its reasons and **Requirements and sampling**). Further holds show only as header labels.
- **Decision card** (Rejected or Cancelled lots only, titled "Rejection" or "Cancelled as received in error"): Grounds (rejection only), Reason, Record in the quality system ("Not stated" when blank), Signed by (name, time in UTC and lot revision), and for a rejection Tests at the rejection (the count, and "N not finished:" with the open or awaiting-review tests) followed by "What stood in the way of release" or "The release gates found nothing missing or failing when the lot was rejected." Closing line: "The lot takes no more records and keeps every record as it was signed." with, for a rejection, "What happens to the material is decided and recorded in the quality system." or, for a cancellation, "Its number is not used again."
- **QC disposition** card beside the Lot card (Quarantine lots): the number of blockers when there are any; first "Evidence" with "Blocked" or "Complete"; then "QC disposition cannot be approved until these are resolved:" and each check that signing the disposition enforces, with its own message and in the same order: active stability holds, then the lot's sampling evidence (requirements assigned, a current sampling record for every sample, deviations assessed) and its analytical evidence, or, with none, "Every required test has a reviewed, conforming result and no investigation is open. This is laboratory evidence only; QC disposition is a separate signed decision and does not mean manufacturer release." (with an accepted supplier result: "Every requirement has a reviewed, conforming result or an accepted supplier result, and no investigation is open. …").
- **Certificates of analysis** card beside the Lot card (Released lots): "Issued" or "Not issued", then links to the lot's certificates, or "No certificate issued yet".
- **Lot** card: **Requirements and sampling** and **Testing and investigations** at the top right; facts Supplier (a link to the supplier, with the supplier lot number below; "Made on site" for a lot made on site), Received (the date, with "by" and the person who recorded the receipt), Quantity (with the containers below), Rule set (with "Applied in addition by the lot's requirements: …" below when other rule sets apply), Requirements ("Requirements assigned", "Applicability hold" or "Not assigned") and Specification (the assigned specification and version, or "—").
- **Receipt** card, header: for analysts on a Quarantine lot, **Correct receipt details** when the lot has receipt details, otherwise **Record receipt details**.
- **Receipt** card, details (the date received and the quantity are in the Lot card): Source; for a lot received from a supplier also Supplier (code, name and location), Supplier lot number ("Not known" when blank), Manufacturer (name and location, or "Not stated") and Manufacturer lot number (only when recorded); then Delivery or batch document, Containers (number, then description) and Examination on receipt (the label "No discrepancy found" or "Discrepancy found", with the examination notes below it).
- **Receipt** card, discrepancy note: when a discrepancy was found, "A discrepancy does not hold the lot by itself. Place a hold from Holds if the lot must not be dispositioned until it is resolved.", with a link to Holds.
- **Receipt history** card (after the Receipt card, when the lot has receipt details; closed until opened): every receipt record of the lot, oldest first. Each entry shows "Receipt recorded" or "Receipt details corrected", the time, the reason and "Recorded by" with the user. A correction also lists each changed detail as old value → new value; an empty value reads "blank".
- **Receipt** card without details: "Receipt details are not recorded: this lot was received before they were kept." On a Quarantine lot it adds "An analyst can record them while the lot is in quarantine."
- **Expiry and retest dates** card (after the Receipt history card): Expiry date and Retest date ("None" when not stated, with the label "Expired" or "Retest due" beside the date that was reached), Basis, and Recorded (time and "by" the user). Without dates: "No expiry or retest date is recorded."; after a correction to none: "The dates recorded earlier were corrected to none: this lot has no expiry or retest date." When a rule set requires dates: "Required before release: <rule set> requires <what>." On a Quarantine lot: "An analyst or quality person records and corrects the dates while the lot is in quarantine; whoever does cannot sign its disposition. The release is refused after the expiry date and from the retest date on, and freezes the dates in force." On a Released lot with dates: "The release froze these dates." (only when the release froze them) and then, as the case is, that the material is past its expiry date and no certificate is issued for it, that the retest date has been reached, the material must be examined again before further use and no certificate is issued for it, or "The lot shows when its retest is due or it has expired." Header: **Record dates**, or **Correct dates** when a dates record exists, for analyst or quality users on a Quarantine lot.
- **Dates history** card (when the lot has any dates record; closed until opened): every record oldest first, "Dates recorded" or "Dates corrected", the time, the reason and "Recorded by" with the user. A correction lists each of Expiry date, Retest date and Basis that changed as old value → new value; a missing date reads "None".
- **Supplier certificates** card, header: **Record supplier certificate** for analysts, when the lot is Quarantine, its current receipt details say "Received from a supplier" and it has approved requirements.
- **Supplier certificates** card, table: when the lot has certificates, the text "Results stated by the supplier, compared with this lot's approved requirements. They are not the laboratory's own tests. A stated result counts towards QC disposition only when it is accepted in place of a test; propose one from its certificate.", then one row per certificate, oldest first: Certificate (number, a link to its record), Issued by, Date, Lot number on the certificate, Results stated and Status.
- **Supplier certificates** card without certificates: "No supplier certificate is recorded. Receipt details come first." when the lot has no receipt details; "This lot was made on site, so it has no supplier certificate." when its receipt details say Made on site; otherwise "No supplier certificate is recorded."
- **Supplier certificates** card, requirements note: on a Quarantine lot received from a supplier that has no approved requirements, an analyst sees no button and, at the end of the card, "Assign approved requirements to the lot first: supplier results are recorded against them.", followed by why they are missing or held (for example "No specification or sampling requirements are assigned."). Other roles do not see this note.
- **Supplier certificates** card, made-on-site note: when a Quarantine lot holds certificates and its receipt details were corrected to Made on site, every viewer sees "The receipt details now state that this lot was made on site. Withdraw a supplier certificate that no longer applies." Such a certificate cannot be corrected, only withdrawn.
- **Supplier results in place of tests** card (only when the lot has such a record, withdrawn ones included): the text "Each accepted result answers its requirement for the whole lot in place of a laboratory test. A proposal answers nothing until a reviewer accepts it, and blocks QC disposition until then.", then one row per record, oldest first: Record (SRA-n, a link), Test (name, with the code below), Supplier's result, Certificate, Qualification, Proposed by and Status.
- **Samples and results** card, with the number of samples (for a reviewer with results to review, "N awaiting review" instead): one section per sample headed by its reference and "collected" with the time (laboratory time zone), then a **Record result** button (Quarantine lots only) and its results. For a sample with analytical tests: Test (its number, a link to the test record, with the kind tag for a retest, resample, rerun or repeat), Code (as a code chip), Status (as on Testing and investigations, e.g. Open, Awaiting review, Reviewed, Invalidated, "Not tested · supplier result") and Reportable (the result as frozen at submission, with its unit, or "—"). For a sample without analytical tests, or with manual foundation results, the foundation results table: Test, Result, Limits, Analyst, Review; a result outside its limits is labelled "Out of specification" and "No results recorded." shows when there are none. Observations, reviews and investigations are on Testing and investigations. "No samples recorded" when the lot has no samples.
- **Retention** card (only when the lot has retention obligations, with or without a reserve sample): one row per obligation with Basis, Anchor (the anchor kind and its date, or "Anchor not yet known"), Retain through (the date, or "N months after the anchor" while the anchor is unknown), Reserve sample (link, or "—" for an obligation of the lot itself) and **Set anchor** while the anchor is unknown.
- **Electronic signatures** card: each signature shows the signer, meaning, server time and the revision it binds. Under "Results", foundation result review signatures ("Result N revision R"); under "Lot", every signature on the lot, oldest first: the disposition (meaning approved) and any signed replacement of its requirements during testing (meaning requirements_replaced). "No lot disposition signature yet." shows until the lot has a signature with the meaning approved. Native test review signatures are not listed here.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add sample** | Analyst role and lot is Quarantine | Analyst | Opens Add sample for this lot |
| **Review disposition** | Quality role and lot is Quarantine, and you made none of the lot's records (otherwise the header says why, "Another quality person must sign") | Quality, independent of the lot's data | Opens Sign lot disposition |
| **Reject lot** | Quality role, lot is Quarantine, and rejecting would be accepted: no open investigation, no unsubmitted result outside its limits, and you made none of the lot's records (otherwise the header shows the first reason) | Quality, independent of the lot's data | Opens Reject lot |
| **Cancel lot received in error** (More menu) | Quality role, lot is Quarantine, and cancelling would be accepted: nothing was sampled, tested or reserved from it, no supplier result stands, and you did not receive it or make its records | Quality, not the lot's receiver or author | Opens Cancel lot received in error |
| **Record receipt details** | Analyst role, lot is Quarantine and has no receipt details | Analyst | Opens Record receipt details for this lot |
| **Correct receipt details** | Analyst role, lot is Quarantine and has receipt details | Analyst | Opens Correct receipt details, prefilled with the current details |
| Supplier code link | Receipt details name a supplier | Any viewer | Opens the supplier record |
| **Record supplier certificate** | Analyst role, lot is Quarantine, current receipt details say "Received from a supplier" and the lot has approved requirements | Analyst | Opens Record supplier certificate for this lot |
| Certificate number link | One per supplier certificate | Any viewer | Opens the supplier certificate record |
| Record link (SRA-n) | One per supplier result proposed or accepted in place of a test | Any viewer | Opens the supplier result acceptance record, where a reviewer accepts it and it can be withdrawn |
| **Record dates** | Analyst or quality role and lot is Quarantine, no dates record yet | Analyst, quality | Opens Record expiry and retest dates |
| **Correct dates** | Analyst or quality role and lot is Quarantine, with a dates record | Analyst, quality | Opens Correct expiry and retest dates, prefilled with the dates in force |
| **Holds** | Receipt details record a discrepancy | Viewers of that page | Opens the Holds list |
| Investigation number link | An investigation is open | Viewers of that page | Opens the investigation |
| **Export record** | Admin, quality or auditor role | Admin, quality, auditor | Opens Export record |
| **Requirements and sampling** | Always | Viewers of that page | Opens the lot's requirement assignment and sampling records |
| **Testing and investigations** | Always | Viewers of that page | Opens native tests, observations, reviews and investigations |
| **Export record** | Admin, quality or auditor role, in any lot status | Admin, quality, auditor | Opens Export record, which downloads the lot's complete record as one file |
| **Record result** | Analyst role and lot is Quarantine | Analyst | Opens the development-only manual result form; saving is refused outside DEBUG or once requirements are assigned |
| **Review result** | Reviewer role, result is Recorded and not its analyst | Reviewer, not its analyst | Opens Sign result review |
| **Issue certificate of analysis** | Quality role and lot is Released | Quality | Opens the certificate preview for this lot |
| Report number link | Lot is Released and a report exists | Viewers of reports | Opens the certificate record |
| **Set anchor** | A retention obligation without an anchor date; analyst or quality role | Analyst, quality | Opens Set anchor for that obligation (stability); once set, the anchor is not changed there |
| **Lots** (breadcrumb) | Always | Any viewer | Returns to the Material lots list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot number (heading) | `Lot.number` | Text | — | Lot identifier |
| Material | `Lot.material` | Text | — | Material received |
| Status | `Lot.state` | Quarantine, Released, Rejected, Cancelled | — | Released only by signed disposition; Rejected and Cancelled only by their signed decisions. Cancelled shows the tooltip "Received in error" |
| Rule set | `Lot.rules` | "code vN" | — | Rule revision chosen at receipt. A signed replacement of the lot's requirements during testing moves it to the version of the same rule set in force then |
| Applied in addition by the lot's requirements | `LotAssignment.payload` (additional rules, latest assignment) | "code vN" list | — | Additional rule set versions frozen with the lot's current requirements: rule sets whose policy states `applies_to` and that named the lot's material, stage or scopes. Not shown when there are none, or while the lot is Not assigned or on Applicability hold |
| Record revision | `Lot.revision` | Integer | — | Rises with each change to the lot, its samples, tests or holds, when receipt details are recorded later or corrected, when a supplier certificate is recorded, corrected or withdrawn, when a supplier result is proposed, accepted or withdrawn in place of a test, and when its requirements are assigned or replaced; disposition and replacement signatures bind to it |
| Assignment status | `LotAssignment.status` (latest) | Requirements assigned, Applicability hold, or "Not assigned" | — | Whether approved specification and sampling requirements are attached |
| Source | `LotReceipt.source` | Received from a supplier, Made on site | — | Where the lot came from |
| Supplier | `LotReceipt.supplier` → `Supplier.code`, `name`, `location` | Link and text | — | Shown when the receipt names a supplier; the code opens the supplier record |
| Supplier lot number | `LotReceipt.supplier_lot` | Text | — | Shown with a supplier; "Not known" when blank |
| Manufacturer | `LotReceipt.manufacturer`, `manufacturer_location` | Text | — | Shown with a supplier; "Not stated" when blank |
| Manufacturer lot number | `LotReceipt.manufacturer_lot` | Text | — | Shown with a supplier, only when recorded |
| Delivery or batch document | `LotReceipt.shipment_ref` | Text | — | Delivery note, packing list or purchase order; for material made on site the batch record or production order |
| Date received | `LotReceipt.received_on` | Date | — | Date the lot arrived |
| Quantity received | `LotReceipt.quantity`, `quantity_unit` | Decimal with unit | — | Exact quantity, without trailing zeros |
| Containers | `LotReceipt.containers`, `container_description` | Integer and text | — | Number of containers, then their type and size |
| Examination on receipt | `LotReceipt.condition`, `condition_notes` | Label and text | — | No discrepancy found or Discrepancy found, with the notes |
| Expiry date, Retest date | `LotDates.expiry_on`, `retest_on` | Date | — | The dates in force; "None" when not stated |
| Basis | `LotDates.basis` | Text | — | Where the dates come from |
| Recorded | `LotDates.recorded_at`, `recorded_by` | Date and time, user | — | When the dates in force were recorded and by whom |
| Dates history entry | `LotDates.recorded_at`, `recorded_by`, `reason`, `replaces` | Date and time, user, text | — | One entry per dates record; a correction is linked to the record it replaces |
| Receipt history entry | `LotReceipt.recorded_at`, `recorded_by`, `reason`, `corrects` | Date and time, user, text | — | One entry per receipt record; a correction is linked to the record it replaces |
| Certificate | `SupplierCertificate.number` | Link | — | Certificate number as printed; shows the current record of each certificate and opens its record |
| Issued by | `SupplierCertificate.issued_by` | Text | — | The company the certificate names as its issuer |
| Date | `SupplierCertificate.issued_on` | Date | — | Date of the certificate |
| Lot number on the certificate | `SupplierCertificate.stated_lot` | Text and label | — | "Differs from the receipt" when it equals neither the supplier lot number nor the manufacturer lot number of the current receipt details, ignoring case and surrounding spaces. No label when it matches or the receipt details state neither number |
| Results stated | `SupplierCertificate.results` → `SupplierCertificateResult.conforms`, `requirement_hash` | Count and labels | — | Number of results on the current record (for example "2 stated"), then "All meet the specification", or "Does not meet the specification" with the names of those tests. "Requirement no longer current" is added when a result was compared with a requirement that is not the lot's current one. A withdrawn certificate shows the number only |
| Status (supplier certificate) | `SupplierCertificateWithdrawal` | Current, Withdrawn | — | Withdrawn when the certificate record was withdrawn; it stays listed |
| Record / Test / Supplier's result / Certificate / Qualification | `SupplierResultAcceptance` (SRA-n), `test_code`, `evidence` | Link and text | — | As frozen when the result was proposed: test name and code, the stated result with its unit (a qualitative result adds "Stated as:" with the certificate's words), the supplier certificate number and the supplier qualification (SQ-n) relied on |
| Proposed by | `SupplierResultAcceptance.proposed_by` | User | — | The analyst who proposed the result; full name, or the username when no name is set |
| Status (supplier result) | `SupplierResultAcceptance.state` | Label | — | Awaiting acceptance; Accepted (with "Qualification revoked since" when the qualification was revoked after the signature); "No longer stands" with the reasons and "Withdraw it."; or Withdrawn |
| Sample heading | `Sample.reference` | Text, unique | — | Sample identifier |
| Collected | `Sample.collected_at` | Date and time | — | Labelled UTC; shown in the deployment time zone (default UTC) |
| Test, Result, Limits, Analyst, Review | `Result.test_code`, `value`, `unit`, `lower_limit`, `upper_limit`, `analyst`, `state` | Text, decimal with unit | — | Foundation manual results only; "Out of specification" when outside the inclusive limits |
| Report link | `Report.number` | Text | — | Issued certificates for this lot |
| Signature lines | `ElectronicSignature.object_id`, `revision`, `signer_name`, `meaning`, `signed_at` | Text, integer, date-time | — | Who signed which meaning, when, bound to which revision |

## Rules and hidden logic

- **Quarantine only**: samples, foundation results, receipt details, receipt corrections, supplier certificate records and supplier results in place of tests are accepted only while the lot is Quarantine ("Only quarantined lots accept new samples."; "Only quarantined lots accept receipt details."; "Only quarantined lots accept receipt corrections."; "Only quarantined lots accept supplier certificate records."; "Supplier results are accepted only while the lot is in quarantine.").
- **Current receipt details**: the card shows the receipt record that no correction has replaced. Receipt records are append-only: none can be edited or deleted, and a correction adds a linked record. A lot has one original record and a single chain of corrections.
- **Lots without receipt details**: a lot received through New material lot always has them. Only a lot received before receipt details were kept has none; an analyst can add them while it is Quarantine, and a released lot stays without them.
- **Receipt history changes**: a correction compares Source, Supplier, Supplier lot number, Manufacturer, Manufacturer location, Manufacturer lot number, Delivery or batch document, Date received, Quantity received (with its unit), Number of containers, Containers, Examination on receipt and Examination notes, and lists only those that differ.
- **Discrepancy**: "Discrepancy found" is information only. It does not place a hold and does not block disposition; only an active hold does.
- **Not enforced by this page**: recording receipt details or a supplier certificate does not need a qualified supplier, and neither changes which tests the lot requires. A supplier certificate does not qualify the supplier. The supplier's qualification is checked only when a supplier result is proposed and accepted in place of a test.
- **Supplier certificates listed**: one row per certificate, showing its current record: the one that no correction has replaced. Rows are ordered by when each certificate was first recorded, oldest first. A lot may hold several certificates. A withdrawn certificate stays listed with the status "Withdrawn"; replaced records are in the History of the supplier certificate record.
- **When Record supplier certificate shows**: the lot is Quarantine, its current receipt details exist and say "Received from a supplier", it has approved requirements, and you hold the analyst role. Approved requirements are the required tests of the lot's current requirement assignment; a lot that is Not assigned or on Applicability hold has none. A released lot keeps its certificates and has no button.
- **Supplier results are separate from the laboratory's tests**: they are compared with the lot's approved requirements when recorded, and each comparison stands as recorded. By itself a stated result does not answer a requirement, does not count towards QC disposition, does not block it and is not printed on the certificate of analysis; the laboratory's own test on Testing and investigations stays required.
- **A supplier result in place of a test**: three things must all hold. The lot's rule set allows it for that test, and so does every additional rule set applied by the lot's requirements; a signed supplier qualification covers the supplier, the material, the test and the date the lot was received; and an acceptance is signed on the lot. An analyst proposes one stated result of the current certificate record, and a reviewer who neither proposed it nor recorded or corrected that certificate or the lot's receipt details signs it. An accepted result answers its requirement for the whole lot, needs no test, and is printed on the certificate of analysis apart from the laboratory's results.
- **Proposals block**: a proposal awaiting acceptance blocks QC disposition until a reviewer accepts it or it is withdrawn.
- **No longer stands**: a proposal or acceptance stops standing when what it relied on changes: its certificate record was corrected or withdrawn, another current certificate record of the lot states a result for the test that does not meet the specification, the receipt details no longer name the same supplier or give another date received, the lot's requirement for the test changed, or the laboratory started testing the requirement (a raw-data file counts). A proposal also stops standing when its qualification is revoked, or the lot's rule set or an additional rule set applied by its requirements is no longer approved and effective, before a reviewer accepts it. The reasons are shown in the Status column. The record blocks QC disposition until it is withdrawn on its own record; nothing withdraws it automatically.
- **Qualification revoked since**: information only. An acceptance signed before its qualification was revoked stands and does not block QC disposition; the disposition signing page shows a warning. A proposal still awaiting acceptance under a revoked qualification shows "No longer stands" instead, with "SQ-1 was revoked before the proposal was accepted"; withdraw it.
- **Testing and acceptance exclude each other**: while a proposal or acceptance is not withdrawn, a test of that requirement takes no observation, no contract laboratory result, no raw-data file and no QC batch, and no test is assigned for it. A requirement the laboratory has started testing cannot be proposed.
- **Sampling stays required**: a lot whose requirements are all answered by accepted supplier results still needs a sample with its sampling record for QC disposition. This is a design default of this product.
- **Supplier result outside the specification**: "Does not meet the specification" is information only. It does not place a hold; only an active hold blocks disposition. The disposition signing page shows a warning for it while the certificate is not withdrawn.
- **Lot number on the certificate**: compared with the current receipt details each time the page is shown. A differing number is flagged and not refused.
- **Supplier certificate records are append-only**: none can be edited or deleted. A correction adds a linked record and a withdrawal adds a withdrawal record, each through its own page from the supplier certificate record.
- **Record result link vs. permission**: the link stays visible to analysts on Quarantine samples, but saving is refused with "Record observations through approved native testing requirements." unless the server runs in DEBUG and the lot has no requirement assignment. Record native results through Testing and investigations.
- **Dates and release**: the status "Expired" or "Retest due" is worked out from the dates in force and the local date, only for a Quarantine or Released lot; a Rejected or Cancelled lot shows none. After release the dates are shown, never changed.
- **Release paths**: with assigned requirements or native tests (and always outside DEBUG), release depends on the assignment, sampling records, native analytical evidence and holds. The manual foundation path (required rule-set tests, reviewed and conforming results) applies only in DEBUG on lots with neither. See Sign lot disposition for every condition and message.
- **Revision and stale pages**: signing pages bind to the revision shown when opened (the result's for review, the lot's for disposition); if it changed, signing fails with "Record changed. Reload and review before signing." Recording receipt details on an earlier lot, or correcting them, raises the lot revision by 1. So does recording or correcting the expiry and retest dates, and so does recording, correcting or withdrawing a supplier certificate, and proposing, accepting or withdrawing a supplier result in place of a test.
- **Independence**: no user dispositions or rejects a lot containing their own receipt, supplier certificate, expiry and retest dates, sampling or test data, even when holding the quality role. Receipt data covers everyone who recorded or corrected the lot's receipt details, including the recorder of a record that was later corrected. Expiry and retest dates cover everyone who recorded or corrected them, replaced records included. Supplier certificate data covers everyone who recorded, corrected or withdrew a supplier certificate of the lot, including the recorder of a record that was later corrected or withdrawn. Everyone who proposed a supplier result in place of a test is an author too, also after the proposal was withdrawn; the reviewer who accepted it is not. **Review disposition** and **Reject lot** still show for an author, and **Cancel lot received in error** also for whoever received the lot; those pages explain the refusal before any PIN is requested.
- **Rejection and cancellation**: quality signs either from Quarantine on its own page. The lot then keeps every record as signed, with the decision frozen on it, and takes no more records (the Quarantine-only rules above apply to it as they do to a Released lot); it cannot be released. Rejection is for a lot that failed its requirements or cannot be used; cancellation only for a lot received in error before samples, tests, reserve samples, studies or a standing supplier result exist. Signatures of the lot, including the decision (meaning rejected or cancelled), are listed under Electronic signatures, and "No lot disposition signature yet." is not shown once the lot is Released, Rejected or Cancelled.
- **Review link after release**: a Recorded foundation result still shows **Review result** to independent reviewers on a released lot, but signing is refused ("This result is not awaiting review.").
- **Certificates of analysis**: the section appears only after release; issuing is a separate signed step on the certificate pages. It is unrelated to the Supplier certificates card.

## Related pages

- [Material lots](/lots/)
- Lot requirements and sampling; Lot testing (Testing and investigations).
- Record receipt details, Correct receipt details; Supplier record.
- Record supplier certificate; Supplier certificate record.
- Supplier result acceptance record; Supplier qualification record (from the acceptance record).
- Add sample, Record result, Sign result review, Sign lot disposition.
- Review certificate; Certificate record.
- [Suppliers](/suppliers/)
- [Holds](/stability/holds/)
- Export record (the lot's complete record as one file).
- [Audit trail](/audit/)
