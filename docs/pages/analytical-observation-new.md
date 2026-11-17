---
title: Record observation
urls: analytical:observation_new
views: analytical.views.observation_new
templates: analytical/form.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.Observation, quality.Lot, quality.Sample, laboratory.Qualification
reviewed: 2026-11-17
summary: Record the next replicate of an open test, with the equipment and lots used and where the original observation is kept.
---

## Common tasks
### Record a numeric or count reading
1. Enter the reading exactly as read in [[Observed value]], or [[Observed count]] for a count.
2. For a result below the reporting limit, enter the limit and tick [[Reported as less than this value]].
3. Tick the [[Equipment used]] and [[Reagent and standard lots used]], fill in [[Original record]] and select [[Record observation]].
### Record a qualitative reading
1. Choose the outcome under [[Observed result]] and describe it in [[What was observed]].
2. Fill in [[Original record]] and select [[Record observation]].
### Record a calculated result
1. Enter each input the form asks for. The server calculates the value with the approved formula.
2. Fill in [[Original record]] and select [[Record observation]].
## Good to know
- Never enter a nondetect as zero. A less-than result is stored as recorded and never converted to zero or to the number.
- The bench checks your qualification for the method and every instrument and lot you tick. A refusal saves nothing.
- When the method runs in a QC batch, the test must be added to a batch before you can record.
- Recording makes you an author of the test's data, so you cannot review it.

## Purpose

Record the next replicate observation of a test, with the location of its original record.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- A test in the wrong state, one that holds a result reported by a contract laboratory, or one whose requirement a supplier result is proposed or accepted for, redirects you back to the test record with a warning (see Rules).
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Record replicate N · T-n" and breadcrumbs.
- Summary card: Test (number, name and code), Lot and sample (sample under the lot), Specification (code and version, hash under it), Acceptance, Record revision, Unit (numeric and count tests only).
- Form, numeric and count tests: **Observed value** (**Observed count** for counts), **Reported as less than this value**, **Original record**.
- Form, qualitative tests: **Observed result** (radio pair), **What was observed**, **Original record**.
- Form, calculated methods: one field per approved input (labelled with its name and unit), **Original record**. No value or less-than field.
- Every form: **Equipment used** and **Reagent and standard lots used** checkboxes before **Original record** (see Fields).
- Summary adds **Calculation** for calculated methods.
- **Cancel**, **Record observation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record observation** | Always | Analyst | Adds the observation; "Observation recorded."; returns to the test |
| **Cancel** | Always | Analyst | Returns to the test without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Observed value / Observed count | `Observation.value`, `qualifier`, `value_text` | Decimal, 20 digits, 8 decimals; unit from the specification | Yes (numeric and count tests) | "Exact value as read; at most 8 decimal places." (count: "Whole number of zero or more, exactly as read.") followed by "Never enter a nondetect as zero: enter the reporting limit and choose “Reported as less than this value”." |
| Reported as less than this value | `Observation.qualifier` ("<") | Checkbox | No (numeric and count tests) | "For a result below the reporting or detection limit (shown as <10). It is stored as recorded and never converted to zero or to the number." The value is kept as the limit with the "<" qualifier |
| Observed result | `Observation.outcome`, `value_text` | Radio: Conforms / Does not conform, or Absent / Present (the pair approved for the test) | Yes (qualitative tests) | Help text shows the acceptance, e.g. "Acceptance: Absent in 25 g (expected: Absent)." |
| What was observed | `Observation.observed_text` | Text, max 200 | Yes (qualitative tests) | "Describe the observation itself, e.g. what was seen or how the test reacted; the outcome is recorded separately." |
| Inputs (calculated methods) | `Observation.inputs` | Decimal per input, at most 8 decimal places; label "name (unit)" | Yes (calculated methods) | "Exact value as read, in <unit>; at most 8 decimal places." Stored as entered, in input order |
| Calculated value | `Observation.value`, `value_text` | Decimal in the calculation unit | — | Set by the server from the inputs; not entered |
| Equipment used | `Observation.eligibility` (equipment) | Checkboxes from the bench: identifier, name and status | When the method requires equipment | "This method requires at least one instrument." or "Select every instrument used, if any." Hidden when the bench offers none and the method does not require one |
| Reagent and standard lots used | `Observation.eligibility` (reagents) | Checkboxes from the bench | When the method requires a lot | As for equipment, for reagent or standard lots |
| Calculation (summary) | `AnalyticalTest.requirement` method calculation | Text | — | Formula, result unit, decimals and method revision; shown for calculated methods |
| Original record | `Observation.raw_reference` | Text, max 200 | Yes | "Notebook page, instrument file or worksheet holding the original observation." |
| Test (summary) | `AnalyticalTest.id` (shown as T-n), `AnalyticalTest.requirement` name, `AnalyticalTest.test_code` | Text | — | "T-n · name (code)": the test being recorded |
| Lot and sample (summary) | `Lot.number`, `Sample.reference` | Text | — | "lot / sample" the test belongs to; for a stability test the row reads "Lot and stability pull" with "lot / stability pull <pull>" |
| Specification (summary) | `AnalyticalTest.requirement` (source, acceptance) | Text | — | Frozen approved requirement: "source · acceptance", e.g. "95.0 to 105.0 unit", "at least L unit", "more than L and at most U unit", "less than U unit" or, for a qualitative test, "Absent in 25 g (expected: Absent)" |
| Record revision (summary) | `AnalyticalTest.revision` | Integer | — | Test revision when the page opened; recording raises it by 1 |
| Unit (summary) | `AnalyticalTest.requirement` unit | Text | — | Unit the value is stored in (`Observation.unit`); not editable; not shown for qualitative tests, which have no unit |
| Replicate number (title) | `Observation.replicate` | Integer | — | "Record replicate N": current observations + 1, assigned by the server |

## Rules and hidden logic

- **Wrong state** (opening or submitting): redirects to the test record with a warning: "This test is not accepting observations." (test not Open, or lot not in quarantine, or for a stability test its pull not open for testing); "A supplier's result is proposed or accepted in place of this test (SRA-1). Withdraw it on the lot record before testing the requirement in the laboratory." (a supplier result stands in place of the test); "This test holds a result reported by a contract laboratory. It takes no observation made in this laboratory; correct the contract laboratory result instead."; "Add this test to a QC batch before recording results."; "All replicates are recorded. Correct a value instead."
- **Preconditions**: test Open ("This test is not accepting observations."); lot in quarantine ("Lot ... is no longer in quarantine."), or for a test of a stability pull the pull pulled and not yet accepted and its study active ("Record the pull before testing it.", "This pull is accepted; its tests take no more work.", "Study … is closed; its pulls take no more testing."; once a study is closed its pulls' tests take no more work); no supplier result proposed or accepted in place of the test (the message above; testing and acceptance exclude each other, and the record is withdrawn from its acceptance record first); no result reported by a contract laboratory on the test (the message above; a test is tested here or reported by a contract laboratory, never both); a QC batch assigned when the method needs one ("Assign this test to a QC batch before recording results."); fewer current values than replicates ("All replicates are recorded. Correct a value instead.").
- **Bench checks**: without a configured bench the page redirects to the test record with "No bench check is configured; results are held." and the server refuses the entry with the same message. After the record locks and validations the bench checks your current qualification for the test's method and every instrument and lot you selected. A refusal shows each reason, as "Refused: <subject>: <reason>", on the checkbox list of the refused instrument or lot, or above the form for your qualification (for example "Refused: analyst.test: No approved, current qualification for “<method>”."). Nothing is saved; the refused attempt is audited by the bench. The accepted evidence (user, activity, qualification, equipment and lots with their use records) is frozen on the observation and in its audit event.
- **Required resources**: a method that requires equipment refuses an entry with none selected ("Select the instrument used; this method requires one."); the same applies to reagent or standard lots. The server repeats this check ("Method <code> requires at least one instrument; select the equipment used.").
- **Calculated results**: when the method has a calculation, the form asks for each input instead of the value. The server calculates the value with the approved formula and rounds it half-up to the approved decimals. A missing, non-finite or over-precise input (more than 8 decimal places or 20 digits), a division by zero ("The value cannot be calculated: The formula divides by zero for these values.") or a result too large to store refuses the entry; nothing is saved. A calculated result cannot be reported as less than a value. The inputs as entered and the calculation applied (method, revision, formula, unit, decimals) are stored on the observation and in its audit event.
- **Form by result type** (from the frozen requirement): numeric and count tests show the value and the less-than checkbox; qualitative tests show the outcome radio pair and **What was observed**, with no numeric field.
- **Reading validation** (form errors, status 422, nothing saved): "A count must be a whole number of zero or more."; "A less-than result needs a value greater than zero."; "A qualitative result cannot be reported as less than a value."; "Choose the observed result: Absent or Present." (or Conforms or Does not conform); "Describe what was observed; the outcome alone is not a complete record."
- **As recorded**: the result text is stored exactly as entered ("99.80", "<10") or as the outcome label ("Absent"). A less-than result is never treated as zero or as its number.
- **Blank record**: "Record where the original observation is kept." when the original record is only spaces.
- **Effect**: in one transaction the observation is stored with the next replicate number, the test revision and the revision of the lot (or, for a stability test, of the pull) rise by 1, and `observation.recorded` is audited with your identity, the reading as recorded (value text, qualifier, outcome, what was observed, inputs and calculation) and the bench evidence. The server sets time and recorder.
- **Validation errors** show on the form with status 422; nothing is saved.
- Out-of-limit values are recorded as entered and marked "No" under Within limits ("Cannot be shown" for a less-than result that cannot be shown to conform; "No" under As expected for a deviating qualitative outcome).

## Related pages

- Test record (return target).
- Record contract laboratory result (for a result an outside laboratory reported).
- [Testing: tests](/testing/)
