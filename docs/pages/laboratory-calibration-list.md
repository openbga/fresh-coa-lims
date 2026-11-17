---
title: Calibrations
urls: laboratory:calibration_list
views: laboratory.views.calibration_list
templates: ops/list.html
models: laboratory.Calibration, laboratory.Equipment
reviewed: 2026-11-17
summary: Every recorded calibration across all equipment. See which are awaiting acceptance, accepted or failed, and accept one that someone else recorded.
---

## Common tasks
### Find calibrations
1. Type an asset ID in [[Search]].
2. To narrow by state, choose [[Awaiting acceptance]], [[Accepted]] or [[Failed]] in [[Status]].
3. Select [[Apply]], then select an asset to open its equipment record.
### Accept a calibration
1. Select [[Accept]] in the row. It shows only to a reviewer, on a calibration awaiting acceptance that someone else recorded.
2. Sign with your PIN on that page.
### Record a new calibration
1. Select the asset, then select [[Record calibration]] on the equipment record. It shows for the analyst and quality roles.
### See every calibration again
1. Select [[Clear all]] to remove the search and the status.
## Good to know
- A passing calibration counts toward fitness only after it is accepted. A failure counts as soon as it is recorded.
- Failed lists every failed calibration, accepted or not.
- Search matches the asset ID only.
- The most recently performed calibration comes first.

## Purpose

Every recorded calibration; the reviewer's queue of calibrations awaiting independent acceptance.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Read-only page: it has no create button. Calibrations are recorded from an equipment record by Analyst or Quality.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Equipment, Calibrations, Qualifications, Reagents and standards, Contract laboratories, Resource use. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Laboratory operations can use every section link.
- **Header**: title and introduction ("Every recorded calibration. Passing records count only after independent acceptance; failures block use as soon as they are recorded.").
- **Toolbar**: **Search** (equipment asset ID contains the text, max 100 characters) and **Status** (All, Awaiting acceptance, Accepted, Failed). **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Equipment, Performed, Due (inclusive), Outcome, State, Recorded by, Action. Sort by Performed (newest first by default), Equipment or Due. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Record a calibration from an equipment page."); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | — | Choice | No | Awaiting acceptance and Accepted filter on `Calibration.state`; Failed filters on outcome, whether or not accepted |
| Equipment | `Equipment.asset_id` | Link | — | Opens the equipment record |
| Performed | `Calibration.performed_at` | Date and time with zone | — | When the calibration was done |
| Due (inclusive) | `Calibration.due_date` | Date | — | Last day the calibration stays valid |
| Outcome / State | `Calibration.outcome`, `.state` | Pass or Fail; Awaiting acceptance or Accepted | — | Status labels |
| Recorded by | `Calibration.recorded_by` | User | — | Who entered it |
| Action | — | Link | — | **Accept** appears only for a Reviewer, on a record awaiting acceptance that they did not record |

## Rules and hidden logic

- **Order**: Performed, newest first, by default; ties break on record number. Unknown sort keys fall back to the default. All calibrations of all equipment are listed.
- Passing records count for fitness only once accepted; failures count immediately.
- The Accept link is a convenience; the server refuses the recorder and non-reviewers on the signing page.

## Related pages

- [Equipment](/laboratory/equipment/)
- Calibration acceptance page (open from the Accept link)
