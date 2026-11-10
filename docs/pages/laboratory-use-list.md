---
title: Resource use
urls: laboratory:use_list
views: laboratory.views.use_list
templates: ops/list.html
models: laboratory.ResourceUse
reviewed: 2026-11-10
---

## Purpose

Append-only record of the eligible equipment and reagents used for work.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction and a **New use** button for Analyst.
- **Toolbar**: **Search** (work/sample ID, activity, test code, asset ID or lot identifier). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Used (time), Resource (links), Work, Activity, Test, By. Sort by Used (newest first by default) or Work. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New use** | Your role can create it | Analyst | Opens the New use form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Work | `ResourceUse.context_type`, `.context_id` | Text | — | For example quality.sample and its ID |
| Activity | `ResourceUse.activity` | Text | — | Method or activity the analyst was qualified for |

## Rules and hidden logic

- Rows are written only by the use gate and cannot be edited or deleted.

## Related pages

- [Equipment](/laboratory/equipment/)
- [Reagents and standards](/laboratory/reagents/)
