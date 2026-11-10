---
title: Reserve samples
urls: stability:reserve_list
views: stability.views.reserve_list
templates: ops/list.html
models: stability.ReserveSample
reviewed: 2026-11-10
---

## Purpose

Identified reserve samples with quantity against the configured minimum. Nothing here can be disposed of.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction and a **New reserve sample** button for Analyst, Quality.
- **Toolbar**: **Search** (identifier or lot number) and **Status** (All, Below minimum quantity). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Reserve (links to the record), Lot, Quantity, Retained, Location, Quantity check. Sort by Retained (newest first by default), Identifier or Lot. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New reserve sample** | Your role can create it | Analyst, Quality | Opens the New reserve sample form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Quantity check | `ReserveSample.minimum_multiple` | Label | — | Meets minimum or Below minimum |

## Rules and hidden logic

- Quantity is compared with the minimum multiple times the quantity for one test set.

## Related pages

- [Holds](/stability/holds/)
- Reserve record
