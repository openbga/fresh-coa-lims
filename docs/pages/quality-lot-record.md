---
title: Export record
urls: quality:lot_record
views: reporting.views.lot_record_export
templates: reporting/lot_record.html, reporting/pdf/lot_record.html, reporting/pdf/_lot_record_entry.html
models: quality.Lot, core.AuditEvent, core.ElectronicSignature, core.AuditReview, analytical.RawDataFile, reporting.ReportVersion
reviewed: 2026-11-17
summary: Download one lot's complete record as a single ZIP file, to keep or hand over for an inspection or review. Exporting changes nothing and is recorded in the lot's audit trail.
---

## Common tasks
### Download the lot's record
1. Check [[What the record holds now]] for what the package will contain.
2. Say why you export it in [[Purpose of the export]], for example an inspection request.
3. Select [[Download the record]]. The ZIP file downloads and the page stays open.
### Check a downloaded copy
1. Open record.pdf. Its first page says whether every stored checksum and hash matched.
2. To check the files, compare them with SHA256SUMS in the same folder.
## Good to know
- Only admin, quality and auditor can export, because the package includes the audit trail.
- Each export is recorded on the lot with your name and the purpose. The lot's record revision does not change.
- The package is read at one instant. A change saved while it is built is not in it.
- Configuration such as rule sets and specifications is included as it stands at the export.
- A checksum that does not match is reported on the first page, not hidden, and the download still proceeds.

## Purpose

Downloads one lot's complete record as a single ZIP file, to keep or to hand over for an inspection, an annual product review or a complaint. Exporting changes nothing in the record; it is recorded in the lot's audit trail.

## Who can use it

- Sign-in required. Opening the page and downloading require **admin**, **quality** or **auditor**, the roles that read the audit trail. Others receive 403, and the lot page does not show them **Export record**.
- The role is checked again when the download is built and when the export is recorded. An account deactivated or without these roles in the meantime receives 403 and nothing is recorded.
- An unknown lot returns 404.

## Layout

- **Header**: breadcrumbs "Material lots › lot number › Export record", the title "Export record · lot number" and the line "One file holding the lot's complete record, to keep or hand over for an inspection or a review. Exporting changes nothing in the record."
- **What the record holds now** card: Lot (a link to the lot, with the material), Status and Record revision, then a table of what an export would hold now: one row per kind of the lot's own records that has at least one record (for example Receipt details, Samples, Tests, Observations, Raw-data files, Investigations, Certificates of analysis, Holds), then Configuration these records name, Audit trail events, Electronic signatures, and Files (raw data and issued certificates).
- **The package** card: what the ZIP file contains (record.pdf, record.json, files, manifest.json and SHA256SUMS), that the stored checksums are recomputed and the first page of the printed copy says whether each matched, and that configuration is included as it stands at the export.
- **Form**: Purpose of the export, then **Cancel** and **Download the record**. Errors appear above the form.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Download the record** | Always | Admin, quality, auditor | Builds the package and downloads it as `<lot number>-record-<time>.zip`, with the time in UTC (for example `LOT-TEST-001-record-20261116T101500Z.zip`); records the export in the lot's audit trail. The page stays as it is; the button shows that the request is running and is usable again after a few seconds |
| **Cancel** | Always | Any viewer | Returns to the lot record without exporting |
| Lot number link | Always | Any viewer | Opens the lot record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Purpose of the export | `AuditEvent.reason` of the export | Text, max 500 | Yes | Why the record is exported, for example an inspection request. Printed on the first page of the record, stored in record.json and manifest.json, and kept as the reason of the export's audit event |
| Lot, Status, Record revision | `Lot.number`, `material`, `state`, `revision` | Text, integer | — | The lot as it stands when the page is opened |
| Record counts | — | Integers | — | What an export would hold if it were made now; the package counts what it read at its own instant |

## Rules and hidden logic

- **One instant**: the package is read in one repeatable-read, read-only database transaction, so every part describes the same moment. A change saved while the package is built is not in it.
- **What it holds**: the lot's own records, found by their links to the lot: the lot; receipt details, with corrections; supplier certificates, their stated results and withdrawals; supplier results proposed or accepted in place of tests; requirement assignments; samples and sampling records with deviation reviews; manual results; stability studies, pulls, reserve samples, retention obligations and holds; tests, and the tests of the lot's stability pulls (which are not part of its release testing); their observations, raw-data files, investigations and investigation entries; the QC batches the tests used, with their checks; certificates of analysis and every issued version; and the instruments, reagent lots and contract laboratory reports used for any of these. Records of other lots are never included; a QC batch shared with other lots brings only the batch and its checks.
- **Configuration**: the rule sets, materials, specifications and their versions, methods and their versions, sampling plans and their versions, suppliers and supplier qualifications, equipment, reagent and standard lots, contract laboratories and their approvals, and stability protocols that the lot's records name, as they stand at the export. This includes every rule set the lot was under and the specification, method and rule set versions frozen in its requirements. A later version that replaced one of them is not included unless the lot's records name it. Their signatures are included; their own history is not.
- **Signatures and audit trail**: every signature on these records, and every audit trail event on the lot's own records, with the audit trail reviews that covered any of them. Accounts appear by name and username only; passwords, PINs and their hashes are never exported.
- **record.pdf**: the printed copy. The first page names the lot, the export time in UTC, who exported it and why, the export ID and the release that produced it, and says whether every stored checksum and hash matched. Then every field of every record; for each of the lot's own records whether the audit trail shows it being entered and how many events acted on it later; each signature with the signer's name, meaning, date and time and the revision signed; the audit trail, oldest first, with what each change replaced (before → after) or, for an event that states no earlier values, what it recorded; the audit trail reviews; the files; and the checks. Structured values longer than 2000 characters, and audit trail values longer than 300 characters, are shortened in the printed copy only.
- **record.json**: the electronic copy, schema `oq.lot-record/1`. Every stored field of every record; decimals as text exactly as stored; times in ISO 8601 UTC; for each record type the label, kind and choices of each field.
- **Files**: raw-data files under `files/raw-data/` and issued certificate versions under `files/certificates/`, byte for byte. Names are reduced to letters, digits, spaces, dots, hyphens and underscores, so no name leads outside the folder: an uploaded file keeps only its own name, and a lot or certificate number keeps every part with other characters replaced by `_` (lot `L/2026/007` gives `L_2026_007-record-...zip`).
- **Checks**: the SHA-256 and size of each raw-data file and certificate file, and the hashes stored with each signature's content, certificate content, requirement assignment and approved specification, method or sampling plan version, are recomputed. A requirement assignment on hold stores no hash and is not checked. Other hashes the records hold are copied, not recomputed. A mismatch is copied as stored and reported on the first page and under Checks, not hidden, and the download still proceeds.
- **Checking a copy**: manifest.json and SHA256SUMS give the size and SHA-256 of every file in the folder; `sha256sum -c SHA256SUMS` in the folder checks them.
- **Audit**: each export adds the event `lot.record_exported` on the lot, with the purpose as its reason and the export ID, file name, the package's SHA-256 and size, the lot revision and the counts. The lot's revision does not change, and no other record changes. A later export lists the earlier exports in its audit trail.
- **Failures**: an empty purpose shows "This field is required."; more than 500 characters shows "Ensure this value has at most 500 characters (it has N)." If the printed copy cannot be produced, the page shows "The record could not be exported: its printed copy could not be produced. Nothing was recorded. Try again; if it fails again, tell your administrator." and nothing is recorded; the reason is written to the server log.
- **Size**: the package is built while you wait. A lot whose raw-data files total several hundred MiB can take longer than the server allows for one request (60 seconds in the provided container image); the export then fails and nothing is recorded.
- **Not enforced by this page**: whether a package serves as a true copy for the laboratory's records is part of the laboratory's validation of this function. The software does not sign or certify the package.

## Related pages

- [Material lots](/lots/)
- Lot record (the lot page, which opens this page from **Export record**).
- [Audit trail](/audit/)
- Certificate version (each issued version included in the package).
