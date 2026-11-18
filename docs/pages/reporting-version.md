---
title: Certificate version
urls: reporting:version, reporting:pdf, reporting:data
views: reporting.views.version_detail, reporting.views.version_pdf, reporting.views.version_data
templates: reporting/version.html, reporting/_certificate.html, reporting/pdf/certificate.html
models: reporting.ReportVersion, reporting.Report, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-18
summary: One issued version of a certificate, shown exactly as stored, with its signature, checksums, the stored PDF and its certificate data to download, also after the certificate is withdrawn.
---

## Common tasks
### Download or open the PDF
1. Select [[Download PDF]] to save it, or [[Open PDF]] to view it in a new tab.
### Download the certificate data for another system
1. Select [[Download data]] to save the certificate's content as a JSON file.
2. Compare its SHA-256 with [[Certificate data SHA-256]] under [[Issued record]]. The PDF carries the same file as an attachment.
### Check who signed this version
1. Under [[Issued record]], read [[Signature]] for the signer, the meaning and the time.
### Go to the version it amends or that replaced it
1. Select the version under [[Amends]] or [[Superseded by]].
## Good to know
- The page and the PDF come from what was stored at issue; a scope certificate reports only its scope. Later changes to other records never alter them.
- Each download or opening of the PDF, and each download of the data, is recorded in the certificate's history.
- A file that fails its integrity check is not sent; you return here with the error. A version issued before certificate data existed has none.
- A superseded version stays available. Only the newest version is current.
- A withdrawn certificate's versions show Withdrawn and stay downloadable exactly as issued, as evidence.

## Purpose

One issued version of a certificate, shown exactly as stored, with its signature, checksums, the PDF and the certificate data to download. This file also covers the PDF and data endpoints opened from its buttons.

## Who can use it

- Sign-in required. Viewing and downloading require **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403. Administrators can open and download every version; signing and issuing stay with the quality role.
- An unknown version number returns 404 to users with a viewing role. Users without one receive 403 for the PDF and the data whether or not the version exists.

## Layout

- **Withdrawn** (red notice, when the certificate is withdrawn): "Certificate … was withdrawn on … by …: this version is no longer valid. It stays on record, and its PDF stays downloadable exactly as issued, as evidence."
- **Header**: breadcrumbs, "Report number version N", status "Withdrawn" (any version of a withdrawn certificate), "Current version" or "Superseded" (a superseded version also shows the fact **Superseded by** as a blue **Superseded** label with the link to the newer version under it), issue time, **Open PDF**, **Download data** (only for a version issued with certificate data) and then **Download PDF** (the primary button, last).
- **Issued record**: Signature, Size, PDF format, Certificate data, links to the version it amends or is superseded by, PDF SHA-256, Certificate data SHA-256 (when there is data), Evidence SHA-256, and a note that content comes from the frozen snapshot.
- **Certificate**: the stored certificate content, including the signature table. A certificate for one scope shows "Certificate for: Scope X" under the lot facts, only that scope's specification and methods, results with Limits and Conformity, and "How conformity is judged"; a general certificate of a lot under several specifications has the section "Conformity with each specification". Each method is listed once.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Download PDF** | Always | Any viewer | Saves the stored PDF as `<number>-v<N>.pdf` (name sanitised) |
| **Open PDF** | Always | Any viewer | Opens the same PDF inline in a new tab |
| **Download data** | The version was issued with certificate data | Any viewer | Saves the stored certificate data as `<number>-v<N>.json` (`application/json`, UTF-8), the same bytes the PDF carries as its attached file `certificate-data.json` |
| Amends / Superseded by | The version has a neighbour | Any viewer | Opens that version |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signature | `ElectronicSignature.signer_name`, `meaning`, `signed_at`, `revision` | Text, UTC time | — | Who signed issue or amendment, and the bound certificate record revision |
| PDF SHA-256 | `ReportVersion.pdf_sha256` | Hex | — | Checksum of the stored PDF |
| Size | `ReportVersion.pdf_size` | Bytes | — | Stored PDF length |
| PDF format | `ReportVersion.pdf_format` | Text | — | What the PDF declares itself to be: "PDF/A-3a, PDF/UA-1" (the archival format, tagged for assistive technology); "Not declared" for a version issued before |
| Certificate data | `ReportVersion.data` | JSON, bytes | — | The certificate's content in a machine-readable form (schema `oq.certificate-data/1`), attached to the PDF and downloadable beside it; "None" for a version issued before |
| Certificate data SHA-256 | `ReportVersion.data_sha256` | Hex | — | Checksum of the certificate data, stored when the version was signed |
| Evidence SHA-256 | `ReportVersion.evidence_hash` | Hex | — | Fingerprint of the evidence signed |
| Amends | `ReportVersion.supersedes` | Version | — | Earlier version replaced |
| Superseded by | `ReportVersion.superseded_by` | Version | — | Later amendment |

## Rules and hidden logic

- **Scope**: the content of a certificate for one scope follows the scope stored with the certificate (`Report.scope`); it never names the lot's other scopes, additional rule sets or decided requirements. Signature rows are limited to the results shown.
- **Stored, not regenerated**: both the page and the PDF come from stored data and bytes; later changes to other records cannot alter them.
- **Product name**: newly issued PDFs display OpenBGA QM LIMS. PDFs issued before the rebrand keep their original name and bytes.
- **PDF endpoint**: GET only (other methods receive 405). Before serving, the bytes are checked against the stored checksum and size; on mismatch you are returned here with "The stored certificate failed its integrity check." and nothing is sent.
- **Data endpoint**: GET only. The bytes are checked against the stored checksum; on mismatch you are returned here with "The stored certificate data failed its integrity check." and nothing is sent. For a version issued before certificate data existed you are returned here with "This version was issued before certificate data was produced. Its PDF is the issued record." The data states what the printed certificate states, and for a certificate for one scope only that scope.
- **Failed or unauthorised**: a user without a viewing role receives 403 for the PDF; the PDF accepts `?inline=1` to open in the browser, otherwise it downloads. The file name keeps only letters, digits, dot, underscore and hyphen.
- **Audit**: each successful download writes `report.downloaded` (PDF) or `report.data_downloaded` (data) with the actor, version and checksum. Responses are marked no-store and private.
- **Immutable**: versions, their certificate data and the declared format cannot be edited or deleted; an amendment is a new version. A withdrawal changes no version: the page and the PDF stay as issued and the download is still recorded.
- Not enforced by this page: any restriction on who may share a downloaded copy.

## Related pages

- Certificate record, [Certificates of analysis](/reports/).
