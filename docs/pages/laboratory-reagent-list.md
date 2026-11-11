---
title: Reagents and standards
urls: laboratory:reagent_list
views: laboratory.views.reagent_list
templates: ops/list.html
models: laboratory.ReagentLot
reviewed: 2026-11-10
---

## Purpose

Reagent, reference-standard and prepared-solution lots with provenance, independent release and expiry gating.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: title, short introduction and a **New reagent lot** button for Analyst, Quality.
- **Toolbar**: **Search** (identifier, name or supplier lot; case-insensitive "contains") and **Status** (All, Awaiting release, Released for use, Expiring within 30 days, Released but expired, Rejected). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Identifier (links to the record), Name, Kind, Supplier lot, Expiry (last day of use), State. Sort by Identifier (default), Name or Expiry. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Record a received reagent or standard lot, or a prepared solution.", with **New reagent lot** for roles that can record); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New reagent lot** | Your role can create it | Analyst, Quality | Opens the New reagent lot form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | — | Choice | No | Awaiting release and Rejected match the stored state. Released for use: released and not past expiry. Expiring within 30 days: released, expiry from today to 30 days ahead. Released but expired: released and past expiry |
| Identifier / Name / Kind / Supplier lot | `ReagentLot.identifier`, `.name`, `.kind`, `.lot_number` | Text; Reagent, Reference standard or Prepared solution | — | Identity; the identifier links to the record |
| Expiry (last day of use) | `ReagentLot.expiry_date` | Date, inclusive | — | Last day the lot may be used |
| State | `ReagentLot.state`, `.expiry_date` | Label | — | Rejected, Awaiting release, Expired, Expiring soon (within 30 days) or Released, checked in that order |

## Rules and hidden logic

- **Order**: Identifier by default; ties break on record number. Unknown sort keys fall back to the default.
- The State label looks at this lot only. It does not show a rejected, unreleased or expired source lot of a prepared solution, nor a future receipt date; the gate below does.
- Expiry is the last day of use (inclusive). A lot is usable only when released, not rejected, not past expiry, not dated in the future, and not prepared (directly or through earlier preparations) from a rejected, unreleased or expired source.

## Related pages

- [Resource use](/laboratory/uses/)
- Reagent lot record
