---
title: Holds
urls: stability:hold_list
views: stability.views.hold_list
templates: ops/list.html
models: stability.Hold
reviewed: 2026-11-11
---

## Purpose

All holds on lots and reserve samples. A hold blocks QC disposition (and any disposal) until a different Quality signer releases it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Protocols, Studies, Pulls, Reserves, Holds. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Stability and retention can use every section link.
- **Header**: title "Holds" and a **New hold** button for Analyst, Reviewer, Quality. The introduction is below the title and action row.
- **Toolbar**: **Search** (lot number, reference or reason; contains, not case sensitive) and **Status** (All, Active, Released). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Hold (links to the record), Lot, Kind, Reference, State, Placed. Placed shows date and time. Sort by Placed (newest first by default) or Lot; ties break by record order. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New hold** | Your role can create it | Analyst, Reviewer, Quality | Opens the New hold form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Hold | `Hold.pk` | HOLD-n | — | Identifier; links to the record |
| Lot | `Hold.lot` | Lot number | — | Lot held |
| Kind | `Hold.kind` | Investigation / Regulatory / Legal / Quality | — | Why the hold exists |
| Reference | `Hold.reference` | Text | — | Investigation, CAPA or matter ID |
| State | `Hold.state` | Active / Released | — | Active holds use the hold tone |
| Placed | `Hold.placed_at` | Date and time | — | When placed |
| Search / Status | — | Text / All, Active, Released | No | Filters |

## Rules and hidden logic

- All holds are listed (no default filter); 25 rows per page by default.
- The reserve sample a hold is limited to is not a column; open the record to see it.

## Related pages

- [Reserve samples](/stability/reserves/)
- [Stability and retention](/stability/)
- Hold record (plain name: opened from the Hold column)
