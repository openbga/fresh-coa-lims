---
title: Sampling: Lots
urls: sampling:lots
views: sampling.views.lot_list
templates: sampling/lot_list.html
models: quality.Lot, sampling.LotAssignment, sampling.SamplingRecord
reviewed: 2026-11-17
summary: Lots for requirement assignment and sampling. Find a lot, see whether its requirements are assigned or on hold and how many samples it has, and open its sampling page.
---

## Common tasks
### Find a lot
1. Type a lot number or material in [[Search]].
2. To see only lots in one requirement state, choose it in [[Status]].
3. Select [[Apply]], then select a lot number to open its requirements and sampling.
### Find lots that still need requirements
1. In [[Status]], choose [[Not assigned]] or [[Applicability hold]], then select [[Apply]].
### Switch to the sampling plans
1. Select [[Sampling plans]] above the page title.
### See every lot again
1. Select [[Clear all]] to remove the search and the status.
## Good to know
- The Requirements column and the status filter use each lot's latest requirement assignment.
- The filter's "Requirements assigned" shows as "Assigned" in the Requirements column.
- "Awaiting quality assessment" means a sampling deviation still needs quality's signed assessment. Until it is accepted, it blocks QC disposition.
- Lots in every status are listed, not only those in quarantine. The newest lot record comes first.

## Purpose

Lists received lots with their requirement status and sample count, so analysts and quality can see which lots still need approved requirements or sampling.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view this list; the page has no actions.
- The page has no create actions; each lot opens its own sampling page.

## Layout

- **Section tabs**: Lots, Sampling plans. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view.
- **Header**: title "Sampling", followed by the introduction.
- **Intro**: "Assign approved specifications and sampling plans to received lots and record what was actually sampled. Lots without approved requirements stay on an applicability hold."
- **Filter bar**: **Search** (placeholder "Lot number or material"), **Status** (default "All statuses"; options "Requirements assigned", "Applicability hold", "Not assigned"), **Apply**, **Clear all** when filtered.
- **Table**: Lot (link, sortable), Material as received, Lot status, Requirements, Samples.
- **Lot status cell**: the lot's status label (Quarantine, Released, Rejected, Cancelled), as on the material lot list.
- **Requirements cell**: "Assigned", "Applicability hold" or "Not assigned", and below it "Awaiting quality assessment" (amber) while a current sampling record of the lot has a deviation not yet assessed by quality.
- **Footer**: "Showing X–Y of N lots", with "matching filters" when filtered; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons.
- **Empty states**: "No lots received yet" ("Receive a material lot first; it then appears here for requirement assignment and sampling.") with a **Go to lots** button; "No lots match these filters" with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Lot number link | Row exists | Any viewer | Opens the lot's requirements and sampling page |
| **Go to lots** | No lots exist | Any viewer | Opens the Material lots list |
| Lot header | Always | Any viewer | Sorts by lot number; activating again reverses |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text | No | Case-insensitive contains match on lot number or material as received. |
| Status | `LotAssignment.status` | Requirements assigned, Applicability hold, Not assigned | No | Filters on the latest assignment of each lot; "Not assigned" means none yet. |
| Lot | `Lot.number` | Text | — | Lot identifier. |
| Material as received | `Lot.material` | Text | — | Free text recorded when the lot was received. |
| Lot status | `Lot.state` | Quarantine, Released, Rejected, Cancelled | — | Disposition state. |
| Awaiting quality assessment | `SamplingRecord.deviation`, `DeviationReview.status` | Label | — | A current (not corrected) sampling record has a deviation with no assessment or one still awaiting quality; the same condition blocks QC disposition. |
| Samples | `SamplingRecord` | Count | — | Sampling records that are not corrections, that is, one per sample. |

## Rules and hidden logic

- **Order**: default is newest received first. Sort keys: lot number ascending or descending; the default is not a header toggle.
- **Latest assignment only**: Requirements and the Status filter use each lot's most recent assignment.
- **Paging**: 25 rows per page by default; **Rows per page** (or `per_page`) chooses 25, 50 or 100; other values fall back to 25.
- **Quarantined and released lots** are both listed.
- Labels differ slightly: the filter says "Requirements assigned", the table says "Assigned".

## Related pages

- [Sampling plans](/sampling/plans/)
- [Material lots](/lots/)
- Lot requirements and sampling (record page).
