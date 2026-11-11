---
name: page-documentation
description: Write or update the in-app documentation for an OpenBGA QLab page (docs/pages/*.md, shown in the top-bar documentation panel). Use whenever a page, its view, form, template, model fields, permissions, filters or state rules are added or changed, and when a named URL is added, renamed or removed.
---

# Page documentation

Every staff page has one Markdown file in `docs/pages/` that the documentation panel (app
`pagedocs`) shows for that page. A change to a page is not complete until its doc matches the
code in the same change. `pagedocs/tests/test_coverage.py` fails when a named URL has no doc, a doc
names a missing URL/view/template/model, or a required section is absent. It cannot check that the
prose is true; you must.

## When to use

- A new named URL that renders a page: create its doc.
- Any change to a page's template, view, form, model fields shown, permission checks, filters,
  ordering/paging, defaults, validations, state transitions, signature or audit effects: update
  the doc and set `reviewed` to today's date.
- A URL renamed or removed: update `urls:` (or delete the doc). Non-page endpoints (JSON,
  POST-only redirects, downloads) go in `pagedocs/coverage.py` exemptions with a reason instead.

## Find the logic (derive everything from code)

| Look in | For |
|---|---|
| `<app>/urls.py` | URL name and namespace (`namespace:name`), path parameters, extra kwargs such as `{"action": ...}` |
| `<app>/views.py` | Decorators (`login_required`, methods), `require_role(...)` roles, queryset filters, `select_related`, search fields, ordering, page size, status codes, redirects, messages |
| `<app>/forms.py` | Fields, labels, required, max length, decimals, initial values, queryset limits (e.g. approved only), `clean_*`/`clean` validations |
| `<app>/services.py`, `core/services.py` | Server-side authorization, state preconditions, self-review rules, revision increments, `sign_transition`, `record_event` actions, locks |
| `<app>/models.py` | Model field names, types, units, defaults, choices, constraints, `Meta.ordering`, properties shown (e.g. `conforms`) |
| Template (`templates/` or `<app>/templates/`) | Visible sections, tabs, columns, buttons/links and the conditions that show them (`{% if %}`), empty states |
| Shared includes / JS | Dialog behaviour, HTMX targets, client-side enhancements |

A button can be visible to users the server will refuse: document both (who sees it, who can use it).

## File format

Copy `template.md` from this skill directory to `docs/pages/<namespace>-<name>.md` (underscores to
hyphens, e.g. `quality-lot-list.md`). One file normally covers one URL name; one file may list
several URL names only when they render the same page with the same rules.

Front matter (plain `key: value`, lists comma separated):

| Key | Required | Content |
|---|---|---|
| `title` | yes | The page title users see |
| `urls` | yes | Every `namespace:name` documented here |
| `views` | recommended | Dotted view paths, e.g. `quality.views.lot_list` (verified importable) |
| `templates` | recommended | Template names (verified loadable) |
| `models` | recommended | `app_label.Model` for models shown or changed (verified to exist) |
| `reviewed` | yes | ISO date the doc was last checked against the code |

Body: these `##` sections in this order. Write `None.` rather than dropping a section.

1. **Purpose**: one or two sentences; what job the page does in the QC workflow.
2. **Who can use it**: sign-in requirement, roles allowed to view, roles allowed for each action,
   and what others see (403, hidden control, disabled control).
3. **Layout**: regions, tabs, tables/columns and empty states, top to bottom.
4. **Actions**: every button and link that acts: what it does, when it is shown, result
   (redirect, message, record created), and server-side preconditions.
5. **Fields**: one table for inputs and displayed values:
   `| Field | Model field | Type / units | Required | Meaning and use |`. Use `—` for display-only
   or non-model values. Name filters and hidden inputs too (e.g. expected revision).
6. **Rules and hidden logic**: applied filters and defaults, ordering, paging, permission
   conditions, state transitions, self-review/independence rules, revision increments,
   e-signature meaning and audit events written, validations and their messages.
7. **Related pages**: pages users reach from here or arrive from. Link fixed paths such as
   `[Material lots](/)`; name pages that need a record ID in plain text (never write an ID).

## Accuracy rules

- Derive every statement from the code you read; never invent behaviour, limits or policy.
- Where the code is silent and the business policy matters, write `Assumption:` or
  `Not enforced by this page:`; do not present it as a rule. Do not claim regulatory compliance.
- Quote user-visible labels and messages exactly as the code renders them.
- Synthetic examples only (e.g. lot `LOT-TEST-001`, user `analyst.test`); no real people,
  customers, products or identifiers.
- Concise: the panel is narrow. Short sentences, tables for fields, no implementation narration
  (no function names in user text unless they help locate a rule; keep them in front matter).
- Supported Markdown: headings, paragraphs, `-`/`1.` lists (one level), pipe tables with leading
  `|`, `>` notes, inline code, bold, italic, links to `/relative` paths or `https://`. Raw HTML
  is escaped.

## Check

```
uv run ruff check pagedocs
uv run pytest pagedocs/tests
```

Then open the page, click the documentation icon and read the doc beside the page: every
visible control should be explained, and nothing described should be missing.
