---
title: Stability protocols
urls: stability:protocol_list
views: stability.views.protocol_list
templates: ops/list.html
models: stability.Protocol
reviewed: 2026-11-17
summary: Every version of every stability protocol: draft, approved, superseded or withdrawn. Find a protocol, open its record, or draft a new one.
---

## Common tasks
### Find a protocol
1. Type a code, title or product in [[Search]].
2. To see only one state, choose it in [[Status]], for example Draft.
3. Select [[Apply]], then select a protocol to open its record.
### Draft a new protocol
1. Select [[New protocol]]. It shows only to analysts and quality users.
2. Fill in the header on that page and select [[Create draft]]. You add conditions and timepoints on the protocol record.
### See every protocol again
1. Select [[Clear all]] to remove the search and the status.
## Good to know
- Each version of a code is its own row. Approving a new version supersedes the earlier approved one, which stays readable.
- A code can have only one draft at a time. Approve or withdraw it before drafting the next version.
- Only a quality user who did not write the draft can approve it.
- Sorting by [[Approved]] orders protocols by when they were drafted, not when they were approved.

## Purpose

All versions of product-specific stability protocols, draft, approved and superseded. Conditions and schedules come from the approved protocol, never from a universal default.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Protocols, Studies, Pulls, Reserves, Holds. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Stability and retention can use every section link.
- **Header**: title and a **New protocol** button for Analyst, Quality. The introduction is below the title and action row.
- **Toolbar**: **Search** (code, title or product) and **Status** (All, Draft, Approved, Superseded, Withdrawn). **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Protocol (code and version, links to the record, with the title under it), Product, State, Approved (date). Approved is blank for drafts. Sort by Protocol (code then version, ascending by default), Product or Approved (sorts by creation time, not approval time). Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New protocol** | Your role can create it | Analyst, Quality | Opens the New protocol form |
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Protocol | `Protocol.code`, `.version` | "CODE vN" | — | Identifier; links to the record |
| Title / Product | `Protocol.title`, `.product` | Text | — | What the protocol covers |
| State | `Protocol.state` | Draft / Approved / Superseded / Withdrawn | — | Approved versions are frozen; approving a new version supersedes the old; a withdrawn draft is never approved |
| Approved | `Protocol.approved_at` | Date | — | Date of approval in the laboratory time zone |
| Search / Status | — | Text / All, Draft, Approved, Superseded, Withdrawn | No | Search matches code, title or product |

## Rules and hidden logic

- Every protocol is listed, with no default filter; 25 rows per page by default.
- Version numbers rise per code; only one draft per code can exist at a time.

## Related pages

- [Stability studies](/stability/studies/)
- [Stability and retention](/stability/)
- Protocol record (plain name: opened from the Protocol column)
