---
title: Certificates of analysis
urls: reporting:list
views: reporting.views.report_list
templates: reporting/report_list.html, includes/grid_toolbar.html, includes/list_results.html, includes/pagination.html, includes/sort_header.html
models: reporting.Report, reporting.RecipientNotification, quality.Lot
reviewed: 2026-11-17
summary: Every certificate of analysis in one list. Find a certificate, see whether it is issued, amended or withdrawn, or start a new one for a lot with a signed QC disposition.
---

## Common tasks
### Find a certificate
1. Type a certificate number, lot number, material or recipient in [[Search]].
2. To see one status, choose it in [[Status]], then select [[Apply]].
3. Select a certificate number to open its record.
### Start a new certificate
1. Select [[New certificate of analysis]]. It shows only to the quality role.
2. Choose the released lot and select [[Review certificate]] on that page.
### Find withdrawn certificates whose recipients are not yet recorded as told
1. Choose [[Awaiting notification]] in [[Status]], then select [[Apply]].
2. Open each certificate and record the notification there.
### See every certificate again
1. Select [[Clear all]].
## Good to know
- A Not issued record holds no evidence. It stays when a signing attempt is refused after the record was opened.
- Amended means the certificate has more than one version and is not withdrawn. Every earlier version stays on the certificate record.
- A lot can have several certificates, one current for each recipient named in Issued to. One issued again after a withdrawal gets a new number.
- Withdrawn certificates show "Notification not recorded" under their status until a recipient notification is recorded.
- The newest certificate record comes first, not the most recently issued or amended.

## Purpose

Lists every certificate of analysis (CoA) record so you can find one, check whether it is issued, amended or withdrawn, find withdrawn certificates whose recipient notification is not recorded, and start a new certificate for a released lot.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **New certificate of analysis** is shown only to users with the **quality** role; an administrator without it can read every certificate but sees no issuing action.

## Layout

- **Header**: title, the line "Versioned, immutable certificates built from signed QC disposition evidence." and the **New certificate of analysis** button (quality only).
- **Toolbar** (at the top of the table card): **Search** (placeholder "Number, lot, material or recipient"), **Status** (default "All statuses"), **Apply**, and **Clear all** (only while a filter is active).
- **Table**: Certificate (with "version N", or "not issued", under it), Lot (links to the lot, with the material under it), Issued to, Status (a withdrawn certificate without a recorded notification shows "Notification not recorded" under Withdrawn). Certificate numbers link to the record; Certificate, Lot and Status headers sort. **Columns** (beside Rows per page) chooses which columns show and their order, saved for your account; the less important columns give way first when the table does not fit.
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
| Status | `Report.state`, `Report.version_count`, `RecipientNotification` | Not issued, Issued, Amended, Withdrawn, Awaiting notification | No | Not issued = record opened, nothing signed; Issued = exactly one version, not withdrawn; Amended = more than one, not withdrawn; Withdrawn = withdrawal signed; Awaiting notification = withdrawn and no recipient notification recorded |
| Certificate | `Report.number` | Text | — | Identifier, `CoA-<lot number>-<sequence>` |
| Lot | `Report.lot` | Lot number | — | Lot the certificate covers |
| Material | `Lot.material` | Text | — | Material on the lot |
| Issued to | `Report.recipient` | Text | — | Named recipient, or "General" when blank |
| Version | `Report.version_count` | Integer | — | Number of issued versions; "—" when none |

## Rules and hidden logic

- **Order and paging**: default order is newest first by creation time (ties by newest record); 25 rows per page by default (50 or 100 through **Rows per page** or `per_page`); an out-of-range page shows the last page. Sorting by Status orders by the status shown (Not issued, Issued, Amended, Withdrawn; reversed on a second click), newest first within each status. Unknown sort values fall back to creation time. The server filters, sorts and pages the whole list; the page accepts GET only.
- **Withdrawn certificates** stay listed with their numbers; a certificate issued later for the same lot and recipient is a new row with the next number.
- **Draft records**: a record with status "Not issued" is created when a quality user submits the signing form for a released lot and holds no evidence. It stays if the signing fails. Draft records are listed to every viewer.
- **Authorization**: access is checked on the server for every request; hidden buttons are not the control.

## Related pages

- [New certificate of analysis](/reports/new/)
- [Material lots](/lots/): certificates are only available for released lots.
