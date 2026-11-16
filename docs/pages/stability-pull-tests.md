---
title: Assign pull tests
urls: stability:pull_tests
views: stability.views.pull_tests
templates: stability/pull_tests.html
models: stability.Pull, stability.Protocol, analytical.AnalyticalTest, catalog.Specification, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

Create the tests of a pulled stability pull in the system, one for each test of its time point, freezing the acceptance criteria of the protocol on them. The tests are then recorded, reviewed and signed like release tests, without changing the record of the study's lot.

## Who can use it

- Sign-in required. Role: Analyst only; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Studies, study, pull, Assign tests) and the title "Assign tests · <timepoint>". The introduction says that assigning creates one test for each test of this time point, that each freezes the acceptance criterion and method version shown, and that the record of the study's lot is not changed.
- **Acceptance criteria of the protocol**: a line naming the specification (a link), the protocol and the version source, then a table with Test (name and code), Acceptance criterion, Method (code and revision), Replicates and Assigned ("To be assigned" or "Already assigned").
- The form (Reason) with **Cancel** and **Assign tests**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign tests** | Always | Analyst; others receive 403 | Creates the missing tests, shows "Assigned N test(s) to the pull." and returns to the pull record; refusals appear as an error summary and your entry is kept (status 422) |
| **Cancel** | Always | Any | Returns to the pull record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Test, Acceptance criterion, Method, Replicates, Assigned | — | Display | — | The criteria in force now for each test of the time point; assigned tests freeze them |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with each `test.assigned` event |

## Rules and hidden logic

- The page opens only for a pull that is Pulled in an Active study, has no linked sample or external evidence, and whose protocol names a specification. Otherwise you return to the pull record with a warning, for example "Record the pull before testing it.", "Study <id> is closed; its pulls take no more testing.", or "The protocol names no specification, so its acceptance criteria are not in the system. Link a sample or external evidence instead; a new protocol version can name one."
- A pull linked to a sample or external evidence is refused: "A pull is tested in the system or linked to other evidence, never both."
- The specification's version in force now supplies the criteria. If it has no approved version in force, does not state a test of the time point, or a method has no approved version in force, the page returns to the pull record with "Tests cannot be assigned: …". All or nothing: no test is assigned unless every test of the time point can be.
- If every test is already assigned: "Every test of this time point is already assigned." Only missing tests are created, so a repeat adds nothing for tests that exist.
- Each test freezes the criterion, method version, specification version and protocol version; a later version of the specification applies only to later pulls. A test of a line the specification marks as not required is still tested: the time point decides what is tested.
- Each created test is a normal test of the pull (no lot, no sample). Event `test.assigned` for each; the pull's revision rises by 1, so an acceptance page opened earlier goes stale. The pull and study are locked while assigning.

## Related pages

- Pull record (return target)
- Specification record (linked from the criteria)
- Test record (each assigned test)
- Link pull evidence (the alternative; never both)
