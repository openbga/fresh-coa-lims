---
date: 2026-11-17
type: changed
impact: medium
title: Stability no longer accepts rejected or cancelled lots
area: Stability
link: stability:study_list
pr: 44
---
A study cannot be started on a rejected or cancelled lot, and a reserve sample, retention obligation or hold is refused on a cancelled lot. Their forms no longer offer those lots.

## Technical notes

- Stability refuses to start a study on a rejected or cancelled lot, and refuses a reserve sample, retention obligation or hold on a cancelled lot; their forms no longer offer those lots.
