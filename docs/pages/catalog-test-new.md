---
title: Add test to a specification version
urls: catalog:test_new
views: catalog.views.test_new
templates: catalog/form.html
models: catalog.SpecificationTest, catalog.SpecificationRevision, catalog.Method
reviewed: 2026-11-12
---

## Purpose

Adds one test line (method, acceptance criterion, replication) to a draft specification version.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Only drafts accept tests. For an approved or withdrawn version you are redirected back to the version with the message "Tests can only be added to a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, specification code, "Version N", Add test. Title: "Add test ·" and the version.
- **Intro**: "Numeric and count tests need a unit and at least one limit; count limits are whole numbers. Qualitative tests need the expected outcome and the criterion wording. Values are stored exactly as entered decimals."
- **Form sections**: Test, Replication, Acceptance criterion, Change control.
- **Buttons**: **Cancel** and **Add test**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add test** | Draft version | Quality | Adds the line; shows "Test <code> added to <version>." and returns to the version page |
| **Cancel** | Always | Quality | Returns to the version |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `SpecificationTest.code` | Slug, max 80 | Yes | Help: "Stable test code, e.g. assay or identity." Unique within the version. |
| Name | `SpecificationTest.name` | Text, max 160 | Yes | Test name. |
| Method | `SpecificationTest.method` | Choice of all methods | Yes | Method used for the test. |
| Position | `SpecificationTest.position` | Integer 1 to 999 | Yes | Display order; defaults to the current test count plus one. |
| Required for QC disposition | `SpecificationTest.required` | Checkbox, default on | No | Required tests must be complete before QC disposition; unticked means information only. |
| Replicates | `SpecificationTest.replicates` | Integer 1 to 10, default 1 | Yes | Help: "Determinations averaged into the reportable value." |
| Each replicate must meet the limits | `SpecificationTest.replicate_limits` | Checkbox, default on | No | Numeric and count: every replicate must conform, not only the mean. Help: "Numeric and count tests. Every replicate of a qualitative test must match the expected outcome." |
| Maximum retests | `SpecificationTest.max_retests` | Integer 0 to 3, default 0 | Yes | Help: "Allowed only under an approved investigation; 0 allows none." |
| Result type | `SpecificationTest.result_type` | "Numeric with limits", "Count (whole number)" or "Qualitative (expected outcome)" | Yes | Decides which criterion fields apply (see the help text on the field). |
| Unit | `SpecificationTest.unit` | Controlled list (for example %, mg/g, ppm, CFU/g, pH); "—" for none | Numeric and count: yes | Help: "Numeric and count tests only." Free-text units are not allowed. |
| Lower limit | `SpecificationTest.lower_limit` | Decimal, up to 20 digits, 8 decimals | Numeric and count: one limit at least | Lower acceptance bound. Count limits are whole numbers of 0 or more. |
| Lower limit is inclusive (≥) | `SpecificationTest.lower_inclusive` | Checkbox, default on | No | Help: "Clear for a strict limit (>)." |
| Upper limit | `SpecificationTest.upper_limit` | Decimal, same format | Numeric and count: one limit at least | Upper acceptance bound. |
| Upper limit is inclusive (≤) | `SpecificationTest.upper_inclusive` | Checkbox, default on | No | Help: "Clear for a strict limit (<)." |
| Round to decimals before comparison | `SpecificationTest.reporting_decimals` | Integer 0 to 8 | No | Help: "Numeric and count tests only. Leave blank to compare the exact recorded value." |
| Expected outcome | `SpecificationTest.expected_result` | Conforms, Absent or Present; "—" for none | Qualitative: yes | The outcome that conforms. Analysts record Conforms or Does not conform (expected Conforms), or Absent or Present (expected Absent or Present). |
| Criterion | `SpecificationTest.expected_text` | Text, max 160 | Qualitative: yes | The approved wording, e.g. "White crystalline powder" or "Not detected in 25 g". Shown with the outcome, e.g. "Absent: Not detected in 25 g". |
| Reason for change | audit event reason | Text, max 2000 | Yes | Stored in the audit event. |

## Rules and hidden logic

- **Numeric and count tests**: "A numeric test needs a unit." (or "A count test needs a unit."), "Enter at least one limit.", "The criterion text applies only to qualitative tests.", "The expected outcome applies only to qualitative tests.", "The upper limit must not be below the lower limit.", and for equal limits "Equal lower and upper limits must both be inclusive; otherwise no result can conform."
- **Count tests**: "Count limits must be whole numbers of 0 or more." Results are recorded as whole numbers, or as less than a value (for example "<10") on the testing pages.
- **Qualitative tests**: "Choose the expected outcome.", "Enter the criterion, e.g. Absent in 25 g.", "Qualitative tests have no numeric limits.", "Rounding applies only to numeric and count tests." The two inclusive boxes and "Each replicate must meet the limits" do not apply: the form stores them as set whatever you tick.
- **Other**: "This test code is already on the revision." "Use 1 to 10 replicates." "Use 0 to 3 retests." "Only draft revisions can be changed." (if the version stopped being a draft meanwhile). The database repeats the basic shape (unit and a limit for numeric and count; criterion and no limits for qualitative) as constraints; the outcome, equal-limit and whole-number rules are checked by the server here and again at approval.
- **Effect**: the record revision of the version increases by 1; audit event `specification_revision.test_added` with the line content and your reason.
- **Not enforced by this page**: the Method list offers every method, approved or not. Approval later requires an approved method version effective at the specification's start.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Specification version (record page).
- [Methods](/catalog/methods/)
