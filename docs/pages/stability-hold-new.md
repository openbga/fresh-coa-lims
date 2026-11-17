---
title: New hold
urls: stability:hold_new
views: stability.views.hold_new
templates: ops/form.html
models: stability.Hold, quality.Lot, core.AuditEvent
reviewed: 2026-11-17
summary: Place a hold on a lot, optionally tied to one reserve sample. It takes effect at once and blocks QC disposition and disposal until a different quality signer releases it.
---

## Common tasks
### Place a hold
1. Choose the [[Lot]] and the [[Kind]]: Investigation, Regulatory, Legal or Quality.
2. Enter the investigation, CAPA or matter ID in [[Reference]], if there is one.
3. Enter the [[Reason for hold]] and select [[Place hold]]. The hold record opens.
### Hold one reserve sample
1. Start from the reserve record and select [[Place hold]] there. The hold is tied to that reserve and its lot is filled in.
## Good to know
- You cannot release a hold you placed. A different quality user signs the release.
- A hold tied to one reserve sample still blocks QC disposition of the whole lot.
- While the lot is in quarantine, a disposition page opened before the hold goes stale and must be reloaded.
- A hold can be placed on a released lot. The released lot's record is not changed.
- A lot cancelled as received in error is not offered.

## Purpose

Place a hold on a lot (optionally tied to one reserve sample). Placing is protective and immediate; releasing needs a different Quality signer.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others (including Admin and Auditor) receive 403.
- Opened with `?reserve=<id>` from a reserve sample, the reserve is attached and the lot is preselected; an unknown or malformed reserve returns 404.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

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
| Lot | `Hold.lot` | Any lot except a cancelled one, ordered by number | Yes | Preselected when opened from a reserve sample |
| Kind | `Hold.kind` | Choice | Yes | Investigation, Regulatory, Legal or Quality |
| Reference | `Hold.reference` | Text, max 200 | No | Investigation, CAPA or matter ID |
| Reason for hold | `Hold.reason` | Text, max 2000 | Yes | Also recorded in the audit event |

## Rules and hidden logic

- While the lot is in quarantine the lot revision rises, so a disposition dialog opened earlier goes stale. A released, rejected or cancelled lot's row is never touched.
- A lot cancelled as received in error is not offered and is refused: "Lot <number> was cancelled as received in error; it has no material." Rejected lots are offered; their revision is not raised.
- A reserve sample from a different lot is refused. Event `hold.placed`.
- An active hold makes QC disposition of the lot refuse with the hold identifier, kind and reason; this applies to reserve-specific holds too.
- Hold state starts Active; the reason is stored trimmed.
- Intentional: a hold can be placed on any lot, including one already released (for example a post-release review). The released lot's row, its frozen disposition evidence and any published certificate are not changed; instead the active hold blocks any future certificate issue or amendment and any disposal until a different Quality signer releases it.

## Related pages

- [Holds](/stability/holds/)
- Reserve sample record (plain name: starting point for a reserve-specific hold)
