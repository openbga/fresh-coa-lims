---
title: Mark pull missed
urls: stability:pull_missed
views: stability.views.pull_missed
templates: ops/form.html
models: stability.Pull, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record that a pull window closed without collection. The pull stays on the study permanently.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Mark missed** | Always | Analyst or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `Pull.missed_reason` | Text, max 2000 | Yes | Why the pull was missed |

## Rules and hidden logic

- Messages: "The pull window has not closed yet."; "Only a scheduled pull of an active study can be marked missed."
- Missed pulls are immutable and cannot be rescheduled. Event `pull.missed`.

## Related pages

- Pull record
