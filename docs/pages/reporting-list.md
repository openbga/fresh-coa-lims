---
title: Certificates of analysis
urls: reporting:list
views: reporting.views.report_list
templates: reporting/report_list.html
models: reporting.Report, quality.Lot
reviewed: 2026-11-10
---

## Purpose

Lists every certificate of analysis (CoA) record so you can find one, check whether it is issued or amended, and start a new certificate for a released lot.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **New certificate of analysis** is shown only to users with the **quality** role.

## Layout

- **Header**: title, short description and the **New certificate of analysis** button (quality only).
- **Filters**: **Search** box, **Status** menu, **Apply filters**, and **Clear filters** (only while a filter is active).
- **Table**: Certificate, Lot, Material, Issued to, Status, Version. Certificate numbers link to the record.
- **Footer**: certificate count and, when there is more than one page, Previous / "Page N of M" / Next.
- **Empty states**: "No certificates of analysis yet." (with a start link for quality users) and, when filters are active, "No certificates match these filters."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New certificate of analysis** | Viewer has the quality role | Quality | Opens [New certificate of analysis](/reports/new/) |
| **Apply filters** | Always | Any viewer | Reloads the list with the search and status |
| **Clear filters** | A search or status is set | Any viewer | Returns to the unfiltered list |
| Column links **Certificate**, **Lot**, **Status** | Always | Any viewer | Sort by that column; a second click reverses it |
| Certificate number | Always | Any viewer | Opens the certificate record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | `Report.number`, `Lot.number`, `Lot.material`, `Report.recipient` | Text | No | Case-insensitive "contains" match on any of these |
| Status | `Report.state`, `Report.version_count` | Not issued, Issued, Amended | No | Not issued = record opened, nothing signed; Issued = exactly one version; Amended = more than one |
| Certificate | `Report.number` | Text | — | Identifier, `CoA-<lot number>-<sequence>` |
| Lot | `Report.lot` | Lot number | — | Lot the certificate covers |
| Material | `Lot.material` | Text | — | Material on the lot |
| Issued to | `Report.recipient` | Text | — | Named recipient, or "General" when blank |
| Version | `Report.version_count` | Integer | — | Number of issued versions; "—" when none |

## Rules and hidden logic

- **Order and paging**: default order is newest first by creation time; 25 per page. Unknown sort values fall back to creation time. The server filters, sorts and pages the whole list.
- **Draft records**: a record with status "Not issued" is created when a quality user starts signing for a lot and holds no evidence. It stays if the signing fails.
- **Authorization**: access is checked on the server for every request; hidden buttons are not the control.

## Related pages

- [New certificate of analysis](/reports/new/)
- [Material lots](/): certificates are only available for released lots.
