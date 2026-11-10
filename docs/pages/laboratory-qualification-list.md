---
title: Qualifications
urls: laboratory:qualification_list
views: laboratory.views.qualification_list
templates: ops/list.html
models: laboratory.Qualification
reviewed: 2026-11-10
---

## Purpose

Approved training and qualification evidence by activity or method, for analysts and equipment. Group membership alone never qualifies anyone.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction and a **New qualification** button for Analyst, Reviewer, Quality.
- **Toolbar**: **Search** (activity, username or asset ID) and **Status** (All, Awaiting approval, Approved, Expiring within 30 days, Expired, Revoked). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Activity (links to the record), Subject, Type (Analyst or Equipment), Valid from, Valid until (inclusive), State. Sort by Recorded (newest first by default), Valid until or Activity. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New qualification** | Your role can create it | Analyst, Reviewer, Quality | Opens the New qualification form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | — | Choice | No | Approved means approved and not past Valid until; Expired means approved but past it |

## Rules and hidden logic

- Expired is shown for an approved qualification whose last valid day has passed.

## Related pages

- [Laboratory operations](/laboratory/)
- Qualification record
