---
title: Calibrations
urls: laboratory:calibration_list
views: laboratory.views.calibration_list
templates: ops/list.html
models: laboratory.Calibration, laboratory.Equipment
reviewed: 2026-11-10
---

## Purpose

Every recorded calibration; the reviewer's queue of calibrations awaiting independent acceptance.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction.
- **Toolbar**: **Search** (equipment asset ID) and **Status** (All, Awaiting acceptance, Accepted, Failed). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Equipment, Performed, Due (inclusive), Outcome, State, Recorded by, Action. Sort by Performed (newest first by default), Equipment or Due. Sortable headers toggle ascending/descending.
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
| Status | — | Choice | No | Awaiting acceptance / Accepted by state; Failed by outcome |
| Action | — | Link | — | **Accept** appears for reviewers other than the recorder |

## Rules and hidden logic

- Passing records count for fitness only once accepted; failures count immediately.
- The Accept link is a convenience; the server refuses the recorder and non-reviewers.

## Related pages

- [Equipment](/laboratory/equipment/)
- Calibration acceptance page
