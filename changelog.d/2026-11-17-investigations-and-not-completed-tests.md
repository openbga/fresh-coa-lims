---
date: 2026-11-17
type: changed
impact: medium
title: Investigations account for tests recorded as not completed
area: Testing
link: analytical:investigation_list
pr: 45
---
A retest or resample recorded as not completed before it held any reading no longer uses up the investigation's retest allowance. An investigation can still be concluded when the test opened for it was recorded as not completed.

## Technical notes

- The retest allowance of an investigation (`retests_used`) no longer counts an authorized retest or resample recorded as not completed before it held any reading, correction or raw-data file. An investigation is not concluded as invalidated while one of its tests was recorded as not completed with a reading outside the limits, and the investigation opened on a test recorded as not completed can be concluded although that test was never reviewed.
