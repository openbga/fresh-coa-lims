---
title: Equipment
urls: laboratory:equipment_list
views: laboratory.views.equipment_list
templates: ops/list.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.Qualification
reviewed: 2026-11-17
summary: Every registered instrument with its fitness for use today. Find equipment, see when its calibration is due and open its record, or register new equipment.
---

## Common tasks
### Find equipment
1. Type an asset ID, description or category in [[Search]].
2. To see one fitness state only, choose it in [[Status]], for example [[Calibration overdue]] or [[Out of service]].
3. Select [[Apply]], then select an asset to open its record.
### Register new equipment
1. Select [[New equipment]]. It shows only for the analyst and quality roles.
2. Fill in the form on that page. The equipment is not fit for use until a passing calibration is accepted.
### See every item again
1. Select [[Clear all]] to remove the search and the status.
## Good to know
- A passing calibration counts only after a different reviewer accepts it. Until then it does not change the fitness shown here.
- A failed calibration counts as soon as it is recorded and takes the equipment out of service.
- Fitness is checked in this order: out of service, not calibrated, calibration failed, overdue, not qualified, due soon, ready. Overdue and unqualified equipment shows Calibration overdue.
- Due soon means the calibration due date, the last valid day, is within 30 days.
- Search does not cover the location.

## Purpose

Find equipment and see at a glance whether it is fit for use today.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; the New control is hidden from roles that cannot use it and the server refuses them with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Equipment, Calibrations, Qualifications, Reagents and standards, Contract laboratories, Resource use. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Laboratory operations can use every section link.
- **Header**: title and a **New equipment** button for Analyst, Quality. The introduction is below the title and action row.
- **Toolbar**: **Search** (asset ID, description or category contains the text) and **Status** (All, Ready, Calibration due soon, Calibration overdue, Not calibrated or qualified, Out of service). **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Asset (links to the record), Description, Category, Location, Calibration due, Fitness. Sort by Asset (default), Category, Calibration due or Fitness (the Fitness sort orders by service state, then asset, not by the label text). Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Register an instrument to track calibration, qualification and use.", with **New equipment** for roles that can register); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New equipment** | Your role can create it | Analyst, Quality | Opens the New equipment form |
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches asset ID, description or category |
| Status | — | Choice | No | Ready (due in more than 30 days), Calibration due soon (0 to 30 days), Calibration overdue, Not calibrated or qualified (no counted calibration, latest failed, or passing and current but unqualified), Out of service. Overdue, due soon and ready apply to in-service equipment with a passing latest calibration; due soon and ready also need qualification when it is required |
| Asset / Description / Category / Location | `Equipment.asset_id`, `.description`, `.category`, `.location` | Text | — | Identity; the asset links to the record |
| Calibration due | `Calibration.due_date` | Date (inclusive last day) | — | Due date of the latest deciding calibration; blank when none. Shows the failed calibration's due date when the latest one failed |
| Fitness | `Equipment.state` and calibration and qualification evidence | Label | — | Out of service, Not calibrated, Calibration failed, Calibration overdue, Not qualified, Due soon (due within 30 days) or Ready, checked in that order |

## Rules and hidden logic

- **Order**: asset ID by default; ties break on record number. Unknown sort keys fall back to the default.
- **Fitness** is derived from the latest calibration that counts (any failure, or a passing one that was independently accepted), the due date, qualification evidence when the equipment requires it, and the service state. A passing calibration awaiting acceptance does not count.
- Filters run over the whole list, not the current page. Search is a case-insensitive "contains" match.
- Equipment with a passing calibration that is overdue and also unqualified is labelled and filtered as Calibration overdue.

## Related pages

- [Calibrations](/laboratory/calibrations/)
- [Laboratory operations](/laboratory/)
- Equipment record (open from the asset link)
