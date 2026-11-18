---
title: Certificate record
urls: reporting:detail
views: reporting.views.report_detail
templates: reporting/report_detail.html, reporting/_certificate.html
models: reporting.Report, reporting.ReportVersion, reporting.RecipientNotification, quality.Lot, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One certificate of analysis: its status, every issued version with its signer, the current version as issued, the PDFs, and for a withdrawn certificate its withdrawal and recipient notifications.
---

## Common tasks
### Download the current certificate
1. Select [[Download PDF]] at the top of the page.
### Open or download an earlier version
1. In [[Versions]], select a version to open it, or [[Download PDF]] on its row.
### Amend an issued certificate
1. Select [[Amend certificate]]. It shows only to the quality role while the certificate is issued.
2. Review the changes on that page, then sign the amendment with your PIN.
### Withdraw a certificate that is no longer valid
1. Under [[More]], select [[Withdraw certificate]]. It shows only to the quality role while the certificate is issued.
2. Sign the withdrawal with your PIN on that page.
3. Tell the recipient, then select [[Record notification]] and record who was told, when, how and where the evidence is kept.
### Issue a certificate that was not issued
1. Select [[Review and issue]]. It shows to the quality role while no version is issued.
## Good to know
- An amendment adds a new version. The earlier one stays unchanged and is marked Superseded.
- A withdrawn certificate keeps every version and its PDF as issued, and is never amended. A new certificate for the lot gets a new number.
- "Recipient notification not recorded" shows until a notification is recorded for a withdrawn certificate.
- The certificate shown is the stored version as issued, never rebuilt from today's records.
- History shows only to the quality, auditor and admin roles. Every PDF download is recorded there.

## Purpose

One certificate of analysis series: its status, every issued version with who signed it, the current certificate as issued, its signatures and history, and, once withdrawn, the withdrawal and the evidence that its recipients were told.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**.
- **Amend certificate**, **Withdraw certificate**, **Record notification** and **Review and issue**: quality only (an administrator without the quality role sees none of them; their pages refuse them).
- The **History** panel is shown only to **quality**, **auditor** and **admin** users.

## Layout

- **Header**: breadcrumbs, certificate number, status (Not issued, Issued, Amended, Withdrawn), "Current: version N" ("Last version N" once withdrawn), and actions. An amended certificate also opens the Record panel with the fact **Amended** (blue) and "Current version N; earlier versions stay on record unchanged" under it.
- **Withdrawn** (red notice, withdrawn certificates only): "This certificate was withdrawn on … by …. It is no longer valid and cannot be amended; every issued version and its PDF stay on record exactly as issued." with the reason and, when given, the reference. While no notification is recorded, a second notice **Notification not recorded**: "Recipient notification not recorded. Tell <Issued to, or each recipient of this certificate> that it is withdrawn, then record the notification here."
- **Record**: Certificate, Lot (link, with material), Issued to ("General certificate (no named recipient)" when blank), Opened; once withdrawn also Withdrawn (time and signer), Withdrawal reference ("None given" when blank) and Reason for withdrawal; and the current PDF SHA-256 ("Last issued PDF SHA-256" once withdrawn).
- **Recipient notifications** (withdrawn certificates only): Recipient, Notified on, Means (with the note under it), Evidence, Recorded (time, with who recorded it under it), oldest first; empty state "No notification recorded yet".
- **Versions** (once issued): Version, Kind, Status (Current, Superseded, or Withdrawn for the last version of a withdrawn certificate), Issued, Signed by, Reason, Files.
- **Certificate**: the current version as issued, from its stored snapshot (same content as Review certificate).
- **Electronic signatures** (once issued): every signature of the certificate record (issued, amended, withdrawn) with signer, meaning, server time, bound revision and the start of the content hash.
- **History** (quality, auditor and admin only): audit events for this record, oldest first, or the empty state "No history yet".
- A record with no version says "No version has been issued. A draft record holds no evidence."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Download PDF** (header) | A version exists | Any viewer | Downloads the latest version |
| **Amend certificate** (primary) | Issued | Quality | Opens the amendment review page |
| **More** > **Withdraw certificate** | Issued | Quality | Opens Withdraw certificate |
| **Record notification** (primary) | Withdrawn, no notification recorded yet | Quality | Opens Record notification |
| **Record notification** (Recipient notifications panel) | Withdrawn, at least one notification recorded | Quality | Opens Record notification for a further one |
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
| Withdrawn | `Report.withdrawn_at`, withdrawal signature signer | Date and time, user | — | Server time of the withdrawal signature |
| Withdrawal reference | `Report.withdrawal_reference` | Text | — | The quality-system record behind the withdrawal, e.g. "IA-3" |
| Reason for withdrawal | `Report.withdrawal_reason` | Text | — | Reason given when the withdrawal was signed |
| Current PDF SHA-256 | `Report.current_pdf_sha256` | Hex | — | Checksum of the latest issued PDF |
| Recipient, Notified on, Means, Evidence, Recorded | `RecipientNotification.recipient`, `notified_on`, `means`, `note`, `evidence_ref`, `recorded_at`, `recorded_by` | Text, date, choice, user | — | Who was told of the withdrawal, when, how and where the evidence is kept |
| Kind | `ReportVersion.kind` | Issue, Amendment | — | First issue or later amendment |
| Status | `ReportVersion.number`, `Report.version_count`, `Report.state` | Current, Superseded, Withdrawn | — | Only the highest version is current; it shows Withdrawn once the certificate is withdrawn |
| Issued | `ReportVersion.issued_at` | UTC date and time | — | Server signing time |
| Signed by | `ElectronicSignature.signer_name`, `meaning` | Text | — | Signer and meaning (issued, amended) |
| Reason | `ReportVersion.reason` | Text, first 80 characters | — | Reason given when signed |

## Rules and hidden logic

- **One current series per lot and recipient**: further certificates for the same lot to a different recipient get their own record; the same recipient is amended, not reissued. Once a certificate is withdrawn, a certificate issued again for the same lot and recipient is a new record with the next number.
- **Frozen content**: the certificate shown is the stored snapshot, never regenerated from today's records.
- **Amendments** add a version that supersedes the previous one; earlier versions stay available.
- **Withdrawal** is a signed, final transition (meaning withdrawn): the versions, their PDFs and checksums are unchanged and stay downloadable, and the amendment pages refuse the certificate ("This certificate was withdrawn; it is not amended. A new certificate for the lot is issued as a new numbered certificate.").
- **Recipient notifications** are append-only evidence; recording one does not change the certificate's revision or signatures.
- **Footer line**: the certificate number, view time and viewer.
- **Audit events** shown include `report.opened`, `signed.issued`, `signed.amended`, `signed.withdrawn`, `report.recipient_notified` and `report.downloaded`.

## Related pages

- [Certificates of analysis](/reports/)
- Certificate version, Amend certificate, Withdraw certificate, Record notification, the lot record ([Material lots](/lots/)).
