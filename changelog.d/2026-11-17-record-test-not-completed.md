---
date: 2026-11-17
type: added
impact: high
title: Record that a test cannot be completed, with its repeat or investigation
area: Testing
link: analytical:test_list
pr: 45
---
**Record not completed** on an open test lets a quality person who is not one of the test's data authors give the cause and a reason and sign. The test keeps everything recorded on it and is repeated or investigated, and the test list has a **Not completed** status filter.

## Technical notes

- Signed record that a test cannot be completed (`analytical:test_not_completed`, **Record not completed** on an open test, quality role, not the test's data authors): the cause (sample lost, damaged or used up; an error in preparing or running the test; equipment, reagent or standard failure; another cause) and a reason, signed with the meaning `not_completed`; the test keeps everything recorded on it and its new state `not_completed` holds `not_completed_record` (`oq.test-not-completed/1`). A test of an investigation is left to it; readings outside the limits open an investigation on the test; any other test is repeated by a linked test of the new kind `repeat`, on the same sample, the pulled material of a stability pull or a new sample of the lot that stands in for it. The test list has a **Not completed** status filter.
- New migration `analytical.0009_not_completed_tests`: `AnalyticalTest.not_completed_record`, the state `not_completed`, the kind `repeat` (allowed without an investigation and on a stability pull), a check constraint keeping the record present exactly in that state, and a test guard that lets only an open test move to it and keeps it immutable afterwards. `lot_evidence` lists such tests under `excluded_tests` with a `not_completed` entry (cause, follow-up, signature); a pull's frozen results list them under `excluded_tests`.
- A test recorded as not completed does not fix its QC batch's results and is left as it is when the batch is rejected; the replacement of a lot's requirements treats it as closed. The refusals of a lot rejection and of a requirement replacement for unsubmitted readings now name this record as the alternative to submitting.
