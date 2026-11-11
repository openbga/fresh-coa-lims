---
title: Test record
urls: analytical:test_detail
views: analytical.views.test_detail
templates: analytical/test_detail.html, analytical/_history.html, analytical/_test_status.html, analytical/_qc_status.html
models: analytical.AnalyticalTest, analytical.Observation, analytical.QCBatch, analytical.Investigation, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

One analytical test: its frozen specification, replicate observations, calculated result, and the actions to record, submit, return or review it.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Add to QC batch**, **Record observation**, **Correct**, **Submit for review**: analysts.
- **Sign review**, **Return test**: reviewers, and never a user who generated the test's data (observation recorders including superseded ones, the submitter, and recorders of the batch's QC), even with the reviewer role.
- Links show whenever their state condition holds for the role; the server enforces the rest.
- **Admin** alone is a read role: no action buttons or submit form, and a posted submission is refused with 403. Admin together with a lab role gets that role's actions; it is never an exemption from the authorship rules.

## Layout

- **Header**: "T-n" and test name; status, kind, lot and sample, Revision. Buttons: **Sign review**, **Return test**, **Add to QC batch**, **Record observation**.
- **Alerts**: the test opened an investigation (cannot be corrected or returned); or it is an investigation test (retest or resample).
- **Observations** ("N of M"): Replicate, Value, Within limits, Original record, Recorded, and **Correct**. Superseded values are struck through and marked "superseded"; corrections are marked "correction". Empty states depend on whether a QC batch is still needed.
- **Submit form** (analysts, when all replicates are present and QC is ready): Reason and **Submit for review**. Otherwise a note explains why submission or review is blocked.
- **Specification and result** panel: Test code, Specification revision with snapshot hash, Limits, Method, Replicates, QC batch, Mean, Reportable, Submitted by, Replaces, Linked tests.
- **Electronic signatures** and **History**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record observation** | Test Open, lot Quarantine, fewer current values than replicates, and a batch assigned if the method needs one | Analyst | Opens the Record observation form |
| **Correct** (row) | Test Open, lot Quarantine, row is current | Analyst | Opens the Correct observation form |
| **Add to QC batch** | Open, lot Quarantine, method needs a batch, none assigned, no observations | Analyst | Opens the Add to QC batch form |
| **Submit for review** | Open, lot Quarantine, current values equal replicates, and QC ready (no batch needed, or its batch is open with QC passed) | Analyst | Posts to this page; freezes the calculation; "Results submitted for independent review." |
| **Return test** | Submitted and conforming | Reviewer | Opens the Return test form |
| **Sign review** | Submitted and QC ready | Reviewer | Opens the Sign review page |

Submitting an out-of-specification result opens an investigation, redirects to it and warns "Out of specification: INV-n opened and lot LOT-TEST-001 is held until it is concluded."

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `AnalyticalTest.state`, `conforms` | Text | — | Open, Awaiting review, Reviewed · conforms, Out of specification · awaiting review or reviewed, Invalidated |
| Value | `Observation.value_text` | Decimal in the test unit | — | Value as entered |
| Within limits | `Observation.value` | Yes or No | — | Value against the specification limits |
| Original record | `Observation.raw_reference` | Text | — | Where the original observation is kept; correction reason shown below it |
| Mean | `AnalyticalTest.mean_value` | Decimal | — | Exact mean, "Not calculated" before submission |
| Reportable | `AnalyticalTest.reportable_value` | Decimal with unit | — | Mean rounded half-up to the approved decimals; when the specification sets no reporting precision, the exact mean (submission is refused if it is not exact within 8 decimals) |
| Limits | `AnalyticalTest.requirement` | Range | — | Inclusive; "Each replicate and the reportable value must conform." when replicate limits apply |
| Reason (submit) | `AuditEvent.reason` | Text, max 2000 | Yes | Initial text "Results complete" |
| Expected revision (hidden) | `AnalyticalTest.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Specification**: frozen from the configured approved-requirements provider when the test was assigned. Not enforced by this page: whether the provider's specification is the correct one.
- **Submit**: needs the test Open, lot in quarantine and, when the method requires a batch, an open batch whose QC has passed ("Batch QC is failed; tests cannot be submitted." or incomplete). When the batch is not open or its QC has not passed, the form is replaced by the note "Results cannot be submitted until the test's QC batch is open and its QC passes."; the server also refuses ("Batch QC is failed; tests cannot be submitted."). A stale page gives "Record changed. Reload and review before continuing.".
- **Conformance**: reportable value within limits and, if replicate limits apply, every replicate within limits.
- **Review blocked**: for a submitted test whose QC batch no longer passes, **Sign review** is hidden and the page says "Review is blocked: the test's QC batch no longer passes."
- **Out of specification**: cannot be corrected or returned; the investigation decides.
- **Revisions**: every evidence change (observation, correction, submit, return, batching, review) raises the test revision and the lot revision by 1.
- **Immutability**: observations are never overwritten; a correction adds a linked row and the original stays visible.
- **Audit**: events such as `observation.recorded`, `test.submitted`, `test.returned`, `signed.reviewed` appear under History.

## Related pages

- [Testing: tests](/testing/)
- Lot testing page, QC batch record, Investigation record.
- Record observation, Correct observation, Add to QC batch, Return test, Sign review.
