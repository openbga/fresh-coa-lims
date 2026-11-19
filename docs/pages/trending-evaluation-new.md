---
title: Evaluate alerts
urls: trending:evaluation_new
views: trending.views.evaluation_new
templates: catalog/form.html
models: trending.Evaluation, trending.EvaluationAlert, trending.Chart, core.AuditEvent
reviewed: 2026-11-19
summary: Open an out-of-trend evaluation for chosen open alerts of one chart, at most 50. Quality only. Findings are recorded afterwards and another quality person concludes it.
---

## Common tasks

### Open an evaluation

1. Keep ticked the [[Alerts]] to look into together, typically the results of one run or one shift, and untick the others.
2. Enter the [[Reason]] and select [[Open evaluation]]. The evaluation opens.

### Leave without opening

1. Select [[Cancel]]. Nothing is opened and the alerts stay open.

## Good to know

- All open alerts of the chart are ticked at first. Untick any you want to leave out; they stay open.
- You can add more open alerts of the same chart while the evaluation is open.
- An evaluation covers at most 50 alerts, and a result can be covered by one evaluation only.
- Opening the evaluation or adding alerts is not authorship of the findings: you can still conclude it if you record none of the findings or the covered results' data.

## Purpose

Opens an out-of-trend evaluation for alerts of one chart.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- A chart with no open alert gives "TC-n has no open alert." and returns to the chart.

## Layout

- **Header**: title "Evaluate alerts · TC-n" and an introduction: "Choose the alerts to look into together, typically the results of one run or one shift. Further alerts of this chart can be added while the evaluation is open."
- **Record** panel: Chart.
- **Form sections**: Alerts (one checkbox per open alert: test T-n · lot number · result as reported with unit · review time · rules broken), Change control (Reason). Buttons **Cancel** (to the chart) and **Open evaluation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Open evaluation** | The chart has an open alert | Quality | Creates the evaluation as open; message "OOT-n opened."; opens the evaluation |
| **Cancel** | Always | Quality | Returns to the chart |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Alerts | `EvaluationAlert.test` | Checkboxes, at least one, at most 50 | Yes | The results whose alerts this evaluation covers |
| Reason | audit reason | Text, max 2000 | Yes | Stored in the audit event |

## Rules and hidden logic

- **Alerts offered**: the chart's open alerts as worked out now: results that conform to their specification, broke a rule of the limits in force when their review was signed, and are covered by no evaluation.
- **Checked again on saving** (under the chart's lock, so approving limits cannot interleave): "Choose at least one alert."; "An evaluation covers at most 50 alerts."; "No longer open alerts of this chart: T-n. Reload the chart." when an alert was covered or no longer applies meanwhile; "A reason is required."
- **Effect**: the evaluation is created open, revision 1, opened by you, and each alert is stored with its result, the limits version that judged it, its review time and the rules it broke, as they stood now. Audit event `evaluation.opened` lists the alerts with your reason.
- **Immutability**: the covered alerts never change or leave the evaluation.

## Related pages

- Chart record
- Evaluation record (opens after saving)
