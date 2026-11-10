---
title: Sign and amend certificate
urls: reporting:amend_sign
views: reporting.views.amend_sign
templates: reporting/sign.html
models: reporting.Report, reporting.ReportVersion, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Signs an amendment: a new version of an issued certificate that supersedes, and never alters, the earlier one.

## Who can use it

- Sign-in required. Only the **quality** role; others receive 403.
- You cannot amend a certificate for a lot on which you recorded the lot, a sample or a result (status 403, nothing signed); the page itself still opens. Not enforced by this page: a different signer from the original issuer; the same quality user may amend.

## Layout

- **Dialog** (full page without JavaScript): heading "Sign and amend certificate", what your signature records ("amended", the new version number), signer, PIN enrolment link, errors, form, **Sign and amend certificate** / **Cancel**. Behaves as Sign and issue certificate.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and amend certificate** | Always | Quality | Creates the next version and PDF; opens the record with "<number> amended." |
| **Cancel** | Always | Quality | Returns to the amendment review page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for amendment | `ReportVersion.reason` | Text, max 2000 | Yes | Printed on the amended certificate and kept in the audit trail |
| Remarks on the certificate | `ReportVersion.remarks` | Text, max 1000 | No | Printed; starts with the latest version's remarks (a new amendment takes whatever you submit, so blank clears them) |
| Evidence hash (hidden) | — | SHA-256 | Yes | Evidence you reviewed |
| Expected version (hidden) | `Report.version_count` | Integer ≥ 1 | Yes | The version you were amending |
| Signing username | — | Text, max 150 | Yes | Must be your own username |
| Signature PIN | — | Masked digits | Yes | Re-enter for every signing; never refilled |

## Rules and hidden logic

- **Arriving here**: the link must carry the current evidence hash with no blockers, and the record must have an issued version; otherwise you are sent back to the review page (or the record).
- **Stale checks**: if another version was issued since you opened the page: "The certificate changed since you reviewed it. Review again."; if the evidence changed: "The evidence changed since you reviewed it. Review again."
- **Gates and authorship**: same blockers and authorship rule as a first issue ("Certificate cannot be issued:" plus reasons).
- **Atomic and audited**: version, PDF, signature (meaning `amended`) and audit event `signed.amended` commit together or not at all; failed PIN attempts are audited and survive the rejection.
- **Preserved original**: the earlier version's bytes and snapshot are untouched; the new version links to it as superseding.
- A blank reason is refused ("A reason is required." / "This field is required.").

## Related pages

- Amend certificate, Certificate record, [Signature PIN](/signature-pin/).
