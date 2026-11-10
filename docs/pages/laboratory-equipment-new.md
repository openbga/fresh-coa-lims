---
title: New equipment
urls: laboratory:equipment_new
views: laboratory.views.equipment_new
templates: ops/form.html
models: laboratory.Equipment, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Register an instrument so calibration, qualification and use can be tracked. Registration does not make it fit for use.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; everyone else receives 403.

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
