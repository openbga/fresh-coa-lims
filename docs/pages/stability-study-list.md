---
title: Stability studies
urls: stability:study_list
views: stability.views.study_list
templates: ops/list.html
models: stability.Study
reviewed: 2026-11-19
summary: Every stability study, one per approved protocol, lot and container closure. Find a study, open its pull schedule, or start a new study.
---

## Common tasks
### Find a study
1. Type a study ID, lot number or product in [[Search]].
2. To see only one state, choose it in [[Status]].
3. Select [[Apply]], then select a study to open its record.
### Start a new study
1. Select [[New study]]. It shows only to analysts and quality users.
2. Choose the approved protocol and the lot on that page and select [[Start study]]. Its pulls are scheduled from time zero.
### See every study again
1. Select [[Clear all]] to remove the search and the status.
## Good to know
- The latest time zero comes first, not the study recorded most recently.
- Search covers study IDs, lot numbers and the protocol's product. It does not search the container closure.
- A second study with the same protocol, lot and container closure is refused.
- Completed and Terminated studies are closed. Their pulls take no more testing.

## Purpose

One study per approved protocol, lot and container closure; the entry point to each study's pulls.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; **New study** is shown only to Analyst and Quality and the server refuses others with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Protocols, Studies, Pulls, Reserves, Holds, Shelf life. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Stability and retention can use every section link.
- **Header**: title and a **New study** button for Analyst, Quality. The introduction is below the title and action row.
- **Toolbar**: **Search** (study ID, lot number or product) and **Status** (All, Active, Completed, Terminated). **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Study (links to the record, with the protocol identifier under it), Lot (links to the lot, with the protocol's product under it), Container closure, Time zero, State. Sort by Time zero (newest first by default), Study (identifier) or Lot (lot number). Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Start a study on an approved protocol to schedule its pulls."); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New study** | Your role can create it | Analyst, Quality | Opens the New study form |
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Study | `Study.identifier` | Text, link | — | Opens the study record |
| Lot / Protocol | `Study.lot`, `Study.protocol` | Lot number, protocol identifier | — | What is under study |
| Container closure / Time zero | `Study.container_closure`, `Study.start_date` | Text, date | — | Study design |
| State | `Study.state` | Active / Completed / Terminated | — | Closed studies are immutable |
| Search | — | Text | No | Matches study ID, lot number or the protocol's product |

## Rules and hidden logic

- Starting a study creates every pull implied by the protocol.
- Status filters on the stored state. Every study is listed regardless of lot or protocol state. Page sizes 25, 50, 100.

## Related pages

- [Stability pulls](/stability/pulls/)
- [Stability protocols](/stability/protocols/)
