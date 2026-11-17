---
date: 2026-11-13
type: added
impact: high
title: Equipment, reagent and analyst checks when a result is entered
area: Testing
link: laboratory:equipment_list
pr: 22
---
Recording or correcting a result, or a batch QC check, names the instruments and the reagent or standard lots used, and is refused when one of them is not fit for use or the analyst has no current qualification for the method. After a failed calibration the equipment page lists the tests and QC batches that used the equipment.

## Technical notes

- Equipment and reagent checks at result entry: recording or correcting a result or a batch QC check names the instruments and the reagent or standard lots used. An entry is refused when an instrument is out of service or out of calibration, a lot is not released or expired, or the analyst has no current qualification for the method, which now applies to batch QC as well. A method version can require an instrument, a lot or both. After a failed calibration the equipment page lists the tests and QC batches that used the equipment.
- `ANALYTICAL_BENCH` replaces `ANALYTICAL_ELIGIBILITY_CHECK`. A deployment that overrides the old setting must name a bench class instead; without one, results are held.
