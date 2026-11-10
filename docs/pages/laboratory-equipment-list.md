---
title: Equipment
urls: laboratory:equipment_list
views: laboratory.views.equipment_list
templates: ops/list.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.Qualification
reviewed: 2026-11-10
---

## Purpose

Find equipment and see at a glance whether it is fit for use today.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.

## Layout

- **Header**: title, short introduction and a **New equipment** button for Analyst, Quality.
- **Toolbar**: **Search** (asset ID, description or category contains the text) and **Status** (All, Ready, Calibration due soon, Calibration overdue, Not calibrated or qualified, Out of service). **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Asset (links to the record), Description, Category, Location, Calibration due, Fitness. Sort by Asset (default), Category, Calibration due or Fitness. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" with a next step; "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New equipment** | Your role can create it | Analyst, Quality | Opens the New equipment form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches asset ID, description or category |
| Status | — | Choice | No | Filters on the fitness label |
| Calibration due | `Calibration.due_date` | Date (inclusive last day) | — | Due date of the latest deciding calibration |
| Fitness | `Equipment.state` | Label | — | Ready, Due soon, Calibration overdue, Calibration failed, Not calibrated, Not qualified or Out of service |

## Rules and hidden logic

- **Order**: asset ID by default; ties break on record number. Unknown sort keys fall back to the default.
- **Fitness** is derived from the latest calibration that counts (any failure, or a passing one that was independently accepted), the due date, qualification evidence when the equipment requires it, and the service state. A passing calibration awaiting acceptance does not count.
- Filters run over the whole list, not the current page.

## Related pages

- [Calibrations](/laboratory/calibrations/)
- [Laboratory operations](/laboratory/)
- Equipment record (open from the asset link)
