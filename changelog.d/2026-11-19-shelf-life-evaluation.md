---
date: 2026-11-19
type: added
impact: high
title: Shelf-life evaluation from stability data
area: Stability
link: stability:shelf_life_list
---
Under **Stability**, **Shelf life**, quality evaluates the shelf life one test supports at one storage condition, from the results of the studies of a protocol in one container closure. Each study's results are fitted by a straight line on months on stability, an analysis of covariance decides whether the studies are pooled, and the estimate is where the 95 % confidence limit of the mean meets the acceptance criterion, the method of ICH Q1E; the page draws the results with the lines and the limit. Another quality person, who neither drafted the evaluation nor produced its results, concludes it with a signature that records the shelf life, no longer than the estimate, and freezes the data and figures.

## Technical notes

- Migrations `stability.0006` and `stability.0007` add `stability_shelflifeevaluation` and `stability_shelflifestudy` with database guards: nothing is deleted, what an evaluation was drafted from never changes, every change advances its revision, a concluded or withdrawn evaluation never changes, and studies are linked or unlinked only while it is a draft and only of its protocol code and container closure. No existing row changes.
- The statistics (`stability/regression.py`) work in `Decimal` to 50 significant digits, with Student's t and F distributions from the incomplete beta function; they are checked against the NIST Norris dataset and the published t table.
- The conclusion (meaning `concluded`) freezes `oq.shelf-life/1` and is refused when the results changed since the page was opened. New audit actions: `shelf_life.drafted`, `shelf_life.changed` and `shelf_life.withdrawn`. New lookup `shelf-life-studies`; the stability section gains the **Shelf life** tab.
