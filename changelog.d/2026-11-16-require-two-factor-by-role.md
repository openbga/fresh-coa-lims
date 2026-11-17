---
date: 2026-11-16
type: added
impact: high
title: Require two-factor sign-in for chosen roles
area: Account access
link: accounts:two_factor
pr: 34
---
A deployment can require two-factor sign-in for chosen roles or for everyone. Until it is set up, such an account reaches only the two-factor page, password change, page help and sign-out.

## Technical notes

- The new setting `MFA_REQUIRED_ROLES` (comma-separated laboratory roles or `all`; empty by default) requires it: such an account reaches only the two-factor page, password change, page help and sign-out until it is set up. Shared demonstration accounts cannot set it up and are never required to.
