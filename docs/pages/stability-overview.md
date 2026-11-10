---
title: Stability and retention
urls: stability:overview
views: stability.views.overview
templates: ops/overview.html
models: stability.Pull, stability.Protocol, stability.Study, stability.Hold, stability.RetentionObligation, stability.ReserveSample
reviewed: 2026-11-10
---

## Purpose

Work queues for stability pulls, protocols, holds and retention, each linking to the list that resolves it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.

## Layout

- Dateline, title, introduction and one table of queues: Pulls overdue; Pulls due now; Pulls awaiting acceptance (active studies only); Active studies; Protocols awaiting approval; Active holds; Retention anchors not yet known; Reserves below minimum quantity.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Queue name link | Always | Any reader | Opens the matching list with its filter applied |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Records | — | Count | — | Live count over all records |

## Rules and hidden logic

- A pull is **due** from the start of its window to its end, **overdue** after the window closes, **upcoming** before it opens. Queue counts for pulls consider active studies only.

## Related pages

- [Stability pulls](/stability/pulls/)
- [Holds](/stability/holds/)
- [Reserve samples](/stability/reserves/)
