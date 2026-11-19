---
title: Specifications and methods: Materials
urls: catalog:materials
views: catalog.views.material_list
templates: catalog/material_list.html
models: catalog.Material, catalog.Specification
reviewed: 2026-11-19
summary: Every controlled material and product that specifications and sampling plans apply to. Find a material, see how many specifications it has, or create a new one.
---

## Common tasks
### Find a material
1. Type part of a material code or name in [[Search]], then select [[Apply]].
2. To change the order, select the [[Material]] column heading (it sorts by name).
### Create a material
1. Select [[New material]]. It shows only to users with the quality role.
2. Enter the code, name, kind and a reason on that page.
### See the specifications of a material
1. Select the number in the [[Specifications]] column. The Specifications list opens, searched by that material code.
### See every material again
1. Select [[Clear all]] to remove the search.
## Good to know
- Materials have no record page and are never edited or deleted. Check the code, name and kind before you create one.
- Search covers material codes and names only.
- The specification count opens a search by code text, so it can also list specifications of materials whose codes contain this one.
- The count includes every specification of the material, with or without an approved version.

## Purpose

Lists the controlled materials and products that specifications and sampling plans apply to.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New material**: **quality** role only; hidden for others.

## Layout

- **Section tabs**: Specifications, Methods, Method evidence, Proficiency testing, Materials. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view.
- **Header**: title "Specifications and methods" and the **New material** button for quality, with the introduction below.
- **Intro**: "Controlled materials and products that specifications and sampling plans apply to."
- **Filter bar**: **Search** (placeholder "Code or name"), **Apply**, **Clear all** when filtered.
- **Table**: Material (its kind's icon, name and code), Kind, Specifications (count), Created (date). The Material header sorts by name. **Columns** (beside Rows per page) chooses which columns show and their order, saved for your account; the less important columns give way first when the table does not fit.
- **Footer**: "Showing X–Y of N materials", with "matching filters" when filtered; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons.
- **Empty states**: "No materials yet" ("Create the first controlled material or product.") with **New material** for quality; "No materials match these filters" ("Change or clear the filters.") with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New material** | Quality role | Quality | Opens the New material form |
| Specifications count link | Count above 0 | Any viewer | Opens the Specifications list searched by this material code |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text | No | Case-insensitive contains match on code or name. |
| Material | `Material.code` | Text | — | Identifier. |
| Name | `Material.name` | Text | — | Material name. |
| Kind | `Material.kind` | Raw material or ingredient, Component or part, Packaging material, Intermediate or bulk, Finished product | — | Category. |
| Specifications | — | Count | — | Number of specifications for the material. |
| Created | `Material.created_at` | Date | — | Creation date. |

## Rules and hidden logic

- **Order**: code ascending by default. Sort keys: code and name, each ascending or descending.
- **Paging**: 25 rows per page by default; **Rows per page** (or `per_page`) chooses 25, 50 or 100; other values fall back to 25.
- **No material record page** exists; materials cannot be edited or deleted (immutable at the database level).
- **Count link**: the specification search matches code text containing the material code, so it can also list specifications of materials with similar codes.

## Related pages

- [Specifications](/catalog/)
- [Methods](/catalog/methods/)
- New material.
