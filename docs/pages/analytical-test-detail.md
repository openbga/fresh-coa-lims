---
title: Test record
urls: analytical:test_detail
views: analytical.views.test_detail
templates: analytical/test_detail.html, analytical/_resources.html, analytical/_raw_files.html, analytical/_history.html, analytical/_test_status.html, analytical/_qc_status.html
models: analytical.AnalyticalTest, analytical.Observation, analytical.RawDataFile, analytical.QCBatch, analytical.Investigation, laboratory.ContractApproval, quality.SupplierResultAcceptance, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

One analytical test: its frozen specification, replicate observations (made here or reported by a contract laboratory), calculated result, and the actions to record, submit, return or review it.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Add to QC batch**, **Record observation**, **Record contract laboratory result**, **Correct contract laboratory result**, **Correct**, **Attach raw data**, **Submit for review**: analysts.
- **Sign review**, **Return test**: reviewers, and never a user who generated the test's data (observation recorders including superseded ones, whoever recorded or corrected a contract laboratory result, the submitter, and recorders of the batch's QC, and uploaders of raw-data files), even with the reviewer role.
- Links show whenever their state condition holds for the role; the server enforces the rest.
- **Admin** alone is a read role: no action buttons or submit form, and a posted submission is refused with 403. Admin together with a lab role gets that role's actions; it is never an exemption from the authorship rules.

## Layout

- **Header**: "T-n" and test name; status, kind, lot and sample, Revision. Buttons: **Sign review**, **Return test**, **Add to QC batch**, **Record observation**, **Record contract laboratory result** or **Correct contract laboratory result**.
- **Superseded** notice, on a test superseded when the lot's requirements were replaced: "The lot's requirements were replaced and this test's requirement is no longer one of them. The test and everything recorded on it are kept as they were. It takes no more work and does not count toward the lot's disposition. See the lot's requirements for the signed replacement", adding "; the test that repeats it under the current requirement is listed under Linked tests" once a repeat exists. "lot's requirements" links to Lot requirements and sampling.
- **Alerts**: the test opened an investigation (cannot be corrected or returned); or it is an investigation test (retest or resample).
- **Supplier result** banner, on an Open test when a supplier result is proposed or accepted in place of it and not withdrawn. Quarantine lot: "A result stated on the supplier's certificate is proposed or accepted in place of this test (SRA-n, on the lot record). This test takes no observation, reported result, raw-data file or QC batch while that stands. Withdraw it there to test the requirement in the laboratory." Released lot: "This test was not performed. The lot was dispositioned with its requirement answered by a result stated on the supplier's certificate (SRA-n, on the lot record)." The words "lot record" link to the lot record.
- **Contract laboratory** banner, when the result was reported by a contract laboratory: "This result was reported by NAME (code, location) in report NUMBER dated DATE. It was not tested in this laboratory. The reviewer checks it against the report." Below it an **Approval revoked** warning when the approval the result relied on was revoked since: "The approval this result relied on (CLA-n) was revoked on DATE TIME. The result stands as recorded. The approval's record lists every result that relied on it, for quality to assess under the laboratory's procedure."
- **Observations** ("N of M"): Replicate, Value (unit in the heading) and Within limits for numeric and count tests, or Result and As expected for qualitative tests, then Original record, Recorded, and **Correct**. For a calculated method the value heading reads "Calculated value" ("Value" when a contract laboratory reported the result). Under each observation a line shows, for a calculated method, **How it was calculated** (each input with its value and unit, the formula, the method revision and the rounding), and **Equipment and lots** (the instruments and lots recorded with it, or "Not recorded"). A replicate reported by a contract laboratory shows instead **Reported by** (laboratory code and name, report number and date) and **Approval relied on** (CLA-n, method, validity dates, evidence reference and, when the approval has one, "scope: TEXT"), and has no **Correct** link. A qualitative result shows what was observed under it. Superseded values are struck through and marked "superseded"; corrections are marked "correction". Empty state "No observations yet": "This method runs in a QC batch. Add the test to an open batch before recording results, or record the result a contract laboratory reported." when the method needs a batch and none is assigned, otherwise "Record each replicate with the location of its original record."
- **Submit form** (analysts, when all replicates are present and QC is ready): Reason and **Submit for review**. Otherwise a note explains why submission or review is blocked.
- **Specification and result** panel: Test code, Specification revision with snapshot hash, Acceptance, Method (with a note when each result must record equipment or lots; for a reported result "Performed by the contract laboratory; its instruments and lots are in its report."), Calculation (calculated methods: formula, inputs with units, result unit and rounding; for a reported result "Not applied here: the value was entered as the contract laboratory reported it."), Replicates, Tested by (reported results only), QC batch, Mean (not shown for qualitative tests), Reportable, Submitted by, Replaces, Linked tests.
- **Raw data files** (count): File, Size, SHA-256 (shortened), Description, Attached (who and when) and **Download**; **Attach raw data** below the list. Empty state "No raw data attached".
- **Electronic signatures** and **History**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record observation** | Test Open, lot Quarantine, fewer current values than replicates, and a batch assigned if the method needs one | Analyst | Opens the Record observation form |
| **Record contract laboratory result** | Test Open, lot Quarantine, no QC batch assigned, no observations | Analyst | Opens the Record contract laboratory result form. When no laboratory is approved for the method you are returned here with "No contract laboratory is approved for method METHOD. Quality records and signs the approval under Laboratory, Contract laboratories." |
| **Correct contract laboratory result** | Test Open, lot Quarantine, every current replicate was reported by a contract laboratory | Analyst | Opens the same page to correct the whole result |
| **Correct** (row) | Test Open, lot Quarantine, row is current and was not reported by a contract laboratory | Analyst | Opens the Correct observation form |
| **Add to QC batch** | Open, lot Quarantine, method needs a batch, none assigned, no observations | Analyst | Opens the Add to QC batch form |
| **Attach raw data** | Test Open and lot Quarantine | Analyst | Opens the Attach raw data form |
| **Download** (row of Raw data files) | A file is attached | Analyst, reviewer, quality, admin, auditor | Sends the stored file; refused if its checksum no longer matches |
| **Submit for review** | Open, lot Quarantine, current values equal replicates, and QC ready (no batch needed, the result was reported by a contract laboratory, or its batch is open with QC passed) | Analyst | Posts to this page; freezes the calculation; "Results submitted for independent review." |
| **Return test** | Submitted and conforming | Reviewer | Opens the Return test form |
| **Sign review** | Submitted and QC ready | Reviewer | Opens the Sign review page |

While a supplier result is proposed or accepted in place of the test, none of the analyst actions above is shown: no **Record observation**, **Record contract laboratory result**, **Add to QC batch**, **Attach raw data** or submit form.

Submitting an out-of-specification result opens an investigation, redirects to it and warns "Out of specification: INV-n opened and lot LOT-TEST-001 is held until it is concluded."

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `AnalyticalTest.state`, `conforms` | Text | — | Open, "Not tested · supplier result" (Open, a supplier result proposed or accepted in place of the test and not withdrawn; also after the lot is released), Awaiting review, Reviewed · conforms, Out of specification · awaiting review or reviewed, Invalidated, "Superseded · requirements replaced" |
| Value / Result | `Observation.value_text`, `observed_text` | Text as recorded, e.g. "99.80", "<10" or "Absent" | — | Result as recorded; for qualitative tests what was observed is shown below it |
| Within limits / As expected | `Observation.value`, `qualifier`, `outcome` | Yes, No or Cannot be shown | — | The reading on its own against the acceptance. A less-than reading "<X" is Yes only when there is no lower limit and X is within the upper limit; otherwise "Cannot be shown". A qualitative reading is Yes only when it shows the expected outcome |
| How it was calculated | `Observation.inputs`, `Observation.calculation` | Inputs with units, formula, method revision, decimals | — | Shows how the value was reached; "Entered directly" for a row without a calculation |
| Equipment and lots | `Observation.eligibility` | Identifiers | — | Equipment and reagent or standard lots frozen with the observation; "Not recorded" for rows written before bench checks or with none selected |
| Reported by / Approval relied on | `Observation.eligibility` (contract) | Text | — | Replicates reported by a contract laboratory: its code and name, the report number and date, and the approval relied on (CLA-n, method, validity dates, evidence reference and its scope when it has one), frozen when the result was recorded. Shown instead of How it was calculated and Equipment and lots |
| Original record | `Observation.raw_reference` | Text | — | Where the original observation is kept (for a reported result, where the laboratory's report is kept); correction reason shown below it |
| Tested by | `Observation.eligibility` (contract) | Text | — | Reported results only: the contract laboratory's name, then "Contract laboratory code · report NUMBER dated DATE" |
| QC batch | `AnalyticalTest.batch` | Text | — | Batch number and QC status, "Not yet assigned" or "Not required by method". For a reported result: "Run by the contract laboratory; see its report" |
| Mean | `AnalyticalTest.mean_value` | Decimal | — | Exact mean; "Not calculated" before submission; "None: a replicate is reported as less than a value" when a submitted result has a less-than replicate; not shown for qualitative tests |
| Reportable | `AnalyticalTest.reportable_text` (`reportable_value` for tests submitted before the text was stored) | Text with unit | — | Frozen at submission. Numeric and count: mean rounded half-up to the approved decimals; when the specification sets no reporting precision, the exact mean (submission is refused if it is not exact within 8 decimals). With any less-than replicate: the common reading ("<10") or the readings joined with "; " in replicate order, and no numeric value. Qualitative: the expected outcome when every replicate shows it, otherwise the deviating outcome |
| Acceptance | `AnalyticalTest.requirement` | Text | — | Each limit is inclusive ("at least", "at most", "L to U") or exclusive ("more than", "less than"); qualitative: criterion and expected outcome, with "Every replicate must read …". Numeric notes: "Each replicate and the reportable value must conform." when replicate limits apply, and the less-than rule |
| Raw data file | `RawDataFile.filename`, `size`, `sha256`, `description`, `uploaded_by`, `uploaded_at` | Text, bytes, 64-hex checksum | — | File kept unchanged in the database; the list is oldest first |
| Reason (submit) | `AuditEvent.reason` | Text, max 2000 | Yes | Initial text "Results complete" |
| Expected revision (hidden) | `AnalyticalTest.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Specification**: frozen from the configured approved-requirements provider when the test was assigned. Not enforced by this page: whether the provider's specification is the correct one.
- **Submit**: needs the test Open, lot in quarantine and, when the method requires a batch, an open batch whose QC has passed ("Batch QC is failed; tests cannot be submitted." or incomplete). When the batch is not open or its QC has not passed, the form is replaced by the note "Results cannot be submitted until the test's QC batch is open and its QC passes."; the server also refuses ("Batch QC is failed; tests cannot be submitted."). A result reported by a contract laboratory is submitted and reviewed without a QC batch of this laboratory, also when the method requires one: that laboratory's batch QC stays in its report. A stale page gives "Record changed. Reload and review before continuing.".
- **Conformance**: numeric and count: the rounded reportable value within the limits (strictly where a limit excludes its boundary) and, if replicate limits apply, every replicate within limits. If any replicate is a less-than reading there is no mean and every replicate must conform on its own, whatever the replicate-limits setting; a less-than reading that cannot be shown to meet the limits does not conform. Qualitative: every replicate must show the expected outcome.
- **Tested here or reported, never both**: **Record contract laboratory result** needs a test with no QC batch and no observations. Once a contract laboratory result is recorded the test takes no observation made here ("This test holds a result reported by a contract laboratory. It takes no observation made in this laboratory; correct the contract laboratory result instead."), no correction of a single replicate and no QC batch; the result is corrected as a whole.
- **Supplier result in place of this test**: while a supplier result is proposed or accepted for this requirement of the lot and not withdrawn, the test stays Open and takes no laboratory work. Opening Record observation, Record contract laboratory result, Add to QC batch or Attach raw data directly returns you here with "A supplier's result is proposed or accepted in place of this test (SRA-1). Withdraw it on the lot record before testing the requirement in the laboratory.", and the server refuses the same on submission. An accepted result answers the requirement for the whole lot, so the Open test does not block QC disposition. Withdraw the record from its acceptance record (reached from the lot record) to test the requirement here. The reverse also holds: a test that is no longer Open, is in a QC batch, or holds an observation or a raw-data file stops a supplier result from being proposed or accepted for its requirement.
- **After release**: an Open test whose requirement an accepted supplier result answered keeps the status "Not tested · supplier result" and shows the banner "This test was not performed. …", here as on the lot's testing page and the test list.
- **Revoked approval**: the warning is information only. The result stands as recorded and can still be submitted and reviewed. A correction that keeps the laboratory and the report is still accepted; one that names another laboratory or report needs an approval that covers it.
- **Review blocked**: for a submitted test whose QC batch no longer passes, **Sign review** is hidden and the page says "Review is blocked: the test's QC batch no longer passes."
- **Calculated results**: submission and review recalculate every current calculated observation from its stored inputs with the frozen formula. A difference refuses the action ("Calculated result changed; correct the observation before submitting." or "Calculated result changed; return the test for resubmission."). A value reported by a contract laboratory is entered as reported, has no stored inputs and is not recalculated; the page then says so under Calculation and heads the column "Value".
- **Out of specification**: cannot be corrected or returned; the investigation decides.
- **Superseded**: set only by a signed replacement of the lot's requirements, for a test that was Open without unsubmitted results, Awaiting review or Reviewed and whose requirement changed or is no longer required. Every action needs the test Open or Awaiting review, so a superseded test shows none of the analyst or reviewer actions (raw-data files can still be downloaded) and takes no observation, raw-data file, batch, submission or review. Its observations, files, signatures and history stay as recorded. Its repeat (kind "Repeat under replaced requirements") is created from Lot testing with **Assign required tests** and links back under Replaces.
- **Revisions**: every evidence change (observation, correction, contract laboratory result, raw-data file, submit, return, batching, review) raises the test revision and the lot revision by 1.
- **Immutability**: observations are never overwritten; a correction adds a linked row and the original stays visible. Raw-data files are never changed or deleted.
- **Audit**: events such as `observation.recorded`, `contract_result.recorded`, `contract_result.corrected`, `test.submitted`, `test.returned`, `rawdata.attached`, `signed.reviewed`, `test.superseded` appear under History.

## Related pages

- [Testing: tests](/testing/)
- Lot testing page, QC batch record, Investigation record.
- Lot requirements and sampling (the signed replacement that superseded a test).
- Record observation, Correct observation, Record contract laboratory result, Attach raw data, Add to QC batch, Return test, Sign review.
- Lot record and Supplier result acceptance record (when a supplier result stands in place of the test).
- [Contract laboratories](/laboratory/contract-laboratories/) (register and approvals).
