---
title: Audit trail
urls: core:audit
views: core.views.audit
templates: core/audit.html
models: core.AuditEvent, core.AuditReview
reviewed: 2026-11-12
---

## Purpose

Inspect recorded changes, export them, and record an independent review of selected events. Opening or filtering the page is not a review.

## Who can use it

- Sign-in required. **Admin**, **quality** or **auditor** role to view, filter and export. The shared menu shows **Audit trail** only for these roles; others receive 403 if they open the URL directly.
- Recording an audit review requires **quality** or **auditor**. Admin-only users have no selection boxes or review form; direct review submissions receive 403.
- Quality/auditor reviewers cannot review their own events: their checkbox is disabled and marked "Your event".

## Layout

- **Filters** card: six filters, **Filter**, **Clear filters**, **Export filtered CSV**.
- Count line: "N matching events" and the review scope note.
- **Events table**: Select (reviewers only), Time / actor, Action / record, Original / new values (expand "Inspect values"), Reason, Review status (Reviewed with each reviewer, time and conclusion, or "Not reviewed").
- **Review conclusion** box and **Record independent review** for quality/auditor users; paging for all viewers.
- Empty: "No events match these filters…" when filtered, else "No audit events recorded yet."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Filter** | Always | Admin, quality, auditor | Reloads with the filters applied |
| **Clear filters** | Always | Admin, quality, auditor | Removes all filters |
| **Export filtered CSV** | Always | Admin, quality, auditor | Downloads `audit.csv` of all matching events (all pages); not a review |
| **Record independent review** | Quality/auditor role | Quality, auditor | Records one review over the checked events; "Independent review recorded for N events." |
| **Previous** / **Next** | More pages | Admin, quality, auditor | Moves a page; keeps filters |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Record type | `AuditEvent.object_type` | Text, exact match | No | e.g. `quality.lot` |
| Record ID | `AuditEvent.object_id` | Text, exact match | No | Record identifier |
| Actor | `AuditEvent.actor` | User choice | No | Only users with events are offered |
| Action | `AuditEvent.action` | Choice | No | Actions that occur in the log |
| From date / Through date | `AuditEvent.occurred_at` | Dates, deployment time zone | No | Inclusive whole days |
| Select | — | Checkbox | 1–50 | Events this review covers |
| Review conclusion | `AuditReview.conclusion` | Text | Yes | What you checked and follow-up needed |
| Time / actor | `AuditEvent.occurred_at`, `AuditEvent.actor` | Date-time with zone, user | — | When and by whom the change was recorded |
| Action / record | `AuditEvent.action`, `object_type`, `object_id` | Text | — | What happened and to which record ("type:id") |
| Original / new values | `AuditEvent.before`, `AuditEvent.after` | JSON | — | Values before and after the change |
| Reason | `AuditEvent.reason` | Text | — | Reason recorded with the change |
| Review status | `AuditReview.reviewer`, `reviewed_at`, `conclusion`, review ID | User, date-time, text | — | Each earlier review of the event, preserved; "Not reviewed" when none |
| Page (`page`) | — | Integer | No | Which page of 50 events is shown and can be selected |

## Rules and hidden logic

- **Order and paging**: newest first (ties by newest ID), 50 per page.
- **Invalid filters** (e.g. "From date must be on or before through date.") show no events and return status 422.
- **Review scope**: only events on the displayed page, between 1 and 50 ("Select between 1 and 50 events on this page.", "Select only the events displayed on this page."). Events by you are refused ("Review requires existing events from other actors.").
- **Duplicates**: a repeated or non-visible event ID is refused ("Select only the events displayed on this page.").
- **After errors**: the conclusion and the checked visible boxes are kept. **After success**: you return to the same filtered page.
- **Not a signature**: recording a review is an attributed audit record, not an electronic signature; no PIN is asked.
- **Effect**: creates an immutable review linked to the events and writes `audit.reviewed`. Earlier conclusions stay visible.
- **CSV**: columns ID, Time, Actor, Action, Record ("type:id"), Before, After, Reason. Export needs valid filters; with invalid filters the page shows the error instead.
- **CSV safety**: values starting with `=`, `+`, `-`, `@`, a tab or a carriage return are prefixed with `'` to prevent spreadsheet formulas.

## Related pages

- [Material lots](/)
- [Rule sets](/rules/)
