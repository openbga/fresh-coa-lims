---
date: 2026-11-16
type: fixed
impact: low
title: Warning about a copied security key only for a signed answer
area: Account access
link: accounts:two_factor
pr: 37
---
The warning that a copy of a security key may exist is logged only when the key signed the answer. An unsigned answer can no longer raise it.

## Technical notes

- The warning that a copy of a security key may exist is logged only for an answer the key signed: the signature count is now compared after the signature is checked, so an unsigned answer can no longer raise it.
