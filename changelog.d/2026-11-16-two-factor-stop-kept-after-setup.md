---
date: 2026-11-16
type: security
impact: high
title: A stopped second factor stays stopped when a new app is confirmed
area: Account access
link: accounts:two_factor
pr: 36
---
After 100 wrong codes stop two-factor sign-in, confirming a new authenticator app no longer clears the stop. Only an administrator's reset does.

## Technical notes

- Confirming a new authenticator app after 100 wrong codes stopped two-factor sign-in no longer clears the stop; a setup started before the stop is refused, and only an administrator's reset clears it.
