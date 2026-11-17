---
title: Dashboard
urls: quality:dashboard
views: quality.dashboard.dashboard
templates: quality/dashboard.html, quality/includes/queue.html
models: stability.Hold, quality.Lot, quality.Sample, quality.LotReceipt, quality.SupplierCertificate, quality.SupplierResultAcceptance, sampling.LotAssignment, sampling.SamplingRecord, sampling.DeviationReview, analytical.AnalyticalTest, analytical.Investigation, reporting.Report, stability.Pull, laboratory.ReagentLot
reviewed: 2026-11-17
summary: The home page. See what waits at each step from a received lot to its certificate of analysis, open a queue's list, and find recently received lots.
---

## Common tasks

### See where work is waiting

1. Read the counts in [[Work in progress]]: one per step, from lots to certificates.
2. Select a step to jump to its queues, then a queue name to open its list.

### Open a recently received lot

1. Find it under [[Recently received lots]] and select its lot number.
2. Select [[Material lots]] to see every lot.

### Start a new lot

1. Select [[New material lot]] (analysts only).

## Good to know

- A lot can wait in two queues at once, so a step's count can be more than the number of lots in it.
- A queue with nothing in it stays on the page with 0: nothing is waiting there.
- "All results reviewed" is not QC disposition: the lot record lists anything still in the way.
- Every reader role sees the same counts; who may act is still checked on each page.

## Purpose

The home page after sign-in. It shows the manufacturing QC flow as work queues, so you can see where lots, samples, results, reviews, decisions and certificates wait, and open the matching list.

## Who can use it

- Sign-in required; signed-out visitors go to the sign-in page.
- Viewing requires one of the roles **analyst**, **reviewer**, **quality**, **admin** or **auditor**. Signed-in accounts without one are sent to [Account access](/accounts/access/). Superuser status does not bypass this check.
- **New material lot** is shown only to **analysts**.

## Layout

- **Header**: title "Dashboard" with today's date and week (laboratory time zone), and **New material lot** for analysts.
- **Work in progress** card, with the total of every queue: a band of six steps (Lots, Samples, Results, Review, Disposition, Certificates), each with its count and a link to its lane; then the six lanes, left to right. Each lane lists its queues in a fixed order; each queue shows its name (a link when a list shows it), its count and, when something waits, a status label and the date of the oldest item ("Oldest YYYY-MM-DD").
- **Recently received lots** card: the eight newest lot records with Lot, Status, Material and Where it is, and **Material lots** to open the full list. Empty: "No material lots yet" with "Receive a lot to start the quality journey." and, for analysts, **New material lot**.
- **Stability and laboratory** card beside it: Pulls overdue, Pulls due now, Pulls awaiting acceptance, Active holds, Calibration overdue, Reagent lots awaiting release.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New material lot** | Analyst role | Analyst | Opens the New material lot form |
| A step in the band | Always | Any viewer | Moves to that step's lane on the page |
| A queue name | The queue has a matching list | Any viewer | Opens the list, filtered where a filter exists |
| Lot number link | One per recent lot | Any viewer | Opens the lot record |
| **Material lots** | Always | Any viewer | Opens the full list of lots |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Requirements not assigned | `Lot.state`, `LotAssignment` | Count; oldest lot record date | — | Lots in Quarantine with no requirement assignment. Opens Sampling filtered to "Not assigned" |
| Applicability hold | `LotAssignment.status` | Count | — | Quarantine lots whose latest assignment is an applicability hold. Opens Sampling filtered to it |
| Supplier certificate not recorded | `LotReceipt.source`, `SupplierCertificate` | Count | — | Quarantine lots received from a supplier with no current (not corrected, not withdrawn) supplier certificate. Information only, not a gate |
| Awaiting sampling | `LotAssignment.status`, `Sample`, `SamplingRecord` | Count | — | Quarantine lots with requirements assigned and no sample or sampling record yet. Opens Sampling filtered to "Requirements assigned" |
| Sampling deviations to assess | `DeviationReview.status` | Count; oldest `created_at` | — | Pending deviation reviews of current sampling records of Quarantine lots |
| Samples without assigned tests | `Sample`, `AnalyticalTest` | Count; oldest `collected_at` | — | Samples of Quarantine lots with no test assigned |
| Tests open | `AnalyticalTest.state` | Count; oldest `created_at` | — | Lot tests that are Open. Opens Tests filtered to Open |
| Out of specification, investigation open | `Investigation.phase` | Count; oldest `opened_at` | — | Lot investigations not closed. Opens Investigations filtered to open ones |
| Retests and resamples not done | `AnalyticalTest.kind`, `state` | Count | — | Retest and resample tests of lots still Open or Awaiting review |
| Awaiting review | `AnalyticalTest.state` | Count; oldest `evaluated_at` | — | Lot tests Awaiting review. Opens Tests filtered to it |
| Supplier results awaiting acceptance | `SupplierResultAcceptance.state` | Count; oldest `proposed_at` | — | Supplier results proposed in place of a test and not yet accepted |
| All results reviewed | `LotAssignment.status`, `AnalyticalTest.state`, `Investigation.phase` | Count | — | Shown as "Complete". Quarantine lots with requirements assigned, at least one reviewed test, no test Open or Awaiting review and no open investigation. Opens Material lots filtered to Quarantine. It does not check every disposition gate |
| Blocked by an investigation | `Investigation.phase`, `outcome` | Count | — | Shown as "Blocked". Quarantine lots with an open investigation or one that confirmed an out-of-specification result |
| Certificates to issue | `Lot.state`, `Report.state` | Count | — | Released lots with no issued certificate of analysis. Opens Certificates |
| Active holds | `Hold.state` | Count; oldest `placed_at` | — | Active stability holds of any lot or reserve; an active hold on a lot blocks its QC disposition. Opens Holds filtered to active ones |
| Stability and laboratory queues | `Pull`, `Equipment`, `ReagentLot` | Counts | — | The same filters as the Stability and Laboratory overviews, each opening its filtered list |

## Rules and hidden logic

- **One query per queue**: each count and oldest date come from one aggregate query on the same conditions as the linked list's filter, so the count and the list agree; the page's cost does not grow with the number of lots.
- **Scope**: counts cover the whole laboratory for every reader role; there is no per-user restriction. Stability tests are not lot tests and are not counted in the lot lanes.
- **Step totals**: a step's count is the sum of its queues; a lot can be counted in more than one queue.
- **Where it is** (recent lots): derived from the lot's requirement assignment, samples, test states, decision and issued certificates; see Material lots.
- **No changes**: the page records nothing and signs nothing.

## Related pages

- [Material lots](/lots/): every lot, with search and status filter.
- [Sampling](/sampling/): requirement assignments and sampling records.
- [Testing](/testing/): tests, batches and investigations.
- [Certificates](/reports/): certificates of analysis.
