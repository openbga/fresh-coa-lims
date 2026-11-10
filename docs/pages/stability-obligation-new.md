---
title: New retention obligation
urls: stability:obligation_new
views: stability.views.obligation_new
templates: ops/form.html
models: stability.RetentionObligation, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record one applicable retention basis with its own anchor and period.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record obligation** | Always | Analyst or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot | `RetentionObligation.lot` | Any lot | When not opened from a reserve | Reserve-scoped obligations use the reserve's lot |
| Anchor kind | `RetentionObligation.anchor_kind` | Expiry or shelf-life date / Last associated batch distribution / Preparation or record date / Discontinued use | Yes | What starts the clock |
| Anchor date | `RetentionObligation.anchor_date` | Date | No | Leave blank if unknown |
| Months retained after the anchor | `RetentionObligation.offset_months` | Whole months | Yes | Retention period |
| Basis | `RetentionObligation.basis` | Text, max 200 | Yes | Controlled basis confirmed by quality |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Obligations are append-only. An unknown anchor keeps the item retained. Month arithmetic clamps to month ends. Event `retention.recorded`.

## Related pages

- [Reserve samples](/stability/reserves/)
