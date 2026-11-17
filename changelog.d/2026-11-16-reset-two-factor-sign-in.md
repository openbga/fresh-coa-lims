---
date: 2026-11-16
type: added
impact: medium
title: Administrators can reset an account's two-factor sign-in
area: Users and roles
link: accounts:user_list
pr: 34
---
An administrator can remove an account's authenticator and recovery codes with a signed **Reset two-factor sign-in**, which also ends its sessions. **Users and roles** shows and filters accounts by two-factor sign-in.

## Technical notes

- **Reset two-factor sign-in** on an account (admin, signed with the meaning `account_authorized`, not on one's own account) removes its authenticator and recovery codes and ends its sessions; the audited command `reset_two_factor <username> --actor <administrator> --reason ...` does the same from the operator shell. **Users and roles** shows and filters accounts by two-factor sign-in.
