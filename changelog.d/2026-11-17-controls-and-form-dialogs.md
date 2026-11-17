---
date: 2026-11-17
type: changed
impact: medium
title: Selects, dates, files and plain create forms use shared controls
area: Whole application
pr: 46
---
Selects, date and date-time fields, file fields and decimal inputs with units look and behave the same on every page, and a select that searches records shows only what the person may use. Plain create forms open in a dialog that asks before unsaved changes are lost; signing pages never use the dialog.

## Technical notes

- Tom Select replaces every browser select. A permission-scoped remote select is served by `core/lookups.py` (one endpoint, `/lookups/<name>/`, and a registry; role-scoped querysets, `tests/test_lookups.py`).
- A shared date and date-time popover (week starting Sunday, Today, Yesterday, Now and Clear; laboratory-local time), decimals kept as typed with unit addons, a file drop zone and tooltips. All forms are `novalidate` with server errors shown inline.
- Form dialog: `core.form_dialog.FormDialogMiddleware` and the context processor `core.form_surfaces.form_presentation`; the sticky footer is only in dialogs and a record's history is never inside one.
