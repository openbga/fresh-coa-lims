---
title: Testing: tests
urls: analytical:test_list
views: analytical.views.test_list
templates: analytical/test_list.html, includes/section_tabs.html, includes/pagination.html, analytical/_test_status.html
models: analytical.AnalyticalTest, quality.SupplierResultAcceptance
reviewed: 2026-11-17
summary: Every analytical test of lot samples and stability pulls in one list. Find a test by lot, sample, study or test code, see its status and open it.
---

## Common tasks
### Find a test
1. Type a lot number, sample reference, study identifier or test code in [[Find]].
2. To see only tests in one state, such as [[Awaiting review]] or [[Out of specification]], choose it in [[Status]].
3. Select [[Apply]], then select a test number to open its record.
### See every test again
1. Select [[Clear all]] to remove the search and the status.
### Switch to QC batches or investigations
1. Select [[QC batches]] or [[Investigations]] in the tabs above the title.
## Good to know
- The list has no actions. Assign tests from a lot's testing page or from a stability pull.
- "Not tested · supplier result" means a supplier's certificate result stands in place of the test. The Open status still lists it.
- Out of specification lists tests that did not conform, awaiting review or reviewed, unless they were invalidated or superseded.
- A stability pull's test shows its study's lot as plain text: the test is not part of that lot's record.

## Purpose

List every analytical test, of a lot's testing or of a stability pull, from assignment through independent review, so work can be found and opened.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- The page has no actions that change data.
- **Admin** and **auditor** see the same list; it has no scientific actions for any role.

## Layout

- **Section tabs**: **Tests**, **QC batches**, **Investigations**. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view.
- **Header**: title "Testing", followed by the introduction (required tests by lot and sample, and the tests of stability pulls; assign tests from a lot's testing page or from a stability pull).
- **Filter bar**: **Find**, **Status** (default "All tests"), **Apply**, and **Clear all** when a filter is active.
- **Table**: Test (the test number, its kind as a tag when it is not an original, and the test name under it), Status, Lot (the lot or the stability pull's lot, with the sample or pull under it), Code, Reportable (value and unit), Batch, Assigned. **Columns** (beside Rows per page) chooses which columns show and their order, saved for your account; the less important columns give way first when the table does not fit. A test that is not an original carries its kind as a tag after the test number (Retest, Resample, Rerun after QC failure, Repeat under replaced requirements, Repeat of a test not completed). Footer: "Showing X–Y of N tests", with "matching filters" when filtered; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons.
- For a test of a stability pull the Lot column shows the study's lot number as plain text (the test is not part of that lot's record) and the Sample column shows the pull link with the note "stability pull".
- **Empty states**: "No tests assigned yet" (link **Material lots**; the text also points to assigning a stability pull's tests from the pull) and, when filtered, "No tests match these filters" (**Clear filters**).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** | Always | Any viewer | Reloads the list with the filters |
| **Clear all** | A search or status is set | Any viewer | Removes the filters |
| Test, Lot and Batch links | Row has the value | Any viewer | Open the test, the lot's testing page (not for a stability pull's test), the stability pull or the QC batch |
| Tabs | Always | Any viewer | Switch section |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find | — | Text | No | Case-insensitive match on lot number, sample reference, stability study identifier, the lot number of a stability study, or test code. A stability test is not found by its own lot number through the lot field, only through its study's lot |
| Status | `AnalyticalTest.state`, `conforms` | Choice | No | All tests, Open, Awaiting review, Out of specification, Reviewed, Invalidated, Superseded, Not completed |
| Test | — | "T-" and the record number | — | Link to the test |
| Status (column) | `AnalyticalTest.state`, `conforms` | Text | — | Open, "Not tested · supplier result", Awaiting review, Reviewed · conforms, Out of specification · awaiting review, Out of specification · reviewed, Invalidated, "Superseded · requirements replaced", Not completed |
| Kind (tag after the test) | `AnalyticalTest.kind` | Retest, Resample, Rerun after QC failure, Repeat under replaced requirements, Repeat of a test not completed | — | How the test arose |
| Reportable | `AnalyticalTest.reportable_text` | Text with unit (no unit for qualitative tests) | — | Frozen on submission: a number at the approved reporting precision, a less-than reading such as "<10", or a qualitative outcome; "—" before |
| Batch | `AnalyticalTest.batch` | Batch number | — | QC batch, or "—" |
| Assigned | `AnalyticalTest.created_at` | Date and time | — | When the test was created |

## Rules and hidden logic

- **Order and paging**: newest first (creation time, then record number); 25 rows per page by default, or 50 or 100 through **Rows per page**; filters are kept across pages.
- **Not tested · supplier result**: shown instead of Open for an Open test when a supplier result is proposed or accepted in place of that test of the lot and not withdrawn, also after the lot is released. Such a test is not work waiting to be done: it takes no observation, contract laboratory result, raw-data file or QC batch until that record is withdrawn. The **Open** filter still lists it; there is no separate filter.
- **Out of specification filter**: tests that did not conform and are neither Invalidated nor Superseded.
- **Superseded**: a test whose requirement changed, or is no longer required, when quality replaced the lot's requirements during testing. It keeps everything recorded on it, takes no more work and never counts. Its repeat under the current requirement has the kind "Repeat under replaced requirements".
- **Not completed**: a test that quality signed as not completed. It keeps everything recorded on it, takes no more work and never counts. Its repeat, when it has one, has the kind "Repeat of a test not completed".
- **Unknown status value** in the address is treated as All tests.

## Related pages

- [Testing: QC batches](/testing/batches/)
- [Investigations](/testing/investigations/)
- [Material lots](/lots/)
- Lot testing page: assign tests from there.
