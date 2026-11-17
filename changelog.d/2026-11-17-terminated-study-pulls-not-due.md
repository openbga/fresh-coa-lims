---
date: 2026-11-17
type: fixed
impact: medium
title: Pulls of a terminated study are no longer shown as overdue or due
area: Stability
link: stability:pull_list
---
A pull that was not taken or not accepted when its study was terminated now reads **Terminated** and no longer counts as **Overdue**, **Due now**, **Upcoming** or **Awaiting acceptance** in the pull list, on the study page, in the Stability overview or on the Dashboard. **Mark missed** is no longer offered for it.

## Technical notes

`stability.views._pull_filter` limits the work statuses to active studies; the overview and the Dashboard count through it. A closed study and its pulls already took no more work (`stability.services.close_study`).
