---
date: 2026-11-19
type: added
impact: high
title: See turnaround and right-first-time figures of the tests reviewed in a period
area: Planning
---
**Planning** has two new tabs for reviewers, quality, auditors and admins. **Figures** shows, for the tests reviewed in a period you choose, the median turnaround from assignment to review, the turnaround nine in ten tests met, how many were reviewed on time against their due date, and how many were right first time: never returned for correction, with no corrected reading, and neither a repeat nor repeated. It also counts results out of specification and those invalidated after an investigation. Choose **Figures by** to break the figures down by kind of work, material, method, analyst or month. Every count opens **Reviewed tests**, which lists those tests with their turnaround, due date and what kept each from being right first time, and can be exported with **Export filtered CSV**.

## Technical notes

- Pages `planning:figures` and `planning:reviewed` (`?export=csv` streams the filtered list as CSV). Both are read-only and need the reviewer, quality, auditor or admin role; an analyst without one of those roles receives 403 and does not see the tabs.
- No migration and no new table: the figures are computed when the page is opened from the review signatures (meaning `reviewed`), the `test.returned` audit events, corrected observations, the lineage of retests, resamples, reruns and repeats, and the due dates of the work list. A period is at most 366 days and dates are local days of `TIME_ZONE`.
