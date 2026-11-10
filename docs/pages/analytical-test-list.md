---
title: Testing: tests
urls: analytical:test_list
views: analytical.views.test_list
templates: analytical/test_list.html, analytical/_tabs.html, analytical/_pager.html, analytical/_test_status.html
models: analytical.AnalyticalTest
reviewed: 2026-11-10
---

## Purpose

List every analytical test, from assignment through independent review, so work can be found and opened.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- The page has no actions that change data.

## Layout

- **Intro** and section tabs: **Tests** (current), **QC batches**, **Investigations**.
- **Filter bar**: **Find**, **Status**, **Apply**, and **Clear filters** when a filter is active.
- **Table** (caption "Analytical tests, newest first"): Test, Status, Lot, Sample, Code, Kind, Reportable, Batch, Assigned. Footer: "Showing a–b of n tests", with "matching filters" when filtered, and a pager when there is more than one page.
- **Empty states**: "No tests assigned yet" (link **Material lots**) and, when filtered, "No tests match these filters" (**Clear filters**).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** | Always | Any viewer | Reloads the list with the filters |
| **Clear filters** | A search or status is set | Any viewer | Removes the filters |
| Test, Lot and Batch links | Row has the value | Any viewer | Open the test, the lot's testing page or the QC batch |
| Tabs | Always | Any viewer | Switch section |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find | — | Text | No | Case-insensitive match on lot number, sample reference or test code |
| Status | `AnalyticalTest.state`, `conforms` | Choice | No | All tests, Open, Awaiting review, Out of specification, Reviewed, Invalidated |
| Test | — | "T-" and the record number | — | Link to the test |
| Status (column) | `AnalyticalTest.state`, `conforms` | Text | — | Open, Awaiting review, Reviewed · conforms, Out of specification · awaiting review, Out of specification · reviewed, Invalidated |
| Kind | `AnalyticalTest.kind` | Original, Retest, Resample, Rerun after QC failure | — | How the test arose |
| Reportable | `AnalyticalTest.reportable_value` | Decimal with unit | — | Calculated on submission, shown at the approved reporting precision; "—" before |
| Batch | `AnalyticalTest.batch` | Batch number | — | QC batch, or "—" |
| Assigned | `AnalyticalTest.created_at` | Date and time | — | When the test was created |

## Rules and hidden logic

- **Order and paging**: newest first (creation time, then record number); 30 per page; filters are kept across pages.
- **Out of specification filter**: tests that did not conform and are not Invalidated.
- **Unknown status value** in the address is treated as All tests.

## Related pages

- [Testing: QC batches](/testing/batches/)
- [Investigations](/testing/investigations/)
- [Material lots](/)
- Lot testing page: assign tests from there.
