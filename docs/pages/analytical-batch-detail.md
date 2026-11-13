---
title: QC batch record
urls: analytical:batch_detail
views: analytical.views.batch_detail
templates: analytical/batch_detail.html, analytical/_resources.html, analytical/_history.html, analytical/_qc_status.html, analytical/_test_status.html
models: analytical.QCBatch, analytical.QCResult, analytical.AnalyticalTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-12
---

## Purpose

One QC batch: its method's QC checks and results, the tests run in it, and rejection when QC has failed.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Record** and **Correct** QC: analysts. **Reject batch**: reviewers.
- **Admin** alone is a read role: no Record, Correct or Reject batch controls. Admin together with a lab role gets that role's controls and its independence rules.

## Layout

- **Header**: batch number; status (QC passed, QC failed, QC incomplete or Rejected), "code revision N", "Created by", Revision; **Reject batch**.
- **Note** when the method requires resources: "Method CODE requires each QC entry to record the equipment used and the reagent or standard lots used." (or only one of them).
- **Alert** when open and failed: "Tests in this batch cannot be submitted or reviewed. Correct a transcription error with a reason, or have a reviewer reject the batch: ..."
- **QC checks**: Check (name and code), Acceptance ("≥ lower and ≤ upper unit"), Result, Status (Not recorded, Passes, Fails), Equipment and lots, Original record with recorder and time, and **Record** or **Correct**. Below it **Corrections**: code, struck-through old value → new value, reason, and the equipment and lots of the correction when recorded.
- Note "QC entries are frozen once a test in this batch is submitted."
- **Tests in this batch**: Test, Lot, Sample, Code, Status; empty "No tests in this batch".
- **Electronic signatures** and **History**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record** (row) | No current result and the batch is not frozen | Analyst | Opens Record QC result |
| **Correct** (row) | Has a result and not frozen | Analyst | Opens Correct QC result |
| **Reject batch** | Batch Open and QC failed | Reviewer | Opens the signing page |
| Test links | Rows present | Any viewer | Open the test |

Frozen means the batch is not Open or any test in it has left Open.

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Result | `QCResult.value_text`, `unit` | Decimal with unit | — | Current value for the check |
| Equipment and lots | `QCResult.eligibility` | Identifiers | — | Equipment and reagent or standard lots frozen with the QC result; "Not recorded" for results written before bench checks or with none selected |
| Original record | `QCResult.raw_reference` | Text | — | Where the original observation is kept |
| Status | `QCBatch.qc_status` | Text | — | Against the check's inclusive limits |
| Revision | `QCBatch.revision` | Integer | — | Rises on every batch change |

## Rules and hidden logic

- **Batch QC status**: Failed if any current check fails; Incomplete if any check is unrecorded; else Passed. Only Passed lets tests be submitted or reviewed.
- **Bench checks**: recording and correcting QC check the analyst's qualification for the batch method and the selected equipment and lots (see Record QC result).
- **Corrections** never overwrite; the original stays in the corrections list.
- **Rejection** invalidates the batch's tests with linked reruns; see Reject QC batch.
- Method and QC limits come from the approved method revision frozen at creation. Not enforced by this page: whether the limits are scientifically right.

## Related pages

- [QC batches](/testing/batches/)
- Record QC result, Correct QC result, Reject QC batch, Test record.
