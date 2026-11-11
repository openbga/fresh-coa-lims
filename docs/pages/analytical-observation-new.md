---
title: Record observation
urls: analytical:observation_new
views: analytical.views.observation_new
templates: analytical/form.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.Observation, quality.Lot, quality.Sample, laboratory.Qualification
reviewed: 2026-11-10
---

## Purpose

Record the next replicate observation of a test, with the location of its original record.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- A test in the wrong state redirects you back to the test record with a warning (see Rules).
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Record replicate N · T-n" and breadcrumbs.
- Summary card: Test, Lot and sample, Specification, Record revision, Unit.
- Form: **Observed value**, **Original record**, **Cancel**, **Record observation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record observation** | Always | Analyst | Adds the observation; "Observation recorded."; returns to the test |
| **Cancel** | Always | Analyst | Returns to the test without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Observed value | `Observation.value`, `value_text` | Decimal, 20 digits, 8 decimals; unit from the specification | Yes | "Exact value as read; at most 8 decimal places. Never enter a nondetect as zero." |
| Original record | `Observation.raw_reference` | Text, max 200 | Yes | "Notebook page, instrument file or worksheet holding the original observation." |
| Test (summary) | `AnalyticalTest.id` (shown as T-n), `AnalyticalTest.requirement` name, `AnalyticalTest.test_code` | Text | — | "T-n · name (code)": the test being recorded |
| Lot and sample (summary) | `Lot.number`, `Sample.reference` | Text | — | "lot / sample" the test belongs to |
| Specification (summary) | `AnalyticalTest.requirement` (source, lower/upper limits, unit) | Text | — | Frozen approved requirement: "source · L to U unit", "at least L unit" or "at most U unit" |
| Record revision (summary) | `AnalyticalTest.revision` | Integer | — | Test revision when the page opened; recording raises it by 1 |
| Unit (summary) | `AnalyticalTest.requirement` unit | Text | — | Unit the value is stored in (`Observation.unit`); not editable |
| Replicate number (title) | `Observation.replicate` | Integer | — | "Record replicate N": current observations + 1, assigned by the server |

## Rules and hidden logic

- **Wrong state** (opening or submitting): redirects to the test record with a warning: "This test is not accepting observations." (test not Open or lot not in quarantine); "Add this test to a QC batch before recording results."; "All replicates are recorded. Correct a value instead."
- **Preconditions**: test Open ("This test is not accepting observations."); lot in quarantine ("Lot ... is no longer in quarantine."); a QC batch assigned when the method needs one ("Assign this test to a QC batch before recording results."); fewer current values than replicates ("All replicates are recorded. Correct a value instead.").
- **Analyst eligibility**: before accepting the value the server checks that you hold a current qualification for this test's method. The qualification's activity must match the approved method code (case-insensitive) and be approved, within its validity dates and not revoked at the time of entry; your account must be active. A laboratory role alone is not enough. If you are not eligible the reasons (for example "No approved, current qualification for “<method>”.") appear as a form error and nothing is saved. Without a configured check: "No analyst eligibility check is configured; observations are held." The evidence (user, activity, qualification) is frozen on the observation and in its audit event.
- **Not checked here**: this check does not select or verify equipment or reagent lots, and it is not applied to batch QC recording or correction.
- **Blank record**: "Record where the original observation is kept." when the original record is only spaces.
- **Effect**: in one transaction the observation is stored with the next replicate number, the test revision and lot revision rise by 1, and `observation.recorded` is audited with your identity. The server sets time and recorder.
- **Validation errors** show on the form with status 422; nothing is saved.
- Out-of-limit values are recorded as entered and marked "No" under Within limits.

## Related pages

- Test record (return target).
- [Testing: tests](/testing/)
