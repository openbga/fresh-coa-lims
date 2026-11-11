---
title: Reserve samples
urls: stability:reserve_list
views: stability.views.reserve_list
templates: ops/list.html
models: stability.ReserveSample
reviewed: 2026-11-10
---

## Purpose

Identified reserve samples with quantity against the minimum multiple of one test set, plus their retention obligations and holds on each record. Nothing here can be disposed of.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; **New reserve sample** is shown only to Analyst and Quality and the server refuses others with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: title, short introduction and a **New reserve sample** button for Analyst, Quality.
- **Toolbar**: **Search** (reserve identifier or lot number, contains, case-insensitive) and **Status** (All, Below minimum quantity). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Reserve (links to the record), Lot, Quantity, Retained, Location, Quantity check. Quantity is the retained amount with its unit. Sort by Retained (newest first by default), Reserve (identifier) or Lot (lot number). Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Record a reserve sample to track its quantity, retention and holds."); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New reserve sample** | Your role can create it | Analyst, Quality | Opens the New reserve sample form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
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
