---
title: New QC batch
urls: analytical:batch_new
views: analytical.views.batch_new
templates: analytical/form.html
models: analytical.QCBatch
reviewed: 2026-11-11
---

## Purpose

Create a QC batch for one approved batch-method revision.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "New QC batch"; form: **Batch number**, **Method revision**, **Reason**, **Cancel**, **Create batch**.
- When no method is available the form shows "No approved batch method is available; batches are held."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create batch** | Always | Analyst | Creates the batch; "QC batch NUMBER created."; opens the batch |
| **Cancel** | Always | Analyst | Returns to the QC batches list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Batch number | `QCBatch.number` | Text, max 80, unique | Yes | Your batch identifier, e.g. BATCH-TEST-001 |
| Method revision | `QCBatch.method_code`, `method` | Choice "code revision N" | Yes | Approved batch methods from the configured provider; frozen with a hash |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with `batch.created` |

## Rules and hidden logic

- **Methods** come from the configured requirement provider; invalid methods and methods that do not require a batch are omitted. Not enforced by this page: approval of the method itself.
- **Validations**: "No approved batch method with this code."; "This batch number already exists." (also when a double submission or another analyst creates the same number at the same moment; only one batch is created); "A reason is required."
- **Effect**: the method revision and its QC checks are frozen into the batch; the batch starts Open at revision 1. Errors return status 422 and save nothing.

## Related pages

- [Testing: QC batches](/testing/batches/)
- QC batch record.
