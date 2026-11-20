---
title: Withdraw draft evaluation
urls: stability:shelf_life_withdraw
views: stability.shelf_life_views.shelf_life_withdraw
templates: ops/form.html
models: stability.ShelfLifeEvaluation, core.AuditEvent
reviewed: 2026-11-19
summary: Withdraw a draft shelf-life evaluation that will not be concluded, so a new one of the same test and condition can be drafted. Quality only.
---

## Common tasks

### Withdraw a draft

1. Enter the [[Reason]] the draft will not be concluded.
2. Select [[Withdraw draft]]. You return to the record, now Withdrawn.

### Draft the replacement

1. On the evaluations list, select [[New evaluation]] and choose the same test and condition.

## Good to know

- Withdrawing is not signed, but your reason is recorded in the history.
- A withdrawn draft stays in the record and is never concluded.
- Only a draft can be withdrawn.
- If the draft changed after you opened this page, the withdrawal is refused. Reload and try again.

## Purpose

Closes a draft that will not be concluded, and frees its scope for a new draft.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.

## Layout

- Breadcrumbs (Stability and retention, Shelf-life evaluations, SLE-n, Withdraw), title "Withdraw SLE-n", an introduction, the form, **Cancel** and **Withdraw draft**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw draft** | Draft | Quality | Withdraws; message "SLE-n withdrawn."; returns to the record |
| **Cancel** | Always | Quality | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | audit reason | Text, max 2000 | Yes | Recorded in the history |
| Expected revision (hidden) | `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **State**: Draft becomes Withdrawn, the time is stored and the revision rises. A withdrawn evaluation never changes again.
- **Audit**: event `shelf_life.withdrawn` with before and after and your reason.
- **Refusals**: "Record changed. Reload before saving."; for an evaluation that is not a draft, you are sent back to its record with "SLE-n is <state>: it no longer changes."

## Related pages

- Evaluation record
- [Shelf-life evaluations](/stability/shelf-life/)
