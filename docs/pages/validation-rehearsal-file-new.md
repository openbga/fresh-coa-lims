---
title: Attach evidence
urls: validation:rehearsal_file_new, validation:rehearsal_file
views: validation.views.rehearsal_file_new, validation.views.rehearsal_file
templates: analytical/raw_file_form.html
models: validation.RehearsalFile, validation.Rehearsal, core.AuditEvent
reviewed: 2026-11-17
---

## Purpose

Attach a file of evidence to a rehearsal, such as a restore check report, a backup manifest or a reconciliation record. The file is kept unchanged with its SHA-256 checksum. This file also covers the download endpoint opened from **Evidence files** on the rehearsal record.

## Who can use it

- Sign-in required. Attaching: only the person who recorded the rehearsal, and only while it awaits acceptance. The role must be Quality or Admin; others receive 403.
- Any other holder of those roles is redirected to the rehearsal with a warning: "Only the person who recorded the rehearsal attaches its evidence." A rehearsal that is accepted or withdrawn redirects with "Evidence is attached only while the rehearsal awaits acceptance."
- Downloading: Analyst, Reviewer, Quality, Admin or Auditor; others receive 403, also for a file that does not exist.

## Layout

- Heading "Attach evidence · RH-n" and breadcrumbs.
- Summary: Rehearsal, Record revision, Size limit.
- Form: **File**, **What the file is**; **Cancel**, **Attach file**.
- The download endpoint has no page of its own.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Attach file** | Always on this page | Recorder | Stores the file; "Evidence attached."; returns to the rehearsal |
| **Cancel** | Always | Recorder | Returns to the rehearsal |
| **Download** (file name on the rehearsal) | A file is attached | Analyst, Reviewer, Quality, Admin, Auditor | Sends the stored bytes as a file download |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| File | `RehearsalFile.content`, `.size`, `.sha256`, `.filename`, `.content_type` | Any file, up to the size limit shown (10 MiB unless the deployment sets another) | Yes | Kept exactly as received; never opened by the system. The declared type is informational |
| What the file is | `RehearsalFile.description` | Text, max 200 | Yes | Help: "For example: restore check report, backup manifest, or the reconciliation record." |
| Record revision (summary) | `Rehearsal.revision` | Integer | — | Raised by 1 when a file is attached |

## Rules and hidden logic

- **Refusals** (form error, status 422, nothing stored): "The file is empty."; "The file is larger than the limit of ..."; "A rehearsal holds at most 20 files."; "This file content is already attached to this rehearsal." (same checksum); "This deployment has reached its storage limit for files. The file was not stored." (only where the deployment sets a total ceiling, counted over raw-data and rehearsal files together); "Describe what the file is."
- **File name**: only the base name is kept, control characters removed; an empty or over-long name is refused.
- **Far oversized upload**: an upload that declares much more than the size limit is refused before it is received with the "Upload too large" page (status 413); role and record checks do not run for such a request.
- **Oversized upload**: a file over the limit that is stopped while arriving returns you to this page with "The file is larger than the limit of ... Nothing was stored." and the description to enter again. The browser also refuses a larger file when chosen (needs JavaScript); the server applies the limit in every case.
- **Effect**: in one transaction the file is stored, the rehearsal revision rises by 1 (a signing page opened earlier becomes stale) and `rehearsal.file_attached` is audited with the file number, name, size, SHA-256 and description.
- **Immutability**: the database refuses any update or delete of a stored file. There is no delete action.
- **Download**: the role check comes before the lookup. The stored size and checksum are recomputed first; on a mismatch the download is refused and you return to the rehearsal with the error. Otherwise the bytes are sent as an attachment of type `application/octet-stream`, marked `nosniff`, no-store and private. The file name in the header keeps only ASCII letters, digits, dot, underscore and hyphen. Downloads are not written to the audit trail.
- Not enforced by this page: scanning for malware, or what the file contains.

## Related pages

- Rehearsal record (return target and the file list)
- Accept rehearsal (needs at least one file)
