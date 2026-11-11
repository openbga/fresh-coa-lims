---
title: Stability and retention
urls: stability:overview
views: stability.views.overview
templates: ops/overview.html
models: stability.Pull, stability.Protocol, stability.Study, stability.Hold, stability.RetentionObligation, stability.ReserveSample
reviewed: 2026-11-10
---

## Purpose

Work queues for stability pulls, studies, protocols, holds, retention anchors and reserve quantities, each linking to the list that resolves it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- Title "Stability and retention", the introduction (native scheduling is thin; link external stability systems where used) and one list of queues, each with a count. A zero count is shown in a neutral tone. The queues: Pulls overdue; Pulls due now; Pulls awaiting acceptance (active studies only); Active studies; Protocols awaiting approval; Active holds; Retention anchors not yet known; Reserves below minimum quantity.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Queue name link | Always | Any reader | Opens the matching list. Pull queues, Active studies, Protocols awaiting approval, Active holds and Reserves below minimum quantity open with their status filter applied; Retention anchors not yet known opens the unfiltered [Reserve samples](/stability/reserves/) list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Pulls overdue / due now / awaiting acceptance | `Pull.state`, `Pull.due_date`, `Timepoint.window_days` | Count | — | Pulls of active studies only |
| Active studies | `Study.state` | Count | — | State Active |
| Protocols awaiting approval | `Protocol.state` | Count | — | State Draft |
| Active holds | `Hold.state` | Count | — | State Active |
| Retention anchors not yet known | `RetentionObligation.anchor_date` | Count | — | Obligations with no anchor date, all lots |
| Reserves below minimum quantity | `ReserveSample.quantity` | Count | — | Quantity below minimum multiple × test quantity |

## Rules and hidden logic

- Only Scheduled pulls count as overdue or due. The window is the due date ± the timepoint's window days: **due** from the first to the last day of the window (inclusive), **overdue** after it closes, **upcoming** before it opens. Awaiting acceptance counts pulls in state Pulled. All three consider active studies only.
- The other queues count every record, whatever its age.
- Not enforced by this page: any reminder or notification; the page only counts.

## Related pages

- [Stability pulls](/stability/pulls/)
- [Holds](/stability/holds/)
- [Stability protocols](/stability/protocols/)
- [Stability studies](/stability/studies/)
- [Reserve samples](/stability/reserves/)
