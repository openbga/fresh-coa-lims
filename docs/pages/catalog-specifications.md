---
title: Specifications and methods: Specifications
urls: catalog:specifications
views: catalog.views.specification_list
templates: catalog/specification_list.html
models: catalog.Specification, catalog.SpecificationRevision, catalog.Material
reviewed: 2026-11-10
---

## Purpose

Lists every specification: the tests and limits a material must meet at a stage and scope. Start here to find a specification or create a new one.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New specification**: **quality** role only. Other viewers do not see the button.

## Layout

- **Intro**: "Approved, effective-dated specifications define the tests and limits each material must meet. Approved versions cannot be changed; create a new version instead."
- **Tabs**: Specifications, Methods, Materials (the current one is highlighted).
- **Filter bar**: **Search** (placeholder "Code, title or material"), **Stage** (default "All stages"), **Apply**, **Clear filters** when filtered.
- **Table**: Specification (code link with title below), Material, Stage, Scope, Versions, Status. Specification and Material headers sort.
- **Status cell**: "Has approved version" or "No approved version", plus "Draft pending" when any draft exists.
- **Footer**: "Showing X–Y of N specifications".
- **Empty states**: "No specifications yet" ("Create a material and an approved method first, then the specification that lists its tests and limits.") with a **New specification** button for quality; "No specifications match these filters" ("Change or clear the filters.") with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New specification** | Viewer has the quality role | Quality | Opens the New specification form |
| Specification code link | Row exists | Any viewer | Opens that specification |
| **Specifications / Methods / Materials** tabs | Always | Any viewer | Switch list |
| Column headers | Always | Any viewer | Sort by the column; activating it again reverses the order |

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
- **Paging**: 25 rows per page. The URL parameter `per_page` accepts 25, 50 or 100 (no on-page control); other values fall back to 25.
- **Permissions**: the page checks the read roles on the server; the New specification button is cosmetic for non-quality users, and the New specification page itself refuses them with 403.
- **Status**: counts are over all versions; "Withdrawn" versions are counted in Versions but not shown as a status.
- **Not enforced by this page**: it does not show whether an approved version is effective right now, only that one is approved.

## Related pages

- [Methods](/catalog/methods/)
- [Materials](/catalog/materials/)
- New specification, Specification (record page).
