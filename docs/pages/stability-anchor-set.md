---
title: Set retention anchor
urls: stability:anchor_set
views: stability.views.anchor_set
templates: ops/form.html
models: stability.RetentionObligation, core.AuditEvent
reviewed: 2026-11-11
---

## Purpose

Set the anchor date, once, of a retention obligation that was recorded without one.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403. An unknown obligation returns 404.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Stability and retention, Reserve samples, Set anchor), title "Set anchor · <anchor kind>", the introduction "The anchor can be set once. If it later moves, record a new obligation.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Set anchor** | Always | Analyst or Quality; others receive 403 | Saves, shows "Retention anchor set." and returns to the obligation's reserve sample record (the reserve list if the obligation has no reserve); domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Anchor date | `RetentionObligation.anchor_date` | Date | Yes | Anchor event date; the retain-until date becomes this date plus the obligation's months |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Evidence for the date; recorded with the event |

## Rules and hidden logic

- Allowed once ("The anchor is already set. Record a new obligation if the anchor moved."); the database refuses any other change. Who set it and when are stored on the obligation. Event `retention.anchor_set` (before and after values, including the computed retain-until date).
- The only date check is that the resulting retain-until date is a representable calendar date; otherwise "The retention date falls outside the supported calendar." is shown and the anchor stays unset.
- The link to this page appears on the reserve record only for obligations without an anchor, and only to Analyst or Quality.

## Related pages

- Reserve record (plain name: opened from the reserve samples list)
- [Reserve samples](/stability/reserves/)
