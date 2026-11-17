---
title: Reserve samples
urls: stability:reserve_list
views: stability.views.reserve_list
templates: ops/list.html
models: stability.ReserveSample
reviewed: 2026-11-17
summary: Every identified reserve sample, with its quantity against the minimum, retention date and any active hold. Find a reserve, open its record, or record a new one.
---

## Common tasks
### Find a reserve sample
1. Type a reserve identifier or lot number in [[Search]] and select [[Apply]].
2. Select a reserve to open its record.
### Find reserves below the minimum quantity
1. Choose [[Below minimum quantity]] in [[Status]] and select [[Apply]].
### Record a new reserve sample
1. Select [[New reserve sample]]. It shows only to analysts and quality users.
2. Fill in the reserve on that page and select [[Record reserve sample]].
## Good to know
- Nothing on this page disposes of a reserve. No disposal action exists in this system yet.
- [[Retain through]] stays blank while any of the reserve's obligations has no anchor date, or when none is recorded.
- [[Hold]] shows Active for a hold on the reserve or on its whole lot.
- A reserve exactly at the minimum meets it. Only a smaller quantity is below minimum.

## Purpose

Identified reserve samples with quantity against the minimum multiple of one test set, plus their retention obligations and holds on each record. Nothing here can be disposed of.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; **New reserve sample** is shown only to Analyst and Quality and the server refuses others with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Protocols, Studies, Pulls, Reserves, Holds. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Stability and retention can use every section link.
- **Header**: title and a **New reserve sample** button for Analyst, Quality. The introduction is below the title and action row.
- **Toolbar**: **Search** (reserve identifier or lot number, contains, case-insensitive) and **Status** (All, Below minimum quantity). **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Reserve (links to the record, with the lot number under it), Quantity, Retained, Location, Quantity check, Retain through (the latest date any of its retention obligations retains it to; blank while an obligation has no anchor date yet, or when none is recorded), Hold ("Active" when an active hold applies to the reserve or to its whole lot). Quantity is the retained amount with its unit. Sort by Retained (newest first by default), Reserve (identifier) or Lot (lot number). Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Record a reserve sample to track its quantity, retention and holds."); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New reserve sample** | Your role can create it | Analyst, Quality | Opens the New reserve sample form |
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reserve | `ReserveSample.identifier` | Text, link | — | Opens the record |
| Quantity / Retained / Location | `ReserveSample.quantity`, `.quantity_unit`, `.retained_on`, `.storage_location` | Decimal with unit, date, text | — | As recorded |
| Quantity check | `ReserveSample.minimum_multiple` | Label | — | Meets minimum or Below minimum |

## Rules and hidden logic

- Quantity is compared with the minimum multiple times the quantity for one test set. The **Below minimum quantity** filter lists reserves with quantity strictly below that product; a reserve at exactly the minimum meets it.
- Not filtered by lot state or role; every reserve is listed. Page sizes 25, 50, 100.

## Related pages

- [Holds](/stability/holds/)
- Reserve record (open a row)
- New reserve sample
