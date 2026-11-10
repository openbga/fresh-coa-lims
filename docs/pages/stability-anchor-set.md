---
title: Set retention anchor
urls: stability:anchor_set
views: stability.views.anchor_set
templates: ops/form.html
models: stability.RetentionObligation, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Set the anchor date of an obligation whose anchor was unknown.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Set anchor** | Always | Analyst or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Anchor date | `RetentionObligation.anchor_date` | Date | Yes | Anchor event date |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Evidence for the date |

## Rules and hidden logic

- Allowed once ("The anchor is already set. Record a new obligation if the anchor moved."); the database refuses any other change. Event `retention.anchor_set`.

## Related pages

- Reserve record
