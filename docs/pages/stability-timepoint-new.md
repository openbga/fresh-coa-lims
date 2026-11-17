---
title: Add timepoint
urls: stability:timepoint_new
views: stability.views.timepoint_new
templates: ops/form.html
models: stability.ProtocolTimepoint, core.AuditEvent
reviewed: 2026-11-17
summary: Add a pull time point to a draft protocol: its storage condition, days from time zero, window and the tests required at that pull. Only the protocol's author can add it.
---

## Common tasks
### Add a timepoint
1. Choose the [[Condition]] and enter the [[Label]], for example 3 months.
2. Enter [[Interval (days)]] from time zero, where 0 is time zero, and the [[Window (± days)]].
3. List the test codes in [[Tests]], separated by commas.
4. Enter a [[Reason]] and select [[Add timepoint]]. You return to the protocol record.
### Pull the same time point under another condition
1. Back on the protocol record, select [[Add timepoint]] again and choose the other condition.
## Good to know
- Each condition can have only one timepoint per interval.
- The window is the days allowed either side of the due date. A pull taken outside it needs a deviation reason.
- Test codes are not checked against the specification here. A protocol that names a specification is checked when it is approved.
- Saving changes the protocol revision. An approval page opened earlier must be reloaded before it can be signed.

## Purpose

Add a pull timepoint and its required tests to a draft protocol.

## Who can use it

- Sign-in required. Roles: Analyst or Quality (others receive 403), and only the protocol author may add to a draft (otherwise 403: "Only the protocol author edits a draft.").
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Stability and retention, Protocols, the protocol, Add timepoint), title "Add timepoint" with the protocol identifier, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add timepoint** | Always | Analyst or Quality, and only the protocol author | Saves, shows "Timepoint added to the draft protocol." and returns to the protocol record; refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Condition | `ProtocolTimepoint.condition` | This protocol's conditions only | Yes | Storage condition for the pull; add conditions first |
| Label | `ProtocolTimepoint.label` | Text, max 40 | Yes | For example 3 months |
| Interval (days) | `ProtocolTimepoint.interval_days` | Whole days ≥ 0 from time zero | Yes | 0 is time zero; one timepoint per condition and interval (a repeat is refused) |
| Window (± days) | `ProtocolTimepoint.window_days` | Whole days ≥ 0 | Yes (default 0) | Allowed deviation either side of the due date |
| Tests | `ProtocolTimepoint.test_codes` | Comma-separated test codes, from the approved profile | Yes | Required tests for each pull; stored as a list. "List one or more distinct test codes." for none or duplicates. Codes are not checked against a profile here. |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Same draft and author rules as adding a condition: only a Draft protocol ("<code> v<n> is approved and frozen; create a new version." (or withdrawn, or superseded)) and only its author (403).
- Saving recalculates the protocol's content digest and raises the protocol revision by 1; event `protocol.timepoint_added` records the protocol revision before and after.
- Timepoints become pulls when a study starts on the approved protocol; later changes do not alter existing studies.

## Related pages

- Protocol record (Cancel and success)
