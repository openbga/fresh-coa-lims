---
title: Correct observation
urls: analytical:observation_correct
views: analytical.views.observation_correct
templates: analytical/form.html, analytical/_summary.html
models: analytical.Observation, analytical.AnalyticalTest, quality.Lot, quality.Sample, laboratory.Qualification
reviewed: 2026-11-10
---

## Purpose

Correct one replicate value by adding a linked correction. The original value stays visible in the record.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- Not restricted to the original recorder. Not enforced by this page: any rule about who may correct whose entry.

## Layout

- Heading "Correct replicate N · T-n".
- Summary card: test facts, "Value being corrected" and "Original record".
- Form: **Observed value**, **Original record** (prefilled), **Reason for correction**, **Cancel**, **Correct observation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Correct observation** | Always | Analyst | Adds a correction; "Correction recorded; the original value is preserved."; returns to the test |
| **Cancel** | Always | Analyst | Returns to the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Observed value | `Observation.value` | Decimal, 8 decimals | Yes | Corrected value; same help text as recording |
| Original record | `Observation.raw_reference` | Text, max 200 | Yes | Source of the corrected value |
| Reason for correction | `Observation.reason` | Text, max 2000 | Yes | "The original value stays visible in the record." |
| Test (summary) | `AnalyticalTest.id` (shown as T-n), `AnalyticalTest.requirement` name, `AnalyticalTest.test_code` | Text | — | "T-n · name (code)": the test being recorded |
| Lot and sample (summary) | `Lot.number`, `Sample.reference` | Text | — | "lot / sample" the test belongs to |
| Specification (summary) | `AnalyticalTest.requirement` (source, lower/upper limits, unit) | Text | — | Frozen approved requirement: "source · L to U unit", "at least L unit" or "at most U unit" |
| Record revision (summary) | `AnalyticalTest.revision` | Integer | — | Test revision when the page opened; recording raises it by 1 |
| Value being corrected (summary) | `Observation.value_text`, `Observation.unit` | Text as entered + unit | — | The current value this correction supersedes; it stays visible struck through |
| Original record (summary) | `Observation.raw_reference` | Text | — | Original record of the value being corrected; prefilled into the input |
| Replicate number (title) | `Observation.replicate` | Integer | — | "Correct replicate N": the correction keeps this replicate number |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the test record with the warning "Only current observations of open tests can be corrected.".
- **Preconditions**: test must be Open ("Only open tests can be corrected. A reviewer must return a submitted test first."); lot in quarantine; the observation must not already be corrected ("This observation has already been corrected.").
- **Analyst eligibility**: before accepting the value the server checks that you hold a current qualification for this test's method. The qualification's activity must match the approved method code (case-insensitive) and be approved, within its validity dates and not revoked at the time of entry; your account must be active. A laboratory role alone is not enough. If you are not eligible the reasons (for example "No approved, current qualification for “<method>”.") appear as a form error and nothing is saved. Without a configured check: "No analyst eligibility check is configured; observations are held." The evidence (user, activity, qualification) is frozen on the observation and in its audit event.
- **Not checked here**: this check does not select or verify equipment or reagent lots, and it is not applied to batch QC recording or correction.
- **Effect**: a new row with the same replicate number supersedes the old one; the test and lot revisions rise by 1; `observation.corrected` is audited with before and after values and your reason.
- **Display**: the old value is struck through and marked "superseded"; the new row is marked "correction".
- **Independence**: a corrected original still counts as that user's data, so a superseded author cannot review the test.
- Out-of-specification submitted tests cannot be returned, so they cannot be corrected.

## Related pages

- Test record (return target).
