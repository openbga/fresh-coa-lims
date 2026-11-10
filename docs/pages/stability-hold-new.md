---
title: New hold
urls: stability:hold_new
views: stability.views.hold_new
templates: ops/form.html
models: stability.Hold, quality.Lot, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Place a hold on a lot (optionally one reserve sample). Protective and immediate.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Place hold** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot | `Hold.lot` | Any lot | Yes | Preselected when opened from a reserve sample |
| Kind | `Hold.kind` | Choice | Yes | Investigation, Regulatory, Legal or Quality |
| Reference | `Hold.reference` | Text, max 200 | No | Investigation, CAPA or matter ID |
| Reason for hold | `Hold.reason` | Text, max 2000 | Yes | Also recorded in the audit event |

## Rules and hidden logic

- While the lot is in quarantine the lot revision rises, so a disposition dialog opened earlier goes stale. A released lot's row is never touched.
- A reserve sample from a different lot is refused. Event `hold.placed`.
- The disposition gate that reads active holds is published for the integrator; until it is wired, holds do not stop a disposition by themselves.

## Related pages

- [Holds](/stability/holds/)
