---
title: Trend chart record
urls: trending:chart_detail
views: trending.views.chart_detail
templates: trending/chart_detail.html, ops/record.html
models: trending.Chart, trending.Limits, trending.Evaluation, trending.EvaluationAlert, analytical.AnalyticalTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One trend chart: the drawn results with the center line, limits and specification limits, the open alerts, the results, the limits versions and the evaluations. Quality drafts limits and evaluates alerts from here.
---

## Common tasks

### Read the chart

1. Look at the drawing: each result in the order its review was signed, with the center line, the limits and the specification limits.
2. Read [[Open alerts]] for results that broke a rule and that no evaluation covers yet; read [[Results]] for every plotted result, newest first.

### Draft the limits

1. Select [[Draft limits]]. It shows to quality while the chart has no draft; with a draft it reads [[Open draft v1]] and opens that draft.
2. Another quality person approves the draft on its own page.

### Evaluate open alerts

1. Select [[Evaluate alerts]]. It shows to quality while the chart has an open alert.
2. Choose the alerts to look into together on the form that opens.

### Find out why a result is not drawn

1. Read [[Not plotted]]: it lists reviewed results of this test without a value in the chart's unit, with the reason.

## Good to know

- A result that fails its specification is flagged "Out of specification" and raises no alert here; its out-of-specification investigation deals with it.
- Each result is judged by the limits version in force when its review was signed, so approving new limits does not re-judge earlier results.
- The drawing and the Results table show the latest 100 results; Results plotted counts all of them. Open alerts lists every open alert.
- Stability and reassessment tests are not plotted, and a lot counts only while its current assignment is this chart's material and stage.

## Purpose

Shows one chart with everything recorded about it, and leads to its limits and evaluations.

## Who can use it

- Sign-in required. Viewing: analyst, reviewer, quality, admin or auditor; others receive 403.
- **Draft limits**, **Open draft vN** and **Evaluate alerts** show to the quality role only; the server checks the role on each target page.

## Layout

- **Header**: the test name and material code ("Test name · MAT-CODE"), the state, TC-n and the action buttons.
- **Notice**: "Out-of-trend alerts" (red) with the number of results that broke a rule and are not covered by an evaluation; "No approved limits" (blue) when results are plotted but no alert is raised until a version is approved.
- **Details**: Material, Stage, Test, Unit, Limits in force (v-number link or "None"); with limits in force also Center line, Limits (lower to upper) and Rules; then Results plotted and Created by.
- **Chart**: the drawing with a key (Result, and, when they appear, Alert not evaluated, Alert evaluated, Out of specification, Center line, Limits, Specification limits) and a note when only the latest results are drawn. Empty: "No result plotted yet" ("Results appear here once a review of this test is signed for a lot of this material and stage.").
- **Open alerts**, **Results**: columns Test (T-n link), Lot, Result, Review signed, Limits, Flag, Rules broken. Limits and Rules broken give way first on narrow screens. Empty: "No open alert." and "No reviewed result of this test yet."
- **Not plotted** (only when there is one): Test, Lot, Review signed, Why.
- **Limits versions**: Version, State, Basis, Center line, Lower limit, Upper limit, Approved. Empty: "No limits drafted yet."
- **Evaluations**: Evaluation (OOT-n link), State, Alerts, Opened. Empty: "No evaluation yet."
- **Signatures** and **History**: the signatures bound to the chart and the audit events of the chart.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Draft limits** | The chart has no draft | Quality | Opens the Draft limits form; it is the primary button while no alert is open |
| **Open draft vN** | The chart has a draft | Quality | Opens the draft limits version |
| **Evaluate alerts** | The chart has an open alert | Quality | Opens the Evaluate alerts form; it is the primary button |
| T-n, lot, v-number, OOT-n links | In the tables | Any viewer | Open the test, the lot, the limits version or the evaluation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Material, Stage, Test, Unit | `Chart.material`, `stage`, `test_code`, `name`, `unit` | Text | — | What the chart follows, fixed when it was created |
| Limits in force | `Limits.version` | v-number link | — | The approved version not yet superseded |
| Center line, Limits, Rules | `Limits.center`, `lower`, `upper`, `rules` | Figures in the chart's unit, rule texts | — | Of the version in force; Limits shows lower to upper with the one that exists |
| Results plotted | — | Count | — | Every plotted result |
| Created by | `Chart.created_by` | Person | — | Who created the chart |
| Result | `AnalyticalTest.reportable_value`, `reportable_display` | Number and unit | — | The result as reported, at its reporting precision; the exact value when no reported text exists |
| Review signed | — | Date and time | — | When the review signature was signed; results are ordered by it |
| Limits | `Limits.version` | v-number link | — | The version that judged the result; empty before any version was approved |
| Flag | — | "Out of specification" (red), "Alert, not evaluated" (red), or the OOT-n link with an "Alert" pill | — | Empty for a result that broke no rule |
| Rules broken | `Limits.rules` | Text | — | The rules the result broke, with the run and trend lengths of its version |
| Why (Not plotted) | — | Text | — | "Not a numeric result", "In another unit (unit)" or "Reported as ..." |
| State | `Limits.state`, `superseded_at` | Draft, In force, Superseded | — | State of each limits version |

## Rules and hidden logic

- **Which results are plotted**: reviewed tests of lots whose current assignment is the chart's material and stage, with the chart's test code, a numeric or count result and a reportable value in the chart's unit, ordered by the time their review was signed. Tests of stability pulls and reassessments, invalidated, superseded and unfinished tests are not plotted.
- **Judging**: each result is judged with the results before it by the limits version in force when its review was signed. A result before any approved version raises no alert. The rule is broken at the result that completes the pattern, and that result is flagged. Results are judged as the record stands: when an earlier result is invalidated or its lot is assigned again, the results after it are judged again, so an alert can appear or go. A result an evaluation covers keeps the version and rules recorded with its alert.
- **Alerts**: a result that conforms to its specification and breaks a rule raises an alert. A result that fails its specification is flagged "Out of specification" and raises none. Alerts are read from the record each time, not stored, until an evaluation covers them.
- **Paging**: the drawing and the Results table show the latest 100 results, with a note giving the count; Open alerts is not limited.
- **Header actions**: **Draft limits** is the primary button only while no alert is open; with open alerts **Evaluate alerts** is.
- **Signatures and history** are those of the chart object; limits and evaluation events are on their own pages.
- **Immutability**: a chart is never changed or deleted.

## Related pages

- [Trend charts](/trends/)
- Draft limits, Limits record
- Evaluate alerts, Evaluation record
- Test record and lot record (links in the tables)
