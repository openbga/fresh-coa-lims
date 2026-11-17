---
name: build-page
description: How to build or change any OpenBGA QM LIMS page, form, dialog or template the house way. Covers the page types and the shared `{% load ui %}` components for each, form controls through the Django widgets (including the remote select with a registered lookup), lists with server paging and per-user column preferences, the form dialog, tokens and Bootstrap Icons only, panel spacing, and the must-see QC facts of a page. Use it whenever you add or edit a Django template, the view context a template reads, a form or widget, a list, record, sign or certificate page, a dialog, or app.css/JS that pages use, even for a "small" markup change. Then run document-page.
---

# Build or change a page

Pages are assembled from shared parts, not written from scratch. Every concept already has one
component; a page that copies markup drifts from the others and fails `tests/test_ui_standards.py`.
The standard is `docs/ui-standards.md`; the short rules are `.agents/rules/frontend.md`. This skill
is the working order. `references/components.md` holds the tables (components, controls, list
columns): read it when you reach the step that needs it.

## 1. Classify the page

Every page is one of the types in `docs/ui-standards.md` ("Components and theme"). The type fixes
the header, layout, breadcrumbs and where the primary action goes:

| Type | Build it with | Primary action |
| --- | --- | --- |
| List | One `{% panel table=True hidden_title=True %}` with `{% grid_toolbar %}`, `{% sort_header %}` columns and `{% list_results %}` (table, pagination, empty, no-results and filter-error states) | `New <thing>` in `page_actions` |
| Record | `{% page_meta %}` (status first, at most four facts), `{% record_layout %}` (lead panel of `{% fact %}` rows in `dl.vr-facts`, optional aside), related panels, `{% signature_list %}`, `{% history_panel %}` last | The next step for the record's state |
| Form / action | `{% form_page form=… cancel_url=… submit_label=… %}`; plain data-entry pages listed in `core/form_surfaces.py` open in the shared form dialog, the page is the no-JS fallback. Title = the words of the button that opened it | The submit, in the action row |
| Sign | `{% signature_card %}` with the summary fill and the form or the refusal (`hook="signature-dialog"` when signing is allowed). Never in the form dialog | Sign (`submit_icon="vector-pen"`) |
| Entry grid | A plain table of form fields, units in the headers, `{% form_actions %}` | Save |
| Overview | Panels of queue and count tables that link to filtered lists | None, or the one most frequent start |
| Document | Breadcrumbs and version identity, a preview of the issued content (the certificate partial), download / version / amendment controls | The decision for the document |

Header (`templates/layouts/document.html`): the view passes `page_title`; no page-own `<h1>`. At
most three secondary buttons, then `{% more_actions %}`, then the one `.btn-primary` last.
A button-only state change is a `{% post_button %}`; an irreversible one confirms with
`{% confirm_dialog %}`. Anything that needs input is a form page (dialog) or a sign page.

## 2. Decide what must be seen first

List the page's must-see facts for each role that opens it: what a person would act on wrongly
if they missed it. In QC that is the record's identity and status (Quarantine, Released, Rejected,
Cancelled), an active hold, an applicability hold, an out-of-specification result or an open
investigation, a result awaiting independent review, a superseded revision, a stale record, a due
or overdue stability pull, an expired reagent or calibration, and an amended certificate. Place
them:

- Status and up to four identifying facts in `{% page_meta %}`, never three panels down.
- A blocking or attention state is a `{% notice %}` above the facts (`blocking=True` when it stops
  the task). An unavailable action says why before any PIN is requested.
- Status is `{% status label=… tone=… %}` through the app's tone partial (for example
  `quality/includes/lot_status.html`); text plus a glyph, never colour alone.
- One emphasis per region; everything else stays quiet (`.vr-muted`, no extra pills).

Use only existing components. A new visual pattern is a design decision for the owner.

## 3. Assemble it from components

- `{% load ui %}` and use the registered tags (`core/templatetags/ui.py`, `COMPONENTS`). Never
  `{% include %}` anything in `templates/includes/`: a tag renders in its own context and reads
  only the parameters you pass (`tests/test_include_isolation.py`). A page's own partial is
  included only with `only`. When a component lacks a variation, add a parameter (header comment
  in the include + its `COMPONENTS` entry + an isolation case); don't copy its markup.
- Panels own their spacing: every body insets by `--vr-panel-inset` and stacks by `--vr-stack`.
  No padding or margin utilities inside a panel body; use `{% panel_section %}` and
  `table=True`. No panel inside a panel (`e2e/test_panel_spacing.py`).
- Lists: the server filters, sorts and pages the whole authorized queryset with
  `core.grids.paginate(request, queryset)` (`PAGE_SIZES` 25/50/100, `?per_page=`); pass
  `sizes=True` to `{% list_results %}` only then. Filters are a Django form handed to
  `{% grid_toolbar inline=… more=… %}`. The identifier in the first column is the row link
  (`th[scope=row] > a.vr-row-link`); no Open/View link. Give each column a stable `col`, lock the
  identifier, mark secondary columns `priority="low"`. `static/js/grid.js` only shows, hides and
  reorders columns of `<table data-vr-grid="app.list" data-vr-grid-version="1">`; layouts are
  saved per user on the server (`core/preferences.py`, keys `grid:<grid>:v<n>`). Renaming or
  removing a column id bumps `data-vr-grid-version`.
- Wording (ui-standards, "Language and accessibility"): `New <thing>` creates, `Record` adds an
  observation, `Change` changes a controlled state, `Correct` keeps the prior record with a
  reason, `Cancel` exits. Sentence case. Title, breadcrumb, sidebar item and opening button use
  the same words. `QC disposition` never means manufacturer release. No compliance claims.
- Roles and states: a control a role can never use is not rendered; one unavailable in the
  current state is explained in text. Hiding is a courtesy: the view and service authorize every
  read and mutation (AGENTS.md rules 3–5). A new top-level destination is a `NavItem` in
  `core/navigation.py`.

## 4. Forms and controls

- Render fields through Django forms: `{% form_page %}`, `{% field %}`. No hand-written
  `<input>`, `<select>`, `<datalist>`, date, number or file control in a page
  (`tests/test_controls.py`). Each control is a widget template in
  `templates/django/forms/widgets/` enhanced by `static/js/controls.js`; see
  `references/components.md`.
- A large or growing model choice (lots, materials, suppliers, users, methods) uses
  `widget=core.lookups.RemoteSelect("<lookup>")` with a `Lookup` registered in `core/lookups.py`.
  Its `queryset(request)` authorizes by role (`require_role`); the field's own queryset stays the
  validator, and the lookup's `source` offers the same records (`tests/test_lookups.py`). Short
  configuration lists and lists scoped to one record stay inline.
- Numbers are text inputs so the exact string reaches the `Decimal` field (the number widget).
  Units go on the widget, `forms.TextInput(attrs={"unit": "mg/g"})` style, never in the label.
- Validation is server-side in the form; errors render inline through `{% form_errors %}` and
  the field template, entered values are kept. A PIN field is never prefilled and never echoed.
- A plain data-entry page that should open in the dialog is listed in `FORM_SURFACES`
  (`core/form_surfaces.py`) with the same roles as its view (`tests/test_form_dialog.py`).
  Signing pages are never listed.

## 5. Style: tokens and icons only

- Colours, spacing, type, radius, shadow and layers come only from the `--vr-*` tokens in the
  Tokens section of `static/css/app.css` (light, dark and print). Templates have no inline style,
  `<style>`, colour literal, raw px/rem or unthemed colour utility. Muted text is `.vr-muted`
  (`tests/test_css_tokens.py`, `tests/test_ui_standards.py`).
- Icons are Bootstrap Icons symbols copied verbatim into `static/img/icons.svg` as `i-<name>`,
  drawn with `{% icon name="…" %}` or `window.vrUi.icon` (`static/js/app.js`); scripts build
  buttons with `window.vrUi.button`. Never draw an SVG or glyph (`tests/test_icons.py`).
- The content security policy forbids inline scripts and styles.

## 6. Verify

```sh
set -a; . ./.env; set +a
uv run ruff check . && uv run ruff format --check .
uv run python manage.py check
uv run python manage.py collectstatic --noinput -v0
TEST_DATABASE_NAME=test_open_qual_<you> uv run pytest tests/test_ui_standards.py tests/test_css_tokens.py \
  tests/test_include_isolation.py tests/test_controls.py tests/test_icons.py tests/test_lookups.py \
  tests/test_form_dialog.py tests/test_preferences.py pagedocs <the app's tests>
```

Then open the page on the dev server (http://127.0.0.1:8010, `demo_analyst`, `demo_reviewer`,
`demo_quality`, `demo_auditor`, `demo_admin`) as each role that sees it, in light and dark, at
1280px and a phone width, keyboard only through the dialogs. For layout changes run the browser
checks (`e2e/test_panel_spacing.py`, `e2e/test_alignment.py`, `e2e/test_shell_layout.py`) and the
journeys that open the page; see the `project-code-review` skill.

## 7. Then document it

If any visible content, action, field, filter, permission or rule changed, run the
`document-page` skill and update `docs/pages/` in the same change. A pure markup refactor that
renders the same needs no doc change.
