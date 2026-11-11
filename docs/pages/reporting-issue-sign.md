---
title: Sign and issue certificate
urls: reporting:issue_sign
views: reporting.views.issue_sign
templates: reporting/sign.html
models: reporting.Report, reporting.ReportVersion, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-11
---

## Purpose

Signs and issues version 1 of a certificate of analysis for a released lot, with your signature PIN. The signature binds the exact evidence you reviewed.

## Who can use it

- Sign-in required. Only the **quality** role; others receive 403. **admin** is read-only here: an administrator without the quality role is refused (403) and sees no signing actions; an administrator who also holds the quality role has the quality actions, with the same authorship rule.
- You cannot sign for a lot on which you authored records (lot, sample, result or native analytical records). You are turned back before the form is shown; a direct submission is still refused (status 403) and nothing is signed.

## Layout

- **Dialog** (a full page without JavaScript): heading "Sign and issue certificate", a statement of what your signature records, your name as signer, a link to enrol or change your signature PIN, any error summary, the form, and **Sign and issue certificate** / **Cancel**.
- Opening the page never signs. With JavaScript it opens as a modal, focus goes to the PIN (or the error), Escape or **Cancel** leaves without signing.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and issue certificate** | Always | Quality | Creates version 1, its PDF and signature, then opens the certificate record with "<number> version 1 issued." |
| **Cancel** | Always | Quality | Returns to the review page without changes |
| Enrol or change your signature PIN | Always | Any | Opens [Signature PIN](/signature-pin/) |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Issued to | `Report.recipient` | Text, max 160 | No | Customer or consignee named on the certificate; blank means a general one. Spaces around it are trimmed |
| Remarks on the certificate | `ReportVersion.remarks` | Text, max 1000 | No | Printed on the certificate |
| Reason for issuing | `ReportVersion.reason` | Text, max 2000 | Yes | Kept in the audit trail and signature; not printed on a first issue |
| Evidence hash (hidden) | — | SHA-256 | Yes | The evidence you reviewed; must still match |
| Signing username | — | Text, max 150 | Yes | Must be your own username |
| Signature PIN | — | Masked digits | Yes | Re-enter for every signing; never refilled after an error |

## Rules and hidden logic

- **Checked before the form is shown**: when you arrive, the link must carry the current evidence hash, the evidence must have no blockers and you must not be an author on the lot. Otherwise you are sent back to the review page with a warning giving the reason: "The evidence changed since you reviewed it. Review it again.", "This certificate cannot be issued: …" followed by the blockers, or "You authored records on this lot, so you cannot sign this certificate as issued." Everything is checked again when you submit. "Already issued for this recipient" cannot be checked on arrival, because the recipient is entered in the form; submitting refuses it.
- **Draft record**: a submission is first checked, without creating anything, for your role, a reason, your signing username and session, the reviewed evidence (unchanged, no blockers, not authored by you) and your PIN. Only when all of these pass is the certificate record for this lot and recipient created (or reused), with `report.opened`; everything is then checked again under lock while signing. The record is committed separately, so it stays as "Not issued" only if signing fails after that point (for example the evidence changes in between, or the PDF cannot be rendered). Certificate numbers are `CoA-<lot number>-<n>`, with n counting records for the lot. The lot must be released: "A certificate needs a lot with a signed QC disposition."
- **Checks under lock at signing**: this record and the lot are locked; evidence is collected again and must equal the hash you reviewed ("The evidence changed since you reviewed it. Review again."); all blockers are re-evaluated ("Certificate cannot be issued:" plus reasons), including, for lots released through native testing, that the requirement assignment signed with the QC disposition can still be resolved and verified; you must not be an author ("You cannot issue a certificate for records you authored."); a certificate already issued for this lot and recipient is refused ("This certificate is already issued; amend it instead.").
- **Atomic**: the PDF is rendered, the version stored, the signature (meaning `issued`) and audit event `signed.issued` written together. A rendering failure ("The certificate could not be rendered: …") or any other failure leaves no version, signature or audit event of the issue.
- **Credentials**: a wrong PIN or username is refused ("Signature PIN was not accepted.", "Enter your own signing username and PIN."); failed PIN attempts are counted and audited even though signing is rejected, and repeated failures lock the PIN.
- **Time**: the issue time printed on the certificate is the server's signing time, identical to the signature's.
- **Immutable**: the issued version, its PDF bytes and hashes cannot be changed or deleted.
- Invalid form input is returned with errors and your entries (except the PIN), status 422.

## Related pages

- Review certificate (where you come from), the certificate record.
- [Signature PIN](/signature-pin/)
