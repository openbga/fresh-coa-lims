---
title: New material
urls: catalog:material_new
views: catalog.views.material_new
templates: catalog/form.html
models: catalog.Material
reviewed: 2026-11-11
---

## Purpose

Creates a controlled material or product that specifications and sampling plans can refer to.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.

## Layout

- **Breadcrumbs**: Specifications and methods, Materials, New material.
- **Intro**: "Material identity cannot be edited after creation; use synthetic names only."
- **Form sections**: Material, Change control.
- **Buttons**: **Cancel** (to Materials) and **Create material**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create material** | Always | Quality | Creates the material, shows "Material <code> created." and returns to the Materials list |
| **Cancel** | Always | Quality | Returns to Materials |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `Material.code` | Slug, max 60, unique | Yes | Help: "Short stable identifier, e.g. api-syn-001." |
| Name | `Material.name` | Text, max 160 | Yes | Material name. |
| Kind | `Material.kind` | Raw material or ingredient, Component or part, Packaging material, Intermediate or bulk, Finished product | Yes | Category. |
| Reason | audit event reason | Text, max 2000 | Yes | Stored in the audit event. |

## Rules and hidden logic

- **Code**: "This material code already exists." If another request saves the same code at the same moment (for example a double submission), the page shows "Another request saved a conflicting record at the same time. Reload and try again." and nothing is created.
- **Immutable**: after creation the code, name and kind cannot be edited or deleted (database trigger).
- **Audit**: `material.created` with your reason. No signature or approval step applies to materials.
- Assumption: material names should be synthetic in this environment, as the intro states; the page does not check the content.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- [Materials](/catalog/materials/)
