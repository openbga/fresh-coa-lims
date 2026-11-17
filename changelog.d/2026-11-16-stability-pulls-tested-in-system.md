---
date: 2026-11-16
type: added
impact: high
title: Stability pulls tested in the system against the protocol's acceptance criteria
area: Stability
link: stability:pull_list
pr: 32
---
**Assign tests** on a recorded pull creates the tests of its time point, which are recorded, reviewed and investigated like release tests. **Accept pull** records whether the reviewed results meet the acceptance criteria, and the study page shows the results of each storage condition by time point beside the criteria.

## Technical notes

- Stability testing in the system: a stability protocol names the specification that states its acceptance criteria, and its approval is refused while that specification's version in force cannot answer a test of the protocol. **Assign tests** on a recorded pull creates the tests of its time point, each freezing the criterion in force; they are recorded, reviewed, batched and investigated like release tests and belong to the pull, so the record of the study's lot, released or not, does not change. A failing result opens an investigation that holds the pull; a retest of the material pulled can be authorized, a resample cannot. **Accept pull** records whether the reviewed results meet the acceptance criteria and freezes them with the signature; a confirmed failure is accepted with the outcome that they were not met. The study page shows the results of each storage condition by time point beside the criteria, and the stability overview counts pulls outside the acceptance criteria. **Assign tests** refuses criteria approved after the page was opened. A study is not closed while testing of its pulls is in progress.
- A test belongs to a lot or to a stability pull. `AnalyticalTest.lot` and `.sample`, and `Investigation.lot`, are empty for a test of a pull, which has `pull` instead; a deployment that reads tests or investigations must accept both. Testing asks the class named by the new setting `ANALYTICAL_STABILITY_PULLS` (`requirements`, `refusal`, `lock`) about pulls; without it no pull is tested in the system.
- A stability pull with its own tests takes no linked sample or external evidence, and the pull page shows **Link evidence** only while it has none. Accepting a pull also refuses whoever produced data for, or investigated, one of its tests.
