---
title: Stability and retention
urls: stability:overview
views: stability.views.overview
templates: ops/overview.html
models: stability.Pull, stability.Protocol, stability.Study, stability.Hold, stability.RetentionObligation, stability.ReserveSample
reviewed: 2026-11-17
summary: Stability work queues at a glance: overdue and due pulls, pulls awaiting acceptance, draft protocols, active holds and reserve gaps. Each count opens the list that resolves it.
---

## Common tasks
### See what needs attention
1. Look for queues marked [[Needs attention]]. A queue with nothing waiting shows [[Clear]].
2. Select a queue name, such as [[Pulls overdue]], to open its list already filtered to those records.
### Open a stability list
1. Select [[Protocols]], [[Studies]], [[Pulls]], [[Reserves]] or [[Holds]] in the tabs above the title.
### Check reserves and retention
1. Select [[Reserves below minimum quantity]] or [[Retention anchors not yet known]] to open the reserve samples list.
## Good to know
- The pull queues count pulls of active studies only. The pulls list they open also shows pulls of closed studies, so its count can be higher.
- Due now runs from the first to the last day of a pull's window, by today's local date. Overdue means the window has closed and the pull was not taken.
- An accepted pull can still be outside its acceptance criteria. [[Pulls outside acceptance criteria]] counts those.
- Every count equals the rows of the list it opens. [[Retention anchors not yet known]] counts reserves with an obligation whose anchor date is not known yet.

## Purpose

Work queues for stability pulls, studies, protocols, holds, retention anchors and reserve quantities, each linking to the list that resolves it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Protocols, Studies, Pulls, Reserves, Holds. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Stability and retention can use every section link.
- Title "Stability and retention", the introduction (a pull is tested in the system against the acceptance criteria of its protocol, or linked to an external stability system where one is used) and today's date under the title. One table of queues: Queue (links to the filtered list), Records (the count) and Attention ("Needs attention" in the queue's tone when the count is above zero, "Clear" in the neutral tone when it is zero). The queues: Pulls overdue; Pulls due now; Pulls awaiting acceptance (active studies only); Pulls outside acceptance criteria (active studies only); Active studies; Protocols awaiting approval; Active holds; Retention anchors not yet known; Reserves below minimum quantity.

Queue names wrap on narrow screens to keep counts and attention labels easier to see. Wide tables can be scrolled sideways.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| Queue name link | Always | Any reader | Opens the matching list. Pull queues (Pulls outside acceptance criteria opens the Pulls list filtered to "Accepted, acceptance criteria not met"), Active studies, Protocols awaiting approval, Active holds, Reserves below minimum quantity and Retention anchors not yet known open with their status filter applied; each count equals the rows that list shows |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Pulls overdue / due now / awaiting acceptance | `Pull.state`, `Pull.due_date`, `Timepoint.window_days` | Count | — | Pulls of active studies only |
| Pulls outside acceptance criteria | `Pull.state`, `Pull.outcome` | Count | — | Accepted pulls whose recorded outcome is "Does not meet the acceptance criteria"; active studies only; shown in the danger tone when above zero |
| Active studies | `Study.state` | Count | — | State Active |
| Protocols awaiting approval | `Protocol.state` | Count | — | State Draft |
| Active holds | `Hold.state` | Count | — | State Active |
| Retention anchors not yet known | `RetentionObligation.anchor_date` | Count of reserves | — | Reserve samples with a retention obligation whose anchor date is not known yet; opens Reserve samples filtered to "Retention anchor not yet known" |
| Reserves below minimum quantity | `ReserveSample.quantity` | Count | — | Quantity below minimum multiple × test quantity |

## Rules and hidden logic

- Only Scheduled pulls of active studies count as overdue or due; each count equals the rows of the pull list it opens. The window is the due date ± the timepoint's window days: **due** from the first to the last day of the window (inclusive), **overdue** after it closes, **upcoming** before it opens. Awaiting acceptance counts pulls in state Pulled. All three consider active studies only, as does Pulls outside acceptance criteria.
- Pulls outside acceptance criteria counts accepted pulls tested in the system whose confirmed results fall outside the criteria, in active studies only (the list it opens also shows closed studies).
- The other queues count every record, whatever its age.
- Not enforced by this page: any reminder or notification; the page only counts.

## Related pages

- [Stability pulls](/stability/pulls/)
- [Holds](/stability/holds/)
- [Stability protocols](/stability/protocols/)
- [Stability studies](/stability/studies/)
- [Reserve samples](/stability/reserves/)
