---
date: 2026-11-17
type: changed
impact: medium
title: Every dashboard and overview count opens exactly the items it counts
area: Dashboard
link: quality:dashboard
---
Each count on the **Dashboard**, the **Stability** overview and the **Laboratory** overview now opens a list that shows exactly that many rows, and every Dashboard queue is a link. **Material lots** has a new **Queue** filter for the Dashboard's lot queues, **Sampling** a status **Awaiting quality assessment**, **Testing** a status **Retests and resamples not done**, and **Reserve samples** a status **Retention anchor not yet known**.

## Technical notes

- Lot queues are defined once in `quality.dashboard.LOT_QUEUES` / `lot_queues()`; the material lot list filters by the same querysets (`?queue=<key>`). Test queues use `analytical.views.TEST_FILTERS` (new key `repeats`); sampling deviations use `sampling.views.deviation_to_assess()`; reserves use `stability.views._reserve_filter`.
- Tests open, Awaiting review and open investigations now include stability testing, as their lists do. Queues that open a list of lots count lots.
- `tests/test_dashboard.py` and the overview tests compare every linked count with the rows of its list for each reader role.
