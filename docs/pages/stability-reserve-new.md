---
title: New reserve sample
urls: stability:reserve_new
views: stability.views.reserve_new
templates: ops/form.html
models: stability.ReserveSample, core.AuditEvent
reviewed: 2026-11-17
summary: Record an identified reserve sample of a lot, with its quantity, one test set and the minimum multiple to keep. A reserve record cannot be changed afterwards.
---

## Common tasks
### Record a reserve sample
1. Enter the [[Identifier]], choose the [[Lot]], and enter the [[Container description]] and [[Storage location]].
2. Enter the [[Quantity]], the [[Test quantity]] for one complete test set, and the [[Quantity unit]].
3. Check [[Minimum multiple]], prefilled with 2, and enter [[Retained on]].
4. Enter a [[Reason]] and select [[Record reserve sample]].
### Record its retention obligations
1. On the reserve record that opens, select [[Record retention obligation]] for each retention basis that applies.
## Good to know
- The record cannot be edited after you save. Check the entries first.
- A quantity below the minimum is accepted, and the reserve is then labeled Below minimum.
- The prefilled multiple of 2 reflects researched drug and supplement rules. The quality owner confirms what applies.
- A lot cancelled as received in error is not offered.

## Purpose

Record an identified reserve sample. Reserve records are immutable.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

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
| Lot | `ReserveSample.lot` | Any lot except a cancelled one, listed by lot number | Yes | Lot retained. Rejected lots are offered |
| Container description / Storage location | `ReserveSample.container_description`, `.storage_location` | Text, max 200 / max 120 | Yes | Packaging as retained (for example full marketed package); where it is kept |
| Quantity / Test quantity / Quantity unit | `ReserveSample.quantity`, `.test_quantity`, `.quantity_unit` | Decimal ≥ 0 (14 digits, 4 places); test quantity > 0; unit text max 20 | Yes | Retained amount; amount needed for one complete set of required tests; shared unit |
| Minimum multiple | `ReserveSample.minimum_multiple` | Decimal ≥ 0 (5 digits, 2 places), default 2 | Yes | Prefilled from the researched drug and supplement rules; the quality owner confirms what applies |
| Retained on | `ReserveSample.retained_on` | Date | Yes | Date retained |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Quantity below the minimum multiple of the test quantity is not blocked; the reserve is then labelled "Below minimum" on the list and record. Event `reserve.recorded` stores whether it meets the minimum.
- A lot cancelled as received in error is not offered and is refused: "Lot <number> was cancelled as received in error; it has no material."
- The record cannot be edited afterwards. Retention obligations and holds are recorded separately and do not change the lot's revision from here.
- Not enforced by this page: whether 2 is the right multiple for a given product; Quality confirms.

## Related pages

- [Reserve samples](/stability/reserves/)
- Reserve record (opened after saving)
