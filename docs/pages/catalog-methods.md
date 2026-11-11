---
title: Specifications and methods: Methods
urls: catalog:methods
views: catalog.views.method_list
templates: catalog/method_list.html
models: catalog.Method, catalog.MethodRevision
reviewed: 2026-11-10
---

## Purpose

Lists the analytical methods that tests rely on, each linked to a controlled procedure and suitability evidence.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New method**: **quality** role only; hidden for others.

## Layout

- **Intro**: "Methods link each test to a controlled procedure and evidence that it is suitable for its intended use."
- **Tabs**: Specifications, Methods, Materials.
- **Filter bar**: **Search** (placeholder "Code or title"), **Apply**, **Clear filters** when filtered.
- **Table**: Method (code link, sortable), Title, Versions, Status ("Has approved version" or "No approved version", plus "Draft pending").
- **Footer**: "Showing X–Y of N methods", with Previous / Next when there are several pages.
- **Empty states**: "No methods yet" ("Add the first method and link its controlled procedure and suitability evidence.") with **New method** for quality; "No methods match these filters" ("Change or clear the filters.") with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New method** | Viewer has the quality role | Quality | Opens the New method form |
| Method code link | Row exists | Any viewer | Opens the method |
| Method header | Always | Any viewer | Toggles code order ascending/descending |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text | No | Case-insensitive contains match on code or title. |
| Method | `Method.code` | Text | — | Identifier. |
| Title | `Method.title` | Text | — | Method title. |
| Versions | — | Count | — | All versions, any status. |
| Status | `MethodRevision.status` | Computed | — | Whether an approved or draft version exists. |

## Rules and hidden logic

- **Order**: code ascending by default; `sort` accepts code or -code.
- **Paging**: 25 rows per page; `per_page` accepts 25, 50 or 100.
- **Permissions**: read roles checked on the server; New method also enforced on its own page.
- **Not enforced by this page**: "Has approved version" does not mean the version is effective now.

## Related pages

- [Specifications](/catalog/)
- [Materials](/catalog/materials/)
- New method, Method (record page).
