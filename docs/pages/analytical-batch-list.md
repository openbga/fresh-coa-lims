---
title: Testing: QC batches
urls: analytical:batch_list
views: analytical.views.batch_list
templates: analytical/batch_list.html, analytical/_tabs.html, analytical/_pager.html, analytical/_qc_status.html
models: analytical.QCBatch
reviewed: 2026-11-10
---

## Purpose

List QC batches: analytical runs for one method revision with their QC checks. Tests are submitted only when batch QC passes.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **New QC batch**: shown to users holding the analyst role only.

## Layout

- **Intro**, section tabs (**Tests**, **QC batches**, **Investigations**), and the **New QC batch** button.
- **Filter bar**: **Find**, **Status**, **Apply**, **Clear filters** when filtered.
- **Table** (caption "QC batches, newest first"): Batch, QC status, Method, Created, Created by. Footer count and pager.
- **Empty states**: "No QC batches yet" (with **New QC batch** for analysts) and "No batches match these filters".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New QC batch** | User holds analyst | Analyst | Opens the New QC batch form |
| **Apply** / **Clear filters** | Always / filtered | Any viewer | Applies or removes filters |
| Batch number link | Each row | Any viewer | Opens the batch |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find | — | Text | No | Matches batch number or method code (case-insensitive) |
| Status | `QCBatch.state` | All batches, Open, Rejected | No | Filter by batch state |
| QC status | `QCBatch.state` plus current QC results | QC passed, QC failed, QC incomplete, Rejected | — | Rejected batches show "Rejected"; otherwise derived from the method's QC checks |
| Method | `QCBatch.method_code`, `method` | "code rev. N" | — | Method revision frozen into the batch |
| Created / Created by | `QCBatch.created_at`, `created_by` | Date and time, user | — | Who created the batch and when |

## Rules and hidden logic

- **QC status**: Failed if any current check is outside its limits; Incomplete if any check has no current result (and none failed); otherwise Passed.
- **Order and paging**: newest first; 30 per page.
- **Unknown status value** is treated as All batches.

## Related pages

- [Testing: tests](/testing/)
- [Investigations](/testing/investigations/)
- New QC batch, QC batch record.
