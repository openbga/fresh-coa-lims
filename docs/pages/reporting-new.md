---
title: New certificate of analysis
urls: reporting:new
views: reporting.views.report_new
templates: reporting/report_new.html
models: quality.Lot
reviewed: 2026-11-10
---

## Purpose

Chooses the released lot a new certificate of analysis will cover. Nothing is created or signed here; you review the evidence next.

## Who can use it

- Sign-in required. Only the **quality** role; others receive 403.

## Layout

- **Breadcrumbs**: Certificates › New certificate of analysis.
- **Form**: **Released lot** menu with its help text, a note that you review the exact evidence before signing, **Review certificate** and **Cancel**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Review certificate** | Always | Quality | Opens the review page for the chosen lot |
| **Cancel** | Always | Quality | Returns to the certificate list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Released lot | `Lot.state`, `Lot.number` | Menu | Yes | Only lots with a signed QC disposition ("released"), ordered by lot number |

## Rules and hidden logic

- The form is submitted with GET, so the chosen lot appears in the address.
- A value that is not a released lot is refused with "Select a valid choice. That choice is not one of the available choices." (status 422).
- This page never writes data or audit events.

## Related pages

- [Certificates of analysis](/reports/)
- Review certificate (needs a lot).
