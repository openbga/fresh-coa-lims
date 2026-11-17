---
date: 2026-11-17
type: changed
impact: medium
title: A test record offers New QC batch when no open batch accepts the test
area: Testing
link: analytical:test_list
---
**Add to QC batch** is offered only when an open QC batch of the test's method revision accepts it. Otherwise the header says why and offers **New QC batch**, which opens with that method revision already chosen.

## Technical notes

`analytical.views.batch_offer` is shared by the test record and the Add to QC batch page; `batch_new` reads `?method=<code>&revision=<n>`.
