---
date: 2026-11-16
type: security
impact: high
title: Django admin sign-in goes through the application's sign-in
area: Sign-in
pr: 34
---
The sign-in page of Django admin no longer signs anyone in. It sends the person to the application's sign-in, so the sign-in lock and the two-factor step apply to every session.

## Technical notes

- Django admin's own sign-in page (`/admin/login/`) no longer signs anyone in: it redirects to the application's sign-in, with the admin page to return to, so the sign-in lock and the two-factor step apply to every session.
