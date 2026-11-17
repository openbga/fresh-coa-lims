---
date: 2026-11-14
type: fixed
impact: low
title: Recording sampling no longer meets a database conflict
area: Sampling
link: sampling:lots
pr: 26
---
Recording sampling and another change to the same lot by the same analyst at the same moment could show an error page. Nothing wrong was saved, and the case no longer occurs.

## Technical notes

- Recording sampling now locks the analyst's account before the lot, the order every other change to a lot uses. An analyst who recorded sampling and another record of the same lot at the same moment could meet a database deadlock and an error page; nothing wrong was saved.
