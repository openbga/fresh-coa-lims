---
title: Attach raw data
urls: analytical:raw_file_new, analytical:raw_file_download
views: analytical.rawdata.raw_file_new, analytical.rawdata.raw_file_download
templates: analytical/raw_file_form.html, analytical/_summary.html, analytical/_raw_files.html, 413.html
models: analytical.RawDataFile, analytical.AnalyticalTest, quality.Lot, core.AuditEvent
reviewed: 2026-11-13
---

## Purpose

Attach a file of raw data (an instrument export, a chromatogram, a photographed notebook page) to a test, so a reviewer can check the original. The file is kept unchanged with its SHA-256 checksum. This file also covers the download endpoint opened from the **Raw data files** list on the test record.

## Who can use it

- Sign-in required. Attaching is for **analysts** only; others receive 403, including admin without the analyst role.
- Downloading requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; a user without one of these roles receives 403, also for a file that does not exist.
- A test that is not Open, or whose lot is not in quarantine, redirects you back to the test record with a warning.
- The person who attaches a file counts as an author of the test's data. They cannot review that test or sign the lot's QC disposition.

## Layout

- Heading "Attach raw data · T-n" and breadcrumbs.
- Summary card: Test, Lot and sample, Record revision, Size limit.
- Form: **File**, **What the file is**.
- **Cancel**, **Attach file**.
- A refused oversized upload shows the page "Upload too large" instead, with the size limit and the link **Return to the form**.
- The download endpoint has no page of its own.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Attach file** | Always | Analyst | Stores the file; "Raw data attached."; returns to the test record. Does nothing while the chosen file is above the size limit |
| **Cancel** | Always | Analyst | Returns to the test record without saving |
| **Return to the form** | On the "Upload too large" page | Anyone who sees it | Opens this page again with an empty form |
| **Download** (test record list) | A file is attached | Analyst, reviewer, quality, admin, auditor | Sends the stored bytes as a file download |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| File | `RawDataFile.content`, `size`, `sha256`, `filename`, `content_type` | Any file, up to the size limit shown in the summary (10 MiB unless the deployment sets another) | Yes | Kept exactly as received. The checksum is computed over the stored bytes. The type the browser declares is kept for information only. A larger file is refused as soon as it is chosen |
| What the file is | `RawDataFile.description` | Text, max 200 | Yes | Says what the file holds. A wrong file stays; a later file's description should say so |
| Record revision (summary) | `AnalyticalTest.revision` | Integer | — | Test revision when the page opened; attaching raises it by 1 |

## Rules and hidden logic

- **Never opened**: the system does not read, display or run the file content. It is only stored, checksummed and returned.
- **File name**: only the base name is kept (folders in `/` or `\` form are dropped) and control characters are removed. A name that is empty afterwards, or longer than 200 characters, is refused.
- **Refusals** (form error with status 422, nothing stored): "The file is empty."; "The file is larger than the limit of ..."; "A test holds at most 20 raw-data files."; "This file content is already attached to this test." (same checksum on the same test); "This deployment has reached its storage limit for raw-data files. The file was not stored." (only where the deployment sets a ceiling for all files together); "Describe what the file is."; "This test is not accepting raw data."; "Lot ... is no longer in quarantine."
- **Size limit in the browser**: choosing a file above the limit shows "The file is larger than the limit of ... and was not sent. Choose a smaller file." under **File**. **Attach file** then sends nothing and returns you to the **File** field until you choose a smaller file. This check needs JavaScript; the server applies the limit in every case.
- **Size limit on the server**: an upload that declares more than the size limit plus 1 MiB is refused before it is received, with status 413 and the page "Upload too large": "The upload was larger than this system accepts. It was refused before it was received, and nothing was stored." The role and test checks do not run for such a request, so the page appears whoever sent it. A file that is over the limit by less than that is stopped while it is being received: you return to this page with "The file is larger than the limit of ... Nothing was stored." and enter the description again.
- **Effect**: in one transaction the file is stored, the test revision and lot revision rise by 1 (so a disposition opened earlier becomes stale) and `rawdata.attached` is audited with the file number, name, size, SHA-256 and description.
- **Immutability**: the database refuses any update or delete of a stored file. There is no delete action.
- **Download**: the checksum and size of the stored bytes are recomputed first. On a mismatch the download is refused with "The stored file failed its integrity check." and you return to the test record. Otherwise the bytes are sent as an attachment of type `application/octet-stream`, marked `nosniff`, no-store and private, whatever type was declared on upload. The file name in the header keeps only letters, digits, dot, underscore and hyphen.
- Not enforced by this page: scanning for malware, or any restriction on who may share a downloaded copy. Downloads are not written to the audit trail.

## Related pages

- Test record (return target, and the list of attached files).
