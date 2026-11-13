---
title: Test record
urls: analytical:test_detail
views: analytical.views.test_detail
templates: analytical/test_detail.html, analytical/_resources.html, analytical/_raw_files.html, analytical/_history.html, analytical/_test_status.html, analytical/_qc_status.html
models: analytical.AnalyticalTest, analytical.Observation, analytical.RawDataFile, analytical.QCBatch, analytical.Investigation, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-12
---

## Purpose

One analytical test: its frozen specification, replicate observations, calculated result, and the actions to record, submit, return or review it.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Add to QC batch**, **Record observation**, **Correct**, **Attach raw data**, **Submit for review**: analysts.
- **Sign review**, **Return test**: reviewers, and never a user who generated the test's data (observation recorders including superseded ones, the submitter, and recorders of the batch's QC, and uploaders of raw-data files), even with the reviewer role.
- Links show whenever their state condition holds for the role; the server enforces the rest.
- **Admin** alone is a read role: no action buttons or submit form, and a posted submission is refused with 403. Admin together with a lab role gets that role's actions; it is never an exemption from the authorship rules.

## Layout

- **Header**: "T-n" and test name; status, kind, lot and sample, Revision. Buttons: **Sign review**, **Return test**, **Add to QC batch**, **Record observation**.
- **Alerts**: the test opened an investigation (cannot be corrected or returned); or it is an investigation test (retest or resample).
- **Observations** ("N of M"): Replicate, Value (unit in the heading) and Within limits for numeric and count tests, or Result and As expected for qualitative tests, then, for a calculated method, **How it was calculated**, then **Equipment and lots**, Original record, Recorded, and **Correct**. For a calculated method the value heading reads "Calculated value". A qualitative result shows what was observed under it. Superseded values are struck through and marked "superseded"; corrections are marked "correction". Empty states depend on whether a QC batch is still needed.
- **Submit form** (analysts, when all replicates are present and QC is ready): Reason and **Submit for review**. Otherwise a note explains why submission or review is blocked.
- **Specification and result** panel: Test code, Specification revision with snapshot hash, Acceptance, Method (with a note when each result must record equipment or lots), Calculation (calculated methods: formula, inputs with units, result unit and rounding), Replicates, QC batch, Mean (not shown for qualitative tests), Reportable, Submitted by, Replaces, Linked tests.
- **Raw data files** (count): File, Size, SHA-256 (shortened), Description, Attached (who and when) and **Download**; **Attach raw data** below the list. Empty state "No raw data attached".
- **Electronic signatures** and **History**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record observation** | Test Open, lot Quarantine, fewer current values than replicates, and a batch assigned if the method needs one | Analyst | Opens the Record observation form |
| **Correct** (row) | Test Open, lot Quarantine, row is current | Analyst | Opens the Correct observation form |
| **Add to QC batch** | Open, lot Quarantine, method needs a batch, none assigned, no observations | Analyst | Opens the Add to QC batch form |
| **Attach raw data** | Test Open and lot Quarantine | Analyst | Opens the Attach raw data form |
| **Download** (row of Raw data files) | A file is attached | Analyst, reviewer, quality, admin, auditor | Sends the stored file; refused if its checksum no longer matches |
| **Submit for review** | Open, lot Quarantine, current values equal replicates, and QC ready (no batch needed, or its batch is open with QC passed) | Analyst | Posts to this page; freezes the calculation; "Results submitted for independent review." |
| **Return test** | Submitted and conforming | Reviewer | Opens the Return test form |
| **Sign review** | Submitted and QC ready | Reviewer | Opens the Sign review page |

Submitting an out-of-specification result opens an investigation, redirects to it and warns "Out of specification: INV-n opened and lot LOT-TEST-001 is held until it is concluded."

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `AnalyticalTest.state`, `conforms` | Text | — | Open, Awaiting review, Reviewed · conforms, Out of specification · awaiting review or reviewed, Invalidated |
| Value / Result | `Observation.value_text`, `observed_text` | Text as recorded, e.g. "99.80", "<10" or "Absent" | — | Result as recorded; for qualitative tests what was observed is shown below it |
| Within limits / As expected | `Observation.value`, `qualifier`, `outcome` | Yes, No or Cannot be shown | — | The reading on its own against the acceptance. A less-than reading "<X" is Yes only when there is no lower limit and X is within the upper limit; otherwise "Cannot be shown". A qualitative reading is Yes only when it shows the expected outcome |
| How it was calculated | `Observation.inputs`, `Observation.calculation` | Inputs with units, formula, method revision, decimals | — | Shows how the value was reached; "Entered directly" for a row without a calculation |
| Equipment and lots | `Observation.eligibility` | Identifiers | — | Equipment and reagent or standard lots frozen with the observation; "Not recorded" for rows written before bench checks or with none selected |
| Original record | `Observation.raw_reference` | Text | — | Where the original observation is kept; correction reason shown below it |
| Mean | `AnalyticalTest.mean_value` | Decimal | — | Exact mean; "Not calculated" before submission; "None: a replicate is reported as less than a value" when a submitted result has a less-than replicate; not shown for qualitative tests |
| Reportable | `AnalyticalTest.reportable_text` (`reportable_value` for tests submitted before the text was stored) | Text with unit | — | Frozen at submission. Numeric and count: mean rounded half-up to the approved decimals; when the specification sets no reporting precision, the exact mean (submission is refused if it is not exact within 8 decimals). With any less-than replicate: the common reading ("<10") or the readings joined with "; " in replicate order, and no numeric value. Qualitative: the expected outcome when every replicate shows it, otherwise the deviating outcome |
| Acceptance | `AnalyticalTest.requirement` | Text | — | Each limit is inclusive ("at least", "at most", "L to U") or exclusive ("more than", "less than"); qualitative: criterion and expected outcome, with "Every replicate must read …". Numeric notes: "Each replicate and the reportable value must conform." when replicate limits apply, and the less-than rule |
| Raw data file | `RawDataFile.filename`, `size`, `sha256`, `description`, `uploaded_by`, `uploaded_at` | Text, bytes, 64-hex checksum | — | File kept unchanged in the database; the list is oldest first |
| Reason (submit) | `AuditEvent.reason` | Text, max 2000 | Yes | Initial text "Results complete" |
| Expected revision (hidden) | `AnalyticalTest.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Specification**: frozen from the configured approved-requirements provider when the test was assigned. Not enforced by this page: whether the provider's specification is the correct one.
- **Submit**: needs the test Open, lot in quarantine and, when the method requires a batch, an open batch whose QC has passed ("Batch QC is failed; tests cannot be submitted." or incomplete). When the batch is not open or its QC has not passed, the form is replaced by the note "Results cannot be submitted until the test's QC batch is open and its QC passes."; the server also refuses ("Batch QC is failed; tests cannot be submitted."). A stale page gives "Record changed. Reload and review before continuing.".
- **Conformance**: numeric and count: the rounded reportable value within the limits (strictly where a limit excludes its boundary) and, if replicate limits apply, every replicate within limits. If any replicate is a less-than reading there is no mean and every replicate must conform on its own, whatever the replicate-limits setting; a less-than reading that cannot be shown to meet the limits does not conform. Qualitative: every replicate must show the expected outcome.
- **Review blocked**: for a submitted test whose QC batch no longer passes, **Sign review** is hidden and the page says "Review is blocked: the test's QC batch no longer passes."
- **Calculated results**: submission and review recalculate every current calculated observation from its stored inputs with the frozen formula. A difference refuses the action ("Calculated result changed; correct the observation before submitting." or "Calculated result changed; return the test for resubmission.").
- **Out of specification**: cannot be corrected or returned; the investigation decides.
- **Revisions**: every evidence change (observation, correction, raw-data file, submit, return, batching, review) raises the test revision and the lot revision by 1.
- **Immutability**: observations are never overwritten; a correction adds a linked row and the original stays visible. Raw-data files are never changed or deleted.
- **Audit**: events such as `observation.recorded`, `test.submitted`, `test.returned`, `rawdata.attached`, `signed.reviewed` appear under History.

## Related pages

- [Testing: tests](/testing/)
- Lot testing page, QC batch record, Investigation record.
- Record observation, Correct observation, Attach raw data, Add to QC batch, Return test, Sign review.
