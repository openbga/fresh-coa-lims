---
date: 2026-11-15
type: fixed
impact: low
title: Assigning tests no longer meets a database conflict
area: Testing
link: analytical:test_list
pr: 29
---
Assigning tests while the same account signed another change could end in an error page. The conflict no longer occurs.

## Technical notes

- Assigning tests locks the analyst's account first, like every other change to a lot; one account that signed while it assigned tests could meet a database deadlock and an error page.
