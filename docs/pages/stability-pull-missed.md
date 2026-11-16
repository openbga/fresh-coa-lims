---
title: Mark pull missed
urls: stability:pull_missed
views: stability.views.pull_missed
templates: ops/form.html
models: stability.Pull, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

Record that a pull was not collected before its window closed, or that a pull that was taken cannot be tested (for example lost or insufficient material). The pull stays on the study permanently.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Studies, study, pull), title "Mark missed" with the timepoint, the introduction (a missed pull stays on the study record and cannot be rescheduled silently; a pull taken but not testable is recorded as missed once nothing of its testing is in progress, its reviewed results stay and its untouched tests take no more work), the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Mark missed** | Always | Analyst or Quality; others receive 403 | Saves, shows the warning "Pull recorded as missed." and returns to the pull record; refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `Pull.missed_reason`; also `AuditEvent.reason` | Text, max 2000 | Yes | Why the pull was missed; stored trimmed on the pull and recorded with the event |

## Rules and hidden logic

- Messages: "Only a pull of an active study can be marked missed."; "The pull window has not closed yet."; "Testing of this pull is in progress; finish it first: …"; "Only a scheduled or pulled pull can be marked missed."
- The study must be Active. A **Scheduled** pull is missed once today (local date) is after the window's last day. A **Pulled** pull can be missed at any time, provided nothing of its testing is in progress: no test of it awaits review, no open test holds results, raw-data files or a QC batch, and no investigation of its tests is open. Its reviewed results stay in the record; its untouched tests then take no more work ("This pull is missed; its tests take no more work."). The pull page shows **Mark missed** only when these hold; the server checks them again under the pull and study locks.
- Sets the pull to Missed and raises the revision by 1. Missed pulls are final and cannot be rescheduled. Event `pull.missed`.
- A missed pull counts as finished when a study is closed as Completed.

## Related pages

- Pull record
- Study record
