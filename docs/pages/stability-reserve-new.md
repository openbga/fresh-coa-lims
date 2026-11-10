---
title: New reserve sample
urls: stability:reserve_new
views: stability.views.reserve_new
templates: ops/form.html
models: stability.ReserveSample, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record an identified reserve sample. Reserve records are immutable.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record reserve sample** | Always | Analyst or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Identifier | `ReserveSample.identifier` | Text, max 60, unique | Yes | Reserve ID |
| Lot | `ReserveSample.lot` | Any lot | Yes | Lot retained |
| Container description / Storage location | `ReserveSample.container_description`, `.storage_location` | Text | Yes | As retained |
| Quantity / Test quantity / Quantity unit | `ReserveSample.quantity`, `.test_quantity`, `.quantity_unit` | Decimal ≥ 0 (4 places); test quantity > 0 | Yes | Retained and one-test-set amounts |
| Minimum multiple | `ReserveSample.minimum_multiple` | Decimal ≥ 0, default 2 | Yes | Prefilled from the researched drug and supplement rules; the quality owner confirms what applies |
| Retained on | `ReserveSample.retained_on` | Date | Yes | Date retained |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Falling below the minimum is shown as a warning, not blocked. Event `reserve.recorded` stores the check result. Retention obligations are recorded separately.

## Related pages

- [Reserve samples](/stability/reserves/)
