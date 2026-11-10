---
title: Stability pulls
urls: stability:pull_list
views: stability.views.pull_list
templates: ops/list.html
models: stability.Pull
reviewed: 2026-11-10
---

## Purpose

Scheduled pulls across studies, oldest due first; the work queue for overdue, due and unreviewed pulls.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction.
- **Toolbar**: **Search** (study ID or lot number) and **Status** (All, Overdue, Due now, Upcoming, Awaiting acceptance, Accepted, Missed). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Pull (study and timepoint, links to the record), Due, Window, Status, Tests. Sort by Due (default), Study or State. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Window | `ProtocolTimepoint.window_days` | Dates | — | Due date ± window days |

## Rules and hidden logic

- Overdue, Due and Upcoming apply to scheduled pulls; the status is computed live over all pulls.

## Related pages

- [Laboratory operations](/stability/)
- Study record
