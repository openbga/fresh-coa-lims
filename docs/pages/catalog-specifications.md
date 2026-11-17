---
title: Specifications and methods: Specifications
urls: catalog:specifications
views: catalog.views.specification_list
templates: catalog/specification_list.html
models: catalog.Specification, catalog.SpecificationRevision, catalog.Material
reviewed: 2026-11-17
summary: Every specification: the tests and limits a material must meet at one stage and scope. Find a specification, see whether it has an approved version, or create a new one.
---

## Common tasks
### Find a specification
1. Type part of a specification code, title or material code in [[Search]].
2. To see one stage only, choose it in [[Stage]], then select [[Apply]].
3. Select a specification code to open its record.
### Create a specification
1. Select [[New specification]]. It shows only to users with the quality role.
2. Choose the material, stage and scope and create draft version 1 on that page.
### Find methods or materials
1. Select the [[Methods]] or [[Materials]] tab above the list.
### See every specification again
1. Select [[Clear all]] to remove the search and the stage.
## Good to know
- Search matches material codes, not material names.
- Has approved version means a version was signed, not that one applies today. Open the specification to see the version in force.
- Draft pending means at least one draft is waiting to be approved or withdrawn.
- Versions counts every version, including withdrawn ones.

## Purpose

Lists every specification: the tests and limits a material must meet at a stage and scope. Start here to find a specification or create a new one.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New specification**: **quality** role only. Other viewers do not see the button.

## Layout

- **Section tabs**: Specifications, Methods, Materials. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view.
- **Header**: title "Specifications and methods" and the **New specification** button for quality, with the introduction below.
- **Intro**: "Approved, effective-dated specifications define the tests and limits each material must meet. Approved versions cannot be changed; create a new version instead."
- **Filter bar**: **Search** (placeholder "Code, title or material"), **Stage** (default "All stages"), **Apply**, **Clear all** when filtered.
- **Table**: Specification (code link with title below), Material (its kind's icon, name and code), Stage, Scope, Versions, Status. Specification and Material headers sort. **Columns** (beside Rows per page) chooses which columns show and their order, saved for your account; the less important columns give way first when the table does not fit.
- **Status cell**: "Has approved version" or "No approved version", plus "Draft pending" when any draft exists.
- **Footer**: "Showing X–Y of N specifications", with "matching filters" when filtered; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons.
- **Empty states**: "No specifications yet" ("Create a material and an approved method first, then the specification that lists its tests and limits.") with a **New specification** button for quality; "No specifications match these filters" ("Change or clear the filters.") with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New specification** | Viewer has the quality role | Quality | Opens the New specification form |
| Specification code link | Row exists | Any viewer | Opens that specification |
| **Specifications / Methods / Materials** tabs | Always | Any viewer | Switch list |
| **Specification** and **Material** headers | Always | Any viewer | Sort by that column; activating it again reverses the order. The other columns do not sort |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text | No | Case-insensitive contains match on specification code, title or material code. |
| Stage | `Specification.stage` | Incoming material, In-process, Finished product, Stability | No | Exact stage filter; an unknown value is ignored. |
| Specification | `Specification.code`, `Specification.title` | Text | — | Identifier and title. |
| Material | `Material.code` | Text | — | Material the specification applies to. |
| Scope | `Specification.scope` | Text | — | "general" or a named market/customer overlay. |
| Versions | — | Count | — | Number of versions of any status. |
| Status | `SpecificationRevision.status` | Computed | — | Approved/draft presence as described above. |

## Rules and hidden logic

- **Filters and order**: default sort is specification code ascending; sort keys are code and material (material code then specification code), each ascending or descending. The sort is kept when you apply a filter.
- **Paging**: 25 rows per page by default; **Rows per page** (or `per_page`) chooses 25, 50 or 100; other values fall back to 25.
- **Permissions**: the page checks the read roles on the server; the New specification button is cosmetic for non-quality users, and the New specification page itself refuses them with 403.
- **Status**: counts are over all versions; "Withdrawn" versions are counted in Versions but not shown as a status.
- **Not enforced by this page**: it does not show whether an approved version is effective right now, only that one is approved.

## Related pages

- [Methods](/catalog/methods/)
- [Materials](/catalog/materials/)
- New specification, Specification (record page).
