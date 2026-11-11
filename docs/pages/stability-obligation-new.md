---
title: New retention obligation
urls: stability:obligation_new
views: stability.views.obligation_new
templates: ops/form.html
models: stability.RetentionObligation, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record one applicable retention basis for a lot or reserve sample, with its own anchor and retention period. The deadline is the anchor date plus the months.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.
- Opened with `?reserve=<id>` (from a reserve sample) the obligation is tied to that reserve and its lot; an unknown reserve returns 404.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Stability and retention, Reserve samples, New retention obligation), title "New retention obligation", introduction "One obligation per applicable retention basis...", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record obligation** | Always | Analyst or Quality; others receive 403 | Saves, shows "Retention obligation recorded." and returns to the reserve sample record (the reserve list when no reserve was given); domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot | `RetentionObligation.lot` | Any lot, ordered by number | Yes, but only shown when not opened from a reserve | Reserve-scoped obligations use the reserve's lot |
| Anchor kind | `RetentionObligation.anchor_kind` | Expiry or shelf-life date / Last associated batch distribution / Preparation or record date / Discontinued use | Yes | What starts the clock |
| Anchor date | `RetentionObligation.anchor_date` | Date | No | Leave blank if unknown; set later once on the anchor page |
| Months retained after the anchor | `RetentionObligation.offset_months` | Whole number ≥ 0, months | Yes | Retention period |
| Basis | `RetentionObligation.basis` | Text, max 200 | Yes | Controlled basis confirmed by quality |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Obligations are append-only. An unknown anchor keeps the item retained (the disposal gate reports it as a blocker; no disposal path exists yet) and is counted in the overview queue "Retention anchors not yet known".
- Retain-until is the anchor plus the months in calendar months; a day past the end of the target month is clamped to its last day.
- Retention is considered cleared only after the retain-until date has passed.
- Event `retention.recorded` (includes the computed retain-until date).
- Not enforced by this page: which bases apply to a lot; quality decides and records one obligation per basis.

## Related pages

- [Reserve samples](/stability/reserves/)
- Set retention anchor (plain name: linked from an obligation without an anchor)
