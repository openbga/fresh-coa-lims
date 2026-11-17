---
date: 2026-11-17
type: added
impact: medium
title: List columns, page size, sort and sidebar state are saved for each user
area: Whole application
pr: 46
---
Every list remembers the page size, sort order and columns a person chose, and the sidebar and the page-help panel remember whether they are collapsed or open. The settings follow the account, so they apply on a shared laboratory workstation after sign-in. Lists hide low-priority columns by their own width so they fit 1280 and 1440 pixel screens and an open help panel.

## Technical notes

Stored on the server in `core.UserPreference` (migration `core/0007_user_preference.py`). The endpoint is `/preferences/` (per user, CSRF-protected) with `core.preferences.GridPreferenceMiddleware`; the page-help panel keeps its own state in the same table. Writes that arrive out of order no longer overwrite a later one.
