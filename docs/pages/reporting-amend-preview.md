---
title: Amend certificate
urls: reporting:amend_preview
views: reporting.views.amend_preview
templates: reporting/preview.html, reporting/_certificate.html
models: reporting.Report, reporting.ReportVersion, quality.Lot
reviewed: 2026-11-10
---

## Purpose

Shows what an amended certificate would contain, built from the lot's current evidence, and how it differs from the latest issued version. Nothing is issued here.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**.
- **Continue to signing**: quality users (not administrators without the quality role) who are not blocked and did not author records on the lot.
- A record with no issued version redirects to the certificate record with "Only an issued certificate can be amended."

## Layout

- **Header**: breadcrumbs, title "Amend certificate · number", status "Preview, not issued", evidence hash prefix.
- **Alerts**: "Cannot issue" reasons, "Not permitted", or "Read only" as on Review certificate (only one of the three shows); plus an "Amendment" note: it replaces version N, which stays on record, and either lists the evidence sections changed or says the evidence is unchanged since that version.
- **Certificate preview** of the evidence as it would now be issued.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Continue to signing** | Quality role, no blockers, no authorship conflict | Quality | Opens the amendment signing page with the evidence hash |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Evidence sections changed | — | Section names | — | Top-level sections of the evidence that differ from the latest version (for example results, holds) |
| Certificate preview | as Review certificate | — | — | Same content and blockers; the "Certificates already opened" list is not shown |

## Rules and hidden logic

- Amendments are held to the same blockers as a first issue, so an open hold prevents amending. Not enforced by this page: withdrawal or recall of an issued certificate.
- Viewing writes no audit event.
- Native lots use the frozen assignment bound to the QC disposition, as described on [Review certificate](/reports/); an unverifiable assignment blocks the amendment. Unknown certificate: 404. GET only.

## Related pages

- Certificate record, Sign and amend certificate.
