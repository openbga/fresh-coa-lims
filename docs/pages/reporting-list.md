---
title: Certificates of analysis
urls: reporting:list
views: reporting.views.report_list
templates: reporting/report_list.html, includes/grid_toolbar.html, includes/list_results.html, includes/pagination.html, includes/sort_header.html
models: reporting.Report, quality.Lot
reviewed: 2026-11-17
---

## Purpose

Lists every certificate of analysis (CoA) record so you can find one, check whether it is issued or amended, and start a new certificate for a released lot.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **New certificate of analysis** is shown only to users with the **quality** role; an administrator without it can read every certificate but sees no issuing action.

## Layout

- **Header**: title, the line "Versioned, immutable certificates built from signed QC disposition evidence." and the **New certificate of analysis** button (quality only).
- **Toolbar** (at the top of the table card): **Search** (placeholder "Number, lot, material or recipient"), **Status** (default "All statuses"), **Apply**, and **Clear all** (only while a filter is active).
- **Table**: Certificate, Lot, Material, Issued to, Status, Version. Certificate numbers link to the record; Certificate, Lot and Status headers sort.
- **Footer**: "Showing X–Y of N certificates", with "matching filters" when filtered; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons.
- **Empty states**: "No certificates of analysis yet" ("A certificate can be issued once a lot has a signed QC disposition.", with **Start a certificate** for quality users) and, when filters are active, "No certificates match these filters" ("Change the search or clear the filters.") with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New certificate of analysis** | Viewer has the quality role | Quality | Opens [New certificate of analysis](/reports/new/) |
| **Apply** | Always | Any viewer | Reloads the list with the search and status |
| **Clear all** / **Clear filters** | A search or status is set | Any viewer | Returns to the unfiltered list |
| **Start a certificate** | No certificate exists and the viewer has the quality role | Quality | Opens [New certificate of analysis](/reports/new/) |
| **Rows per page** / **Show**, pager | Always / more than one page | Any viewer | Changes the rows per page or the page; filters and sort are kept |
| Column links **Certificate**, **Lot**, **Status** | Always | Any viewer | Sort by that column; a second click reverses it |
| Certificate number | Always | Any viewer | Opens the certificate record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search (`q`) | `Report.number`, `Lot.number`, `Lot.material`, `Report.recipient` | Text | No | Case-insensitive "contains" match on any of these; leading and trailing spaces ignored |
| Status | `Report.state`, `Report.version_count` | Not issued, Issued, Amended | No | Not issued = record opened, nothing signed; Issued = exactly one version; Amended = more than one |
| Certificate | `Report.number` | Text | — | Identifier, `CoA-<lot number>-<sequence>` |
| Lot | `Report.lot` | Lot number | — | Lot the certificate covers |
| Material | `Lot.material` | Text | — | Material on the lot |
| Issued to | `Report.recipient` | Text | — | Named recipient, or "General" when blank |
| Version | `Report.version_count` | Integer | — | Number of issued versions; "—" when none |

## Rules and hidden logic

- **Order and paging**: default order is newest first by creation time (ties by newest record); 25 rows per page by default (50 or 100 through **Rows per page** or `per_page`); an out-of-range page shows the last page. Sorting by Status orders by the status shown (Not issued, Issued, Amended; reversed on a second click), newest first within each status. Unknown sort values fall back to creation time. The server filters, sorts and pages the whole list; the page accepts GET only.
- **Draft records**: a record with status "Not issued" is created when a quality user submits the signing form for a released lot and holds no evidence. It stays if the signing fails. Draft records are listed to every viewer.
- **Authorization**: access is checked on the server for every request; hidden buttons are not the control.

## Related pages

- [New certificate of analysis](/reports/new/)
- [Material lots](/lots/): certificates are only available for released lots.
