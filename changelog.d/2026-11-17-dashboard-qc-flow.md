---
date: 2026-11-17
type: added
impact: medium
title: Dashboard shows the QC flow with counts
area: Dashboard
link: quality:dashboard
pr: 46
---
The **Dashboard** shows the QC flow from lot to sample, result, review, disposition and certificate of analysis, with the number of items waiting at each stage and the date of the oldest. Each count opens the list it counts.

## Technical notes

`quality/dashboard.py`. Every queue is one aggregate query (count and oldest date) on the same conditions as the list it links to, so a count and its list agree. Counts are not scoped per user: every reader role sees the same laboratory, as in the lists, and the services decide who may act. A lot can sit in two queues; a stage total is the sum of its queues.
