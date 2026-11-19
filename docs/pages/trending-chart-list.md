---
title: Trend charts
urls: trending:chart_list
views: trending.views.chart_list
templates: ops/list.html
models: trending.Chart, trending.Limits, catalog.Material
reviewed: 2026-11-19
summary: Every trend chart, one per test of a material at a stage, with the limits in force and any open out-of-trend alerts. Find a chart, see which need attention, or create one. Quality creates; readers can open all.
---

## Common tasks

### Find a chart

1. Type a word of the test code, the test name or the material code or name in [[Search]].
2. Narrow the list with [[Status]] or [[Stage]], then apply the filter.
3. Select the TC number to open the chart.

### See which charts need attention

1. Choose [[Open alerts]] in [[Status]] for charts with results that broke a rule and that no evaluation covers yet.
2. Choose [[No approved limits]] for charts that raise no alert yet, or [[Limits drafted]] for charts waiting for approval of a draft.

### Create a chart

1. Select [[New trend chart]]. It shows only to quality users.
2. Choose the test and enter a reason on the form that opens.

## Good to know

- The state shows open alerts first: a chart with no approved limits cannot raise an alert, so "No approved limits" means nothing is being judged yet.
- Alerts are worked out from the reviewed results each time the page opens; nothing is stored until quality evaluates them.
- The Results column counts every plotted result of the chart, not only the latest ones the chart page draws.
- Analysts, reviewers, quality, admin and auditor accounts can read the list; only quality can create a chart.

## Purpose

The register of trend charts. Each chart follows one test of one material at one stage and shows whether its reviewed results break the rules of the limits quality approved.

## Who can use it

- Sign-in required. Roles that can open it: analyst, reviewer, quality, admin and auditor. Others receive 403.
- **New trend chart** shows to the quality role only. The server checks the role again on the form.

## Layout

- **Section tabs**: Charts (current) and Evaluations. In the sidebar the page sits under Trends, in the Work section.
- **Header**: title "Trend charts", an introduction ("A trend chart follows one test of one material at one stage: the reviewed results of its lots in the order their reviews were signed, judged by the limits and rules quality approved. A result that breaks a rule raises an out-of-trend alert for quality to evaluate.") and the **New trend chart** button.
- **Filter**: Search, Status, Stage.
- **Table** columns: Chart (TC-n link with the test name beneath, sortable), Material (code with the name beneath, sortable), Test (test code, sortable), Stage, Limits, Results, Last reviewed, State. Stage, Results and Last reviewed give way first on narrow screens. **Columns** chooses which columns show.
- **Empty states**: "No records yet" ("Quality creates a chart for each test whose results it wants to follow, from a numeric or count test of a specification in force.") with **New trend chart** for quality; "Nothing matches these filters" when a filter excludes everything.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New trend chart** | Quality role | Quality | Opens the New trend chart form |
| TC number | Each row | Any reader | Opens the chart |
| Limits version (v1, v2 ...) | The chart has limits in force | Any reader | Opens that limits version |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches test code, test name, material code and material name (contains, any case) |
| Status | — | All, Open alerts, No approved limits, Limits drafted | No | Keeps charts with an open alert, with no approved limits version, or with a draft limits version |
| Stage | `Chart.stage` | All, Incoming material, In-process, Finished product, Stability | No | Keeps one stage |
| Chart | `Chart.pk`, `name` | TC-n | — | Identifier, with the test name beneath |
| Material | `Chart.material` | Code and name | — | The material followed |
| Test | `Chart.test_code` | Text | — | The test code of the specification line |
| Stage | `Chart.stage` | Label | — | Stage of the specification the chart was created from |
| Limits | `Limits.version` | v1, v2 ... | — | The approved version in force now; empty when none |
| Results | — | Count | — | Results plotted on the chart |
| Last reviewed | — | Date and time | — | When the review of the newest plotted result was signed |
| State | — | Status label | — | "N open alerts" (red), "No approved limits" (neutral) or "No open alert" (green) |

## Rules and hidden logic

- **State shown**: open alerts come first, then "No approved limits" when no version is in force, otherwise "No open alert". An open alert is a result that conforms to its specification, broke a rule of the limits in force when its review was signed, and is not covered by an evaluation.
- **Status filter**: Open alerts works out each chart's alerts from the record; No approved limits keeps charts without any approved version; Limits drafted keeps charts that have a draft.
- **Order and paging**: by material code then test code by default; sort by Chart, Material or Test. Paged on the server.
- **Filters**: held in the address, so a filtered list can be bookmarked. An unknown filter value gives no filter.
- **Permissions**: reading is open to the five roles above. Admin status alone gives no action.

## Related pages

- New trend chart
- Chart record (each row)
- [Evaluations](/trends/evaluations/)
- [Reminders](/planning/reminders/), which lists open alerts too
