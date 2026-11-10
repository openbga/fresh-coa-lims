---
title: Add to QC batch
urls: analytical:test_batch
views: analytical.views.test_batch
templates: analytical/form.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.QCBatch, quality.Lot
reviewed: 2026-11-10
---

## Purpose

Add a test whose method runs in a QC batch to an open batch of the same method revision.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.

## Layout

- Heading "Add T-n to a QC batch".
- Summary card: test facts and Method ("code revision N").
- Form: **Open QC batch**, **Reason**, **Cancel**, **Add to batch**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add to batch** | Always | Analyst | Links the test; "Test added to the QC batch."; returns to the test |
| **Cancel** | Always | Analyst | Returns to the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Open QC batch | `AnalyticalTest.batch` | Choice | Yes | Only Open batches with the test's method code and identical method revision, newest first |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Reason recorded with `test.batched` |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the test record with the warning "This test cannot be added to a QC batch." (test not Open, method needs no batch, or a batch already assigned).
- **Preconditions**: batch Open and test Open ("Only open tests can join an open batch."); test has no batch and no observations ("This test already has a batch or recorded observations."); batch has no submitted results ("This batch already has submitted results; start a new batch."); the method requires a batch and matches ("The test's method revision does not match this batch.").
- **Effect**: test and batch revisions and the lot revision rise by 1; `test.batched` is audited.
- If the list is empty, create a batch first.

## Related pages

- Test record (return target).
- [Testing: QC batches](/testing/batches/)
