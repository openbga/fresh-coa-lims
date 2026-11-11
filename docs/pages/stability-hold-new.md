---
title: New hold
urls: stability:hold_new
views: stability.views.hold_new
templates: ops/form.html
models: stability.Hold, quality.Lot, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Place a hold on a lot (optionally tied to one reserve sample). Placing is protective and immediate; releasing needs a different Quality signer.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others (including Admin and Auditor) receive 403.
- Opened with `?reserve=<id>` from a reserve sample, the reserve is attached and the lot is preselected; an unknown reserve returns 404.

## Layout

- Breadcrumbs (Stability and retention, Holds, New hold), title "New hold", the introduction "Placing a hold is protective and immediate. Releasing it needs a different quality signer.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Place hold** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves, shows the warning "HOLD-n placed." and opens the hold record; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot | `Hold.lot` | Any lot, ordered by number | Yes | Preselected when opened from a reserve sample |
| Kind | `Hold.kind` | Choice | Yes | Investigation, Regulatory, Legal or Quality |
| Reference | `Hold.reference` | Text, max 200 | No | Investigation, CAPA or matter ID |
| Reason for hold | `Hold.reason` | Text, max 2000 | Yes | Also recorded in the audit event |

## Rules and hidden logic

- While the lot is in quarantine the lot revision rises, so a disposition dialog opened earlier goes stale. A released lot's row is never touched.
- A reserve sample from a different lot is refused. Event `hold.placed`.
- An active hold makes QC disposition of the lot refuse with the hold identifier, kind and reason; this applies to reserve-specific holds too.
- Hold state starts Active; the reason is stored trimmed.
- Intentional: a hold can be placed on any lot, including one already released (for example a post-release review). The released lot's row, its frozen disposition evidence and any published certificate are not changed; instead the active hold blocks any future certificate issue or amendment and any disposal until a different Quality signer releases it.

## Related pages

- [Holds](/stability/holds/)
- Reserve sample record (plain name: starting point for a reserve-specific hold)
