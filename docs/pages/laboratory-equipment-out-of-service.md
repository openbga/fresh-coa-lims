---
title: Take equipment out of service
urls: laboratory:equipment_out_of_service
views: laboratory.views.equipment_out_of_service
templates: ops/form.html
models: laboratory.Equipment, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Immediately block an instrument that is unfit for use. Protective, so no signature is needed.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.

## Layout

- Breadcrumbs (Laboratory, Equipment, the asset, Take out of service), title "Take ASSET out of service", the introduction "Use only when the equipment is unfit. Returning it needs a signed approval.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Take out of service** | Always (the equipment record offers it only while in service) | Analyst, Reviewer or Quality; others receive 403 | Saves and opens the equipment record with "Equipment removed from service."; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why it is unfit |

## Rules and hidden logic

- Messages: "State why the equipment is unfit for use."; "Equipment is already out of service."
- The equipment must exist (404 otherwise). Opening the page for equipment already out of service shows the form; saving then fails with the message above.
- Sets state Out of service, records who and when, raises the revision, and writes `equipment.out_of_service`.
- Returning to service needs a signed approval by a Quality user who did not remove it. Calibration failures also remove equipment from service automatically.

## Related pages

- Equipment record
