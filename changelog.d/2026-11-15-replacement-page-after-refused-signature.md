---
date: 2026-11-15
type: fixed
impact: medium
title: Requirement replacement can be signed again after a refused signature
area: Lots
link: quality:lot_list
pr: 30
---
After a refused signature the replacement page can be signed after review without being opened again. Before, every further attempt was refused as stale.

## Technical notes

- After a refused signature the replacement page carries the token and the lot revision of what it then shows, so it can be signed after review without being opened again; before, every further attempt was refused as stale.
