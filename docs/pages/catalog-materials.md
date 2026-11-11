---
title: Specifications and methods: Materials
urls: catalog:materials
views: catalog.views.material_list
templates: catalog/material_list.html
models: catalog.Material, catalog.Specification
reviewed: 2026-11-10
---

## Purpose

Lists the controlled materials and products that specifications and sampling plans apply to.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New material**: **quality** role only; hidden for others.

## Layout

- **Intro**: "Controlled materials and products that specifications and sampling plans apply to."
- **Tabs**: Specifications, Methods, Materials.
- **Filter bar**: **Search** (placeholder "Code or name"), **Apply**, **Clear filters** when filtered.
- **Table**: Material (code), Name, Kind, Specifications (count), Created (date). Material and Name headers sort.
- **Footer**: "Showing X–Y of N materials".
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
- **Paging**: 25 rows per page; `per_page` accepts 25, 50 or 100.
- **No material record page** exists; materials cannot be edited or deleted (immutable at the database level).
- **Count link**: the specification search matches code text containing the material code, so it can also list specifications of materials with similar codes.

## Related pages

- [Specifications](/catalog/)
- [Methods](/catalog/methods/)
- New material.
