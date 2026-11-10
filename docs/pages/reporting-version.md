---
title: Certificate version
urls: reporting:version, reporting:pdf
views: reporting.views.version_detail, reporting.views.version_pdf
templates: reporting/version.html, reporting/_certificate.html
models: reporting.ReportVersion, reporting.Report, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

One issued version of a certificate, shown exactly as stored, with its signature, checksums and the PDF to download. This file also covers the PDF endpoint opened from its buttons.

## Who can use it

- Sign-in required. Viewing and downloading require **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- An unknown version number returns 404.

## Layout

- **Header**: breadcrumbs, "Report number version N", status "Current version" or "Superseded", issue time, **Download PDF** and **Open PDF**.
- **Issued record**: Signature, Size, links to the version it amends or is superseded by, PDF SHA-256, Evidence SHA-256, and a note that content comes from the frozen snapshot.
- **Certificate**: the stored certificate content, including the signature table.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Download PDF** | Always | Any viewer | Saves the stored PDF as `<number>-v<N>.pdf` (name sanitised) |
| **Open PDF** | Always | Any viewer | Opens the same PDF inline in a new tab |
| Amends / Superseded by | The version has a neighbour | Any viewer | Opens that version |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signature | `ElectronicSignature.signer_name`, `meaning`, `signed_at`, `revision` | Text, UTC time | — | Who signed issue or amendment, and the bound certificate record revision |
| PDF SHA-256 | `ReportVersion.pdf_sha256` | Hex | — | Checksum of the stored PDF |
| Size | `ReportVersion.pdf_size` | Bytes | — | Stored PDF length |
| Evidence SHA-256 | `ReportVersion.evidence_hash` | Hex | — | Fingerprint of the evidence signed |
| Amends | `ReportVersion.supersedes` | Version | — | Earlier version replaced |
| Superseded by | `ReportVersion.superseded_by` | Version | — | Later amendment |

## Rules and hidden logic

- **Stored, not regenerated**: both the page and the PDF come from stored data and bytes; later changes to other records cannot alter them.
- **PDF endpoint**: GET only (other methods receive 405). Before serving, the bytes are checked against the stored checksum and size; on mismatch you are returned here with "The stored certificate failed its integrity check." and nothing is sent.
- **Failed or unauthorised**: a user without a viewing role receives 403 for the PDF; the PDF accepts `?inline=1` to open in the browser, otherwise it downloads. The file name keeps only letters, digits, dot, underscore and hyphen.
- **Audit**: each successful download writes `report.downloaded` with the actor, version and checksum. Responses are marked no-store and private.
- **Immutable**: versions cannot be edited or deleted; an amendment is a new version.
- Not enforced by this page: any restriction on who may share a downloaded copy.

## Related pages

- Certificate record, [Certificates of analysis](/reports/).
