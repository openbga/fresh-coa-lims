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
- Reading is allowed for these roles; **New qualification** is hidden from Admin and Auditor, whom the server also refuses with 403.

## Layout

- **Header**: title, short introduction and a **New qualification** button for Analyst, Reviewer, Quality.
- **Toolbar**: **Search** (activity, the person's username, or the equipment asset ID; case-insensitive "contains") and **Status** (All, Awaiting approval, Approved, Expiring within 30 days, Expired, Revoked). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Activity (links to the record), Subject, Type (Analyst or Equipment), Valid from, Valid until (inclusive), State. Sort by Recorded (newest first by default; there is no Recorded column), Valid until or Activity. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Record controlled training evidence for an analyst and activity.", with **New qualification**); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New qualification** | Your role can create it | Analyst, Reviewer, Quality | Opens the New qualification form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | — | Choice | No | Awaiting approval and Revoked match the stored state. Approved: approved and not past Valid until. Expiring: approved with Valid until from today to 30 days ahead. Expired: approved but past Valid until |
| Activity / Subject / Type | `Qualification.activity`, `.user`, `.equipment` | Text | — | Subject is the username or the asset ID; Type is Analyst or Equipment |
| Valid from / Valid until (inclusive) | `Qualification.valid_from`, `.valid_until` | Dates | — | Validity window |
| State | `Qualification.state` | Label | — | Awaiting approval, Approved, Expired (shown for approved records past their last day) or Revoked |

## Rules and hidden logic

- Expired is shown for an approved qualification whose last valid day has passed.
- **Order**: by recorded time, newest first, unless you sort; ties break on record number. Unknown sort keys fall back to the default.
- Not enforced by this list: Approved does not check Valid from, so an approved record that has not started yet still reads Approved (it does not qualify anyone until its start date).

## Related pages

- [Laboratory operations](/laboratory/)
- Qualification record
