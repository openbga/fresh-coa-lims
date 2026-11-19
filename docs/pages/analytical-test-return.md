---
title: Return test for correction
urls: analytical:test_return
views: analytical.views.test_return
templates: analytical/form.html, analytical/_summary.html
models: analytical.AnalyticalTest, quality.Lot
reviewed: 2026-11-19
summary: A reviewer sends a conforming submitted test back to the analyst for correction. No signature is made, and the observations stay as recorded.
---

## Common tasks
### Return the test for correction
1. Explain what must be corrected in [[Reason]].
2. Select [[Return test]]. The test is open again so the analyst can correct and resubmit it.
### Keep the test as submitted
1. Select [[Cancel]] to go back to the test record without returning it.
## Good to know
- Where the method version asks for qualified reviewers, you also need an approved, current qualification to review that method to return the test.
- Out-of-specification results cannot be returned. The investigation decides whether the result is invalid.
- You cannot return a test whose data you recorded, corrected, submitted or attached, or whose batch QC you recorded.
- Returning clears the reportable result, the conformance and the submitter. The observations stay.

## Purpose

A reviewer sends a conforming submitted test back to the analyst for correction. No signature is made.

## Who can use it

- Sign-in required. **Reviewers** only; others receive 403.
- Never a user who generated the test's data (observation recorders including superseded ones, the submitter, recorders of the batch's QC).
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Return T-n for correction".
- Summary card: test facts (Specification as code and version with its hash, and Acceptance) and the Reportable result with unit, e.g. "99.8 %", "<10 CFU/g" or "Absent".
- Form: **Reason**, hidden revision, **Cancel**, **Return test**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Return test** | Always | Reviewer | Test becomes Open; "Test returned to the analyst."; returns to the test |
| **Cancel** | Always | Reviewer | Returns to the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the test is returned |
| Expected revision (hidden) | `AnalyticalTest.revision` | Integer | Yes | Revision when the page opened |

## Rules and hidden logic

- **Checked before the form opens** (on opening and on submitting, with the same rules the return uses): redirects to the test record with the first applicable warning: "Lot LOT-TEST-001 is no longer in quarantine." (for a stability test the pull's reason: it must be pulled and not yet accepted and its study active); "Only submitted tests can be returned."; "You cannot review your own test." (you recorded, corrected or submitted its data, or recorded its batch QC); "Out-of-specification results cannot be returned for correction; the investigation decides whether the result is invalid.". The return itself rechecks all of these under lock, plus the record revision.
- **Qualified reviewer**: when the test's frozen method version was approved with Reviewers qualified for the method, you need an approved qualification to review that method, in effect now (Qualified for "Reviewing results"). Otherwise the return is refused with "No approved, current qualification to review “<code>”." The qualification relied on is recorded in the `test.returned` audit event, not on the test.
- **Preconditions**: test Submitted ("Only submitted tests can be returned."); not your own ("You cannot review your own test."); conforming ("Out-of-specification results cannot be returned for correction; the investigation decides whether the result is invalid."); lot in quarantine (or, for a stability test, the pull open for testing).
- **Stale page**: "Record changed. Reload and review before continuing."
- **Effect**: mean, reportable value, reportable text, conformance and submitter are cleared; test revision and the revision of the lot (or, for a stability test, the pull) rise by 1; `test.returned` is audited with the previous values. Observations remain.
- The link on the test record shows only for submitted conforming tests.

## Related pages

- Test record (return target).
