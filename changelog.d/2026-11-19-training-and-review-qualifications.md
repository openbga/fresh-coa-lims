---
date: 2026-11-19
pr: 63
type: added
impact: high
title: Record training, qualify people to review a method, and see qualifications falling due
area: Laboratory
link: laboratory:training_list
---
**Laboratory** has a new **Training** tab. Someone other than the trainee records a person's training in a method or activity, and the trainee confirms it with **Acknowledge** and their signature. A qualification now states whether it is for **Performing the work** or **Reviewing results**, and can rely on the person's acknowledged **Training records**. A method version can ask for **Reviewers qualified for the method**. A result of that version is then reviewed or returned only by a reviewer who holds a current qualification to review the method, and the test shows which qualification the review relied on. **Planning > Reminders** also lists qualifications that reach their last valid day with no approved renewal.

## Technical notes

- Migrations `laboratory.0006` (the `TrainingRecord` table with a guard trigger that allows only the trainee's acknowledgement and no deletion, plus the `Qualification.work` and `Qualification.training` columns), `catalog.0008` (`MethodRevision.requires_review_qualification`) and `analytical.0013` (`AnalyticalTest.review_evidence`, and a replaced test guard that lets that column change only from awaiting review to reviewed). Existing qualifications become qualifications to perform. Existing method versions ask for no qualified reviewer, so reviews work as before until a new version is approved with the setting.
- New pages `laboratory:training_list`, `laboratory:training_new`, `laboratory:training_detail` and `laboratory:training_acknowledge`, and the lookup `training-records`. New audit action `training.recorded`. The acknowledgement is signed with the meaning `acknowledged`.
- New setting `ANALYTICAL_REVIEWERS` (default `config.integrations.LaboratoryReviewers`). A settings module without it fails the new system check `analytical.E001`. `core.services.sign_transition` now also accepts a tuple of roles as `permission`.
- A method version's approved content (`oq.method/1`) now carries `requires_review_qualification`. Requirement payloads frozen on tests are unchanged.
