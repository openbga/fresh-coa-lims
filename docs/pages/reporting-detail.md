---
title: Certificate record
urls: reporting:detail
views: reporting.views.report_detail
templates: reporting/report_detail.html, reporting/_certificate.html
models: reporting.Report, reporting.ReportVersion, quality.Lot, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

One certificate of analysis series: its status, every issued version with who signed it, the current certificate as issued, and its history.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**.
- **Amend certificate** and **Review and issue**: quality only (an administrator without the quality role sees neither; the amendment pages refuse them).
- The **History** panel is shown only to **quality**, **auditor** and **admin** users.

## Layout

- **Header**: breadcrumbs, certificate number, status (Not issued, Issued, Amended), "Current: version N", and actions.
- **Record**: Certificate, Lot (link, with material), Issued to ("General certificate (no named recipient)" when blank), Opened, and the current PDF SHA-256.
- **Versions** (once issued): Version, Kind, Status, Issued, Signed by, Reason, Files.
- **Certificate**: the current version as issued, from its stored snapshot (same content as Review certificate).
- **History** (quality, auditor and admin only): audit events for this record, oldest first, or "No history yet."
- A record with no version says "No version has been issued. A draft record holds no evidence."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Download PDF** (header) | A version exists | Any viewer | Downloads the current version |
| **Amend certificate** | A version exists | Quality | Opens the amendment review page |
| **Review and issue** | No version yet | Quality | Opens the review page for the lot |
| Version link | Always, per version | Any viewer | Opens that version |
| **Download PDF** (table) | Always, per version | Any viewer | Downloads that version |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Certificate | `Report.number` | Text | — | `CoA-<lot number>-<sequence>` |
| Lot | `Report.lot` | Lot | — | Links to the lot record |
| Issued to | `Report.recipient` | Text | — | Recipient or general certificate |
| Opened | `Report.created_at`, `created_by` | Date and time, user | — | When and by whom the record was opened |
| Current PDF SHA-256 | `Report.current_pdf_sha256` | Hex | — | Checksum of the latest issued PDF |
| Kind | `ReportVersion.kind` | Issue, Amendment | — | First issue or later amendment |
| Status | `ReportVersion.number`, `Report.version_count` | Current, Superseded | — | Only the highest version is current |
| Issued | `ReportVersion.issued_at` | UTC date and time | — | Server signing time |
| Signed by | `ElectronicSignature.signer_name`, `meaning` | Text | — | Signer and meaning (issued, amended) |
| Reason | `ReportVersion.reason` | Text, first 80 characters | — | Reason given when signed |

## Rules and hidden logic

- **One series per lot and recipient**: further certificates for the same lot to a different recipient get their own record; the same recipient is amended, not reissued.
- **Frozen content**: the certificate shown is the stored snapshot, never regenerated from today's records.
- **Amendments** add a version that supersedes the previous one; earlier versions stay available.
- **Footer line**: the certificate number, view time and viewer.
- **Audit events** shown include `report.opened`, `signed.issued`, `signed.amended` and `report.downloaded`.

## Related pages

- [Certificates of analysis](/reports/)
- Certificate version, Amend certificate, the lot record ([Material lots](/)).
