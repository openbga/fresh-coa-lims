---
title: Sign and amend certificate
urls: reporting:amend_sign
views: reporting.views.amend_sign
templates: reporting/sign.html
models: reporting.Report, reporting.ReportVersion, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: Sign an amendment of an issued certificate with your PIN. It adds a new version that supersedes the earlier one, which stays unchanged.
---

## Common tasks
### Sign the amendment
1. Give the [[Reason for amendment]]. It is printed on the amended certificate.
2. Check [[Remarks on the certificate]]. They start as the latest version's remarks; a blank field removes them from the new version.
3. Enter your [[Signing username]] and [[Signature PIN]], then select [[Sign and amend certificate]].
### Leave without signing
1. Select [[Cancel]] to return to the amendment review. Nothing changes.
## Good to know
- If another version was issued or the evidence changed after you reviewed it, signing is refused. Review it again.
- You cannot amend a certificate for a lot where you recorded the lot, a sample or a result. If a rule set reserves certificates, you also need its Issuing certificates qualification.
- The earlier version's PDF and content never change. The new version links to it.
- An amendment cannot change Issued to or the scope it is for. A certificate for another recipient is a new certificate.

## Purpose

Signs an amendment: a new version of an issued certificate that supersedes, and never alters, the earlier one.

## Who can use it

- Sign-in required. Only the **quality** role; others receive 403. **admin** is read-only here: an administrator without the quality role is refused (403) and sees no signing actions; an administrator who also holds the quality role has the quality actions, with the same authorship rule.
- You cannot amend a certificate for a lot on which you recorded the lot, a sample or a result, and, where a rule set reserves certificates, without the Issuing certificates qualification it names; you are turned back before the form is shown, and a direct submission is refused (status 403, nothing signed). Not enforced by this page: a different signer from the original issuer; the same quality user may amend.

## Layout

- **Dialog** (full page without JavaScript): heading "Sign and amend certificate", what your signature records ("amended", the new version number; the certificate is named "NUMBER, new version N, for all of the lot's requirements" or "..., for scope X"), signer, PIN enrolment link, errors, form, **Sign and amend certificate** / **Cancel**. Behaves as Sign and issue certificate.

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

- **Checked before the form is shown**: the certificate must not be withdrawn (otherwise you return to the record with "This certificate was withdrawn; it is not amended. A new certificate for the lot is issued as a new numbered certificate."), the record must have an issued version (otherwise you return to the record with "Only an issued certificate can be amended."), and the link must carry the current evidence hash with no blockers and you must not be an author on the lot. Otherwise you are sent back to the amendment review page with the reason ("The evidence changed since you reviewed it. Review it again.", "This certificate cannot be amended: …" or "You authored records on this lot, so you cannot sign this certificate as amended."). Submitting checks everything again.
- **Withdrawn meanwhile**: a certificate withdrawn after you opened the page is refused when you submit, with the same message; nothing is signed.
- **Stale checks**: if another version was issued since you opened the page: "The certificate changed since you reviewed it. Review again."; if the evidence changed: "The evidence changed since you reviewed it. Review again."
- **Dates**: the date blockers apply as on a first issue: an expired lot, a lot whose use ended with a reassessment, a lot whose retest date in force was reached (a later date given by a suitable reassessment lifts this), or dates that are not those the release froze refuse the amendment ("Certificate cannot be issued:" plus reasons).
- **Scope**: the amendment keeps the certificate's scope, stored again in the new version's snapshot, and is judged against that scope's blockers as on a first issue.
- **Qualification**: where a rule set the lot is under reserves certificates, you need an approved, current Issuing certificates qualification for each activity named. Without it you return to the amendment review with a warning before the form, and a submission is refused before the PIN is checked (the reason names the rule set and activity). It is checked again under the locks. When you hold it, the dialog states "This signature relies on your qualification QUAL-3, for issuing certificates in “CERT-TEST” (Rule set RS-TEST v1), and records it."; the qualification is frozen in the new version and shown there as "Signed under".
- **Gates and authorship**: same blockers and authorship rule as a first issue, including that a native lot's signed requirement assignment must still resolve and verify; later assignments do not replace it ("Certificate cannot be issued:" plus reasons).
- **Atomic and audited**: version, PDF, signature (meaning `amended`) and audit event `signed.amended` commit together or not at all; failed PIN attempts are audited and survive the rejection.
- **Preserved original**: the earlier version's bytes and snapshot are untouched; the new version links to it as superseding.
- A blank reason is refused ("A reason is required." / "This field is required.").

## Related pages

- Amend certificate, Certificate record, [Signature PIN](/signature-pin/).
