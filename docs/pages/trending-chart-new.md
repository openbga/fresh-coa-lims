---
title: New trend chart
urls: trending:chart_new
views: trending.views.chart_new
templates: catalog/form.html
models: trending.Chart, catalog.SpecificationTest, catalog.Material, core.AuditEvent
reviewed: 2026-11-19
summary: Create a trend chart from a numeric or count test of a specification version in force. The chart follows that test for the specification's material and stage. Quality only.
---

## Common tasks

### Create a chart

1. Choose the [[Test]]: type a word of the test code, the material or the specification to find it.
2. Enter the [[Reason]].
3. Select [[Create chart]]. The chart opens; draft its limits next.

### Go on to the limits

1. After the chart opens, select [[Draft limits]] to set the limits and rules that judge its results.

## Good to know

- Only numeric and count tests of approved specification versions in force are offered, at any stage except stability, and only those without a chart yet.
- Results are plotted at once, but no alert is raised until a version of the limits is approved.
- A chart is never changed or deleted. Its test, material, stage and unit are fixed from the specification line when you create it.
- There is one chart for each material, stage and test code.

## Purpose

Starts the trend chart of one test of one material at one stage.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403. The role is checked before anything else.

## Layout

- **Header**: title "New trend chart" and an introduction: the description of a trend chart followed by "Results are plotted at once; alerts start when limits are approved."
- **Form sections**: Chart (Test), Change control (Reason). Buttons **Cancel** (to the chart list) and **Create chart**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create chart** | Always | Quality | Creates the chart; message "TC-n created. Draft its limits next."; opens the chart |
| **Cancel** | Always | Quality | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Test | `SpecificationTest` (copied to `Chart.test_code`, `name`, `unit`, `decimals`) | Choice (search), shown as material · stage · test code (unit) · specification and version | Yes | A numeric or count test of a specification version in force. The chart follows this test for the specification's material and stage, in its unit |
| Reason | audit reason | Text, max 2000 | Yes | Stored in the audit event |

## Rules and hidden logic

- **Tests offered**: lines of approved specification versions that are in force now (effective, not ended, not superseded), of result type numeric or count, at any stage but stability, whose test code has no chart yet for that material and stage.
- **Checked again on saving**: "Choose a numeric or count test of a specification version in force." and "This test of this material and stage has a chart." The chart takes the material and stage of the specification and the test code, name, unit and reporting decimals of the line. Charts of one material are created one at a time, so two requests cannot create the same chart.
- **Validations**: "A reason is required."
- **Audit**: event `trend_chart.created` with the chart snapshot, the specification code and version, and your reason.
- **Immutability**: the database refuses deleting or changing a chart.
- Not enforced by this page: which tests deserve a chart.

## Related pages

- [Trend charts](/trends/)
- Chart record (opens after saving)
- [Specifications](/catalog/)
