---
date: 2026-11-12
type: added
impact: high
title: Count, qualitative and less-than results, and limits that exclude their boundary
area: Testing
link: analytical:test_list
pr: 21
---
Native testing records counts, qualitative results (conforms or does not conform, absent or present) with what was observed, and results reported as less than a value. Specification limits can exclude their boundary, and certificates show the acceptance text and the result as recorded.

## Technical notes

- More result types in native testing: counts, qualitative results (conforms or does not conform, absent or present) recorded with what was observed, results reported as less than a value kept as recorded, and specification limits that exclude their boundary. Certificates show the acceptance text and the result as recorded. A qualitative specification line now needs an expected outcome; lines approved without one are held until a new version states it.

Count result type and `expected_result` on specification lines; `oq.test-requirement/2` for the new shapes. Readings carry a qualifier, outcome and observed text; the reportable text is frozen at submission and checked again at review. A less-than result never becomes zero and never enters a mean.
