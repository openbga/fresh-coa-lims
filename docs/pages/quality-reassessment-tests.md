---
title: Assign reassessment tests
urls: quality:reassessment_tests
views: quality.reassessment_views.reassessment_tests
templates: quality/reassessment_tests.html
models: quality.Reassessment, analytical.AnalyticalTest, core.AuditEvent
reviewed: 2026-11-17
summary: Assign the tests of an open reassessment, one for each required test of the specifications in force for the lot. Each test freezes the acceptance criterion and method version shown. Analysts only.
---

## Common tasks

### Assign the reassessment's tests

1. Check [[Acceptance criteria in force]]. [[To be assigned]] marks each test that will be created.
2. Enter a [[Reason]] and select [[Assign tests]]. You return to the reassessment record.

### Assign after the criteria changed

1. If the page says the criteria changed since it was opened, review the criteria now shown.
2. Select [[Assign tests]] again to assign the tests against them.

## Good to know

- The tests belong to the reassessment. Assigning them does not change the record of the lot.
- The criteria come from the specifications in force for the lot's material now, not those frozen at release. Each test keeps the criterion shown when it is assigned.
- All or nothing: if the specifications cannot state every required test, no test is assigned.
- Only missing tests are created. Tests shown as [[Already assigned]] are left as they are.
- The tests are performed on the sample taken for the reassessment. A failing result is retested on that sample, never resampled.

## Purpose

Create the tests of an open reassessment, one for each required test of the specifications in force for the lot's material, stage and scopes, freezing the acceptance criteria on them. The tests are then recorded, reviewed and signed like any other test, without changing the record of the lot.

## Who can use it

- Sign-in required. **analyst** role only; others, and an account holding only Admin, receive 403.
- The **Assign tests** button on the reassessment record is shown to analysts while the reassessment is open and tests are missing. If the tests cannot be stated, the record shows the reasons instead.
- Assigning tests is not authorship of the tests' data and does not stop anyone concluding the reassessment.

## Layout

- **Breadcrumbs**: Material lots, the lot number, the reassessment (RA-n), then "Assign tests". Title "Assign tests · RA-n".
- **Intro**: assigning creates one test for each required test of the specifications in force for the lot; each test freezes the acceptance criterion and the method version shown and is recorded, reviewed and signed like any other test, on the reassessment's sample. The tests belong to the reassessment and the lot's record is not changed.
- **Acceptance criteria in force**: a table with Test (name and code), Acceptance criterion, Method (code and revision), Replicates, Specification and Assigned ("To be assigned" or "Already assigned").
- **Form**: Reason, with **Cancel** and **Assign tests**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign tests** | Always (the page opens only when tests are missing) | Analyst | Creates the missing tests; message "Assigned N test(s) to RA-n."; returns to the reassessment record. A refusal shows an error summary and keeps your entry (status 422) |
| **Cancel** | Always | Analyst | Returns to the reassessment record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Test, Acceptance criterion, Method, Replicates, Specification, Assigned | — | Display | — | The criteria in force now for each required test; assigned tests freeze them |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with each `test.assigned` event |
| Criteria (hidden) | — | Token | Yes | Identifies the criteria the page showed (specification and method versions); a difference is refused |

## Rules and hidden logic

- **When the page opens**: only for an open reassessment with tests still to assign. Otherwise you return to the reassessment record with a message: "RA-n is concluded; its tests take no more work."; "RA-n was withdrawn; its tests take no more work."; "Tests cannot be assigned: …" with the reasons the specifications cannot state the tests; or "Every test of the reassessment is already assigned."
- **Criteria**: the required tests of the specifications in force for the lot's material, stage and scopes now. A later approved version changes what is shown here, not what the lot was released against.
- **Criteria read again on submit**: under the reassessment's lock. If they changed since the page opened, nothing is assigned and the page shows "The acceptance criteria in force changed since this page was opened. Review the criteria shown now before assigning the tests." with the criteria now in force; it can then be submitted after review.
- **All or nothing**: when a required test cannot be stated, no test is assigned.
- **Concurrent assigning**: two analysts assigning at once do not create a test twice; the second finds the first's tests and assigns only what is missing. If nothing is left: "Every test of the reassessment is already assigned."
- **Effects**: each test is a normal test of the reassessment, with no lot of its own, on the reassessment's sample. One `test.assigned` event for each test, with the reason; the reassessment's revision rises by 1, so a conclusion page opened earlier is refused as stale. The lot's revision does not change.
- Reviews, investigations and retests follow the rules of any test, except that a reassessment test is retested on its own sample, never resampled.

## Related pages

- Reassessment record (return target)
- Test record (each assigned test)
- Start reassessment; Conclude reassessment
