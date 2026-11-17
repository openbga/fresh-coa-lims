---
title: Page title as users see it
urls: namespace:url_name
views: app.views.view_name
templates: app/template.html
models: app.Model
reviewed: YYYY-MM-DD
---

## Purpose

What job this page does in the quality workflow, in one or two sentences.

## Who can use it

- Sign-in required. Roles that can open the page: ...
- Actions limited to: ... Others receive "403 Forbidden" / do not see the control.

## Layout

- **Header**: title, primary action.
- **Main table / sections / tabs**: what each shows, empty state text.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New thing** | Always | Analyst | Opens the New thing form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Number | `Model.number` | Text, max 80 | Yes | Unique identifier |

## Rules and hidden logic

- **Filters and order**: ...
- **Permissions**: ...
- **State and transitions**: ...
- **Signatures and audit**: ...
- **Validations**: "Exact message" when ...

## Related pages

- [List page](/path/)
