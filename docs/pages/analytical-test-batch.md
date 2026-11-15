---
title: Add to QC batch
urls: analytical:test_batch
views: analytical.views.test_batch
templates: analytical/form.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.QCBatch, quality.Lot
reviewed: 2026-11-15
---

## Purpose

Add a test whose method runs in a QC batch to an open batch of the same method revision.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Add T-n to a QC batch".
- Summary card: test facts (including the Specification source and acceptance) and Method ("code revision N").
- Form: **Open QC batch**, **Reason**, **Cancel**, **Add to batch**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add to batch** | Always | Analyst | Links the test; "Test added to the QC batch."; returns to the test |
| **Cancel** | Always | Analyst | Returns to the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Open QC batch | `AnalyticalTest.batch` | Choice | Yes | Only Open batches with the test's method code and identical method revision that have no submitted results (no test other than Open, apart from a test superseded before it was ever submitted), newest first. Any other batch posted is refused ("Select a valid choice..."); the add rechecks under lock ("This batch already has submitted results; start a new batch.") |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Reason recorded with `test.batched` |

## Rules and hidden logic

- **Checked before the form opens** (on opening and on submitting; the add itself rechecks under lock): you are redirected to the test record with the first applicable warning: "Lot LOT-TEST-001 is no longer in quarantine."; "Only open tests can join an open batch."; "This test already has a batch or recorded observations."; "A supplier's result is proposed or accepted in place of this test (SRA-1). Withdraw it on the lot record before testing the requirement in the laboratory."; "This test cannot be added to a QC batch." (method needs no batch); "No open QC batch accepting tests uses METHOD revision N. Create one under QC batches first." (no candidate batch left after the filter below; New QC batch offers the test's revision also when a later version of the method is in force, while the test waits for a batch).
- **Preconditions**: batch Open and test Open ("Only open tests can join an open batch."); lot in quarantine ("Lot ... is no longer in quarantine."); test has no batch and no observations ("This test already has a batch or recorded observations."; a result reported by a contract laboratory counts as observations, so such a test cannot join a batch); no supplier result proposed or accepted in place of the test (the message above; withdraw that record from its acceptance record first); batch has no submitted results ("This batch already has submitted results; start a new batch."); the method requires a batch and matches ("The test's method revision does not match this batch.").
- **Effect**: test and batch revisions and the lot revision rise by 1; `test.batched` is audited.
- **Tested here from then on**: a test in a QC batch of this laboratory takes no result reported by a contract laboratory ("This test is in a QC batch of this laboratory. It is tested here; a contract laboratory's result cannot be recorded on it."). There is no action that takes a test out of a batch, so record a contract laboratory result instead of adding the test when an outside laboratory performs it.
- If the list is empty, create a batch first.

## Related pages

- Test record (return target).
- [Testing: QC batches](/testing/batches/)
