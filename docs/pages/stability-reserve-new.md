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

- Breadcrumbs (Reserve samples, New reserve sample), title, the introduction (reserve records are immutable; minimum multiple is prefilled from researched drug and supplement rules and the quality owner confirms what applies), the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record reserve sample** | Always | Analyst or Quality; others receive 403 | Saves, shows "Reserve sample recorded. Record its retention obligations." and opens the reserve record; refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Identifier | `ReserveSample.identifier` | Text, max 60, unique | Yes | Reserve ID; a duplicate is refused |
| Lot | `ReserveSample.lot` | Any lot, listed by lot number | Yes | Lot retained |
| Container description / Storage location | `ReserveSample.container_description`, `.storage_location` | Text, max 200 / max 120 | Yes | Packaging as retained (for example full marketed package); where it is kept |
| Quantity / Test quantity / Quantity unit | `ReserveSample.quantity`, `.test_quantity`, `.quantity_unit` | Decimal ≥ 0 (14 digits, 4 places); test quantity > 0; unit text max 20 | Yes | Retained amount; amount needed for one complete set of required tests; shared unit |
| Minimum multiple | `ReserveSample.minimum_multiple` | Decimal ≥ 0 (5 digits, 2 places), default 2 | Yes | Prefilled from the researched drug and supplement rules; the quality owner confirms what applies |
| Retained on | `ReserveSample.retained_on` | Date | Yes | Date retained |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Quantity below the minimum multiple of the test quantity is not blocked; the reserve is then labelled "Below minimum" on the list and record. Event `reserve.recorded` stores whether it meets the minimum.
- The record cannot be edited afterwards. Retention obligations and holds are recorded separately and do not change the lot's revision from here.
- Not enforced by this page: whether 2 is the right multiple for a given product; Quality confirms.

## Related pages

- [Reserve samples](/stability/reserves/)
- Reserve record (opened after saving)
