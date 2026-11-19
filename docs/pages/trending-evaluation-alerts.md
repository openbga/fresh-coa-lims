---
title: Add alerts to an evaluation
urls: trending:evaluation_alerts
views: trending.views.evaluation_alerts
templates: catalog/form.html
models: trending.Evaluation, trending.EvaluationAlert, trending.Chart, core.AuditEvent
reviewed: 2026-11-19
summary: Add further open alerts of the same chart to an evaluation that is still open. Quality only. The evaluation covers at most 50 alerts.
---

## Common tasks

### Add alerts

1. Tick the [[Alerts]] to add.
2. Enter the [[Reason]] and select [[Add alerts]]. You return to the evaluation.

### Leave without adding

1. Select [[Cancel]]. Nothing is added.

## Good to know

- Only open alerts of this evaluation's chart are offered: alerts raised since it was opened, or left out of it.
- Added alerts are never removed or changed.
- A concluded evaluation takes no more alerts; the page sends you back with "OOT-n is concluded: it no longer changes."
- Adding alerts does not stop you from concluding the evaluation later.

## Purpose

Adds open alerts of the chart to an open evaluation.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- A chart with no further open alert gives "TC-n has no further open alert." and returns to the evaluation.

## Layout

- **Header**: title "Add alerts · OOT-n" and an introduction: "Open alerts of the same chart, raised since the evaluation was opened or left out of it."
- **Record** panel: Evaluation (OOT-n · TC-n and title).
- **Form sections**: Alerts (one checkbox per open alert: test T-n · lot number · result as reported with unit · review time · rules broken), Change control (Reason). Buttons **Cancel** (to the evaluation) and **Add alerts**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add alerts** | The evaluation is open | Quality | Adds the alerts; message "Alerts added to OOT-n."; returns to the evaluation |
| **Cancel** | Always | Quality | Returns to the evaluation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Alerts | `EvaluationAlert.test` | Checkboxes, at least one | Yes | The results whose alerts are added; none is ticked at first |
| Reason | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `Evaluation.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Checked on saving** (under the chart's lock): the evaluation is still open ("OOT-n is concluded: it no longer changes."); the revision is unchanged ("Record changed. Reload before saving."); the total stays within 50 ("An evaluation covers at most 50 alerts."); each alert is still open ("No longer open alerts of this chart: T-n. Reload the chart."); "Choose at least one alert."; "A reason is required."
- **Effect**: the alerts are stored with the result, the limits version that judged it, the review time and the rules broken; the revision rises by 1; audit event `evaluation.alerts_added` lists them with your reason.

## Related pages

- Evaluation record
- Chart record
