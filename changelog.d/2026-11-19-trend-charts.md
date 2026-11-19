---
date: 2026-11-19
pr: 68
type: added
impact: high
title: Trend charts of release results with approved limits and out-of-trend alerts
area: Trends
link: trending:chart_list
---
Under **Trends**, quality keeps a chart for each test it follows, of a material at a stage: the reviewed release results of its lots, in the order their reviews were signed. Limits are computed from a baseline of results (mean ± 3σ) or entered, with the run, trend and zone rules quality chooses, and another quality person approves each version with a signature. A result that meets its specification and breaks a rule raises an out-of-trend alert, shown on the chart, in **Reminders** and as a notice where the lot's disposition is signed; quality evaluates alerts in an **Out-of-trend evaluation** concluded with a signature by someone who recorded none of its findings or of the results' data.

## Technical notes

- New app `trending`; migrations `trending.0001` and `trending.0002` add `trending_chart`, `trending_limits`, `trending_evaluation` and `trending_evaluationalert` with database guards: a chart never changes, an approved limits version changes only by setting `superseded_at` once, a concluded evaluation never changes, every change of an open one advances its revision, and alert rows are inserted only while their evaluation is open and never changed or deleted. Nothing is ever deleted. No existing row changes.
- Alerts are derived on reading from reviewed tests, their review signatures and the limits in force; only the alerts an evaluation covers are stored. A result that fails its specification raises no alert.
- Approval (meaning `approved`) freezes `oq.trend-limits/1`; the conclusion (meaning `concluded`) freezes `oq.out-of-trend/1`. New audit actions: `trend_chart.created`, `trend_limits.drafted`, `trend_limits.changed`, `trend_limits.superseded`, `evaluation.opened`, `evaluation.alerts_added` and `evaluation.findings_recorded`.
- New lookup `trend-lines`; reminders take the kind `trend`; the **Trends** item joins the Work section of the navigation.
