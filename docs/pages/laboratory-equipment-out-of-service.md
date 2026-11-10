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

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Take out of service** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why it is unfit |

## Rules and hidden logic

- Messages: "State why the equipment is unfit for use."; "Equipment is already out of service."
- Sets state Out of service, records who and when, raises the revision, and writes `equipment.out_of_service`.
- Returning to service needs a signed approval by Quality who did not remove it.

## Related pages

- Equipment record
