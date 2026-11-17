---
title: Stability pulls
urls: stability:pull_list
views: stability.views.pull_list
templates: ops/list.html
models: stability.Pull
reviewed: 2026-11-17
summary: Every stability pull across active and closed studies, oldest due first. Find pulls that are due, overdue or awaiting acceptance and open their records.
---

## Common tasks
### Find pulls that need work
1. Choose a state in [[Status]], such as [[Due now]], [[Overdue]] or [[Awaiting acceptance]].
2. Select [[Apply]], then select a pull to open its record.
### Find the pulls of one study or lot
1. Type a study ID or lot number in [[Search]] and select [[Apply]].
### See pulls that failed their criteria
1. Choose [[Accepted, acceptance criteria not met]] in [[Status]] and select [[Apply]].
### See every pull again
1. Select [[Clear all]] to remove the search and the status.
## Good to know
- Pulls of closed studies stay listed. The overview's pull counts include active studies only.
- [[Accepted]] also lists pulls whose results did not meet the criteria. Accepted means reviewed, not conforming.
- Due now and Overdue apply only to pulls not yet taken, by today's date and the pull's window.
- Pulls are created when a study starts. There is no way to add one here.

## Purpose

Pulls across active and closed studies, oldest due first; the work queue for overdue, due and unreviewed pulls.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Read-only page: there is no create control. Pulls are created when a study starts.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Protocols, Studies, Pulls, Reserves, Holds. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Stability and retention can use every section link.
- **Header**: title and the introduction "Scheduled pulls across active and closed studies, oldest due first."
- **Toolbar**: **Search** (study ID or lot number) and **Status** (All, Overdue, Due now, Upcoming, Awaiting acceptance, Accepted, Accepted, acceptance criteria not met, Missed); Search is a contains match, case-insensitive. **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Pull (study identifier, condition and timepoint label; links to the pull record), Due, Window ("from to to" dates), Status, Tests (required test codes). Sort by Due (default; ties by pk), Study (study ID, then due date) or Status (stored state). Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Pulls appear when a study starts on an approved protocol."); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Pull | `Pull.study`, `Pull.timepoint` | Link | — | Study ID, condition and timepoint label |
| Due | `Pull.due_date` | Date | — | Time zero plus the timepoint interval |
| Window | `ProtocolTimepoint.window_days` | Dates | — | Due date minus and plus window days |
| Status | `Pull.state`, `Pull.outcome` | Label | — | Upcoming, Due now, Overdue (scheduled pulls, by today's window); otherwise Awaiting acceptance (pulled), Accepted or Missed: the same labels as the Status filter. An accepted pull tested in the system reads "Accepted · meets acceptance criteria" (success) or "Accepted · acceptance criteria not met" (danger) |
| Tests | `ProtocolTimepoint.test_codes` | Codes | — | Tests required for the pull |
| Search | — | Text | No | Matches study ID or lot number |
| Status filter | — | Choice | No | See Layout |

## Rules and hidden logic

- Overdue, Due now and Upcoming apply to scheduled pulls only, using the local date: Overdue is after the window closes, Due now is inside the window, Upcoming is before it opens. Awaiting acceptance is state Pulled. Accepted, acceptance criteria not met is state Accepted with the outcome "Does not meet the acceptance criteria"; the filter Accepted also lists those pulls.
- Status is computed live over all pulls; sorting and paging run over the whole list. Page sizes 25, 50, 100.
- Study state is not filtered: pulls of closed studies stay listed.

## Related pages

- [Laboratory operations](/stability/)
- Study record (opened from a pull's study)
- Pull record (open a row)
