---
date: 2026-11-17
type: changed
impact: medium
title: Password and Sign-in announcement pages show the current state
area: Account access
link: accounts:password
---
**Password** now shows whether a new password is required and when you last changed it; **Change password** opens the change in a dialog. **Sign-in announcement** shows the notice as visitors see it and its history; **Change announcement** opens the signed change. Account changes and the announcement change are signed on the same signature card as other signing pages.

## Technical notes

New URL names `accounts:password` (`/accounts/password/`) and `accounts:announcement_change` (`/accounts/announcement/change/`); `accounts:password_change` moved to `/accounts/password/change/`. A required password change still goes straight to the change form.
