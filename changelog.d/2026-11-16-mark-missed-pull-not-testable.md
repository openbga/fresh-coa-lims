---
date: 2026-11-16
type: changed
impact: low
title: Mark a pull missed when it was taken but cannot be tested
area: Stability
link: stability:pull_list
pr: 32
---
**Mark missed** also applies to a pull that was taken but cannot be tested, when nothing of its testing is in progress and none of its results failed.

## Technical notes

- **Mark missed** also applies to a pull that was taken but cannot be tested, when nothing of its testing is in progress, it is not ready for acceptance and none of its results failed. Rejecting a QC batch leaves an open test of a missed pull, or of a closed study, as it is.
