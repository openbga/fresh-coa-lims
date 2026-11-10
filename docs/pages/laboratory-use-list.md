---
title: Resource use
urls: laboratory:use_list
views: laboratory.views.use_list
templates: ops/list.html
models: laboratory.ResourceUse
reviewed: 2026-11-10
---

## Purpose

Append-only record of the eligible equipment and reagents used for work.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Reading is allowed for these roles; **New use** is hidden from everyone but Analyst, and the server refuses others on the form with 403.

## Layout

- **Header**: title, short introduction and a **New use** button for Analyst.
- **Toolbar**: **Search** (work ID, activity, test code, equipment asset ID or reagent lot identifier; case-insensitive "contains"). There is no Status filter. **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Used (time), Resource (links), Work, Activity, Test, By. Sort by Used (newest first by default) or Work. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Record the equipment and reagents used for a sample before testing.", with **New use** for Analysts); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New use** | Your role can create it | Analyst | Opens the New use form |
| **Apply** / **Clear filters** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Used | `ResourceUse.used_at` | Date and time with zone | — | When the use was recorded (server time) |
| Resource | `ResourceUse.equipment` or `.reagent_lot` | Link | — | Equipment asset ID or reagent lot identifier; each row has exactly one |
| Work | `ResourceUse.context_type`, `.context_id` | Text | — | Context type and the sample's internal record number (for example `quality.sample 12`), not its reference |
| Activity | `ResourceUse.activity` | Text | — | Method or activity the analyst was qualified for |
| Test | `ResourceUse.test_code` | Text | — | Test code, if given |
| By | `ResourceUse.used_by` | User | — | The analyst who recorded it |

## Rules and hidden logic

- **Order**: Used, newest first, by default; Work sorts by the work's record number as text. Ties break on record number. Unknown sort keys fall back to the default.
- Rows are written only by the use gate and cannot be edited or deleted (database guard). A use records the evidence relied on, but this list does not display it.
- Refused attempts are not listed here; they are audit events.

## Related pages

- [Equipment](/laboratory/equipment/)
- [Reagents and standards](/laboratory/reagents/)
