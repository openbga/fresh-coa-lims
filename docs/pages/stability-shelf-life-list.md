---
title: Shelf-life evaluations
urls: stability:shelf_life_list
views: stability.shelf_life_views.shelf_life_list
templates: ops/list.html
models: stability.ShelfLifeEvaluation, stability.ShelfLifeStudy
reviewed: 2026-11-19
summary: Every shelf-life evaluation: one test at one storage condition, fitted over the studies of a protocol and container closure. Find a draft, a concluded shelf life or a withdrawn draft. Quality drafts new ones.
---

## Common tasks

### Find an evaluation

1. Type a protocol code, product, test code, test name or storage condition in [[Search]].
2. To see only drafts, concluded or withdrawn evaluations, choose it in [[Status]], then select [[Apply]].
3. Select an evaluation to open its record.

### Start a new evaluation

1. Select [[New evaluation]]. Quality users see it.
2. Choose a study on the next page and continue.

### See every evaluation again

1. Select [[Clear all]] to remove the search and the status.

## Good to know

- The State column shows the shelf life recorded, for example "Concluded · 24 months", or "Concluded · none supported".
- Only one draft can exist for the same protocol, container closure, storage condition and test. Withdraw it before drafting another.
- Studies counts the studies the evaluation uses, not only those with enough results to be fitted.
- The newest draft comes first.

## Purpose

Lists the shelf-life evaluations. Each one finds where the 95 % confidence limit of the mean of one test's results meets its acceptance criterion, following the method of ICH Q1E. The laboratory decides which studies, conditions and tests to evaluate and what shelf life to record.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- **New evaluation** is shown only to Quality; the server refuses others with 403.
- Admin is read-only here: an account holding only the Admin role sees no action buttons.

## Layout

- **Section tabs**: Overview, Protocols, Studies, Pulls, Reserves, Holds, Shelf life. The current page is highlighted. Anyone who can read Stability and retention can use every section link.
- **Header**: title "Shelf-life evaluations", the **New evaluation** button for Quality, and an introduction saying what an evaluation is.
- **Toolbar**: **Search** and **Status** (Draft, Concluded, Withdrawn). **Apply** runs the filter; **Clear all** appears when a filter is set.
- **Table**: Evaluation (identifier, such as SLE-1, linking to the record, with the test name under it), Protocol (code, with the product under it), Storage condition, Studies (count), State and Drafted. Sort by Drafted (newest first by default) or Protocol.
- **Footer**: the count, **Rows per page** and a pager.
- **Empty state**: "Quality drafts an evaluation from a study whose pulls are tested in the system."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New evaluation** | You hold the quality role | Quality | Opens the new evaluation form |
| Evaluation link | Always | Any reader | Opens the evaluation record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text | No | Matches protocol code, product, test code, test name or storage condition (contains, not case sensitive) |
| Status | `ShelfLifeEvaluation.state` | Draft, Concluded, Withdrawn | No | Filters by state |
| Evaluation | `ShelfLifeEvaluation.pk`, `name` | Link | — | Identifier "SLE-n" and the test name |
| Protocol | `protocol_code`, `product` | Text | — | Protocol code and product |
| Storage condition | `condition` | Text | — | The condition whose results are evaluated |
| Studies | study links | Count | — | Studies the evaluation uses |
| State | `state`, `outcome`, `shelf_life_months` | Label | — | Draft; Withdrawn; "Concluded · N months"; "Concluded · none supported" |
| Drafted | `drafted_at` | Date and time | — | When the draft was made |

## Rules and hidden logic

- **Filters and order**: newest drafted first; ties break by record order. Filters and sort live in the address.
- **Permissions**: reading is open to the laboratory roles above; drafting is Quality only, checked again on the server.
- **State**: Draft becomes Concluded when signed or Withdrawn when withdrawn. Neither changes again.

## Related pages

- [Stability and retention](/stability/)
- New evaluation
- Evaluation record
- [Stability studies](/stability/studies/)
