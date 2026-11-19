---
title: Amend certificate
urls: reporting:amend_preview
views: reporting.views.amend_preview
templates: reporting/preview.html, reporting/_certificate.html
models: reporting.Report, reporting.ReportVersion, quality.Lot, quality.LotDates, quality.Reassessment
reviewed: 2026-11-19
summary: What an amended certificate would contain, built from the lot's current evidence, and which evidence sections changed since the latest version. Nothing is issued here.
---

## Common tasks
### Review and sign an amendment
1. Read the [[Amendment]] notice for the evidence sections changed since the latest version.
2. Check the preview, then select [[Continue to signing]]. It shows only to the quality role when nothing blocks it, you authored no records on the lot and you hold any qualification a rule set reserves.
3. Sign with your PIN on that page using [[Sign and amend certificate]].
### Find out why an amendment cannot be signed
1. Read the reasons under [[Cannot issue]]. An amendment is blocked by the same reasons as a first issue, including a result that no longer meets the certificate's scope.
## Good to know
- The version being replaced stays on record unchanged.
- When the evidence is unchanged since the latest version, amend only to correct the certificate's remarks or wording.
- An open hold, or any other blocker, prevents an amendment just as it prevents a first issue.
- Only an issued certificate can be amended. A withdrawn one never is.

## Purpose

Shows what an amended certificate would contain, built from the lot's current evidence, and how it differs from the latest issued version. Nothing is issued here.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**.
- **Continue to signing**: quality users (not administrators without the quality role) who are not blocked, did not author records on the lot and hold the Issuing certificates qualification any rule set of the lot reserves.
- A record with no issued version redirects to the certificate record with "Only an issued certificate can be amended."; a withdrawn certificate redirects there with "This certificate was withdrawn; it is not amended. A new certificate for the lot is issued as a new numbered certificate."

## Layout

- **Header**: breadcrumbs, title "Amend certificate · number", status "Preview, not issued", "For scope X" when the certificate is for one scope, evidence hash prefix.
- **Alerts**: "Cannot issue" reasons, "Not permitted" (an authorship conflict, or a rule set reserving certificates for a qualification you do not hold), or "Read only" as on Review certificate (only one of the three shows); plus an "Amendment" note: it replaces version N, which stays on record, and either lists the evidence sections changed or says the evidence is unchanged since that version.
- **Certificate preview** of the evidence as it would now be issued, for the certificate's own scope (no scope chooser here). A certificate for one scope previews as on Review certificate: only that scope's specification, limits and conformity.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Continue to signing** | Quality role, no blockers, no authorship conflict, holds any reserved qualification | Quality | Opens the amendment signing page with the evidence hash |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Evidence sections changed | — | Section names | — | Top-level sections of the evidence that differ from the latest version (for example results, holds) |
| Certificate preview | as Review certificate | — | — | Same content and blockers; the "Certificates already opened" list is not shown |

## Rules and hidden logic

- The scope of an amendment is the scope of the certificate and cannot be changed. The scope's blockers apply as on a first issue: an amendment is refused while a result does not meet, or cannot be judged against, the scope's specification, or a required test has no result.
- Amendments are held to the same blockers as a first issue, so an open hold prevents amending. So do the date blockers: after the lot's expiry date ("The lot expired after 2026-11-01; no certificate is issued for it."), from its retest date on ("The lot's retest date, 2026-11-01, has been reached; no certificate is issued for a lot due for retest.") and when the dates are not those the release froze ("The lot's expiry and retest dates are not those its release froze."). The same applies when the lot's use ended with a reassessment ("The lot's use ended with reassessment RA-n; no certificate is issued for it."); a lot whose retest date was reached can be amended again once a reassessment concluded as suitable gave a later retest date in force. The preview prints the lot's Expiry date and Retest date (the date in force) when it has them, with a "Reassessed" line when a reassessment gave it, and "dates" is listed among the changed sections when they differ from the latest version. Withdrawal is signed from the certificate record (Withdraw certificate), not here.
- **Certificates reserved for qualified people**: an amendment needs the same Issuing certificates qualification as a first issue, for the rule sets the lot is under (see Review certificate). Without it the page shows "Not permitted" with the reason and no **Continue to signing**.
- Viewing writes no audit event.
- Native lots use the frozen assignment bound to the QC disposition, as described on [Review certificate](/reports/); an unverifiable assignment blocks the amendment. Unknown certificate: 404. GET only.

## Related pages

- Certificate record, Sign and amend certificate.
