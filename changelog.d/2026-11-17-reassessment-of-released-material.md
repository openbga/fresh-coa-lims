---
date: 2026-11-17
type: added
impact: high
title: Reassess released material whose retest date is near, for a later retest date or the end of its use
area: Lots
link: quality:lot_list
---
An analyst or quality person starts a reassessment of a released lot from its **Reassessments** panel, with the sample taken for it; its tests come from the specifications in force and leave the lot's original record as signed. Once the results are reviewed, a quality person who did none of the work signs **Suitable** with a new retest date, never after the expiry date, or **Not suitable**, after which the lot shows **Use ended** and takes no certificate. The new retest date appears on the lot record, in **Material lots** and on the certificate of analysis, and the dashboard counts lots due for retest and reassessments open.

## Technical notes

- Migrations `quality.0014_reassessment` (the `Reassessment` table and its database guards) and `analytical.0010_reassessment_tests` (a test may belong to a reassessment; the subject constraint is now `analytical_test_subject_of_three`).
- New setting `ANALYTICAL_REASSESSMENTS` (default `config.integrations.Reassessments`). Audit action `lot.reassessment_started`; signature meanings `reassessed` and `withdrawn` on `quality.reassessment`. The conclusion freezes `oq.reassessment-results/1`.
- The certificate evidence's `dates` gains `reassessment` or `use_ended` only for a lot that has one. The lot record export gains the sections `reassessments` and `reassessment_tests`.
- The dashboard's **Certificates to issue** queue now leaves out released lots that cannot take a certificate: expired, due for retest or whose use ended.
