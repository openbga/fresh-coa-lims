---
title: Reagents and standards
urls: laboratory:reagent_list
views: laboratory.views.reagent_list
templates: ops/list.html
models: laboratory.ReagentLot
reviewed: 2026-11-10
---

## Purpose

Reagent, reference-standard and prepared-solution lots with provenance, independent release and expiry gating.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction and a **New reagent lot** button for Analyst, Quality.
- **Toolbar**: **Search** (identifier, name or supplier lot) and **Status** (All, Awaiting release, Released for use, Expiring within 30 days, Released but expired, Rejected). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Identifier (links to the record), Name, Kind, Supplier lot, Expiry (last day of use), State. Sort by Identifier (default), Name or Expiry. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New reagent lot** | Your role can create it | Analyst, Quality | Opens the New reagent lot form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| State | `ReagentLot.state` | Label | — | Awaiting release, Released, Expiring soon, Expired or Rejected |

## Rules and hidden logic

- Expiry is the last day of use (inclusive). A lot is usable only when released, not rejected, not past expiry, not dated in the future, and not prepared (directly or through earlier preparations) from a rejected, unreleased or expired source.

## Related pages

- [Resource use](/laboratory/uses/)
- Reagent lot record
