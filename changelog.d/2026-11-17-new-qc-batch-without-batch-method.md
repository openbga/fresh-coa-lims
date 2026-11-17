---
date: 2026-11-17
type: fixed
impact: medium
title: New QC batch no longer fails when no batch method is approved
area: Testing
link: analytical:batch_list
pr: 46
---
**New QC batch** returned an error page when there was no approved batch method. It now opens with the notice "No approved batch method is available; batches are held."
