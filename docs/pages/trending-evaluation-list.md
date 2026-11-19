---
title: Out-of-trend evaluations
urls: trending:evaluation_list
views: trending.views.evaluation_list
templates: ops/list.html
models: trending.Evaluation, trending.EvaluationAlert, trending.Chart
reviewed: 2026-11-19
summary: Every out-of-trend evaluation: what quality looked into for a chart's alerts, whether it is open or concluded and its outcome. Find one or see which are still open. Evaluations start from a chart.
---

## Common tasks

### Find an evaluation

1. Type a word of the test code, the material code or the quality-system reference in [[Search]].
2. Narrow the list with [[Status]] or [[Outcome]], then apply the filter.
3. Select the OOT number to open the evaluation.

### See what is still open

1. Choose [[Open]] in [[Status]].

### Start an evaluation

1. Open the chart whose alerts you want to evaluate and select [[Evaluate alerts]]. This list has no button to create one.

## Good to know

- An evaluation covers the open alerts of one chart. A result is covered by one evaluation at most.
- Outcome stays empty while the evaluation is open.
- A concluded evaluation never changes, and evaluations are never deleted.
- Analysts, reviewers, quality, admin and auditor accounts can read the list; only quality opens or concludes evaluations.

## Purpose

The register of out-of-trend evaluations, one row per evaluation.

## Who can use it

- Sign-in required. Roles that can open it: analyst, reviewer, quality, admin and auditor. Others receive 403.
- The page has no action; opening, changing and concluding an evaluation are quality actions on other pages.

## Layout

- **Section tabs**: Charts and Evaluations (current).
- **Header**: title "Out-of-trend evaluations" and an introduction: "Each evaluation looks into out-of-trend alerts of one chart: what the laboratory check found, the cause, the lots and results affected and the actions, concluded with a signature by a quality person who recorded none of it."
- **Filter**: Search, Status, Outcome.
- **Table** columns: Evaluation (OOT-n link), Chart (TC-n link with the title beneath, sortable), Alerts, Opened (sortable), Opened by, Quality-system reference, State. Alerts, Opened by and Quality-system reference give way first on narrow screens. **Columns** chooses which columns show.
- **Empty states**: "No records yet" ("Quality opens an evaluation from a chart's open alerts."); "Nothing matches these filters" when a filter excludes everything.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| OOT number | Each row | Any reader | Opens the evaluation |
| TC number | Each row | Any reader | Opens the chart |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches the chart's test code, the material code and the quality-system reference (contains, any case) |
| Status | `Evaluation.state` | All, Open, Concluded | No | Keeps one state |
| Outcome | `Evaluation.outcome` | All, Out of trend confirmed, Not confirmed | No | Keeps one concluded outcome |
| Evaluation | `Evaluation.pk` | OOT-n | — | Identifier |
| Chart | `Evaluation.chart` | TC-n with title | — | The chart whose alerts are covered |
| Alerts | — | Count | — | Alerts the evaluation covers |
| Opened, Opened by | `opened_at`, `opened_by` | Date and time, person | — | When and by whom it was opened |
| Quality-system reference | `quality_reference` | Text | — | The deviation, investigation or CAPA record |
| State | `state`, `outcome` | "Open" (amber), "Out of trend confirmed" (red), "Not confirmed" (green) | — | Open, or the concluded outcome |

## Rules and hidden logic

- **Order and paging**: newest opened first by default; sort by Chart (test code) or Opened. Paged on the server.
- **Filters**: held in the address. An unknown filter value gives no filter.
- **Permissions**: reading is open to the five roles above. Admin status alone gives no action.

## Related pages

- Evaluation record (each row)
- Chart record
- [Trend charts](/trends/)
