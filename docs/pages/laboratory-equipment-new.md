---
title: New equipment
urls: laboratory:equipment_new
views: laboratory.views.equipment_new
templates: ops/form.html
models: laboratory.Equipment, core.AuditEvent
reviewed: 2026-11-17
summary: Register an instrument so its calibration, qualification and use can be tracked. Registration alone does not make it fit for use.
---

## Common tasks
### Register an instrument
1. Enter [[Asset id]], [[Description]] and [[Category]], and [[Location]] if known.
2. Leave [[Requires qualification]] ticked if the instrument needs approved qualification evidence before use.
3. Give a [[Reason]] and select [[Register equipment]]. The new equipment record opens.
### Leave without registering
1. Select [[Cancel]] to return to the Equipment list. Nothing is saved.
## Good to know
- New equipment is in service but not fit for use until a passing calibration is recorded and accepted by a different reviewer.
- With Requires qualification ticked, approved, current qualification evidence is also needed before the equipment can be used.
- The asset id, description, category, location and qualification setting cannot be changed after registration.
- Asset ids are unique. A duplicate is refused.

## Purpose

Register an instrument so calibration, qualification and use can be tracked. Registration does not make it fit for use.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; everyone else receives 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Laboratory, Equipment, New equipment), title, the introduction "Registration does not make equipment fit for use; calibration and any required qualification must be independently accepted.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Register equipment** | Always | Analyst or Quality; everyone else receives 403 | Saves and opens the new equipment record with "Equipment registered."; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Asset id | `Equipment.asset_id` | Text, max 60, unique | Yes | Your asset identifier; a duplicate is refused ("Equipment with this Asset id already exists.") |
| Description | `Equipment.description` | Text, max 160 | Yes | What it is |
| Category | `Equipment.category` | Text, max 80 | Yes | For example balance, HPLC, chamber |
| Location | `Equipment.location` | Text, max 120 | No | Where it is kept |
| Requires qualification | `Equipment.requires_qualification` | Checkbox, on by default | No | When on, approved current qualification evidence is also needed for fitness |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the registration |

## Rules and hidden logic

- New equipment starts In service, revision 1, with you recorded as creator. Writes the audit event `equipment.registered` with the full values. Asset IDs are unique and cannot be edited later.
- New equipment has no calibration, so it is not fit for use until a passing calibration is independently accepted.

## Related pages

- [Equipment](/laboratory/equipment/)
