---
date: 2026-11-17
type: changed
impact: high
title: New visual design for the whole interface
area: Whole application
pr: 46
---
The interface has a new look, **Line**: calm tonal surfaces, rounded panels, a petrol accent and one type family, in light and dark. Each record answers what matters now first, with status and hold pills, the critical facts and the actions that resolve a state beside one primary action. Scientific, signing and audit behaviour is unchanged.

## Technical notes

- Every template of every app is built on one component registry (`{% load ui %}`, `core/templatetags/ui.py`): isolated, keyword-only tags for panels, notices, lists, facts, record layouts, form pages, form dialogs, signature cards, history, status pills, material tags and code chips. Per-app copies of empty states, pagers, history and toolbars are gone; `tests/test_include_isolation.py` and `tests/test_ui_standards.py` enforce it.
- Design tokens have full scales (space, type, weight, radius, shadow, z-index) with `--bs-*` semantic colours mapped onto them for light, dark and print; no colour literals outside the Tokens section (`tests/test_css_tokens.py`). Bootstrap Icons only, copied verbatim (`tests/test_icons.py`).
- Records lead with status and hold pills, the material tag and the critical facts (holds, out-of-specification results, overdue, revoked, amended, superseded). The lot record and signing share one `disposition_blockers()` list, extracted from `dispose_lot` with the same order and conditions under the lock. The signature dialog markup moved to `{% signature_card %}` with unchanged semantics.
- Tests changed on evidence: markup assertions moved to stable hooks (`data-audit-action`, `data-signature-dialog`, and similar); none was weakened. The page documentation, the roadmap and `docs/product.md` status were updated with the change.
