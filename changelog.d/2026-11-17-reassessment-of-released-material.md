---
date: 2026-11-17
type: added
impact: high
title: Reassess released material whose retest date is near, for a later retest date or the end of its use
area: Lots
link: quality:lot_list
---
From the **Reassessments** panel of a released lot that has a retest date, an analyst or quality person starts a reassessment with the sample taken for it; its tests come from the specifications in force and belong to the reassessment, so the lot's original results, dates and disposition stay as signed. Once the results are reviewed, a quality person who did none of the work signs **Suitable** with a new retest date, never after the expiry date, which the lot record, the lot list and the certificate of analysis then show, or **Not suitable**, after which the lot shows **Use ended** and takes no certificate. **Material lots** can list lots with a reassessment open or whose use ended, and the dashboard counts lots due for retest.

## Technical notes

- Migrations `quality.0014_reassessment` (the `Reassessment` table and its database guards) and `analytical.0010_reassessment_tests` (a test may belong to a reassessment; the subject constraint is now `analytical_test_subject_of_three`).
- New setting `ANALYTICAL_REASSESSMENTS` (default `config.integrations.Reassessments`). Audit action `lot.reassessment_started`; signature meanings `reassessed` and `withdrawn` on `quality.reassessment`. The conclusion freezes `oq.reassessment-results/1`.
- The certificate evidence's `dates` gains `reassessment` or `use_ended` only for a lot that has one. The lot record export gains the sections `reassessments` and `reassessment_tests`.
