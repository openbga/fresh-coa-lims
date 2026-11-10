---
title: Holds
urls: stability:hold_list
views: stability.views.hold_list
templates: ops/list.html
models: stability.Hold
reviewed: 2026-11-10
---

## Purpose

Holds that block QC disposition and disposal until a different quality signer releases them.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction and a **New hold** button for Analyst, Reviewer, Quality.
- **Toolbar**: **Search** (lot number, reference or reason) and **Status** (All, Active, Released). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Hold (links to the record), Lot, Kind, Reference, State, Placed. Sort by Placed (newest first by default) or Lot. Sortable headers toggle ascending/descending.
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
| Kind | `Hold.kind` | Investigation / Regulatory / Legal / Quality | — | Why the hold exists |

## Rules and hidden logic

- Active holds are shown with the hold tone and text.

## Related pages

- [Reserve samples](/stability/reserves/)
