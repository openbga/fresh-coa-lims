---
title: Stability pulls
urls: stability:pull_list
views: stability.views.pull_list
templates: ops/list.html
models: stability.Pull
reviewed: 2026-11-10
---

## Purpose

Pulls across active and closed studies, oldest due first; the work queue for overdue, due and unreviewed pulls.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Read-only page: there is no create control. Pulls are created when a study starts.

## Layout

- **Header**: title and the introduction "Scheduled pulls across active and closed studies, oldest due first."
- **Toolbar**: **Search** (study ID or lot number) and **Status** (All, Overdue, Due now, Upcoming, Awaiting acceptance, Accepted, Missed); Search is a contains match, case-insensitive. **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Pull (study identifier, condition and timepoint label; links to the pull record), Due, Window ("from to to" dates), Status, Tests (required test codes). Sort by Due (default; ties by pk), Study (study ID, then due date) or Status (stored state). Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Pulls appear when a study starts on an approved protocol."); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Pull | `Pull.study`, `Pull.timepoint` | Link | — | Study ID, condition and timepoint label |
| Due | `Pull.due_date` | Date | — | Time zero plus the timepoint interval |
| Window | `ProtocolTimepoint.window_days` | Dates | — | Due date minus and plus window days |
| Status | `Pull.state` | Label | — | Upcoming, Due, Overdue (scheduled pulls, by today's window); otherwise Pulled, Accepted or Missed |
| Tests | `ProtocolTimepoint.test_codes` | Codes | — | Tests required for the pull |
| Search | — | Text | No | Matches study ID or lot number |
| Status filter | — | Choice | No | See Layout |

## Rules and hidden logic

- Overdue, Due now and Upcoming apply to scheduled pulls only, using the local date: Overdue is after the window closes, Due now is inside the window, Upcoming is before it opens. Awaiting acceptance is state Pulled.
- Status is computed live over all pulls; sorting and paging run over the whole list. Page sizes 25, 50, 100.
- Study state is not filtered: pulls of closed studies stay listed.

## Related pages

- [Laboratory operations](/stability/)
- Study record (opened from a pull's study)
- Pull record (open a row)
