---
title: Stability studies
urls: stability:study_list
views: stability.views.study_list
templates: ops/list.html
models: stability.Study
reviewed: 2026-11-10
---

## Purpose

One study per approved protocol, lot and container closure.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction and a **New study** button for Analyst, Quality.
- **Toolbar**: **Search** (study ID, lot number or product) and **Status** (All, Active, Completed, Terminated). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Study (links to the record), Lot, Protocol, Container closure, Time zero, State. Sort by Time zero (newest first by default), Study or Lot. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New study** | Your role can create it | Analyst, Quality | Opens the New study form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| State | `Study.state` | Active / Completed / Terminated | — | Closed studies are immutable |

## Rules and hidden logic

- Starting a study creates every pull implied by the protocol.

## Related pages

- [Stability pulls](/stability/pulls/)
- [Stability protocols](/stability/protocols/)
