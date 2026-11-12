---
title: Correct observation
urls: analytical:observation_correct
views: analytical.views.observation_correct
templates: analytical/form.html, analytical/_summary.html
models: analytical.Observation, analytical.AnalyticalTest, quality.Lot, quality.Sample, laboratory.Qualification
reviewed: 2026-11-12
---

## Purpose

Correct one replicate result by adding a linked correction. The original result stays visible in the record. A correction may change the value, the less-than qualifier or the qualitative outcome.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- Not restricted to the original recorder. Not enforced by this page: any rule about who may correct whose entry.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Correct replicate N · T-n".
- Summary card: test facts, "Result being corrected", "What was observed" (when recorded) and "Original record".
- Form, numeric and count tests: **Observed value** (**Observed count** for counts), **Reported as less than this value**, **Original record** (prefilled), **Reason for correction**.
- Form, qualitative tests: **Observed result** (radio pair), **What was observed** (the correction carries its own), **Original record** (prefilled), **Reason for correction**.
- **Cancel**, **Correct observation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Correct observation** | Always | Analyst | Adds a correction; "Correction recorded; the original value is preserved."; returns to the test |
| **Cancel** | Always | Analyst | Returns to the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Observed value / Observed count | `Observation.value`, `qualifier`, `value_text` | Decimal, 20 digits, 8 decimals; unit from the specification | Yes (numeric and count tests) | "Exact value as read; at most 8 decimal places." (count: "Whole number of zero or more, exactly as read.") followed by "Never enter a nondetect as zero: enter the reporting limit and choose “Reported as less than this value”." |
| Reported as less than this value | `Observation.qualifier` ("<") | Checkbox | No (numeric and count tests) | "For a result below the reporting or detection limit (shown as <10). It is stored as recorded and never converted to zero or to the number." The value is kept as the limit with the "<" qualifier |
| Observed result | `Observation.outcome`, `value_text` | Radio: Conforms / Does not conform, or Absent / Present (the pair approved for the test) | Yes (qualitative tests) | Help text shows the acceptance, e.g. "Acceptance: Absent in 25 g (expected: Absent)." |
| What was observed | `Observation.observed_text` | Text, max 200 | Yes (qualitative tests) | "Describe the observation itself, e.g. what was seen or how the test reacted; the outcome is recorded separately." |
| Original record | `Observation.raw_reference` | Text, max 200 | Yes | Source of the corrected value |
| Reason for correction | `Observation.reason` | Text, max 2000 | Yes | "The original result stays visible in the record." |
| Test (summary) | `AnalyticalTest.id` (shown as T-n), `AnalyticalTest.requirement` name, `AnalyticalTest.test_code` | Text | — | "T-n · name (code)": the test being recorded |
| Lot and sample (summary) | `Lot.number`, `Sample.reference` | Text | — | "lot / sample" the test belongs to |
| Specification (summary) | `AnalyticalTest.requirement` (source, acceptance) | Text | — | Frozen approved requirement: "source · acceptance", e.g. "95.0 to 105.0 unit", "at least L unit", "more than L and at most U unit", "less than U unit" or, for a qualitative test, "Absent in 25 g (expected: Absent)" |
| Record revision (summary) | `AnalyticalTest.revision` | Integer | — | Test revision when the page opened; recording raises it by 1 |
| Result being corrected (summary) | `Observation.value_text`, `Observation.unit` | Text as recorded + unit (no unit for qualitative tests) | — | The current result this correction supersedes, e.g. "<10 CFU/g" or "Absent"; it stays visible struck through |
| What was observed (summary) | `Observation.observed_text` | Text | — | Shown when the result being corrected recorded an observation |
| Original record (summary) | `Observation.raw_reference` | Text | — | Original record of the value being corrected; prefilled into the input |
| Replicate number (title) | `Observation.replicate` | Integer | — | "Correct replicate N": the correction keeps this replicate number |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the test record with the warning "Only current observations of open tests can be corrected.".
- **Preconditions**: test must be Open ("Only open tests can be corrected. A reviewer must return a submitted test first."); lot in quarantine; the observation must not already be corrected ("This observation has already been corrected.").
- **Analyst eligibility**: before accepting the value the server checks that you hold a current qualification for this test's method. The qualification's activity must match the approved method code (case-insensitive) and be approved, within its validity dates and not revoked at the time of entry; your account must be active. A laboratory role alone is not enough. If you are not eligible the reasons (for example "No approved, current qualification for “<method>”.") appear as a form error and nothing is saved. Without a configured check: "No analyst eligibility check is configured; observations are held." The evidence (user, activity, qualification) is frozen on the observation and in its audit event.
- **Form by result type** (from the frozen requirement): numeric and count tests show the value and the less-than checkbox; qualitative tests show the outcome radio pair and **What was observed**, with no numeric field.
- **Reading validation** (form errors, status 422, nothing saved): "A count must be a whole number of zero or more."; "A less-than result needs a value greater than zero."; "A qualitative result cannot be reported as less than a value."; "Choose the observed result: Absent or Present." (or Conforms or Does not conform); "Describe what was observed; the outcome alone is not a complete record."
- **As recorded**: the result text is stored exactly as entered ("99.80", "<10") or as the outcome label ("Absent"). A less-than result is never treated as zero or as its number.
- **Not checked here**: this check does not select or verify equipment or reagent lots, and it is not applied to batch QC recording or correction.
- **Effect**: a new row with the same replicate number supersedes the old one; the test and lot revisions rise by 1; `observation.corrected` is audited with the before and after readings as recorded (value text, qualifier, outcome, what was observed) and your reason.
- **Display**: the old value is struck through and marked "superseded"; the new row is marked "correction".
- **Independence**: a corrected original still counts as that user's data, so a superseded author cannot review the test.
- Out-of-specification submitted tests cannot be returned, so they cannot be corrected.

## Related pages

- Test record (return target).
