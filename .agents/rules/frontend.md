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

Full standard: `docs/ui-standards.md`.

- Build pages from the shared templates: `templates/base.html`, `templates/layouts/` and
  `templates/includes/*.html` (`field`, `form_errors`, `status`, `breadcrumbs`, `section_tabs`,
  `history_item`, `record_foot`, …). Read an include's header comment before using it. Never copy
  its markup into a page; ask its owner for a parameter instead.
- TODO: name the `{% load ui %}` component registry here once `.local/team/components-contract.md`
  is settled.
- Colours, spacing, type, radius and shadow come only from the `--vr-*` tokens in the Tokens section
  of `static/css/app.css`, in light and dark. No hex/rgb/hsl, inline `style` or utilities that
  bypass the theme tokens.
- Icons are Bootstrap Icons only, from `static/img/icons.svg` as `i-<name>`, rendered through
  `{% include "includes/icon.html" with name="…" %}` and paired with visible or visually hidden
  text. Never draw or invent an icon. Exceptions: the brand mark and the sign-in art.
- Controls are Bootstrap form components through the Django widget templates in
  `templates/django/forms/widgets/`; forms build on `core.forms.StyledForm`. Validation is
  server-side in the Django form and errors render inline.
- Signing uses the shared signature dialog (`templates/signatures/`, `static/js/signature-dialog.js`)
  as a view of a server-enforced transition; never offer self-review.
- No toasts. One primary action per page header.
- When a page's visible content, actions, fields or rules change, update its doc in `docs/pages/`
  with the `document-page` skill (`.agents/skills/document-page/SKILL.md`).
