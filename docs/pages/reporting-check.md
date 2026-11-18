---
title: Check a certificate
urls: reporting:check
views: reporting.views.check, reporting.views.public_check
templates: reporting/check.html, reporting/_check_answer.html, reporting/check_public.html
models: reporting.CertificateCheck, reporting.ReportVersion, reporting.Report
reviewed: 2026-11-18
summary: Find out whether a certificate file someone holds was issued here and whether it is the current version, replaced or withdrawn. Recipients can do the same without an account where the laboratory offers it.
---

## Common tasks
### Check a certificate a customer sent back
1. On [[Certificates of analysis]], select [[Check a certificate]].
2. Drop the PDF on [[Certificate file]], or paste its checksum in [[Or its SHA-256]].
3. Select [[Check certificate]]. The answer shows above the form, which stays open for the next file.
### Act on a replaced or withdrawn certificate
1. Read the answer: [[Replaced]] names the version that replaces it; [[Withdrawn]] gives the date.
2. Select [[Open certificate]] to send the current version or record the recipient's notification.
### Tell recipients where to check
1. When the laboratory offers the check without an account, the line under the title gives its address. Give that address to your customers.
## Good to know
- Only the exact file as issued is found. A printed or scanned copy, or a PDF saved again by a program, has other bytes and shows [[Not found]].
- The certificate data file attached to the PDF is found too, and the answer says so.
- The file is never stored or opened: only its SHA-256 is calculated, while it arrives.
- A check that finds a certificate is listed on its page under [[Checks]], with what it answered and who checked. A recipient's checks show once a day.
- The answer is about the certificate. Whether the material is within its expiry or retest date is printed on the certificate.

## Purpose

Compares a certificate file, or its SHA-256, with every version of every certificate this laboratory issued, and says whether it is genuine (issued here, unchanged) and current, replaced by a later version, or withdrawn. The same check is offered to recipients without an account where the deployment enables it.

## Who can use it

- Sign-in required. **analyst**, **reviewer**, **quality**, **admin** and **auditor** can open the page and check; others receive 403. The check changes no certificate, so administrators check like any reader.
- The check without an account, at `/check/`, exists only where the deployment sets `CERTIFICATE_CHECK=true`; otherwise that address answers 404. It needs no account, starts no session and is linked from the sign-in page while it is offered.

## Layout

- **Header**: breadcrumbs (Certificates › Check a certificate), the title and one line explaining the check. While the check without an account is offered, the line adds "Recipients can make the same check without an account at" and the full address.
- **Answer** (after a check): one notice and the facts of the version found.
  - **Genuine and current** (green): "This file is certificate …, version N, issued on …. It is the current version."
  - **Replaced** (amber): the version found, and "Version M, issued on …, replaces it. Send the recipient the current version."
  - **Withdrawn** (red): the version found, and "The laboratory withdrew this certificate on …. Whoever holds it should be told; record each notification on the certificate."
  - **Not found** (amber): "No certificate issued by this laboratory matches this file." with the likely causes and "Ask the laboratory for a copy of the certificate."
  - Facts: **Certificate**, **Version** ("2 of 3" when replaced), **Issued**, **Lot** (number · material), **File checked** (Certificate PDF or Certificate data (JSON)), **Issued to**; then the links **Open version N** and **Open certificate …**.
- **Form**: **Certificate file**, **Or its SHA-256**, a note on what is compared, **Cancel** and **Check certificate**. In the form dialog opened from the certificate list the answer shows in the dialog.
- **Without an account**: the sign-in page's layout with the title "Check a certificate", the same form and answer without **Issued to** and without links, the advice "Ask the laboratory for the current version." (replaced) or "Do not rely on it; contact the laboratory." (withdrawn), and a link **Laboratory staff sign in**.

## Actions

- **Check certificate**: computes the SHA-256 of the file while it arrives (or takes the one entered) and looks for an issued version whose PDF or certificate data has it. A version found is recorded as a check of that certificate with its answer; nothing is recorded when nothing is found. The page answers 422 with the error when the form is invalid.
- **Open version N** / **Open certificate …** (signed in only): the version page and the certificate page.
- **Cancel**: back to the certificate list, or closes the dialog.

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
| --- | --- | --- | --- | --- |
| Certificate file | — | File, `.pdf` or `.json`, up to the deployment's upload limit | One of the two | The certificate PDF, or the certificate data file attached to it, exactly as received. Only its SHA-256 is kept in memory; its bytes are dropped as they arrive. |
| Or its SHA-256 | — | Text, up to 200 characters | One of the two | 64 hexadecimal characters in any case, with or without spaces or colons; a checksum tool's line with the file name after it is accepted. |
| Certificate, Version, Issued, Lot | `Report.number`, `ReportVersion.number`, `ReportVersion.issued_at`, `Lot.number`, `Lot.material` | Display | — | What the certificate prints, so the person can compare it with the file they hold. |
| File checked | `CertificateCheck.matched` | Display | — | Whether the PDF or the certificate data matched. |
| Issued to | `Report.recipient` | Display, signed in only | — | The certificate's recipient, or "General certificate (no named recipient)". |

## Rules and hidden logic

- **Validation**: "Give the file or its SHA-256, not both."; "Choose the certificate file, or enter its SHA-256."; "A SHA-256 is 64 characters, 0-9 and a-f."; a file over the upload limit: "The file is larger than the limit of …. No issued certificate is that large." A request that declares more than the limit is refused with 413 before it is read.
- **Answer**: **Withdrawn** for every version of a withdrawn certificate; otherwise **Replaced** for a version an amendment replaced; otherwise **Genuine and current**. It is read under a lock on the certificate, so a check made while an amendment or a withdrawal is signed answers as before or after it, never a mix, and the database refuses to keep a check with any other answer.
- **What is recorded**: a check that finds a version adds an append-only check row (time, version, file matched, answer and the signed-in person, or none for a recipient without an account). Checks without an account are kept once a day for each version and answer (the laboratory's time zone): later ones that day get the same answer and add no row. No address, name or file of a recipient is kept. Checks are not audit events; they are listed on the certificate page and in the lot's exported record.
- **Without an account**: checks are limited for the whole deployment to `CERTIFICATE_CHECK_RATE` a minute (20 unless the deployment sets otherwise), counted before the file is read; past it the page answers 429 with "Many certificates were checked in the last minute. Try again in N seconds." and a `Retry-After` header. A check sent from another site's page (the browser reports it as cross-site, or names another origin) is refused with 403 before it is counted. Someone signed in who reads certificates is named on a check made there. The page is sent with `Cache-Control: no-store` and `X-Robots-Tag: noindex`.
- **Disclosure**: nothing finds a certificate but the SHA-256 of its exact file, so the answer tells a recipient nothing the file does not print, apart from its status and, when replaced, the number and issue time of the current version. Reasons for an amendment or a withdrawal, signers and results are not shown.
- Not enforced by this page: whether a recipient may rely on a certificate for their purpose, and whether the material is still within its dates; those stay with the recipient and are printed on the certificate.

## Related pages

- [Certificates of analysis](/reports/): where the check is opened.
- Certificate: the certificate page lists every check of its versions under **Checks**.
- Certificate version: the version found, with its checksums.
