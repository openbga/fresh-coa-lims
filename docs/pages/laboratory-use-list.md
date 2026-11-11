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
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: title, short introduction and a **New use** button for Analyst.
- **Toolbar**: **Search** (a sample reference or work ID, activity, test code, equipment asset ID or reagent lot identifier; case-insensitive "contains"; searching a sample reference finds the uses recorded for that sample, whether the work was recorded against the sample or against one of its native analytical tests; every matching record is searched, with no cap). There is no Status filter. **Apply** runs the filter; **Clear filters** appears when any filter is set. Filters and sort live in the address.
- **Table**: Used (time), Resource (links), Work, Activity, Test, By. Sort by Used (newest first by default). Sortable headers toggle ascending/descending.
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
| Work | `ResourceUse.context_type`, `.context_id` | Text or link | — | The sample reference for sample work (links to its lot); only the recognized sample and analytical-test context types are resolved, and any other type (or an unresolvable ID) is shown unchanged as its raw context type and ID; so is a recognized type whose ID is not a plain record number, such as one with a leading zero, a non-ASCII digit or an oversized value, for example `external.batch EXT-9` |
| Activity | `ResourceUse.activity` | Text | — | Method or activity the analyst was qualified for |
| Test | `ResourceUse.test_code` | Text | — | Test code, if given |
| By | `ResourceUse.used_by` | User | — | The analyst who recorded it |

## Rules and hidden logic

- **Order**: Used, newest first, by default; only Used is sortable. Ties break on record number. Unknown sort keys fall back to the default.
- Rows are written only by the use gate and cannot be edited or deleted (database guard). A use records the evidence relied on, but this list does not display it.
- Refused attempts are not listed here; they are audit events.

## Related pages

- [Equipment](/laboratory/equipment/)
- [Reagents and standards](/laboratory/reagents/)
