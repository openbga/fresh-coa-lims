---
paths:
  - "templates/**"
  - "*/templates/**"
  - "static/css/**"
  - "static/js/**"
  - "*/static/**"
  - "*/templatetags/**"
  - "*/forms.py"
  - "docs/pages/**"
---

# Frontend rules

Full standard: `docs/ui-standards.md`. Enforced by `tests/test_ui_standards.py`,
`tests/test_css_tokens.py`, `tests/test_controls.py` and `tests/test_icons.py`.

- Build pages from the `{% load ui %}` components (`core/templatetags/ui.py`, `COMPONENTS`):
  `panel`, `panel_section`, `list_results`, `grid_toolbar`, `sort_header`, `pagination`, `notice`,
  `status`, `fact`, `page_meta`, `record_layout`, `form_page`, `form_actions`, `field`,
  `signature_card`, `signature_list`, `history_panel`, `history_item`, `post_button`,
  `confirm_dialog`, `more_actions`, `breadcrumbs`, `section_tabs`, `icon` and the shell pieces in
  `templates/layouts/document.html`. Each tag's parameters are in the header comment of
  `templates/includes/<name>.html`. Never `{% include %}` a component or copy its markup
  (`tests/test_include_isolation.py`); add a parameter instead. Working order: the `build-page`
  skill.
- Colours, spacing, type, radius and shadow come only from the `--vr-*` tokens in the Tokens section
  of `static/css/app.css`, in light and dark. No hex/rgb/hsl, inline `style` or utilities that
  bypass the theme tokens.
- Icons are Bootstrap Icons only, from `static/img/icons.svg` as `i-<name>`, rendered through
  `{% icon name="…" %}` (scripts: `window.vrUi.icon`) and paired with visible or visually hidden
  text (`tests/test_icons.py`). Never draw or invent an icon. Exceptions: the brand mark and the sign-in art.
- Controls are Django form fields rendered through the widget templates in
  `templates/django/forms/widgets/`; `static/js/controls.js` enhances them (Tom Select, date
  popover, decimal/unit, file drop zone). Never write a raw `<select>`, date/number/file `<input>`
  or `<datalist>` in a page (`tests/test_controls.py`). Growing model lists use
  `core.lookups.RemoteSelect`. Per-user presentation settings use `core/preferences.py`
  (`window.vrPreferences`), not `localStorage`. Validation is server-side in the Django form and
  errors render inline.
- Signing uses the shared signature dialog (`templates/signatures/`, `static/js/signature-dialog.js`)
  as a view of a server-enforced transition; never offer self-review.
- No toasts. One primary action per page header.
- When a page's visible content, actions, fields or rules change, update its doc in `docs/pages/`
  with the `document-page` skill (`.agents/skills/document-page/SKILL.md`).
