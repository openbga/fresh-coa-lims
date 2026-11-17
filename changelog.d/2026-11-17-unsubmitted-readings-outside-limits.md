---
date: 2026-11-17
type: changed
impact: medium
title: Unsubmitted readings are judged against their limits when a batch or lot is rejected
area: Testing
link: analytical:batch_list
pr: 45
---
Rejecting a QC batch or a lot now also judges readings that were never submitted. A reading counts as outside its limits when it fails once rounded to the reporting precision, and a batch rejection then opens an investigation.

## Technical notes

- Batch rejection and lot rejection judge readings that were never submitted with `outside_limits`: a reading also counts as outside its limits when it fails once rounded half-up to the reporting precision, and a complete replicate set when the result submission would calculate fails; batch rejection then opens an investigation, and lot rejection waits for one. Batch rejection locks the investigations of its tests before the tests, which removes a deadlock with concluding an investigation whose retest was in the batch. Investigation triggers are shortened to fit their 200 characters.
