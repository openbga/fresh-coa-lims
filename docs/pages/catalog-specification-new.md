---
title: New specification
urls: catalog:specification_new
views: catalog.views.specification_new
templates: catalog/form.html
models: catalog.Specification, catalog.SpecificationRevision, catalog.Material
reviewed: 2026-11-10
---

## Purpose

Creates a specification (one material, one stage, one scope) together with its draft version 1. Tests are added afterwards on the version page.

## Who can use it

- Sign-in required. **quality** role only; any other signed-in user receives 403 Forbidden, including admins without the quality role.
- Independent approval comes later: another quality user must approve the version.

## Layout

- **Breadcrumbs**: Specifications and methods, New specification.
- **Intro**: "One specification covers one material at one stage for one scope. Version 1 starts as a draft; add tests, then ask another quality approver to sign it."
- **Form sections**: Specification, Basis, Effective period, Change control.
- **Buttons**: **Cancel** (back to the list) and **Create draft**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft** | Always | Quality | Creates the specification and draft version 1, shows "Specification created as draft version 1. Add its tests." and opens the new version page |
| **Cancel** | Always | Quality | Returns to the Specifications list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `Specification.code` | Slug (letters, numbers, hyphen, underscore), max 60, unique | Yes | Stable identifier. |
| Title | `Specification.title` | Text, max 200 | Yes | Descriptive title. |
| Material | `Specification.material` | Choice of all materials | Yes | Material the specification covers. |
| Stage | `Specification.stage` | Incoming material, In-process, Finished product, Stability | Yes | Stage of the material. |
| Scope | `Specification.scope` | Slug, max 60, default "general" | Yes | Help: "general, or a named market/customer overlay. Overlays are never merged." |
| Basis | `SpecificationRevision.basis` | Text | Yes | Help: "Scientific, compendial or contractual basis for these limits." |
| Effective from (time zone) | `SpecificationRevision.effective_from` | Date and time | Yes | Start of the effective period, inclusive. |
| Effective until (time zone) | `SpecificationRevision.effective_until` | Date and time | Yes | Exclusive end. Help text: "Exclusive end. Approved versions of one record must not overlap." |
| Reason for change | `SpecificationRevision.change_reason` | Text, max 2000 | Yes | Why this change is made; stored on the new record and in its audit event. |


## Rules and hidden logic

- **Uniqueness**: one specification per material, stage and scope. "A specification already exists for this material, stage and scope. Create a new version of it instead."
- **Code**: "This specification code already exists."
- **Interval**: "The effective end must be after the start." (form) and "The effective end must be after the effective start." (server).
- **Reason**: "A reason is required." if blank at the server.
- **Draft start**: the version is created as Draft, version 1, record revision 1, author = you. Draft content (basis, dates) is fixed at creation; to change it, create a new version.
- **Audit**: events `specification.created` and `specification_revision.created`, both with your reason. No signature yet.
- Date-time fields are labelled with the deployment time zone (setting `TIME_ZONE`, default UTC) and shown in it.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- [Specifications](/catalog/)
- Specification version (record page, opened after creation), where tests are added.
- [Materials](/catalog/materials/): a material must exist first.
